"""Search tools router."""

from typing import Callable

from mcp.server.fastmcp import FastMCP

from ...knowledge import LITE_MODE
from ._lite import get_hitl_generation_prompt

keyword_search: Callable[..., str]
search_by_source: Callable[..., str]

if LITE_MODE:
    from ._lite import keyword_search, search_by_source  # type: ignore[no-redef]
else:
    from ._full import keyword_search, search_by_source  # type: ignore[no-redef]


def register_search_tools(mcp: FastMCP) -> None:
    """Register search tools with MCP server."""
    mcp.tool(description="Search ATX documentation using keyword search")(keyword_search)
    mcp.tool(description="Search filtered by source (dev-guide, sdk, api)")(search_by_source)
    mcp.tool(
        description="Get complete HITL UI generation rules. Call before generating domTreeJson."
    )(get_hitl_generation_prompt)
