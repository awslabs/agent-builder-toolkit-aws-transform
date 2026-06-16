# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Agent tools - granular registry operations."""

import json
import logging
import uuid
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..registry._client import registry_client

logger = logging.getLogger(__name__)


def _default_a2a(container: dict[str, Any], path: str) -> list[str]:
    """Apply the missing→true / false→warn policy to a single container.

    Mutates ``container`` in place when ``a2aSupported`` is absent or
    explicitly ``None`` (both treated as missing). Returns warning strings
    (also logged at WARNING level) for the caller to surface. Non-bool
    values other than ``None``/``False`` (e.g. ``0``, ``""``) are left
    unchanged so the registry's own schema validation rejects them.
    """
    a2a = container.get("a2aSupported")
    if a2a is None:
        container["a2aSupported"] = True
        msg = (
            f"{path} was missing; defaulted to true. "
            "Required for chat routing in the AWS Transform webapp."
        )
    elif a2a is False:
        msg = (
            f"{path} is false. The AWS Transform webapp will not chat with "
            "this agent. Set a2aSupported=true unless this is intentionally "
            "a non-chat agent."
        )
    else:
        return []
    logger.warning(msg)
    return [msg]


def _ensure_orchestrator_a2a(metadata: dict[str, Any]) -> list[str]:
    """Default and validate `a2aSupported` in registration metadata.

    The AWS Transform webapp only routes chat traffic to orchestrators whose
    `jobOrchestratorMetadata.a2aSupported` is true. Once registered the field
    cannot be changed (UpdateAgent does not accept jobOrchestratorMetadata),
    so getting it wrong forces re-registering under a new agent name.

    When `jobOrchestrator` is true and `jobOrchestratorMetadata` is present,
    apply the missing→true / false→warn policy. Does NOT synthesize a
    missing `jobOrchestratorMetadata` block: that block also requires
    `chatUILabel` and `chatAgentIdentifier`, and inventing those would
    produce a registration the server rejects. Let the registry surface
    that case via its own validation.
    """
    job_meta = metadata.get("jobOrchestratorMetadata")
    if not metadata.get("jobOrchestrator") or not isinstance(job_meta, dict):
        return []
    return _default_a2a(job_meta, "jobOrchestratorMetadata.a2aSupported")


def _ensure_capabilities_a2a(configuration: dict[str, Any]) -> list[str]:
    """Default and validate `a2aSupported` in a publish-version agentCard.

    The agentCard's `capabilities.a2aSupported` is a separate field from
    the registration metadata's `jobOrchestratorMetadata.a2aSupported`,
    but has the same chat-routing implication. Same policy: missing → true,
    explicit false → warn.
    """
    agent_card = configuration.get("agentCard")
    if not isinstance(agent_card, dict):
        return []
    capabilities = agent_card.get("capabilities")
    if not isinstance(capabilities, dict):
        return []
    return _default_a2a(capabilities, "agentCard.capabilities.a2aSupported")


def _attach_warnings(response: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Merge advisory warnings into a response under `_warnings`.

    Preserves any pre-existing `_warnings` by concatenation. Returns the
    input unchanged when ``warnings`` is empty.
    """
    if not warnings:
        return response
    merged = dict(response)
    merged["_warnings"] = [*(merged.get("_warnings") or []), *warnings]
    return merged


def register_agent_tools(mcp: FastMCP) -> None:
    """Register agent tools with MCP server."""
    mcp.tool(description="Retrieve an agent's metadata and visibility settings")(get_agent)
    mcp.tool(description="Return version-specific configuration for an agent")(get_agent_version)
    mcp.tool(
        description=(
            "Register a new agent with the AWS Transform Agent Registry. "
            "For orchestrators, defaults missing "
            "jobOrchestratorMetadata.a2aSupported to true."
        )
    )(register_agent)
    mcp.tool(
        description=(
            "Publish a new version of an agent with its configuration. "
            "Defaults missing agentCard.capabilities.a2aSupported to true."
        )
    )(publish_agent_version)
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
    """Register a new agent with the AWS Transform Agent Registry.

    For orchestrators (``jobOrchestrator: true``) with a present
    ``jobOrchestratorMetadata`` block, defaults a missing ``a2aSupported``
    to ``true`` so the AWS Transform webapp can chat with the registered
    agent. An explicit ``false`` is preserved but flagged in the response.
    """
    warnings = _ensure_orchestrator_a2a(metadata)
    try:
        response = registry_client().register_agent(
            name=name,
            metadata=metadata,
            idempotencyToken=str(uuid.uuid4()),
        )
        return json.dumps(_attach_warnings(response, warnings), indent=2, default=str)
    except Exception as e:
        return json.dumps(_attach_warnings({"error": str(e)}, warnings))


def publish_agent_version(
    name: str,
    version: str,
    configuration: dict[str, Any],
) -> str:
    """Publish a new version of an agent with its configuration.

    Defaults a missing ``configuration.agentCard.capabilities.a2aSupported``
    to ``true`` so the AWS Transform webapp will chat with this version.
    An explicit ``false`` is preserved but flagged in the response. Note:
    this field is independent of the registration metadata's
    ``jobOrchestratorMetadata.a2aSupported`` set at ``register_agent`` time.
    """
    warnings = _ensure_capabilities_a2a(configuration)
    try:
        response = registry_client().publish_agent_version(
            name=name,
            version=version,
            configuration=configuration,
            idempotencyToken=str(uuid.uuid4()),
        )
        return json.dumps(_attach_warnings(response, warnings), indent=2, default=str)
    except Exception as e:
        return json.dumps(_attach_warnings({"error": str(e)}, warnings))


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
