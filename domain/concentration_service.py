"""Concentration analysis service.

Pure-domain HHI / top-N concentration computations and alert rules over a
collection of valued positions. The service does not access the database,
quote API or any other I/O boundary — its caller must pre-value the
positions (typically via :class:`~domain.position_valuation_service.PositionValuationService`).

All monetary inputs and outputs are integer cents. Percentages in the
payload are decimal fractions (``0.20`` = 20%) per the project convention.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

# Alert thresholds (decimal fractions; documented in the response payload).
_SINGLE_ASSET_WARNING = Decimal("0.15")
_SINGLE_ASSET_CRITICAL = Decimal("0.25")
_TOP5_INFO = Decimal("0.60")
_TOP5_WARNING = Decimal("0.75")
_TOP10_WARNING = Decimal("0.90")
_LOW_DIVERSIFICATION_MIN_ASSETS = 5

_PCT_QUANT = Decimal("0.0001")
_HHI_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class ValuedAsset:
    """A single position contribution used for concentration analysis."""

    asset_code: str
    value_cents: int


def _format_pct(value: Decimal) -> float:
    return float(value.quantize(_PCT_QUANT, rounding=ROUND_HALF_EVEN))


def _format_hhi(value: Decimal) -> float:
    return float(value.quantize(_HHI_QUANT, rounding=ROUND_HALF_EVEN))


class ConcentrationService:
    """Compute concentration metrics and emit threshold-based alerts."""

    def analyse(self, valued_assets: Iterable[ValuedAsset]) -> dict[str, Any]:
        """Return the concentration payload.

        Empty / fully-zero portfolios are handled gracefully: numeric metrics
        collapse to zero and a ``low_diversification`` alert is raised so the
        consumer can render an explanatory state.
        """
        # Only positive market values contribute to concentration: short or
        # negative positions (historical-data-gap signal) cannot meaningfully
        # be expressed as a percentage of a positive denominator.
        assets = [a for a in valued_assets if a.value_cents > 0]
        total = sum(a.value_cents for a in assets)
        num_assets = len(assets)

        # Sort largest first; deterministic on ties via asset_code.
        ordered = sorted(assets, key=lambda a: (-a.value_cents, a.asset_code))

        by_asset_payload: list[dict[str, Any]] = []
        ratios: list[Decimal] = []
        for rank, asset in enumerate(ordered, start=1):
            ratio = (
                Decimal(asset.value_cents) / Decimal(total)
                if total > 0
                else Decimal(0)
            )
            ratios.append(ratio)
            by_asset_payload.append(
                {
                    "asset_code": asset.asset_code,
                    "value_cents": asset.value_cents,
                    "pct": _format_pct(ratio),
                    "rank": rank,
                }
            )

        metrics = {
            "top_1_pct": _format_pct(sum(ratios[:1], Decimal(0))),
            "top_3_pct": _format_pct(sum(ratios[:3], Decimal(0))),
            "top_5_pct": _format_pct(sum(ratios[:5], Decimal(0))),
            "top_10_pct": _format_pct(sum(ratios[:10], Decimal(0))),
            "herfindahl_index": _format_hhi(sum((r * r for r in ratios), Decimal(0))),
        }

        alerts = self._build_alerts(ratios, ordered, num_assets)

        return {
            "total_value_cents": int(total),
            "num_assets": num_assets,
            "metrics": metrics,
            "by_asset": by_asset_payload,
            "alerts": alerts,
            "thresholds": {
                "single_asset_warning_pct": _format_pct(_SINGLE_ASSET_WARNING),
                "single_asset_critical_pct": _format_pct(_SINGLE_ASSET_CRITICAL),
                "top5_info_pct": _format_pct(_TOP5_INFO),
                "top5_warning_pct": _format_pct(_TOP5_WARNING),
                "top10_warning_pct": _format_pct(_TOP10_WARNING),
                "low_diversification_min_assets": _LOW_DIVERSIFICATION_MIN_ASSETS,
            },
        }

    def _build_alerts(
        self,
        ratios: list[Decimal],
        ordered: list[ValuedAsset],
        num_assets: int,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        if num_assets == 0:
            alerts.append(
                {
                    "level": "warning",
                    "code": "low_diversification",
                    "message": "Carteira sem posições com valor de mercado positivo.",
                }
            )
            return alerts

        # Single-asset checks (largest holding).
        top_ratio = ratios[0]
        top_asset = ordered[0]
        if top_ratio > _SINGLE_ASSET_CRITICAL:
            alerts.append(
                {
                    "level": "critical",
                    "code": "single_asset_high",
                    "message": (
                        f"{top_asset.asset_code} representa "
                        f"{_format_pct(top_ratio) * 100:.0f}% do portfólio "
                        f"(limite crítico: {int(_SINGLE_ASSET_CRITICAL * 100)}%)"
                    ),
                }
            )
        elif top_ratio > _SINGLE_ASSET_WARNING:
            alerts.append(
                {
                    "level": "warning",
                    "code": "single_asset_high",
                    "message": (
                        f"{top_asset.asset_code} representa "
                        f"{_format_pct(top_ratio) * 100:.0f}% do portfólio "
                        f"(limite sugerido: {int(_SINGLE_ASSET_WARNING * 100)}%)"
                    ),
                }
            )

        top5 = sum(ratios[:5], Decimal(0))
        if top5 > _TOP5_WARNING:
            alerts.append(
                {
                    "level": "warning",
                    "code": "top5_concentration",
                    "message": (
                        f"Top 5 ativos representam {_format_pct(top5) * 100:.0f}% "
                        f"da carteira (limite sugerido: {int(_TOP5_WARNING * 100)}%)"
                    ),
                }
            )
        elif top5 > _TOP5_INFO:
            alerts.append(
                {
                    "level": "info",
                    "code": "top5_concentration",
                    "message": (
                        f"Top 5 ativos representam {_format_pct(top5) * 100:.0f}% "
                        "da carteira"
                    ),
                }
            )

        top10 = sum(ratios[:10], Decimal(0))
        if top10 > _TOP10_WARNING and num_assets > 5:
            alerts.append(
                {
                    "level": "warning",
                    "code": "top10_concentration",
                    "message": (
                        f"Top 10 ativos representam {_format_pct(top10) * 100:.0f}% "
                        "da carteira"
                    ),
                }
            )

        if num_assets < _LOW_DIVERSIFICATION_MIN_ASSETS:
            alerts.append(
                {
                    "level": "warning",
                    "code": "low_diversification",
                    "message": (
                        f"Carteira possui apenas {num_assets} ativo(s) com "
                        "valor positivo (sugerido: pelo menos "
                        f"{_LOW_DIVERSIFICATION_MIN_ASSETS})."
                    ),
                }
            )

        return alerts


__all__ = ["ConcentrationService", "ValuedAsset"]
