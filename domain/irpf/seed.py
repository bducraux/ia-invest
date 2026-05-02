"""Loader do seed CSV de cadastro fiscal IRPF.

O seed (``domain/irpf/data/asset_metadata_seed.csv``) é um arquivo versionado
no repositório, mantido colaborativamente: cada linha foi verificada manualmente
ou via a Skill ``asset-metadata-enrich`` e representa um par
``ticker -> (cnpj, razão social, classe IRPF)`` confirmado em fonte oficial
(B3, RI ou CVM).

Este módulo apenas lê o CSV — a aplicação ao banco fica em
``scripts/bootstrap_asset_metadata.py``. Linhas em branco e comentários
``#`` são ignorados.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

SEED_PATH = Path(__file__).parent / "data" / "asset_metadata_seed.csv"

_VALID_CLASSES = frozenset({"acao", "fii", "fiagro", "bdr", "etf"})


@dataclass(frozen=True)
class SeedEntry:
    ticker: str
    cnpj: str
    razao_social: str
    asset_class_irpf: str
    fonte: str


def load_seed(path: Path | None = None) -> dict[str, SeedEntry]:
    """Lê o CSV do seed e devolve um dict ``ticker -> SeedEntry``.

    Levanta ``ValueError`` se encontrar uma classe inválida ou ticker
    duplicado — isso é intencional: o seed é fonte de verdade local e
    qualquer inconsistência precisa ser resolvida no PR, não silenciada.
    """

    csv_path = path or SEED_PATH
    if not csv_path.exists():
        return {}

    out: dict[str, SeedEntry] = {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        # Pula linhas de comentário antes de passar ao DictReader.
        cleaned_lines = [
            line for line in fh if line.strip() and not line.lstrip().startswith("#")
        ]

    if not cleaned_lines:
        return {}

    reader = csv.DictReader(cleaned_lines)
    for row_num, row in enumerate(reader, start=2):
        ticker = (row.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        cnpj = (row.get("cnpj") or "").strip()
        razao = (row.get("razao_social") or "").strip()
        classe = (row.get("asset_class_irpf") or "").strip().lower()
        fonte = (row.get("fonte") or "").strip()

        if classe not in _VALID_CLASSES:
            raise ValueError(
                f"asset_metadata_seed.csv: linha {row_num} ({ticker}) tem classe "
                f"inválida {classe!r}; permitido: {sorted(_VALID_CLASSES)}"
            )
        if ticker in out:
            raise ValueError(
                f"asset_metadata_seed.csv: ticker duplicado {ticker!r} "
                f"(linha {row_num})"
            )

        out[ticker] = SeedEntry(
            ticker=ticker,
            cnpj=cnpj,
            razao_social=razao,
            asset_class_irpf=classe,
            fonte=fonte,
        )

    return out
