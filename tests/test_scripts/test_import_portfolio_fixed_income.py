from __future__ import annotations

from pathlib import Path

from scripts import import_portfolio as import_portfolio_module
from storage.repository.db import Database


def test_import_portfolio_persists_fixed_income_csv(monkeypatch, tmp_path: Path) -> None:
    portfolios_dir = tmp_path / "portfolios"
    portfolio_dir = portfolios_dir / "renda-fixa-test"
    inbox_dir = portfolio_dir / "inbox"
    processed_dir = portfolio_dir / "processed"

    inbox_dir.mkdir(parents=True)
    (portfolio_dir / "staging").mkdir()
    processed_dir.mkdir()
    (portfolio_dir / "rejected").mkdir()

    (portfolio_dir / "portfolio.yml").write_text(
        """
id: renda-fixa-test
name: Renda Fixa Test
description: Test portfolio
base_currency: BRL
status: active
rules:
  allowed_asset_types:
    - CDB
    - LCI
    - LCA
sources:
  - type: fixed_income_csv
    enabled: true
import:
  move_processed_files: true
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    (inbox_dir / "rf.csv").write_text(
        """
institution,asset_type,product_name,remuneration_type,benchmark,benchmark_percent,application_date,maturity_date,liquidity_label,principal_applied_brl,imported_gross_value_brl
Banco X,CDB,CDB 104 CDI,CDI_PERCENT,CDI,104.00,2024-01-02,2026-01-02,Diária,1000.00,1100.00
Banco X,LCI,LCI 95 CDI,CDI_PERCENT,CDI,95.00,2024-01-03,2026-01-03,No vencimento,5000.00,5050.00
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(import_portfolio_module, "_PORTFOLIOS_DIR", portfolios_dir)

    db_path = tmp_path / "ia.db"
    result = import_portfolio_module.import_portfolio(
        "renda-fixa-test",
        db_path=db_path,
    )

    assert result["files_processed"] == 1
    assert result["inserted"] == 2
    assert result["errors"] == 0
    assert not (inbox_dir / "rf.csv").exists()
    assert (processed_dir / "rf.csv").exists()

    db = Database(db_path)
    db.initialize()
    rows = db.connection.execute(
        "SELECT institution, asset_type, principal_applied_brl FROM fixed_income_positions ORDER BY id"
    ).fetchall()
    op_count = db.connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    db.close()

    assert [(row["institution"], row["asset_type"], row["principal_applied_brl"]) for row in rows] == [
        ("Banco X", "CDB", 100_000),
        ("Banco X", "LCI", 500_000),
    ]
    assert op_count == 0
