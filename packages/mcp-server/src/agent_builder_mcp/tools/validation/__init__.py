# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validation tools."""

import json

from mcp.server.fastmcp import FastMCP

from ..registry._client import registry_client


def register_validation_tools(mcp: FastMCP) -> None:
    """Register validation tools with MCP server."""
    mcp.tool(description="Validate that an agent version is correctly set up and reachable")(
        validate_agent_setup
    )


def validate_agent_setup(agent_name: str, agent_version: str) -> str:
    """Validate that an agent version is correctly set up and reachable."""
    try:
        client = registry_client()
        response = client.validate_agent_setup(
            agentName=agent_name,
            agentVersion=agent_version,
        )
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
