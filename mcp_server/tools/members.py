"""MCP server tools — member management and member-level aggregations.

These tools mirror the existing portfolio tools but operate at the member
level (a member is an owner of one or more portfolios).
"""

from __future__ import annotations

from typing import Any

from mcp_server.tools.portfolios import (
    get_consolidated_summary,
    get_portfolio_operations,
    get_portfolio_positions,
    get_portfolio_summary,
)
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository


def _member_to_dict(member: Any) -> dict[str, Any]:
    return {
        "id": member.id,
        "name": member.name,
        "display_name": member.display_name,
        "email": member.email,
        "status": member.status,
        "created_at": member.created_at,
        "updated_at": member.updated_at,
    }


def list_members(db: Database, *, only_active: bool = True) -> list[dict[str, Any]]:
    """Return all members (default: only active ones)."""
    repo = MemberRepository(db.connection)
    members = repo.list_active() if only_active else repo.list_all()
    out = []
    for m in members:
        d = _member_to_dict(m)
        d["portfolio_count"] = repo.count_portfolios(m.id, only_active=only_active)
        out.append(d)
    return out


def get_member(db: Database, member_id: str) -> dict[str, Any]:
    """Return a single member by id (or by name/display_name lookup)."""
    repo = MemberRepository(db.connection)
    member = repo.get(member_id) or repo.get_by_id_or_name(member_id)
    if member is None:
        return {"error": f"Member '{member_id}' not found."}
    out = _member_to_dict(member)
    out["portfolio_count"] = repo.count_portfolios(member.id, only_active=True)
    return out


def get_member_summary(db: Database, member_id: str) -> dict[str, Any]:
    """Return a consolidated summary across all portfolios owned by the member."""
    member_repo = MemberRepository(db.connection)
    member = member_repo.get(member_id) or member_repo.get_by_id_or_name(member_id)
    if member is None:
        return {"error": f"Member '{member_id}' not found."}

    portfolio_repo = PortfolioRepository(db.connection)
    portfolios = portfolio_repo.list_by_owner(member.id, only_active=True)

    summaries = []
    total_cost = 0
    total_pnl = 0
    total_dividends = 0
    total_open = 0

    for p in portfolios:
        s = get_portfolio_summary(db, p.id)
        if "error" in s:
            continue
        summaries.append(s)
        total_cost += int(s.get("total_cost_cents") or 0)
        total_pnl += int(s.get("realized_pnl_cents") or 0)
        total_dividends += int(s.get("dividends_cents") or 0)
        total_open += int(s.get("open_positions") or 0)

    return {
        "member": _member_to_dict(member),
        "portfolios": summaries,
        "totals": {
            "open_positions": total_open,
            "total_cost_cents": total_cost,
            "realized_pnl_cents": total_pnl,
            "dividends_cents": total_dividends,
        },
    }


def get_member_positions(
    db: Database, member_id: str, *, open_only: bool = True
) -> list[dict[str, Any]]:
    """Return positions across every portfolio owned by the member."""
    member_repo = MemberRepository(db.connection)
    member = member_repo.get(member_id) or member_repo.get_by_id_or_name(member_id)
    if member is None:
        return [{"error": f"Member '{member_id}' not found."}]

    portfolio_repo = PortfolioRepository(db.connection)
    out: list[dict[str, Any]] = []
    for p in portfolio_repo.list_by_owner(member.id, only_active=True):
        for pos in get_portfolio_positions(db, p.id, open_only=open_only):
            if "error" in pos:
                continue
            row = dict(pos)
            row["portfolio_id"] = p.id
            row["portfolio_name"] = p.name
            out.append(row)
    return out


def get_member_operations(
    db: Database,
    member_id: str,
    *,
    asset_code: str | None = None,
    operation_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return operations across every portfolio owned by the member."""
    member_repo = MemberRepository(db.connection)
    member = member_repo.get(member_id) or member_repo.get_by_id_or_name(member_id)
    if member is None:
        return [{"error": f"Member '{member_id}' not found."}]

    portfolio_repo = PortfolioRepository(db.connection)
    out: list[dict[str, Any]] = []
    remaining = limit
    for p in portfolio_repo.list_by_owner(member.id, only_active=True):
        if remaining <= 0:
            break
        ops = get_portfolio_operations(
            db,
            p.id,
            asset_code=asset_code,
            operation_type=operation_type,
            start_date=start_date,
            end_date=end_date,
            limit=remaining,
            offset=0,
        )
        for op in ops:
            if "error" in op:
                continue
            row = dict(op)
            row["portfolio_id"] = p.id
            row["portfolio_name"] = p.name
            out.append(row)
            remaining -= 1
            if remaining <= 0:
                break
    return out


def compare_members(db: Database, member_ids: list[str]) -> list[dict[str, Any]]:
    """Return side-by-side member-level summaries."""
    return [get_member_summary(db, mid) for mid in member_ids]


def transfer_portfolio_owner_tool(
    db: Database, portfolio_id: str, new_owner_id: str
) -> dict[str, Any]:
    """Reassign a portfolio to a different member.

    Note: this only updates the database — moving the on-disk folder is the
    responsibility of `scripts/transfer_portfolio_owner.py`.  The MCP tool
    is intended for read-mostly clients (e.g. Claude Desktop) where the
    filesystem isn't accessible.
    """
    from domain.portfolio_service import PortfolioService

    portfolio_repo = PortfolioRepository(db.connection)
    member_repo = MemberRepository(db.connection)
    svc = PortfolioService(portfolio_repo=portfolio_repo, member_repo=member_repo)
    try:
        portfolio = svc.transfer_ownership(portfolio_id, new_owner_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "portfolio_id": portfolio.id,
        "owner_id": portfolio.owner_id,
        "name": portfolio.name,
    }


def get_consolidated_summary_filtered(
    db: Database, *, owner_id: str | None = None
) -> dict[str, Any]:
    """Wrapper around get_consolidated_summary that supports owner filtering."""
    summary = get_consolidated_summary(db)
    if owner_id is None:
        return summary

    member_repo = MemberRepository(db.connection)
    member = member_repo.get(owner_id) or member_repo.get_by_id_or_name(owner_id)
    if member is None:
        return {"error": f"Member '{owner_id}' not found."}

    portfolio_repo = PortfolioRepository(db.connection)
    pids = {p.id for p in portfolio_repo.list_by_owner(member.id, only_active=True)}

    filtered = [s for s in summary.get("portfolios", []) if s.get("id") in pids]
    totals = {
        "open_positions": sum(int(s.get("open_positions") or 0) for s in filtered),
        "total_cost_cents": sum(int(s.get("total_cost_cents") or 0) for s in filtered),
        "realized_pnl_cents": sum(int(s.get("realized_pnl_cents") or 0) for s in filtered),
        "dividends_cents": sum(int(s.get("dividends_cents") or 0) for s in filtered),
    }
    return {"owner_id": member.id, "portfolios": filtered, "totals": totals}
