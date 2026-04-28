"""Agent tools - granular registry operations."""

import json
import uuid
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..registry._client import registry_client


def register_agent_tools(mcp: FastMCP) -> None:
    """Register agent tools with MCP server."""
    mcp.tool(description="Retrieve an agent's metadata and visibility settings")(get_agent)
    mcp.tool(description="Return version-specific configuration for an agent")(get_agent_version)
    mcp.tool(description="Register a new agent with the ATX Agent Registry")(register_agent)
    mcp.tool(description="Publish a new version of an agent with its configuration")(
        publish_agent_version
    )
    mcp.tool(description="Update an agent's metadata")(update_agent)
    mcp.tool(description="List all agents registered by the caller")(list_agents_by_publisher)
    mcp.tool(description="List AWS account IDs with access to a RESTRICTED agent")(
        list_agent_access_control
    )
    mcp.tool(description="Enable or disable access for an AWS account to a RESTRICTED agent")(
        update_publisher_access_control
    )


def get_agent(name: str) -> str:
    """Retrieve an agent's metadata and visibility settings by name."""
    try:
        client = registry_client()
        response = client.get_agent(name=name)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_agent_version(name: str, version: Optional[str] = None) -> str:
    """Return version-specific configuration for an agent."""
    try:
        client = registry_client()
        kwargs: dict[str, Any] = {"name": name}
        if version:
            kwargs["version"] = version
        response = client.get_agent_version(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def register_agent(
    name: str,
    metadata: dict[str, Any],
) -> str:
    """Register a new agent with the ATX Agent Registry."""
    try:
        client = registry_client()
        response = client.register_agent(
            name=name,
            metadata=metadata,
            idempotencyToken=str(uuid.uuid4()),
        )
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def publish_agent_version(
    name: str,
    version: str,
    configuration: dict[str, Any],
) -> str:
    """Publish a new version of an agent with its configuration."""
    try:
        client = registry_client()
        response = client.publish_agent_version(
            name=name,
            version=version,
            configuration=configuration,
            idempotencyToken=str(uuid.uuid4()),
        )
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def update_agent(
    name: str,
    customer_configured_agent_dependencies: Optional[list[str]] = None,
    marketplace_metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Update an agent's metadata."""
    try:
        client = registry_client()
        kwargs: dict[str, Any] = {"name": name}
        if customer_configured_agent_dependencies is not None:
            kwargs["customerConfiguredAgentDependencies"] = customer_configured_agent_dependencies
        if marketplace_metadata is not None:
            kwargs["marketplaceMetadata"] = marketplace_metadata
        response = client.update_agent(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_agents_by_publisher() -> str:
    """List all agents registered by the caller."""
    try:
        client = registry_client()
        response = client.list_agents_by_publisher()
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_agent_access_control(
    name: str,
    max_results: Optional[int] = None,
    next_token: Optional[str] = None,
) -> str:
    """List AWS account IDs that have been granted access to a RESTRICTED agent."""
    try:
        client = registry_client()
        kwargs: dict[str, Any] = {"name": name}
        if max_results is not None:
            kwargs["maxResults"] = max_results
        if next_token is not None:
            kwargs["nextToken"] = next_token
        response = client.list_agent_access_control(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def update_publisher_access_control(
    agent_name: str,
    customer_account_id: str,
    access_control: str,
) -> str:
    """Enable or disable access for an AWS account to a RESTRICTED agent."""
    try:
        client = registry_client()
        response = client.update_publisher_access_control(
            agentName=agent_name,
            customerAccountId=customer_account_id,
            accessControl=access_control,
            idempotencyToken=str(uuid.uuid4()),
        )
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
