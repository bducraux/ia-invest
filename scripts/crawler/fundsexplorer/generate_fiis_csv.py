#!/usr/bin/env python3
"""
generate_fiis_csv.py
====================
Pipeline completo em um único script: baixa as listagens de FIIs **e
FIAGROs** do FundsExplorer, junta tudo em uma lista única ordenada
alfabeticamente por ticker, em seguida acessa a página individual de
cada fundo para extrair nome completo e CNPJ, e grava o resultado em
``data/asset_catalog/fiis.csv`` no schema canônico do catálogo de ativos:

    ticker,cnpj,razao_social,asset_class,sector_category,sector_subcategory,site_ri,fonte

Características:
- Faz 1 requisição por listagem (FIIs + FIAGROs).
- Cada ticker conhece sua classe (``fii`` vem de ``/funds``, ``fiagro``
  vem de ``/fiagros``); a classificação é automática a partir da fonte.
- Em seguida, abre uma página por fundo em paralelo (default: 8 threads)
  com jitter aleatório, usando a URL correta para cada classe.
- **Merge não-destrutivo**: nunca sobrescreve uma célula já preenchida no
  CSV destino. Edições manuais (site_ri preenchido pela skill IA, etc.)
  permanecem intactas.
- Checkpointing: grava progresso a cada N fundos. Se interrompido, basta
  rodar de novo que retoma os pendentes (lê o CSV de saída).
- Retry automático com backoff exponencial.
- Fundos que falharem após todas as tentativas vão para
  ``fiis_failed.csv`` ao lado deste script e NÃO entram em ``fiis.csv``.

Uso:
    uv run python scripts/crawler/fundsexplorer/generate_fiis_csv.py [OUTPUT_CSV]
    uv run python scripts/crawler/fundsexplorer/generate_fiis_csv.py --retry-failed

Padrão:
    OUTPUT_CSV = data/asset_catalog/fiis.csv (do repositório)

Modo --retry-failed:
    Processa apenas os tickers listados em fiis_failed.csv (ao lado deste
    script). Útil para reprocessar fundos que falharam em uma execução
    anterior por instabilidade do site (HTTP 403/500). Ao final atualiza
    fiis_failed.csv removendo os que foram resolvidos.

Requer:
    pip install requests beautifulsoup4
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# -------------------------------------------------------------------- config
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data" / "asset_catalog" / "fiis.csv"
FAILED_CSV = HERE / "fiis_failed.csv"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Crawler do FundsExplorer para FIIs e FIAGROs. "
            "Atualiza data/asset_catalog/fiis.csv com merge não-destrutivo."
        )
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"CSV de saída (padrão: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            f"Processa apenas os tickers listados em {FAILED_CSV.name} "
            "(ao lado deste script). Útil para reprocessar fundos que "
            "falharam em uma execução anterior."
        ),
    )
    return parser.parse_args(argv)


def _load_failed_tickers(path: Path) -> set[str]:
    if not path.exists():
        print(f"[!] Arquivo de retry '{path}' não existe.")
        sys.exit(1)
    tickers: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            t = (row.get("ticker") or "").strip().upper()
            if t:
                tickers.add(t)
    if not tickers:
        print(f"[!] Nenhum ticker em '{path}'.")
        sys.exit(1)
    return tickers

# Cada fonte: (asset_class, URL da listagem, template da página individual).
SOURCES: list[tuple[str, str, str]] = [
    (
        "fii",
        "https://www.fundsexplorer.com.br/funds",
        "https://www.fundsexplorer.com.br/funds/{ticker}",
    ),
    (
        "fiagro",
        "https://www.fundsexplorer.com.br/fiagros",
        "https://www.fundsexplorer.com.br/fiagros/{ticker}",
    ),
]

CHECKPOINT_EVERY = 25      # grava o CSV a cada N fundos processados
MAX_WORKERS      = 8       # threads em paralelo
TIMEOUT          = 30      # segundos
MAX_RETRIES      = 3
SLEEP_MIN        = 0.30    # delay mínimo entre requests por thread (s)
SLEEP_MAX        = 0.80    # delay máximo (jitter)

FIELDNAMES = [
    "ticker",
    "cnpj",
    "razao_social",
    "asset_class",
    "sector_category",
    "sector_subcategory",
    "site_ri",
    "fonte",
]
FONTE_TAG = f"FundsExplorer {datetime.utcnow():%Y-%m}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

RE_CNPJ = re.compile(r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b")


# ============================================================ passo 1: lista
def fetch_list_page(url: str) -> str:
    print(f"[i] Baixando listagem {url} ...")
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    print(f"[i] OK ({len(resp.text):,} bytes)")
    return resp.text


def parse_listing(html: str, asset_class: str, fund_url_tpl: str) -> list[dict]:
    """Extrai a lista de fundos do HTML da listagem.

    Cada card tem:
      - .tickerBox__type      → "Tipo: Subtipo" (pode estar vazio)
      - [data-element="ticker-box-title"] ou .tickerBox__title → ticker
      - .tickerBox__desc      → nome do fundo (pode estar vazio)

    Cada item resultante carrega ``asset_class`` e ``fund_url_tpl`` para
    que a etapa de enrichment saiba qual URL bater por ticker.
    """
    soup = BeautifulSoup(html, "html.parser")

    title_nodes = soup.select(
        '[data-element="ticker-box-title"], .tickerBox__title'
    )
    print(f"[i] {asset_class.upper()}: {len(title_nodes)} cards na listagem.")

    rows: list[dict] = []
    seen_tickers: set[str] = set()

    for title in title_nodes:
        ticker = title.get_text(strip=True).upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        # O wrapper imediato do título é um <a class="tickerBox__link_ticker">.
        # O card que contém .tickerBox__type / .tickerBox__desc é um <div>
        # com a classe-token exata "tickerBox" (não os modificadores
        # tickerBox__*). Por isso filtramos pela presença do token cru.
        card = title.find_parent(
            lambda tag: tag.name == "div"
            and tag.get("class")
            and "tickerBox" in tag.get("class")
        )
        if card is None:
            card = title.parent

        tipo_el = card.select_one(".tickerBox__type") if card else None
        nome_el = card.select_one(".tickerBox__desc") if card else None

        tipo_raw = tipo_el.get_text(strip=True) if tipo_el else ""
        nome = nome_el.get_text(strip=True) if nome_el else ""

        category, subcategory = _split_tipo(tipo_raw)
        rows.append({
            "ticker": ticker,
            "nome": nome,
            "asset_class": asset_class,
            "fund_url_tpl": fund_url_tpl,
            "sector_category": category,
            "sector_subcategory": subcategory,
        })

    return rows


def _split_tipo(tipo_raw: str) -> tuple[str, str]:
    """``"Tijolo: Lajes Corporativas"`` → ``("Tijolo", "Lajes Corporativas")``.

    Valores ``"INDEFINIDO"`` (em qualquer caixa) viram string vazia.
    """
    if not tipo_raw:
        return "", ""
    if ":" in tipo_raw:
        head, tail = tipo_raw.split(":", 1)
        category, subcategory = head.strip(), tail.strip()
    else:
        category, subcategory = tipo_raw.strip(), ""
    if category.upper() == "INDEFINIDO":
        category = ""
    if subcategory.upper() == "INDEFINIDO":
        subcategory = ""
    return category, subcategory


def collect_listings() -> list[dict]:
    """Baixa todas as listagens e devolve uma lista única, ordenada por ticker.

    Se um mesmo ticker aparecer em mais de uma listagem (improvável), a
    classe da listagem mais específica vence — a ordem em ``SOURCES`` define
    a prioridade (entradas posteriores sobrescrevem anteriores), então
    ``fiagro`` ganha de ``fii``.
    """
    priority = {cls: idx for idx, (cls, _, _) in enumerate(SOURCES)}
    by_ticker: dict[str, dict] = {}
    for asset_class, list_url, fund_url_tpl in SOURCES:
        html = fetch_list_page(list_url)
        for row in parse_listing(html, asset_class, fund_url_tpl):
            ticker = row["ticker"]
            existing = by_ticker.get(ticker)
            if (
                existing is None
                or priority[asset_class] > priority[existing["asset_class"]]
            ):
                by_ticker[ticker] = row

    merged = sorted(by_ticker.values(), key=lambda r: r["ticker"])
    by_class: dict[str, int] = {}
    for r in merged:
        by_class[r["asset_class"]] = by_class.get(r["asset_class"], 0) + 1
    print(f"[i] Listagem consolidada: {len(merged)} fundos {by_class}.")
    return merged


# ========================================================= passo 2: enrich
def extract_name_and_cnpj(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extrai nome e CNPJ do HTML da página individual do fundo."""
    soup = BeautifulSoup(html, "html.parser")

    name: Optional[str] = None
    cnpj: Optional[str] = None

    name_tag = soup.select_one("p.headerTicker__content__name")
    if name_tag and name_tag.get_text(strip=True):
        name = name_tag.get_text(strip=True)

    cnpj_tag = soup.select_one("div.headerTicker__content__cnpj")
    if cnpj_tag:
        b = cnpj_tag.find("b")
        if b and b.get_text(strip=True):
            cnpj = b.get_text(strip=True)
        else:
            m = RE_CNPJ.search(cnpj_tag.get_text())
            if m:
                cnpj = m.group(1)

    if not name:
        for label in soup.find_all(string=re.compile(r"Razão Social", re.I)):
            parent = label.parent
            if not parent:
                continue
            sibling = parent.find_next(["strong", "b", "p"])
            if sibling and sibling.get_text(strip=True):
                name = sibling.get_text(strip=True)
                break

    if not cnpj:
        text = soup.get_text("\n", strip=True)
        m = re.search(r"CNPJ do Fundo[:\s]*([0-9./-]{18})", text)
        if m:
            cnpj = m.group(1).strip()
        else:
            m = RE_CNPJ.search(text)
            if m:
                cnpj = m.group(1)

    return name, cnpj


def fetch_fund(
    ticker: str, fund_url_tpl: str, session: requests.Session
) -> dict:
    url = fund_url_tpl.format(ticker=ticker.lower())
    last_err: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
            resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 404:
                return {"ticker": ticker, "nome_pagina": "", "cnpj": "",
                        "error": "404 Not Found"}
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}"
                time.sleep(2 ** attempt)
                continue
            name, cnpj = extract_name_and_cnpj(resp.text)
            return {
                "ticker": ticker,
                "nome_pagina": name or "",
                "cnpj": cnpj or "",
                "error": "" if (name or cnpj) else "no data extracted",
            }
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(2 ** attempt)

    return {"ticker": ticker, "nome_pagina": "", "cnpj": "",
            "error": last_err or "unknown error"}


# ============================================================== I/O helpers
def load_existing_output(path: Path) -> tuple[list[str], dict[str, dict]]:
    """Carrega o CSV destino preservando comentários do cabeçalho.

    Devolve ``(header_comments, rows_by_ticker)``. Comentários (linhas
    começando com ``#``) anteriores ao cabeçalho CSV são mantidos para
    serem reescritos no flush.
    """
    if not path.exists():
        return _default_header_comments(), {}

    comments: list[str] = []
    data_lines: list[str] = []
    found_header = False
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not found_header:
                if line.lstrip().startswith("#") or not line.strip():
                    comments.append(line)
                    continue
                found_header = True
            data_lines.append(line)

    if not data_lines:
        return comments or _default_header_comments(), {}

    reader = csv.DictReader(data_lines)
    rows: dict[str, dict] = {}
    for row in reader:
        ticker = (row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        rows[ticker] = {key: (row.get(key) or "").strip() for key in FIELDNAMES}
    return comments or _default_header_comments(), rows


def _default_header_comments() -> list[str]:
    return [
        "# Catálogo de FIIs e FIAGROs (asset_class=fii|fiagro)\n",
        "#\n",
        "# Arquivo gerado/atualizado pelo crawler do FundsExplorer:\n",
        "#   uv run python scripts/crawler/fundsexplorer/generate_fiis_csv.py\n",
        "#\n",
        "# A classe (fii ou fiagro) é definida automaticamente pela listagem\n",
        "# de origem no FundsExplorer (/funds vs /fiagros). Reclassificações\n",
        "# manuais ainda são respeitadas pelo merge não-destrutivo.\n",
        "#\n",
        "# O crawler é não-destrutivo: nunca sobrescreve uma célula já\n",
        "# preenchida (ex.: site_ri preenchido pela skill de IA permanece intacto).\n",
        "#\n",
        "# Schema canônico: ver data/asset_catalog/README.md.\n",
    ]


def write_output(path: Path, header_comments: list[str], rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        for line in header_comments:
            fh.write(line)
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for ticker in sorted(rows):
            row = rows[ticker]
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


def merge_row(existing: dict[str, str] | None, incoming: dict[str, str]) -> dict[str, str]:
    """Merge não-destrutivo: célula existente não-vazia sempre vence."""
    if existing is None:
        return {key: incoming.get(key, "") for key in FIELDNAMES}
    out: dict[str, str] = {}
    for key in FIELDNAMES:
        prev = (existing.get(key) or "").strip()
        new = (incoming.get(key) or "").strip()
        out[key] = prev if prev else new
    return out


# ================================================================ pipeline
def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    output_csv: Path = args.output

    retry_tickers: set[str] | None = None
    if args.retry_failed:
        retry_tickers = _load_failed_tickers(FAILED_CSV)
        print(f"[i] Modo --retry-failed: {len(retry_tickers)} tickers em "
              f"'{FAILED_CSV.name}'.")

    listing_rows = collect_listings()
    if not listing_rows:
        print("[!] Nenhum fundo extraído das listagens — estrutura pode ter mudado.")
        sys.exit(1)

    if retry_tickers is not None:
        listing_rows = [r for r in listing_rows if r["ticker"] in retry_tickers]
        missing = retry_tickers - {r["ticker"] for r in listing_rows}
        if missing:
            print(f"[!] {len(missing)} ticker(s) de retry não apareceram nas "
                  f"listagens (ignorados): {sorted(missing)}")
        if not listing_rows:
            print("[!] Nenhum ticker do retry encontrado nas listagens — abortando.")
            sys.exit(1)

    sem_nome_listagem = sum(1 for r in listing_rows if not r["nome"])
    sem_tipo_listagem = sum(
        1 for r in listing_rows
        if not r["sector_category"] and not r["sector_subcategory"]
    )
    print(f"[i] Total: {len(listing_rows)} fundos "
          f"({sem_nome_listagem} sem nome, {sem_tipo_listagem} sem tipo).")

    header_comments, existing = load_existing_output(output_csv)
    if existing:
        print(f"[i] CSV atual em '{output_csv}' tem {len(existing)} linhas — "
              f"merge não-destrutivo (manual prevalece).")

    if retry_tickers is not None:
        # Em retry-mode forçamos o fetch de todos os tickers do retry,
        # mesmo que já tenham CNPJ — é a intenção do usuário.
        pending = list(listing_rows)
    else:
        # Pendentes = na listagem mas ainda sem CNPJ no CSV. Tickers já com
        # CNPJ preenchido pulam direto a etapa de fetch (rápido).
        pending = [
            r for r in listing_rows
            if not (existing.get(r["ticker"]) or {}).get("cnpj")
        ]
    print(f"[i] A processar agora: {len(pending)} fundos "
          f"(workers={MAX_WORKERS}).")

    # results: ticker -> dict pronto para merge (sem ainda mesclar com existing)
    fetched: dict[str, dict[str, str]] = {}
    failed: list[dict] = []
    processed_since_checkpoint = 0
    started = time.time()

    session = requests.Session()

    def build_row(ticker: str, listing_row: dict, fetch_res: dict | None) -> dict[str, str]:
        nome = (
            (listing_row.get("nome") or "")
            or (fetch_res.get("nome_pagina") if fetch_res else "")
            or ""
        )
        cnpj = (fetch_res.get("cnpj") if fetch_res else "") or ""
        return {
            "ticker": ticker,
            "cnpj": cnpj,
            "razao_social": nome,
            "asset_class": listing_row.get("asset_class", "fii"),
            "sector_category": listing_row.get("sector_category") or "",
            "sector_subcategory": listing_row.get("sector_subcategory") or "",
            "site_ri": "",
            "fonte": FONTE_TAG,
        }

    def flush_to_disk():
        merged = dict(existing)  # começa do estado já em disco
        # Tickers só vistos na listagem (sem fetch bem-sucedido) ainda
        # ganham linha com sector_category/subcategory + asset_class default.
        for r in listing_rows:
            t = r["ticker"]
            incoming = build_row(t, r, fetched.get(t))
            merged[t] = merge_row(merged.get(t), incoming)
        write_output(output_csv, header_comments, merged)

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            future_to_ticker = {
                pool.submit(
                    fetch_fund, r["ticker"], r["fund_url_tpl"], session
                ): r
                for r in pending
            }
            for i, fut in enumerate(as_completed(future_to_ticker), 1):
                row = future_to_ticker[fut]
                ticker = row["ticker"]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"ticker": ticker, "nome_pagina": "",
                           "cnpj": "", "error": f"exception: {e}"}

                if res.get("error"):
                    failed.append({"ticker": ticker, "error": res["error"]})
                else:
                    fetched[ticker] = {
                        "nome_pagina": res.get("nome_pagina", ""),
                        "cnpj": res.get("cnpj", ""),
                    }

                processed_since_checkpoint += 1
                if processed_since_checkpoint >= CHECKPOINT_EVERY:
                    flush_to_disk()
                    processed_since_checkpoint = 0
                    elapsed = time.time() - started
                    rate = i / elapsed if elapsed else 0
                    print(f"[i] {i}/{len(pending)}  "
                          f"({rate:.1f} fundos/s, {len(failed)} falhas)")

    except KeyboardInterrupt:
        print("\n[!] Interrompido pelo usuário — gravando progresso parcial...")
    finally:
        flush_to_disk()

        if retry_tickers is not None:
            # Em retry-mode: atualizamos o fiis_failed.csv removendo os
            # tickers que agora foram processados com sucesso e mantendo
            # apenas os que continuam falhando (novos erros + tickers do
            # retry que não foram tentados por interrupção).
            still_failed_map = {f["ticker"]: f["error"] for f in failed}
            attempted = {r["ticker"] for r in pending}
            succeeded = {t for t in attempted if t in fetched}
            survivors: list[dict] = []
            # Preserva entradas originais de fiis_failed.csv que não foram
            # nem reprocessadas com sucesso nem registradas com novo erro.
            if FAILED_CSV.exists():
                with FAILED_CSV.open("r", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        t = (row.get("ticker") or "").strip().upper()
                        if not t or t in succeeded or t in still_failed_map:
                            continue
                        survivors.append({"ticker": t,
                                          "error": (row.get("error") or "").strip()})
            survivors.extend({"ticker": t, "error": err}
                             for t, err in still_failed_map.items())
            if survivors:
                with FAILED_CSV.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["ticker", "error"])
                    w.writeheader()
                    w.writerows(sorted(survivors, key=lambda r: r["ticker"]))
                print(f"[!] {len(survivors)} ticker(s) ainda em "
                      f"'{FAILED_CSV}' ({len(succeeded)} resolvido(s) nesta "
                      f"execução).")
            else:
                if FAILED_CSV.exists():
                    os.remove(FAILED_CSV)
                print(f"[ok] Todos os {len(succeeded)} tickers do retry "
                      f"foram resolvidos — '{FAILED_CSV.name}' removido.")
        else:
            if failed:
                with FAILED_CSV.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["ticker", "error"])
                    w.writeheader()
                    w.writerows(failed)
                print(f"[!] {len(failed)} fundos com erro — registrados em "
                      f"'{FAILED_CSV}'.")
            elif FAILED_CSV.exists():
                os.remove(FAILED_CSV)

        elapsed = time.time() - started
        print(f"[ok] Concluído. CSV final: '{output_csv}' "
              f"({len(listing_rows)} tickers; tempo: {elapsed:.1f}s)")


if __name__ == "__main__":
    main()
