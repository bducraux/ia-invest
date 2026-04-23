"""Lifecycle transitions for fixed-income positions.

Two actions are supported:

close(position_id)
    Delete the position entirely. Use when a matured (or early-redeemed)
    position should simply be removed with no reinvestment.

redeem(position_id, as_of_date)
    Reinvest the net proceeds: create a fresh ACTIVE position with the same
    contract terms but new application/maturity dates and a principal equal
    to the net value on the action date, then delete the old position.

Both actions are non-reversible and leave no history in the database.

reconcile_auto_reapply(portfolio_id, as_of_date)
    Called on every read of the fixed-income list. Finds all positions with
    auto_reapply_enabled=True whose maturity date has passed and calls
    redeem() on each. Natural idempotency: once redeemed the old row is gone.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_valuation import FixedIncomeValuationService
from storage.repository.fixed_income import FixedIncomePositionRepository


class FixedIncomeLifecycleService:
    """Encapsulates fixed-income lifecycle actions with transactional safety."""

    def __init__(
        self,
        repo: FixedIncomePositionRepository,
        valuation_service: FixedIncomeValuationService,
    ) -> None:
        self._repo = repo
        self._valuation = valuation_service

    # ------------------------------------------------------------------
    # Close — delete without reinvesting
    # ------------------------------------------------------------------

    def close(
        self,
        portfolio_id: str,
        position_id: int,
    ) -> None:
        """Delete a position. No new position is created."""
        position = self._require_position(portfolio_id, position_id)
        self._repo.delete(position.id or position_id, portfolio_id)

    # ------------------------------------------------------------------
    # Redeem — reinvest proceeds, delete old position
    # ------------------------------------------------------------------

    def redeem(
        self,
        portfolio_id: str,
        position_id: int,
        *,
        as_of_date: str | None = None,
    ) -> FixedIncomePosition:
        """Create a new position with net proceeds and delete the old one.

        Returns the newly created position.
        """
        original = self._require_position(portfolio_id, position_id)
        action_date = _parse_iso_date(as_of_date) if as_of_date else date.today()
        valuation = self._valuation.revalue_as_of(original, action_date)

        duration_days = _duration_days(original.application_date, original.maturity_date)
        new_maturity = action_date + timedelta(days=duration_days)

        replacement = replace(
            original,
            id=None,
            import_job_id=None,
            external_id=None,
            application_date=action_date.isoformat(),
            maturity_date=new_maturity.isoformat(),
            principal_applied_brl=valuation.net_value_current_brl,
            status="ACTIVE",
        )

        conn = self._repo._conn  # noqa: SLF001
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._repo.insert(replacement, commit=False)
            self._repo.delete(original.id or position_id, original.portfolio_id, commit=False)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        created = self._repo.get(replacement.id or 0)
        if created is None:
            raise ValueError("Failed to create re-applied position")
        return created

    # ------------------------------------------------------------------
    # Auto-reapply reconciliation
    # ------------------------------------------------------------------

    def reconcile_auto_reapply(
        self,
        portfolio_id: str,
        *,
        as_of_date: str | None = None,
    ) -> int:
        """Redeem all matured positions that have auto_reapply_enabled.

        Returns the number of positions processed.
        Natural idempotency: once redeemed the old row is deleted, so
        subsequent calls will not find it again.
        """
        action_date = _parse_iso_date(as_of_date) if as_of_date else date.today()
        action_date_iso = action_date.isoformat()

        candidates = self._repo.list_auto_reapply_candidates(
            portfolio_id,
            as_of_date=action_date_iso,
        )
        reapplied = 0
        for candidate in candidates:
            if candidate.id is None:
                continue
            self.redeem(portfolio_id, candidate.id, as_of_date=action_date_iso)
            reapplied += 1

        return reapplied

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_position(self, portfolio_id: str, position_id: int) -> FixedIncomePosition:
        position = self._repo.get(position_id)
        if position is None or position.portfolio_id != portfolio_id:
            raise ValueError("Position not found")
        return position


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _duration_days(application_date: str, maturity_date: str) -> int:
    app = _parse_iso_date(application_date)
    mat = _parse_iso_date(maturity_date)
    return (mat - app).days
