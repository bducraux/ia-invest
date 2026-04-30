"""IA-Invest MCP Server.

Exposes domain-oriented tools to MCP clients (e.g. Claude Desktop).

Start the server::

    python -m mcp_server.server

The server communicates via stdin/stdout using the MCP protocol.  Configure
your MCP client to launch this process as a local server.

Claude Desktop config example (~/Library/Application Support/Claude/claude_desktop_config.json):

.. code-block:: json

    {
      "mcpServers": {
        "ia-invest": {
          "command": "python",
          "args": ["-m", "mcp_server.server"],
          "cwd": "/path/to/ia-invest"
        }
      }
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions

from mcp_server.tools.app_settings import get_app_settings
from mcp_server.tools.concentration import get_concentration_analysis
from mcp_server.tools.dividends_summary import get_dividends_summary
from mcp_server.tools.fixed_income_summary import get_fixed_income_summary
from mcp_server.tools.members import (
    compare_members,
    get_consolidated_summary_filtered,
    get_member,
    get_member_operations,
    get_member_positions,
    get_member_summary,
    list_members,
    transfer_portfolio_owner_tool,
)
from mcp_server.tools.equity_curve import get_portfolio_equity_curve
from mcp_server.tools.performance import get_portfolio_performance
from mcp_server.tools.portfolio_alerts import get_portfolio_alerts
from mcp_server.tools.portfolios import (
    compare_portfolios,
    get_consolidated_summary,
    get_portfolio_operations,
    get_portfolio_positions,
    get_portfolio_summary,
    list_portfolios,
)
from mcp_server.tools.positions_with_quote import get_position_with_quote
from storage.repository.db import Database

_DB_PATH = Path(os.environ.get("IA_INVEST_DB", "ia_invest.db"))

app = Server("ia-invest")

# Single DB instance for the lifetime of the server process.
# initialize() runs schema setup once here instead of on every tool call.
_db: Database | None = None


def _get_db() -> Database:
    global _db  # noqa: PLW0603
    if _db is None:
        _db = Database(_DB_PATH)
        _db.initialize()
    return _db


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@app.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_portfolios",
            description="List all active investment portfolios.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_portfolio_summary",
            description=(
                "Get a summary of a portfolio including open positions count, "
                "total invested cost, realised P&L and dividends received."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {
                        "type": "string",
                        "description": "Portfolio identifier (e.g. 'renda-variavel')",
                    }
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_portfolio_positions",
            description="Get current open positions for a portfolio.",
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "open_only": {
                        "type": "boolean",
                        "description": "If true (default), return only positions with quantity > 0.",
                        "default": True,
                    },
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_portfolio_operations",
            description="Get operations (trades) for a portfolio, with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "asset_code": {"type": "string", "description": "Filter by asset ticker."},
                    "operation_type": {
                        "type": "string",
                        "description": "Filter by type: buy, sell, dividend, etc.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date filter (YYYY-MM-DD).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date filter (YYYY-MM-DD).",
                    },
                    "limit": {"type": "integer", "default": 100},
                    "offset": {"type": "integer", "default": 0},
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="compare_portfolios",
            description="Compare summaries of multiple portfolios side by side.",
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of portfolio IDs to compare.",
                    }
                },
                "required": ["portfolio_ids"],
            },
        ),
        types.Tool(
            name="get_consolidated_summary",
            description=(
                "Get a consolidated view across all active portfolios. "
                "Optionally filtered by owner_id to scope the result to a "
                "specific member."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "owner_id": {
                        "type": "string",
                        "description": "Optional member id to filter results.",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_app_settings",
            description=(
                "Return current global financial settings (CDI, SELIC, IPCA): "
                "annual and daily rates plus their last sync date. Missing "
                "series are reported as null with a warning, never an error."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_position_with_quote",
            description=(
                "Return positions for a portfolio enriched with the latest "
                "available quote, current market value and unrealised P&L. "
                "Positions without a quote are still returned with quote "
                "fields set to null."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "asset_code": {
                        "type": "string",
                        "description": "Optional ticker filter (case-insensitive).",
                    },
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_dividends_summary",
            description=(
                "Summarise proventos (dividend, JCP, rendimento) received in a "
                "rolling window. Returns totals, per-asset/per-month/per-type "
                "breakdowns and a moving-window DY estimate based on the "
                "current portfolio market value."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "period_months": {
                        "type": "integer",
                        "description": "Rolling window in months (default 12).",
                        "default": 12,
                        "minimum": 1,
                    },
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_concentration_analysis",
            description=(
                "Concentration risk analysis: top-N percentages, normalised "
                "Herfindahl-Hirschman index and threshold-based alerts "
                "(single-asset, top-5, top-10, low diversification)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_portfolio_performance",
            description=(
                "Lifetime + period performance metrics for a portfolio: "
                "current market value, lifetime capital/income/total return, "
                "dividends received in the rolling window and CDI accumulated "
                "over the same window for benchmark comparison."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "period_months": {
                        "type": "integer",
                        "description": "Rolling window in months (default 12).",
                        "default": 12,
                        "minimum": 1,
                    },
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_fixed_income_summary",
            description=(
                "CDB/LCI/LCA summary: principal vs current gross/net values, "
                "estimated IR, maturity ladder (<=30d, <=90d, <=365d, >365d) "
                "and upcoming maturities."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_portfolio_alerts",
            description=(
                "Aggregated portfolio alerts merging concentration risks, "
                "upcoming fixed-income maturities, missing market quotes "
                "and incomplete fixed-income valuations into a single, "
                "severity-sorted list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="get_portfolio_equity_curve",
            description=(
                "Monthly equity curve (evolução patrimonial) covering all "
                "asset classes: renda variável, internacional, cripto, "
                "renda fixa e previdência. Returns one point per month "
                "with consolidated market value, per-class breakdown, "
                "net contributions and dividends received in the month."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {
                        "type": "string",
                        "description": "Portfolio ID. Omit for consolidated view.",
                    },
                    "from_month": {
                        "type": "string",
                        "description": "Lower bound (YYYY-MM, inclusive).",
                    },
                    "to_month": {
                        "type": "string",
                        "description": "Upper bound (YYYY-MM, inclusive). Defaults to current month.",
                    },
                    "period_months": {
                        "type": "integer",
                        "description": "Window size when from_month is omitted (default 24).",
                        "default": 24,
                        "minimum": 1,
                    },
                },
                "required": [],
            },
        ),
        # ----------------------------------------------------------- members
        types.Tool(
            name="list_members",
            description="List family members (owners of portfolios). Default: only active.",
            inputSchema={
                "type": "object",
                "properties": {
                    "only_active": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_member",
            description="Get a single member by id (or by name).",
            inputSchema={
                "type": "object",
                "properties": {"member_id": {"type": "string"}},
                "required": ["member_id"],
            },
        ),
        types.Tool(
            name="get_member_summary",
            description="Consolidated summary across all portfolios of a member.",
            inputSchema={
                "type": "object",
                "properties": {"member_id": {"type": "string"}},
                "required": ["member_id"],
            },
        ),
        types.Tool(
            name="get_member_positions",
            description="All open positions across every portfolio owned by a member.",
            inputSchema={
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "open_only": {"type": "boolean", "default": True},
                },
                "required": ["member_id"],
            },
        ),
        types.Tool(
            name="get_member_operations",
            description="Operations across every portfolio owned by a member.",
            inputSchema={
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "asset_code": {"type": "string"},
                    "operation_type": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["member_id"],
            },
        ),
        types.Tool(
            name="compare_members",
            description="Side-by-side member-level summaries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "member_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["member_ids"],
            },
        ),
        types.Tool(
            name="transfer_portfolio_owner",
            description=(
                "Reassign a portfolio to a different member (DB only — does "
                "not move on-disk folders; use the script for that)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "new_owner_id": {"type": "string"},
                },
                "required": ["portfolio_id", "new_owner_id"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

@app.call_tool()  # type: ignore[untyped-decorator]
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    args = arguments or {}
    db = _get_db()

    try:
        result: Any
        if name == "list_portfolios":
            result = list_portfolios(db)
        elif name == "get_portfolio_summary":
            result = get_portfolio_summary(db, args["portfolio_id"])
        elif name == "get_portfolio_positions":
            result = get_portfolio_positions(
                db,
                args["portfolio_id"],
                open_only=args.get("open_only", True),
            )
        elif name == "get_portfolio_operations":
            result = get_portfolio_operations(
                db,
                args["portfolio_id"],
                asset_code=args.get("asset_code"),
                operation_type=args.get("operation_type"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
                limit=args.get("limit", 100),
                offset=args.get("offset", 0),
            )
        elif name == "compare_portfolios":
            result = compare_portfolios(db, args["portfolio_ids"])
        elif name == "get_consolidated_summary":
            owner_filter = args.get("owner_id")
            if owner_filter:
                result = get_consolidated_summary_filtered(db, owner_id=owner_filter)
            else:
                result = get_consolidated_summary(db)
        elif name == "get_app_settings":
            result = get_app_settings(db)
        elif name == "get_position_with_quote":
            result = get_position_with_quote(
                db,
                args["portfolio_id"],
                asset_code=args.get("asset_code"),
            )
        elif name == "get_dividends_summary":
            result = get_dividends_summary(
                db,
                args["portfolio_id"],
                period_months=int(args.get("period_months", 12)),
            )
        elif name == "get_concentration_analysis":
            result = get_concentration_analysis(db, args["portfolio_id"])
        elif name == "get_portfolio_performance":
            result = get_portfolio_performance(
                db,
                args["portfolio_id"],
                period_months=int(args.get("period_months", 12)),
            )
        elif name == "get_fixed_income_summary":
            result = get_fixed_income_summary(db, args["portfolio_id"])
        elif name == "get_portfolio_alerts":
            result = get_portfolio_alerts(db, args["portfolio_id"])
        elif name == "get_portfolio_equity_curve":
            result = get_portfolio_equity_curve(
                db,
                portfolio_id=args.get("portfolio_id"),
                from_month=args.get("from_month"),
                to_month=args.get("to_month"),
                period_months=int(args.get("period_months", 24)),
            )
        elif name == "list_members":
            result = list_members(db, only_active=args.get("only_active", True))
        elif name == "get_member":
            result = get_member(db, args["member_id"])
        elif name == "get_member_summary":
            result = get_member_summary(db, args["member_id"])
        elif name == "get_member_positions":
            result = get_member_positions(
                db,
                args["member_id"],
                open_only=args.get("open_only", True),
            )
        elif name == "get_member_operations":
            result = get_member_operations(
                db,
                args["member_id"],
                asset_code=args.get("asset_code"),
                operation_type=args.get("operation_type"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
                limit=int(args.get("limit", 100)),
            )
        elif name == "compare_members":
            result = compare_members(db, args["member_ids"])
        elif name == "transfer_portfolio_owner":
            result = transfer_portfolio_owner_tool(
                db, args["portfolio_id"], args["new_owner_id"]
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:  # noqa: BLE001
        result = {"error": str(exc)}
    finally:
        db.close()

    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ia-invest",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
