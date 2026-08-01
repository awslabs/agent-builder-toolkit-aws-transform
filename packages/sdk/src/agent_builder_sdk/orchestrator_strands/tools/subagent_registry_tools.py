# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Subagent registry tools for Strands agents.

This module provides tools to interact with the ATX platform's subagent registry
to retrieve information about registered subagents.
"""

import logging
import os
from typing import List

from strands.tools import tool

from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.agent_registry_types import (
    AgentCapabilities,
    AgentCard,
    AgentConfiguration,
    AgentMetadata,
    AgentProvider,
    AgentSkill,
    AgentType,
    AgentVisibility,
    GetAgentVersionOutput,
    MonitoringType,
    NotificationStatus,
    VersionStatus,
)
from agent_builder_sdk.env_var import get_agent_context_from_env

logger = logging.getLogger(__name__)

_USE_MOCK_REGISTRY = os.environ.get("ATX_USE_MOCK_REGISTRY", "").lower() in ("true", "1", "yes")


def _parse_agent_version_output(raw: dict) -> GetAgentVersionOutput:
    """Parse raw API response dict into GetAgentVersionOutput."""
    metadata_raw = raw.get("metadata", {})
    metadata = AgentMetadata(
        type=AgentType(metadata_raw.get("type", "SUB_AGENT")),
        description=metadata_raw.get("description", ""),
        owner_name=metadata_raw.get("ownerName", ""),
        owner_account_id=metadata_raw.get("ownerAccountId", ""),
        owner_contact_info=metadata_raw.get("ownerContactInfo", ""),
    )

    config_raw = raw.get("configuration", {})
    card_raw = config_raw.get("agentCard", {})
    skills = [
        AgentSkill(
            id=s.get("id", ""),
            name=s.get("name", ""),
            description=s.get("description", ""),
            tags=s.get("tags", []),
            examples=s.get("examples"),
            input_modes=s.get("inputModes"),
            output_modes=s.get("outputModes"),
        )
        for s in card_raw.get("skills", [])
    ]
    caps_raw = card_raw.get("capabilities", {})
    capabilities = AgentCapabilities(
        extensions=None,
        push_notifications=caps_raw.get("pushNotifications"),
        state_transition_history=caps_raw.get("stateTransitionHistory"),
        streaming=caps_raw.get("streaming"),
    )
    provider_raw = card_raw.get("provider")
    provider = (
        AgentProvider(
            organization=provider_raw.get("organization", ""),
            url=provider_raw.get("url", ""),
        )
        if provider_raw
        else None
    )
    agent_card = AgentCard(
        name=card_raw.get("name", raw.get("name", "")),
        description=card_raw.get("description", ""),
        version=card_raw.get("version", raw.get("version", "")),
        url=card_raw.get("url", ""),
        skills=skills,
        capabilities=capabilities,
        provider=provider,
    )
    configuration = AgentConfiguration(
        short_description=config_raw.get("shortDescription", ""),
        status=VersionStatus(config_raw.get("status", raw.get("status", "ACTIVE"))),
        agent_card=agent_card,
        monitoring_type=MonitoringType(config_raw.get("monitoringType", "HEALTHCHECK")),
        notifications_enabled=NotificationStatus(
            config_raw.get("notificationsEnabled", "ENABLED")
        ),
        input_payload_schema=config_raw.get("inputPayloadSchema"),
        output_payload_schema=config_raw.get("outputPayloadSchema"),
        objective_negotiation_prompt=config_raw.get("objectiveNegotiationPrompt"),
    )

    return GetAgentVersionOutput(
        version=raw.get("version", ""),
        metadata=metadata,
        visibility=AgentVisibility(raw.get("visibility", "RESTRICTED")),
        configuration=configuration,
        status=VersionStatus(raw.get("status", "ACTIVE")),
    )


def _get_mock_subagents() -> List[GetAgentVersionOutput]:
    """Return dev fixture data. Only used when ATX_USE_MOCK_REGISTRY=true."""
    mock_metadata = AgentMetadata(
        type=AgentType.SUB_AGENT,
        description="A subagent for weather related tasks",
        owner_name="DYNAMIC_SHOWCASE",
        owner_account_id="123456789012",
        owner_contact_info="mock@example.com",
    )
    mock_agent_card = AgentCard(
        name="dynamic-showcase-subagent",
        description=(
            "A subagent for weather related tasks. This agent can get up to date "
            "weather forecasts and make forecast predictions for any city in the world."
        ),
        version="1.0.0",
        url="https://mock-subagent.example.com",
        skills=[
            AgentSkill(
                id="weather_1",
                name="get_forecast",
                description="The skill to fetch the daily, weekly, 10-day weather forecast for the given city",
                tags=["forecast"],
            )
        ],
        capabilities=AgentCapabilities(push_notifications=True, streaming=False),
        provider=AgentProvider(
            organization="ATX Foundation Partner",
            url="https://mock-atx-foundation-partner.amazon.com",
        ),
    )
    mock_config = AgentConfiguration(
        short_description="Mock subagent",
        status=VersionStatus.ACTIVE,
        agent_card=mock_agent_card,
        monitoring_type=MonitoringType.HEALTHCHECK,
        notifications_enabled=NotificationStatus.ENABLED,
    )
    return [
        GetAgentVersionOutput(
            version="1.0.0",
            metadata=mock_metadata,
            visibility=AgentVisibility.PUBLIC,
            configuration=mock_config,
            status=VersionStatus.ACTIVE,
        )
    ]


class SubagentRegistryTools:
    """Subagent registry tools for fetching subagents registered with ATX platform."""

    def __init__(self):
        """Initialize the subagent registry tools."""
        logger.info("Initialized SubagentRegistryTools")

    @tool
    async def discover_subagents(self) -> List[GetAgentVersionOutput]:
        """Get the list of subagents registered with the ATX platform.

        Calls the Agentic API's ListAgentInstances endpoint filtered to SUB_AGENT types,
        then enriches with registry metadata. Falls back to mock data when
        ATX_USE_MOCK_REGISTRY=true (for local development without platform connectivity).

        Returns:
            List[GetAgentVersionOutput]: Version information of subagents registered with the ATX platform
        """
        if _USE_MOCK_REGISTRY:
            logger.warning("Using mock registry data (ATX_USE_MOCK_REGISTRY=true)")
            return _get_mock_subagents()

        try:
            client = get_agentic_api_client()
            context = get_agent_context_from_env()

            request_data = {
                "agentFilter": {
                    "requesterAgentInstanceId": context.agent_instance_id,
                },
                "requestContext": {
                    "jobMetadata": {
                        "jobId": context.job_id,
                        "workspaceId": context.workspace_id,
                    },
                    "agentInstanceId": context.agent_instance_id,
                    "authorizationToken": context.authorization_token,
                },
            }
            response = client.list_agent_instances(**request_data)
            summaries = response.get("agentInstanceSummaries", [])

            subagent_summaries = [
                s for s in summaries if s.get("agentType") == "SUB_AGENT"
            ]

            results: List[GetAgentVersionOutput] = []
            for summary in subagent_summaries:
                agent_name = summary.get("agentName", summary.get("agentId", ""))
                results.append(
                    GetAgentVersionOutput(
                        version=summary.get("agentVersion", "unknown"),
                        metadata=AgentMetadata(
                            type=AgentType.SUB_AGENT,
                            description=summary.get("description", ""),
                            owner_name=summary.get("ownerName", ""),
                            owner_account_id=summary.get("ownerAccountId", ""),
                            owner_contact_info=summary.get("ownerContactInfo", ""),
                        ),
                        visibility=AgentVisibility(
                            summary.get("visibility", "RESTRICTED")
                        ),
                        configuration=AgentConfiguration(
                            short_description=summary.get("shortDescription", agent_name),
                            status=VersionStatus(
                                summary.get("agentInstanceStatus", "ACTIVE")
                            ),
                            agent_card=AgentCard(
                                name=agent_name,
                                description=summary.get("description", ""),
                                version=summary.get("agentVersion", "unknown"),
                                url="",
                                skills=[],
                                capabilities=AgentCapabilities(),
                            ),
                            monitoring_type=MonitoringType.HEALTHCHECK,
                            notifications_enabled=NotificationStatus.ENABLED,
                        ),
                        status=VersionStatus(
                            summary.get("agentInstanceStatus", "ACTIVE")
                        ),
                    )
                )

            logger.info(f"Discovered {len(results)} subagent(s) from registry")
            return results

        except Exception as e:
            logger.error(f"Subagent registry operation error: {e}")
            raise Exception(f"Subagent registry operation failed: {str(e)}")
