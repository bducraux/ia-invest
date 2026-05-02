"""MCP server tools package."""

from mcp_server.tools.app_settings import get_app_settings
from mcp_server.tools.concentration import get_concentration_analysis
from mcp_server.tools.dividends_summary import get_dividends_summary
from mcp_server.tools.fixed_income_summary import get_fixed_income_summary
from mcp_server.tools.irpf_report import get_irpf_report
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

__all__ = [
    "list_portfolios",
    "get_portfolio_summary",
    "get_portfolio_positions",
    "get_portfolio_operations",
    "compare_portfolios",
    "get_consolidated_summary",
    "get_app_settings",
    "get_position_with_quote",
    "get_dividends_summary",
    "get_concentration_analysis",
    "get_portfolio_performance",
    "get_fixed_income_summary",
    "get_portfolio_alerts",
    "get_irpf_report",
]
