"""Portfolio domain service — loads and validates portfolio manifests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from domain.models import Portfolio

if TYPE_CHECKING:
    from storage.repository.members import MemberRepository
    from storage.repository.portfolios import PortfolioRepository

log = structlog.get_logger(__name__)


class PortfolioService:
    """Loads portfolio configuration from YAML manifests and validates them."""

    REQUIRED_FIELDS = ("id", "name", "base_currency", "status", "owner_id")
    VALID_STATUSES = ("active", "inactive", "archived")

    def __init__(
        self,
        portfolio_repo: PortfolioRepository | None = None,
        member_repo: MemberRepository | None = None,
    ) -> None:
        self._portfolios = portfolio_repo
        self._members = member_repo

    def load_from_yaml(self, manifest_path: Path) -> Portfolio:
        """Parse a portfolio.yml file and return a Portfolio domain object.

        Raises:
            FileNotFoundError: if the manifest does not exist.
            ValueError: if required fields are missing or values are invalid.
        """
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with manifest_path.open(encoding="utf-8") as fh:
            config: dict[str, Any] = yaml.safe_load(fh)

        self._validate_config(config)

        return Portfolio(
            id=config["id"],
            name=config["name"],
            description=config.get("description"),
            base_currency=config.get("base_currency", "BRL"),
            status=config.get("status", "active"),
            owner_id=str(config["owner_id"]).strip().lower(),
            config=config,
        )

    def validate_asset_type(self, portfolio: Portfolio, asset_type: str) -> bool:
        """Return True if the given asset type is allowed by the portfolio rules."""
        allowed = portfolio.allowed_asset_types
        if not allowed:
            return True  # no restrictions configured
        return asset_type in allowed

    # ---------------------------------------------------------------- creation
    def create(self, portfolio: Portfolio) -> Portfolio:
        """Persist a new portfolio after validating its owner exists.

        Requires both `portfolio_repo` and `member_repo` to be wired.
        """
        if self._portfolios is None or self._members is None:
            raise RuntimeError(
                "PortfolioService.create requires portfolio_repo and member_repo."
            )
        if not portfolio.owner_id:
            raise ValueError("Portfolio.owner_id must not be empty.")
        if self._members.get(portfolio.owner_id) is None:
            raise ValueError(
                f"Owner member '{portfolio.owner_id}' does not exist."
            )
        if self._portfolios.get(portfolio.id) is not None:
            raise ValueError(f"Portfolio '{portfolio.id}' already exists.")
        self._portfolios.upsert(portfolio)
        log.info(
            "portfolio_created",
            portfolio_id=portfolio.id,
            owner_id=portfolio.owner_id,
        )
        return portfolio

    # -------------------------------------------------------- transfer ownership
    def transfer_ownership(
        self, portfolio_id: str, new_owner_id: str
    ) -> Portfolio:
        """Move portfolio ownership to a different member.

        Records a structured-log entry suitable for audit purposes.
        """
        if self._portfolios is None or self._members is None:
            raise RuntimeError(
                "PortfolioService.transfer_ownership requires both repositories."
            )

        portfolio = self._portfolios.get(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio '{portfolio_id}' not found.")
        target = self._members.get(new_owner_id)
        if target is None:
            raise ValueError(f"Member '{new_owner_id}' not found.")

        old_owner = portfolio.owner_id
        if old_owner == new_owner_id:
            log.info(
                "portfolio_transfer_no_op",
                portfolio_id=portfolio_id,
                owner_id=new_owner_id,
            )
            return portfolio

        self._portfolios.transfer_ownership(portfolio_id, new_owner_id)
        log.info(
            "portfolio_ownership_transferred",
            portfolio_id=portfolio_id,
            previous_owner_id=old_owner,
            new_owner_id=new_owner_id,
        )
        portfolio.owner_id = new_owner_id
        return portfolio

    # --------------------------------------------------------------- internals
    def _validate_config(self, config: dict[str, Any]) -> None:
        for field in self.REQUIRED_FIELDS:
            if not config.get(field):
                raise ValueError(
                    f"Portfolio manifest is missing required field: '{field}'"
                )

        status = config.get("status", "active")
        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid portfolio status '{status}'. "
                f"Allowed: {self.VALID_STATUSES}"
            )

        portfolio_id: str = config["id"]
        if not portfolio_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"Portfolio id '{portfolio_id}' must contain only alphanumeric "
                "characters, hyphens and underscores."
            )

        owner_id: str = str(config["owner_id"])
        if not owner_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"Portfolio owner_id '{owner_id}' must contain only "
                "alphanumeric characters, hyphens and underscores."
            )
