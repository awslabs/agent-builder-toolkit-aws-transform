"""Agent deployment tools."""

from mcp.server.fastmcp import FastMCP

from ._build import build_agent_image
from ._deploy import deploy_agent_to_agentcore
from ._pipeline import deploy_agent_full_pipeline


def register_deployment_tools(mcp: FastMCP) -> None:
    """Register agent deployment tools with MCP server."""
    mcp.tool(
        description=(
            "Build ATX agent Docker image for ARM64 platform. "
            "Supports three build methods: local finch (preferred), local docker (fallback), "
            "or AWS CodeBuild (required for Windows, optional for others). "
            "Automatically detects best runtime for current platform."
        )
    )(build_agent_image)

    mcp.tool(
        description=(
            "Deploy agent image to Bedrock AgentCore and poll until ACTIVE. "
            "Creates AgentCore runtime and monitors deployment status."
        )
    )(deploy_agent_to_agentcore)

    mcp.tool(
        description=(
            "Complete deployment pipeline: build → push → deploy → register. "
            "Orchestrates all phases for full agent deployment to ATX platform."
        )
    )(deploy_agent_full_pipeline)
