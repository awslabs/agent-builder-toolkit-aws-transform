# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the SubagentRegistryTools class."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agent_builder_sdk.custom_types.agent_registry_types import (
    AgentType,
    GetAgentVersionOutput,
    VersionStatus,
)
from agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools import (
    SubagentRegistryTools,
    _get_mock_subagents,
    _parse_agent_version_output,
)


@pytest.fixture
def subagent_registry_tools():
    """Create a SubagentRegistryTools instance."""
    return SubagentRegistryTools()


class TestMockRegistry:
    """Tests for the dev-mode mock registry path."""

    @patch.dict(os.environ, {"ATX_USE_MOCK_REGISTRY": "true"})
    @pytest.mark.asyncio
    async def test_discover_subagents_returns_mock_when_flag_set(self, subagent_registry_tools):
        """When ATX_USE_MOCK_REGISTRY=true, returns fixture data without calling the API."""
        result = _get_mock_subagents()

        assert isinstance(result, list)
        assert len(result) == 1
        mock_agent = result[0]
        assert isinstance(mock_agent, GetAgentVersionOutput)
        assert mock_agent.version == "1.0.0"
        assert mock_agent.metadata.type == AgentType.SUB_AGENT
        assert mock_agent.configuration.agent_card.name == "dynamic-showcase-subagent"
        assert mock_agent.status == VersionStatus.ACTIVE

    def test_mock_subagents_has_required_fields(self):
        """Verify mock agent has all required fields for LLM consumption."""
        result = _get_mock_subagents()
        mock_agent = result[0]
        assert mock_agent.version
        assert mock_agent.metadata
        assert mock_agent.configuration
        assert mock_agent.status
        assert mock_agent.visibility
        assert mock_agent.configuration.agent_card.skills


class TestRealRegistry:
    """Tests for the live registry path (with mocked boto3 client)."""

    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools._USE_MOCK_REGISTRY", False)
    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.get_agent_context_from_env")
    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.get_agentic_api_client")
    @pytest.mark.asyncio
    async def test_discover_subagents_calls_api(
        self, mock_get_client, mock_get_context, subagent_registry_tools
    ):
        """Real path calls list_agent_instances and parses response."""
        mock_context = MagicMock()
        mock_context.agent_instance_id = "orch-123"
        mock_context.job_id = "job-456"
        mock_context.workspace_id = "ws-789"
        mock_context.authorization_token = "token-abc"
        mock_get_context.return_value = mock_context

        mock_client = MagicMock()
        mock_client.list_agent_instances.return_value = {
            "agentInstanceSummaries": [
                {
                    "agentType": "SUB_AGENT",
                    "agentName": "my-subagent",
                    "agentVersion": "2.0.0",
                    "agentInstanceStatus": "ACTIVE",
                    "description": "Test subagent",
                    "ownerName": "TEST_TEAM",
                    "ownerAccountId": "111222333444",
                    "ownerContactInfo": "test@example.com",
                    "visibility": "PUBLIC",
                    "shortDescription": "Test subagent short",
                },
                {
                    "agentType": "ORCHESTRATOR_AGENT",
                    "agentName": "other-orch",
                    "agentVersion": "1.0.0",
                    "agentInstanceStatus": "ACTIVE",
                },
            ]
        }
        mock_get_client.return_value = mock_client

        result = await subagent_registry_tools.discover_subagents()

        assert len(result) == 1
        agent = result[0]
        assert agent.configuration.agent_card.name == "my-subagent"
        assert agent.version == "2.0.0"
        assert agent.metadata.type == AgentType.SUB_AGENT

    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools._USE_MOCK_REGISTRY", False)
    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.get_agent_context_from_env")
    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.get_agentic_api_client")
    @pytest.mark.asyncio
    async def test_discover_subagents_empty_response(
        self, mock_get_client, mock_get_context, subagent_registry_tools
    ):
        """Returns empty list when no subagents are registered."""
        mock_context = MagicMock()
        mock_context.agent_instance_id = "orch-123"
        mock_context.job_id = "job-456"
        mock_context.workspace_id = "ws-789"
        mock_context.authorization_token = "token-abc"
        mock_get_context.return_value = mock_context

        mock_client = MagicMock()
        mock_client.list_agent_instances.return_value = {"agentInstanceSummaries": []}
        mock_get_client.return_value = mock_client

        result = await subagent_registry_tools.discover_subagents()
        assert result == []

    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools._USE_MOCK_REGISTRY", False)
    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.get_agent_context_from_env")
    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.get_agentic_api_client")
    @pytest.mark.asyncio
    async def test_discover_subagents_api_error_raises(
        self, mock_get_client, mock_get_context, subagent_registry_tools
    ):
        """API errors propagate as exceptions."""
        mock_context = MagicMock()
        mock_context.agent_instance_id = "orch-123"
        mock_context.job_id = "job-456"
        mock_context.workspace_id = "ws-789"
        mock_context.authorization_token = "token-abc"
        mock_get_context.return_value = mock_context

        mock_client = MagicMock()
        mock_client.list_agent_instances.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="Subagent registry operation failed"):
            await subagent_registry_tools.discover_subagents()


class TestParseAgentVersionOutput:
    """Tests for _parse_agent_version_output helper."""

    def test_parses_full_response(self):
        """Parse a complete API response into typed dataclass."""
        raw = {
            "version": "3.1.0",
            "status": "ACTIVE",
            "visibility": "PUBLIC",
            "metadata": {
                "type": "SUB_AGENT",
                "description": "Analysis agent",
                "ownerName": "TEAM_X",
                "ownerAccountId": "999888777666",
                "ownerContactInfo": "teamx@example.com",
            },
            "configuration": {
                "shortDescription": "Analyzes things",
                "monitoringType": "HEARTBEAT",
                "notificationsEnabled": "DISABLED",
                "agentCard": {
                    "name": "analysis-agent",
                    "description": "Does analysis",
                    "version": "3.1.0",
                    "url": "https://example.com",
                    "skills": [
                        {
                            "id": "s1",
                            "name": "analyze",
                            "description": "Runs analysis",
                            "tags": ["ml"],
                        }
                    ],
                    "capabilities": {"pushNotifications": True, "streaming": True},
                    "provider": {"organization": "TeamX", "url": "https://teamx.com"},
                },
            },
        }
        result = _parse_agent_version_output(raw)
        assert result.version == "3.1.0"
        assert result.metadata.owner_name == "TEAM_X"
        assert result.configuration.agent_card.skills[0].name == "analyze"
        assert result.configuration.agent_card.capabilities.streaming is True

    def test_handles_minimal_response(self):
        """Parses gracefully when optional fields are missing."""
        raw = {"version": "1.0.0", "status": "ACTIVE"}
        result = _parse_agent_version_output(raw)
        assert result.version == "1.0.0"
        assert result.metadata.description == ""
        assert result.configuration.agent_card.skills == []
