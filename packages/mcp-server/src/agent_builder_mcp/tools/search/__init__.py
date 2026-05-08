# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
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
    mcp.tool(
        description=(
            "Search AWS Transform documentation using keyword matching. "
            "Returns previews with source file paths (file/module) when available. "
            "Tips: use class names (BaseAgent, HitlClient), API operation names "
            "(RegisterAgent, DeployAgent), split compound queries into separate calls."
        )
    )(keyword_search)
    mcp.tool(
        description=(
            "Search AWS Transform docs filtered by source. "
            "Valid sources: dev-guide, sdk, agentic-api, registry-api, "
            "hitl-sdk-python, hitl-sdk-java, hitl-component-library, "
            "hitl-common-patterns, hitl-custom-components, hitl-validation, "
            "hitl-generation-rules, hitl-agent-integration, hitl-architecture, "
            "hitl-render-limitations. "
            "Returns previews with source file paths (file/module) when available."
        )
    )(search_by_source)
    mcp.tool(
        description="Get complete HITL UI generation rules. Call before generating domTreeJson."
    )(get_hitl_generation_prompt)
