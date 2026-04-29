"""Member domain — family member who owns one or more portfolios.

A `Member` is a logical organisation entity (NOT an authentication credential
— IA-Invest is a local-first single-user system).  Every portfolio belongs to
exactly one member; transferring ownership is an auditable operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from storage.repository.members import MemberRepository
    from storage.repository.portfolios import PortfolioRepository

log = structlog.get_logger(__name__)

# Tight RFC-5322-lite email pattern good enough for our local-first context.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
# kebab-case slug used as the canonical id of a member.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_VALID_STATUSES = ("active", "inactive")


@dataclass
class Member:
    """Family member who owns one or more portfolios."""

    id: str
    name: str
    display_name: str | None = None
    email: str | None = None
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None


class MemberServiceError(ValueError):
    """Raised by MemberService when business rules are violated."""


class MemberService:
    """Business rules around members."""

    def __init__(
        self,
        member_repo: MemberRepository,
        portfolio_repo: PortfolioRepository | None = None,
    ) -> None:
        self._members = member_repo
        self._portfolios = portfolio_repo

    # ------------------------------------------------------------------ create
    def create(
        self,
        *,
        member_id: str,
        name: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> Member:
        """Create a new member after validating the inputs."""
        member_id = (member_id or "").strip().lower()
        name = (name or "").strip()
        display_name = display_name.strip() if display_name else None
        email = email.strip().lower() if email else None

        self._validate_id(member_id)
        if not name:
            raise MemberServiceError("Member 'name' must not be empty.")

        if email is not None:
            self._validate_email(email)
            existing = self._members.get_by_email(email)
            if existing is not None and existing.id != member_id:
                raise MemberServiceError(
                    f"E-mail '{email}' already used by member '{existing.id}'."
                )

        if self._members.get(member_id) is not None:
            raise MemberServiceError(
                f"Member with id '{member_id}' already exists."
            )

        member = Member(
            id=member_id,
            name=name,
            display_name=display_name,
            email=email,
            status="active",
        )
        self._members.upsert(member)
        log.info("member_created", member_id=member_id, name=name)
        return member

    # ------------------------------------------------------------------ update
    def update(
        self,
        member_id: str,
        *,
        name: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
    ) -> Member:
        existing = self._members.get(member_id)
        if existing is None:
            raise MemberServiceError(f"Member '{member_id}' not found.")

        if name is not None:
            stripped = name.strip()
            if not stripped:
                raise MemberServiceError("Member 'name' must not be empty.")
            existing.name = stripped

        if display_name is not None:
            stripped = display_name.strip()
            existing.display_name = stripped or None

        if email is not None:
            email_clean: str | None = email.strip().lower() or None
            if email_clean is not None:
                self._validate_email(email_clean)
                conflict = self._members.get_by_email(email_clean)
                if conflict is not None and conflict.id != member_id:
                    raise MemberServiceError(
                        f"E-mail '{email_clean}' already used by member "
                        f"'{conflict.id}'."
                    )
            existing.email = email_clean

        self._members.upsert(existing)
        log.info("member_updated", member_id=member_id)
        return existing

    # -------------------------------------------------------------- inactivate
    def inactivate(self, member_id: str) -> Member:
        """Mark a member as inactive.

        Blocked while the member still owns one or more **active** portfolios —
        the caller must transfer ownership first.
        """
        existing = self._members.get(member_id)
        if existing is None:
            raise MemberServiceError(f"Member '{member_id}' not found.")

        active_owned = self._members.count_portfolios(member_id, only_active=True)
        if active_owned > 0:
            raise MemberServiceError(
                f"Cannot inactivate '{member_id}': still owns {active_owned} "
                "active portfolio(s). Transfer ownership first."
            )

        self._members.set_status(member_id, "inactive")
        log.info("member_inactivated", member_id=member_id)
        existing.status = "inactive"
        return existing

    # -------------------------------------------------------------- activation
    def activate(self, member_id: str) -> Member:
        existing = self._members.get(member_id)
        if existing is None:
            raise MemberServiceError(f"Member '{member_id}' not found.")
        self._members.set_status(member_id, "active")
        existing.status = "active"
        log.info("member_activated", member_id=member_id)
        return existing

    # ------------------------------------------------------------------ delete
    def delete(self, member_id: str) -> None:
        """Hard-delete a member; only allowed when the member owns nothing."""
        existing = self._members.get(member_id)
        if existing is None:
            raise MemberServiceError(f"Member '{member_id}' not found.")
        owned = self._members.count_portfolios(member_id)
        if owned > 0:
            raise MemberServiceError(
                f"Cannot delete '{member_id}': still owns {owned} portfolio(s). "
                "Inactivate or transfer ownership first."
            )
        self._members.delete(member_id)
        log.info("member_deleted", member_id=member_id)

    # ------------------------------------------------------------------- queries
    def list_portfolios_of(self, member_id: str) -> list:  # noqa: ANN201
        """Delegate to the portfolio repository to list portfolios of a member."""
        if self._portfolios is None:
            raise MemberServiceError(
                "PortfolioRepository not provided to MemberService."
            )
        if self._members.get(member_id) is None:
            raise MemberServiceError(f"Member '{member_id}' not found.")
        return self._portfolios.list_by_owner(member_id, only_active=True)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _validate_id(member_id: str) -> None:
        if not member_id:
            raise MemberServiceError("Member 'id' must not be empty.")
        if not _ID_RE.match(member_id):
            raise MemberServiceError(
                f"Invalid member id '{member_id}': must be lowercase "
                "kebab-case (letters, digits, hyphen, underscore) and start "
                "with a letter or digit."
            )

    @staticmethod
    def _validate_email(email: str) -> None:
        if not _EMAIL_RE.match(email):
            raise MemberServiceError(f"Invalid email format: '{email}'.")

    @staticmethod
    def is_valid_status(status: str) -> bool:
        return status in _VALID_STATUSES
