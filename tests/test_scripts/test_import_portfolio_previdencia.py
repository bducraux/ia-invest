from __future__ import annotations

from pathlib import Path

from scripts import import_portfolio as import_portfolio_module
from storage.repository.db import Database


def test_import_portfolio_previdencia_processes_only_latest_pdf(monkeypatch, tmp_path: Path) -> None:
    source_inbox = (
        Path(__file__).resolve().parents[2]
        / "portfolios"
        / "fundacao-ibm"
        / "inbox"
    )

    portfolios_dir = tmp_path / "portfolios"
    portfolio_dir = portfolios_dir / "fundacao-ibm"
    inbox_dir = portfolio_dir / "inbox"
    processed_dir = portfolio_dir / "processed"

    inbox_dir.mkdir(parents=True)
    (portfolio_dir / "staging").mkdir()
    processed_dir.mkdir()
    (portfolio_dir / "rejected").mkdir()

    (portfolio_dir / "portfolio.yml").write_text(
        """
id: fundacao-ibm
name: Fundacao IBM
base_currency: BRL
status: active
rules:
  allowed_asset_types:
    - previdencia
sources:
  - type: previdencia_ibm_pdf
    enabled: true
import:
  move_processed_files: true
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    for name in ["extrato_janeiro_2026.pdf", "extrato_fevereiro_2026.pdf", "extrato_março_2026.pdf"]:
        (inbox_dir / name).write_bytes((source_inbox / name).read_bytes())

    monkeypatch.setattr(import_portfolio_module, "_PORTFOLIOS_DIR", portfolios_dir)

    db_path = tmp_path / "ia.db"
    result = import_portfolio_module.import_portfolio("fundacao-ibm", db_path=db_path)

    assert result["files_processed"] == 3
    assert result["inserted"] == 1
    assert result["skipped"] == 2
    assert result["errors"] == 0

    assert not (inbox_dir / "extrato_janeiro_2026.pdf").exists()
    assert not (inbox_dir / "extrato_fevereiro_2026.pdf").exists()
    assert not (inbox_dir / "extrato_março_2026.pdf").exists()

    assert (processed_dir / "extrato_janeiro_2026.pdf").exists()
    assert (processed_dir / "extrato_fevereiro_2026.pdf").exists()
    assert (processed_dir / "extrato_março_2026.pdf").exists()

    db = Database(db_path)
    db.initialize()
    row = db.connection.execute(
        """
        SELECT asset_code, product_name, period_month, unit_price_cents
        FROM previdencia_snapshots
        WHERE portfolio_id = 'fundacao-ibm'
        """
    ).fetchone()
    db.close()

    assert row is not None
    assert row["asset_code"] == "PREV_IBM_CD"
    assert row["product_name"] == "IBM CD"
    assert row["period_month"] == "2026-03"
    assert row["unit_price_cents"] == 4751
