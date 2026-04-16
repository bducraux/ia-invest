"""Portfolio domain service — loads and validates portfolio manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from domain.models import Portfolio


class PortfolioService:
    """Loads portfolio configuration from YAML manifests and validates them."""

    REQUIRED_FIELDS = ("id", "name", "base_currency", "status")
    VALID_STATUSES = ("active", "inactive", "archived")

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
            config=config,
        )

    def validate_asset_type(self, portfolio: Portfolio, asset_type: str) -> bool:
        """Return True if the given asset type is allowed by the portfolio rules."""
        allowed = portfolio.allowed_asset_types
        if not allowed:
            return True  # no restrictions configured
        return asset_type in allowed

    def _validate_config(self, config: dict[str, Any]) -> None:
        for field in self.REQUIRED_FIELDS:
            if not config.get(field):
                raise ValueError(f"Portfolio manifest is missing required field: '{field}'")

        status = config.get("status", "active")
        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid portfolio status '{status}'. "
                f"Allowed: {self.VALID_STATUSES}"
            )

        portfolio_id: str = config["id"]
        if not portfolio_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"Portfolio id '{portfolio_id}' must contain only alphanumeric characters, "
                "hyphens and underscores."
            )
