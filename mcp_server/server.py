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

from mcp_server.tools.portfolios import (
    compare_portfolios,
    get_consolidated_summary,
    get_portfolio_operations,
    get_portfolio_positions,
    get_portfolio_summary,
    list_portfolios,
)
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
            description="Get a consolidated view across all active portfolios.",
            inputSchema={"type": "object", "properties": {}, "required": []},
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
            result = get_consolidated_summary(db)
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
