"""Tests for B3MovimentacaoXlsxExtractor."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from extractors.b3_movimentacao_xlsx import B3MovimentacaoXlsxExtractor

_HEADERS = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]


def _write_xlsx(path: Path, rows: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(_HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


@pytest.fixture
def extractor() -> B3MovimentacaoXlsxExtractor:
    return B3MovimentacaoXlsxExtractor()


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    rows = [
        # 1) Dividendo — gross == net
        ["Credito", "30/12/2025", "Dividendo",
         "MDIA3 - M.DIAS BRANCO S.A. IND COM DE ALIMENTOS",
         "INTER DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA",
         100, 0.03, 3.0],
        # 2) JCP — net = gross * 0.85 (15% IR)
        ["Credito", "31/03/2026", "Juros Sobre Capital Próprio",
         "ISAE4 - CTEEP - CIA TRANSMISSÃO ENERGIA ELÉTRICA PAULISTA",
         "INTER DTVM",
         400, 0.251, 85.19],
        # 3) Rendimento FII
        ["Credito", "17/04/2026", "Rendimento",
         "IRIM11 - IRIDIUM FUNDO DE INVESTIMENTO IMOBILIÁRIO",
         "INTER DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA",
         24, 0.75, 18.0],
        # --- Lines below MUST be ignored ---
        # 4) Trade liquidation (compras/vendas vêm via b3_csv)
        ["Credito", "27/04/2026", "Transferência - Liquidação",
         "WEGE3 - WEG S.A.", "INTER", 270, 47.8, 12906.0],
        # 5) Aluguel (out of scope)
        ["Credito", "28/04/2026", "Empréstimo",
         "BBAS3 - BCO BRASIL S.A.", "INTER", 640, "-", "-"],
        # 6) "JCP - Transferido" — duplicidade contábil entre corretoras
        ["Credito", "11/07/2025", "Juros Sobre Capital Próprio - Transferido",
         "BBDC4 - BANCO BRADESCO S/A", "INTER", 121, 0.019, 1.95],
        ["Debito", "11/07/2025", "Juros Sobre Capital Próprio - Transferido",
         "BBDC4 - BANCO BRADESCO S/A", "XP", 121, 0.019, 1.95],
        # 7) Cessão de direitos / subscrição (escopo futuro)
        ["Credito", "10/05/2025", "Cessão de Direitos",
         "MXRF11 - MAXI RENDA FII", "INTER", 100, "-", "-"],
        # 8) Atualização (ignorar)
        ["Credito", "10/05/2025", "Atualização",
         "TESOURO IPCA+ 2035", "INTER", 0, "-", 12.34],
    ]
    return _write_xlsx(tmp_path / "movimentacao-2026-04-29.xlsx", rows)


def test_can_handle(extractor: B3MovimentacaoXlsxExtractor, sample_file: Path) -> None:
    assert extractor.can_handle(sample_file) is True


def test_cannot_handle_b3_negociacao(
    extractor: B3MovimentacaoXlsxExtractor, tmp_path: Path
) -> None:
    """The Negociação export has different headers and must NOT be claimed."""
    other = tmp_path / "neg.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Data do Negócio", "Tipo de Movimentação", "Mercado",
        "Código de Negociação", "Quantidade", "Preço", "Valor",
    ])
    wb.save(other)
    assert extractor.can_handle(other) is False


def test_only_proventos_are_emitted(
    extractor: B3MovimentacaoXlsxExtractor, sample_file: Path
) -> None:
    result = extractor.extract(sample_file)
    assert result.errors == []
    # Exactly 3 records: dividendo, JCP, rendimento. Everything else ignored.
    assert len(result.records) == 3
    types = sorted(r["operation_type"] for r in result.records)
    assert types == ["dividend", "jcp", "rendimento"]


def test_dividendo_record_fields(
    extractor: B3MovimentacaoXlsxExtractor, sample_file: Path
) -> None:
    rec = next(r for r in extractor.extract(sample_file).records if r["operation_type"] == "dividend")
    assert rec["asset_code"] == "MDIA3"
    assert rec["operation_date"] == "2025-12-30"
    assert rec["quantity"] == 100
    assert rec["unit_price"] == pytest.approx(0.03)  # BRL
    assert rec["gross_value"] == pytest.approx(3.0)  # 100 × 0.03 = 3.00 BRL
    assert rec["fees"] == 0  # dividendo: gross == net
    assert rec["source"] == "b3_movimentacao_xlsx"


def test_jcp_records_ir_in_fees(
    extractor: B3MovimentacaoXlsxExtractor, sample_file: Path
) -> None:
    rec = next(r for r in extractor.extract(sample_file).records if r["operation_type"] == "jcp")
    assert rec["asset_code"] == "ISAE4"
    assert rec["operation_date"] == "2026-03-31"
    # Gross: 400 × 0.251 = 100.40 BRL
    assert rec["gross_value"] == pytest.approx(100.40)
    # Net (Valor da Operação): 85.19 BRL → IR = gross - net ≈ 15.21 BRL (~15.15%)
    assert rec["fees"] == pytest.approx(100.40 - 85.19, abs=0.01)


def test_rendimento_record_fields(
    extractor: B3MovimentacaoXlsxExtractor, sample_file: Path
) -> None:
    rec = next(r for r in extractor.extract(sample_file).records if r["operation_type"] == "rendimento")
    assert rec["asset_code"] == "IRIM11"
    assert rec["gross_value"] == pytest.approx(18.0)  # 24 × 0.75 = 18.00 BRL
    assert rec["fees"] == 0


def test_external_id_is_deterministic(
    extractor: B3MovimentacaoXlsxExtractor, sample_file: Path
) -> None:
    """Re-running the extractor on the same file yields identical external_ids."""
    first = extractor.extract(sample_file).records
    second = extractor.extract(sample_file).records
    assert [r["external_id"] for r in first] == [r["external_id"] for r in second]
    # Sample format check.
    div = next(r for r in first if r["operation_type"] == "dividend")
    assert div["external_id"] == "b3mov:2025-12-30:dividend:MDIA3:INTER:300"


def test_institution_normalization_collapses_variants(tmp_path: Path) -> None:
    """Same event reported with two different institution spellings → same external_id."""
    extractor = B3MovimentacaoXlsxExtractor()
    f1 = _write_xlsx(tmp_path / "a.xlsx", [
        ["Credito", "30/12/2025", "Dividendo", "MDIA3 - M.DIAS BRANCO",
         "INTER DTVM", 100, 0.03, 3.0],
    ])
    f2 = _write_xlsx(tmp_path / "b.xlsx", [
        ["Credito", "30/12/2025", "Dividendo", "MDIA3 - M.DIAS BRANCO",
         "INTER DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA",
         100, 0.03, 3.0],
    ])
    e1 = extractor.extract(f1).records[0]["external_id"]
    e2 = extractor.extract(f2).records[0]["external_id"]
    assert e1 == e2


def test_source_type(extractor: B3MovimentacaoXlsxExtractor, sample_file: Path) -> None:
    assert extractor.extract(sample_file).source_type == "b3_movimentacao_xlsx"
