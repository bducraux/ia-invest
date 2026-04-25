"""Portfolio alerts aggregator.

Pure-domain merger of alert signals from other services into a single,
prioritised list. The service does not call services or repositories
itself — its caller is responsible for loading concentration alerts,
fixed-income upcoming maturities and the list of assets without quotes,
then handing them in. This keeps the service trivially testable and
makes the cross-service dependency graph explicit at the tool layer.

Severity ordering used for the final ``alerts`` list:

* ``critical`` (most severe)
* ``warning``
* ``info`` (least severe)

Within the same severity, ordering is stable on the input order — the
caller should pre-sort by severity-relevant signal (e.g. days-to-maturity
ascending for fixed-income alerts).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

_SEVERITY_RANK: dict[str, int] = {"critical": 0, "warning": 1, "info": 2}


def _severity_key(alert: dict[str, Any]) -> int:
    return _SEVERITY_RANK.get(str(alert.get("level", "info")), 99)


class PortfolioAlertsService:
    """Merge heterogeneous alert sources into a single sorted payload."""

    def aggregate(
        self,
        *,
        concentration_alerts: Iterable[dict[str, Any]] | None = None,
        upcoming_maturities: Iterable[dict[str, Any]] | None = None,
        missing_quote_assets: Iterable[str] | None = None,
        incomplete_fixed_income_valuations: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        alerts: list[dict[str, Any]] = []

        for alert in concentration_alerts or ():
            alerts.append(
                {
                    "source": "concentration",
                    "level": alert.get("level", "info"),
                    "code": alert.get("code", "concentration"),
                    "message": alert.get("message", ""),
                }
            )

        for entry in upcoming_maturities or ():
            days = int(entry.get("days_to_maturity", 9_999))
            level = "warning" if days <= 7 else "info"
            alerts.append(
                {
                    "source": "fixed_income",
                    "level": level,
                    "code": "upcoming_maturity",
                    "message": (
                        f"{entry.get('product_name', 'aplicação')} vence em "
                        f"{days} dia(s) ({entry.get('maturity_date', '?')})."
                    ),
                    "details": {
                        "position_id": entry.get("position_id"),
                        "maturity_date": entry.get("maturity_date"),
                        "days_to_maturity": days,
                        "net_value_cents": entry.get("net_value_cents"),
                    },
                }
            )

        missing = sorted({a for a in (missing_quote_assets or ()) if a})
        if missing:
            alerts.append(
                {
                    "source": "quotes",
                    "level": "info",
                    "code": "missing_quotes",
                    "message": (
                        "Sem cotação atual para: " + ", ".join(missing)
                    ),
                    "details": {"assets": missing},
                }
            )

        for entry in incomplete_fixed_income_valuations or ():
            alerts.append(
                {
                    "source": "fixed_income",
                    "level": "warning",
                    "code": "valuation_incomplete",
                    "message": (
                        f"Valuation incompleta para {entry.get('product_name', 'aplicação')}: "
                        f"{entry.get('reason', 'série de benchmark insuficiente')}."
                    ),
                    "details": entry,
                }
            )

        alerts.sort(key=_severity_key)

        counts = {"critical": 0, "warning": 0, "info": 0}
        for a in alerts:
            level = str(a.get("level", "info"))
            if level in counts:
                counts[level] += 1

        return {
            "alerts": alerts,
            "counts": counts,
            "total": len(alerts),
        }


__all__ = ["PortfolioAlertsService"]
