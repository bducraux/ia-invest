"""Unit tests for ``domain.concentration_service.ConcentrationService``."""

from __future__ import annotations

from domain.concentration_service import ConcentrationService, ValuedAsset


def _assets(*pairs: tuple[str, int]) -> list[ValuedAsset]:
    return [ValuedAsset(asset_code=code, value_cents=value) for code, value in pairs]


def test_single_asset_yields_hhi_one_and_critical_alert() -> None:
    result = ConcentrationService().analyse(_assets(("ITSA4", 1_000_000)))
    assert result["num_assets"] == 1
    assert result["metrics"]["herfindahl_index"] == 1.0
    assert result["metrics"]["top_1_pct"] == 1.0

    codes = {a["code"] for a in result["alerts"]}
    assert "single_asset_high" in codes
    assert "low_diversification" in codes
    levels = {a["level"] for a in result["alerts"] if a["code"] == "single_asset_high"}
    assert levels == {"critical"}


def test_uniform_ten_assets_yields_hhi_one_tenth() -> None:
    result = ConcentrationService().analyse(_assets(*[(f"A{i}", 1_000) for i in range(10)]))
    assert result["num_assets"] == 10
    # HHI = 10 * (0.1)^2 = 0.10.
    assert result["metrics"]["herfindahl_index"] == 0.1
    assert result["metrics"]["top_1_pct"] == 0.1
    assert result["metrics"]["top_5_pct"] == 0.5
    assert result["metrics"]["top_10_pct"] == 1.0
    # No single-asset, top-5 alerts. Top-10 alert is expected because 10
    # uniform assets exhaust the carteira (top-10 = 100% > 90%).
    codes = [a["code"] for a in result["alerts"]]
    assert "single_asset_high" not in codes
    assert "top5_concentration" not in codes
    assert "low_diversification" not in codes
    assert codes == ["top10_concentration"]


def test_empty_portfolio_emits_low_diversification_warning() -> None:
    result = ConcentrationService().analyse([])
    assert result["num_assets"] == 0
    assert result["total_value_cents"] == 0
    assert result["metrics"]["herfindahl_index"] == 0.0
    codes = {a["code"] for a in result["alerts"]}
    assert "low_diversification" in codes


def test_single_asset_warning_threshold() -> None:
    # 16% allocation in top asset → warning, not critical.
    result = ConcentrationService().analyse(
        _assets(
            ("ITSA4", 1600),
            ("BBAS3", 1500),
            ("PETR4", 1500),
            ("VALE3", 1500),
            ("ITUB4", 1500),
            ("BBDC4", 1400),
            ("EGIE3", 1000),
        )
    )
    single = [a for a in result["alerts"] if a["code"] == "single_asset_high"]
    assert len(single) == 1
    assert single[0]["level"] == "warning"


def test_top5_concentration_info_then_warning() -> None:
    # Top 5 ≈ 65% → info; not warning yet.
    result = ConcentrationService().analyse(
        _assets(
            ("A1", 1500), ("A2", 1500), ("A3", 1500), ("A4", 1000), ("A5", 1000),
            ("A6", 700), ("A7", 700), ("A8", 700), ("A9", 700), ("A10", 700),
        )
    )
    top5 = [a for a in result["alerts"] if a["code"] == "top5_concentration"]
    assert len(top5) == 1
    assert top5[0]["level"] == "info"

    # Push past 75% → warning.
    result = ConcentrationService().analyse(
        _assets(
            ("A1", 2500), ("A2", 2000), ("A3", 1500), ("A4", 1000), ("A5", 1000),
            ("A6", 500), ("A7", 500), ("A8", 500), ("A9", 250), ("A10", 250),
        )
    )
    top5 = [a for a in result["alerts"] if a["code"] == "top5_concentration"]
    assert top5 and top5[0]["level"] == "warning"


def test_negative_and_zero_positions_excluded_from_concentration() -> None:
    """Short / historical-data-gap positions must not enter the denominator."""
    assets = _assets(("ITSA4", 1000), ("BBAS3", 0))
    assets.append(ValuedAsset(asset_code="ETH", value_cents=-500))
    result = ConcentrationService().analyse(assets)
    assert result["num_assets"] == 1
    assert result["total_value_cents"] == 1000


def test_by_asset_is_sorted_descending_by_value_with_ranks() -> None:
    result = ConcentrationService().analyse(
        _assets(("Z", 100), ("A", 500), ("M", 300))
    )
    codes = [a["asset_code"] for a in result["by_asset"]]
    ranks = [a["rank"] for a in result["by_asset"]]
    assert codes == ["A", "M", "Z"]
    assert ranks == [1, 2, 3]


def test_top10_warning_only_above_threshold_and_with_more_than_5_assets() -> None:
    # 9 assets, top 10 = 100% > 90% → warning expected.
    result = ConcentrationService().analyse(
        _assets(*[(f"A{i}", 1000) for i in range(9)])
    )
    top10 = [a for a in result["alerts"] if a["code"] == "top10_concentration"]
    assert len(top10) == 1


def test_thresholds_block_documents_constants() -> None:
    result = ConcentrationService().analyse(_assets(("X", 100)))
    th = result["thresholds"]
    assert th["single_asset_warning_pct"] == 0.15
    assert th["single_asset_critical_pct"] == 0.25
    assert th["top5_info_pct"] == 0.60
    assert th["top5_warning_pct"] == 0.75
    assert th["top10_warning_pct"] == 0.90
    assert th["low_diversification_min_assets"] == 5
