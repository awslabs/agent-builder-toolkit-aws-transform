"""Subagent registry tools for Strands agents.

This module provides tools to interact with the ATX platform's subagent registry
to retrieve information about registered subagents.
"""

import logging
from typing import List

from strands.tools import tool

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

logger = logging.getLogger(__name__)


class SubagentRegistryTools:
    """Subagent registry tools for fetching subagents registered with ATX platform."""

    def __init__(self):
        """Initialize the subagent registry tools."""
        logger.info("Initialized SubagentRegistryTools")

    @tool
    async def discover_subagents(self) -> List[GetAgentVersionOutput]:
        """Get the list of subagents registered with the ATX platform.

        Returns:
            List[GetAgentVersionOutput]: Version information of subagents registered with the ATX platform
        """
        try:
            # Mock implementation - will be replaced with the actual API call
            mock_metadata = AgentMetadata(
                type=AgentType.SUB_AGENT,
                description="A subagent for weather related tasks",
                owner_name="DYNAMIC_SHOWCASE",
                owner_account_id="123456789012",
                owner_contact_info="mock@example.com",
            )

            mock_agent_card = AgentCard(
                name="dynamic-showcase-subagent",
                description="A subagent for weather related tasks. This agent can get up to date weather forecasts and make forecast predictions for any city in the world.",
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

            # Mock implementation - actual will add compute configuration, input/output payload schema
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

        except Exception as e:
            logger.error(f"Subagent registry operation error: {e}")
            raise Exception(f"Subagent registry operation failed: {str(e)}")
