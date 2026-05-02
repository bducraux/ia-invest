"""Integration tests for the IRPF report builder."""

from __future__ import annotations

import pytest

from domain.irpf.builder import IrpfReportBuilder
from domain.irpf.models import IrpfReport, IrpfSection
from domain.models import Operation, Portfolio
from storage.repository.asset_metadata import AssetMetadata, AssetMetadataRepository
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository


@pytest.fixture
def portfolio_with_data(tmp_db: Database) -> tuple[Database, str]:
    portfolio = Portfolio(
        id="default__rv",
        name="Renda Variável",
        description="",
        base_currency="BRL",
        status="active",
        owner_id="default",
        config={"id": "rv", "name": "Renda Variável", "rules": {}},
    )
    PortfolioRepository(tmp_db.connection).upsert(portfolio)

    meta_repo = AssetMetadataRepository(tmp_db.connection)
    meta_repo.upsert(
        AssetMetadata(
            asset_code="ITSA4",
            cnpj="61.532.644/0001-15",
            asset_class="acao",
            asset_name_oficial="ITAUSA S.A.",
            source="manual",
        )
    )
    meta_repo.upsert(
        AssetMetadata(
            asset_code="SAPR11",
            cnpj="76.484.013/0001-45",
            asset_class="fii",
            asset_name_oficial="CIA SANEAMENTO DO PARANA - SANEPAR",
            source="manual",
        )
    )
    # XPML11 left without metadata to exercise inference + warning.

    ops = [
        # ITSA4 — compras em 2023 (formando posição inicial) e em 2024.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="b1",
            asset_code="ITSA4",
            asset_type="stock",
            asset_name="ITAUSA S.A.",
            operation_type="buy",
            operation_date="2023-06-15",
            quantity=400,
            unit_price=800,
            gross_value=320000,
            fees=0,
        ),
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="b2",
            asset_code="ITSA4",
            asset_type="stock",
            asset_name="ITAUSA S.A.",
            operation_type="buy",
            operation_date="2024-04-10",
            quantity=265,
            unit_price=860,
            gross_value=227900,
            fees=0,
        ),
        # ITSA4 — dividendo (cód. 09) em 2024.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="d1",
            asset_code="ITSA4",
            asset_type="stock",
            asset_name="ITAUSA S.A.",
            operation_type="dividend",
            operation_date="2024-08-15",
            quantity=0,
            unit_price=0,
            gross_value=19052,
            fees=0,
        ),
        # ITSA4 — JCP (cód. 10) — bruto 320 / IR 48 / líquido 272.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="j1",
            asset_code="ITSA4",
            asset_type="stock",
            asset_name="ITAUSA S.A.",
            operation_type="jcp",
            operation_date="2024-09-01",
            quantity=0,
            unit_price=0,
            gross_value=32004,
            fees=4800,
        ),
        # ITSA4 — bonificação custo zero (cód. 18 valor 0,00).
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="bn1",
            asset_code="ITSA4",
            asset_type="stock",
            asset_name="ITAUSA S.A.",
            operation_type="split_bonus",
            operation_date="2024-11-30",
            quantity=10,
            unit_price=0,
            gross_value=0,
            fees=0,
        ),
        # SAPR11 — compras 2023 + 2024 → posição final 278 cotas.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="s1",
            asset_code="SAPR11",
            asset_type="fii",
            asset_name="SANEPAR",
            operation_type="buy",
            operation_date="2023-08-10",
            quantity=200,
            unit_price=2700,
            gross_value=540000,
            fees=0,
        ),
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="s2",
            asset_code="SAPR11",
            asset_type="fii",
            asset_name="SANEPAR",
            operation_type="buy",
            operation_date="2024-03-12",
            quantity=78,
            unit_price=2880,
            gross_value=224643,  # ajusta total para PM ~27,73 (770943 / 278)
            fees=300,
        ),
        # SAPR11 — rendimento (cód. 99) em 2024.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="r1",
            asset_code="SAPR11",
            asset_type="fii",
            asset_name="SANEPAR",
            operation_type="rendimento",
            operation_date="2024-10-20",
            quantity=0,
            unit_price=0,
            gross_value=12089,
            fees=0,
        ),
        # XPML11 — sem metadata; também cai como FII via inferência. JCP
        # provisionado em 2024 (settlement em 2025) — vai para 99-99 (tipo
        # ``rendimento``) ou 99-07 (tipo ``jcp``).  Aqui usamos ``rendimento``
        # para validar provisão sem metadata.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="x1",
            asset_code="XPML11",
            asset_type="fii",
            asset_name="FII XP MALLS",
            operation_type="rendimento",
            operation_date="2024-12-20",
            quantity=0,
            unit_price=0,
            gross_value=7700,
            fees=0,
            settlement_date="2025-01-10",
        ),
        # ITSA4 — JCP provisionado em 2024 com pagamento em 2025 → cód. 99-07.
        Operation(
            portfolio_id=portfolio.id,
            source="t",
            external_id="j2",
            asset_code="ITSA4",
            asset_type="stock",
            asset_name="ITAUSA S.A.",
            operation_type="jcp",
            operation_date="2024-12-22",
            quantity=0,
            unit_price=0,
            gross_value=8424,  # bruto
            fees=1264,         # IR 15%
            settlement_date="2025-02-05",
        ),
    ]
    OperationRepository(tmp_db.connection).insert_many(ops)
    return tmp_db, portfolio.id


def _section(report: IrpfReport, code: str) -> IrpfSection | None:
    for s in report.sections:
        if s.code == code:
            return s
    return None


def test_builder_groups_dividend_under_09(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec_09 = _section(report, "09")
    assert sec_09 is not None
    assert len(sec_09.rows) == 1
    row = sec_09.rows[0]
    assert row.asset_code == "ITSA4"
    assert row.cnpj == "61.532.644/0001-15"
    assert row.value_cents == 19052
    assert sec_09.total_cents == 19052


def test_builder_jcp_uses_liquid_value(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec_10 = _section(report, "10")
    assert sec_10 is not None
    # 32004 - 4800 = 27204 (líquido).
    assert sec_10.rows[0].value_cents == 27204


def test_builder_fii_under_99(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec_99 = _section(report, "99")
    assert sec_99 is not None
    codes = {r.asset_code for r in sec_99.rows}
    assert "SAPR11" in codes


def test_builder_bonificacao_zero_value(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec_18 = _section(report, "18")
    assert sec_18 is not None
    assert len(sec_18.rows) == 1
    assert sec_18.rows[0].value_cents == 0
    assert "valor_zero" in sec_18.rows[0].warnings


def test_builder_bens_e_direitos_ações(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec = _section(report, "03-01")
    assert sec is not None
    rows = {r.asset_code: r for r in sec.rows}
    assert "ITSA4" in rows
    itsa = rows["ITSA4"]
    assert itsa.extra is not None
    # 400 (2023) + 265 (2024) + 10 (bonificação custo zero) = 675 cotas
    assert itsa.extra.quantity == 675
    # Custo total: 320000 + 227900 + 0 (bonificação) = 547900
    assert itsa.extra.total_cents == 547900
    assert itsa.discriminacao is not None
    assert "ITSA4" in itsa.discriminacao
    # Snapshot anterior (31/12/2023): 400 cotas, 320000 centavos.
    assert itsa.extra.previous_total_cents == 320000


def test_builder_bens_e_direitos_fii_section(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec = _section(report, "07-03")
    assert sec is not None
    codes = {r.asset_code for r in sec.rows}
    assert "SAPR11" in codes
    # XPML11 não tem buys (apenas rendimento provisionado), então não aparece
    # em Bens e Direitos — só na seção de provisionados (99-99).
    assert "XPML11" not in codes


def test_builder_provisioned_99_07_and_99_99(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)

    sec_9907 = _section(report, "99-07")
    assert sec_9907 is not None
    assert sec_9907.rows[0].asset_code == "ITSA4"
    # 8424 - 1264 = 7160 (líquido)
    assert sec_9907.rows[0].value_cents == 7160

    sec_9999 = _section(report, "99-99")
    assert sec_9999 is not None
    assert sec_9999.rows[0].asset_code == "XPML11"
    assert sec_9999.rows[0].value_cents == 7700


def test_builder_warns_about_missing_metadata(portfolio_with_data: tuple[Database, str]) -> None:
    db, portfolio_id = portfolio_with_data
    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year=2024)
    assert any(w.startswith("asset_metadata_missing:") for w in report.warnings)
    # XPML11 está sem metadata.
    sec_99_99 = _section(report, "99-99")
    assert sec_99_99 is not None
    assert "cnpj_missing" in sec_99_99.rows[0].warnings
