"""Tests for MCP server member tools."""

from __future__ import annotations

import pytest

from domain.members import Member
from domain.models import Portfolio
from mcp_server.tools.members import (
    compare_members,
    get_consolidated_summary_filtered,
    get_member,
    get_member_summary,
    list_members,
    transfer_portfolio_owner_tool,
)
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository


@pytest.fixture
def db_with_members(tmp_db: Database) -> Database:
    m = MemberRepository(tmp_db.connection)
    m.upsert(Member(id="bob", name="Bob", email="b@x.com"))
    m.upsert(Member(id="alice", name="Alice"))
    p = PortfolioRepository(tmp_db.connection)
    p.upsert(Portfolio(id="rv-bob", name="RV", owner_id="bob"))
    p.upsert(Portfolio(id="rf-bob", name="RF", owner_id="bob"))
    p.upsert(Portfolio(id="rv-alice", name="RV", owner_id="alice"))
    return tmp_db


def test_list_members(db_with_members: Database) -> None:
    members = list_members(db_with_members)
    ids = {m["id"] for m in members}
    assert {"bob", "alice"}.issubset(ids)
    bob = next(m for m in members if m["id"] == "bob")
    assert bob["portfolio_count"] == 2


def test_get_member(db_with_members: Database) -> None:
    m = get_member(db_with_members, "bob")
    assert m["id"] == "bob"
    assert m["portfolio_count"] == 2


def test_get_member_resolves_by_name(db_with_members: Database) -> None:
    m = get_member(db_with_members, "Alice")
    assert m["id"] == "alice"


def test_get_member_unknown(db_with_members: Database) -> None:
    m = get_member(db_with_members, "ghost")
    assert "error" in m


def test_get_member_summary(db_with_members: Database) -> None:
    summary = get_member_summary(db_with_members, "bob")
    assert summary["member"]["id"] == "bob"
    assert len(summary["portfolios"]) == 2
    assert summary["totals"]["open_positions"] == 0


def test_compare_members(db_with_members: Database) -> None:
    out = compare_members(db_with_members, ["bob", "alice"])
    assert len(out) == 2
    assert out[0]["member"]["id"] == "bob"
    assert out[1]["member"]["id"] == "alice"


def test_transfer_portfolio_owner_tool(db_with_members: Database) -> None:
    out = transfer_portfolio_owner_tool(db_with_members, "rv-bob", "alice")
    assert out["owner_id"] == "alice"
    refreshed = PortfolioRepository(db_with_members.connection).get("rv-bob")
    assert refreshed is not None and refreshed.owner_id == "alice"


def test_transfer_portfolio_owner_tool_errors(db_with_members: Database) -> None:
    out = transfer_portfolio_owner_tool(db_with_members, "rv-bob", "ghost")
    assert "error" in out


def test_consolidated_summary_filtered_by_owner(db_with_members: Database) -> None:
    summary = get_consolidated_summary_filtered(db_with_members, owner_id="bob")
    pids = {p["id"] for p in summary["portfolios"]}
    assert pids == {"rv-bob", "rf-bob"}
    assert summary["owner_id"] == "bob"


def test_consolidated_summary_filtered_unknown_owner(
    db_with_members: Database,
) -> None:
    summary = get_consolidated_summary_filtered(db_with_members, owner_id="ghost")
    assert "error" in summary
