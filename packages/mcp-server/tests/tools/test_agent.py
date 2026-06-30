# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for agent registry tools."""

import json
from unittest.mock import MagicMock, patch

from agent_builder_mcp.tools.agent import deregister_agent, update_agent

MODULE = "agent_builder_mcp.tools.agent"


class TestDeregisterAgent:
    """Tests for the deregister_agent tool."""

    def test_deregister_agent_success(self):
        """Test successful deregistration returns DEREGISTERED status."""
        mock_client = MagicMock()
        mock_client.deregister_agent.return_value = {
            "deregistrationStatus": "DEREGISTERED",
        }

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deregister_agent(name="test-agent", force=True))

        assert result["deregistrationStatus"] == "DEREGISTERED"
        mock_client.deregister_agent.assert_called_once_with(name="test-agent", force=True)

    def test_deregister_agent_without_force(self):
        """Test deregistration without force flag."""
        mock_client = MagicMock()
        mock_client.deregister_agent.return_value = {
            "deregistrationStatus": "DEREGISTERED",
        }

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deregister_agent(name="test-agent"))

        assert result["deregistrationStatus"] == "DEREGISTERED"
        mock_client.deregister_agent.assert_called_once_with(name="test-agent")

    def test_deregister_agent_in_progress(self):
        """Test deregistration with active instances returns IN_PROGRESS."""
        mock_client = MagicMock()
        mock_client.deregister_agent.return_value = {
            "deregistrationStatus": "DEREGISTRATION_IN_PROGRESS",
        }

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deregister_agent(name="test-agent", force=True))

        assert result["deregistrationStatus"] == "DEREGISTRATION_IN_PROGRESS"

    def test_deregister_agent_not_found(self):
        """Test deregistration of non-existent agent returns error."""
        mock_client = MagicMock()
        mock_client.deregister_agent.side_effect = Exception("Agent not-exist does not exist")

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deregister_agent(name="not-exist", force=True))

        assert "error" in result
        assert "does not exist" in result["error"]

    def test_deregister_agent_access_denied(self):
        """Test deregistration of agent owned by different account returns error."""
        mock_client = MagicMock()
        mock_client.deregister_agent.side_effect = Exception("Access denied")

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deregister_agent(name="other-agent", force=True))

        assert "error" in result
        assert "Access denied" in result["error"]


class TestUpdateAgent:
    """Tests for the update_agent tool."""

    def test_update_agent_description(self):
        """Test updating agent description."""
        mock_client = MagicMock()
        mock_client.update_agent.return_value = {}

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(update_agent(name="test-agent", description="New description"))

        mock_client.update_agent.assert_called_once_with(
            name="test-agent", description="New description"
        )

    def test_update_agent_multiple_fields(self):
        """Test updating multiple fields at once."""
        mock_client = MagicMock()
        mock_client.update_agent.return_value = {}

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(
                update_agent(
                    name="test-agent",
                    description="Updated",
                    owner_name="NewTeam",
                    deprecated=True,
                    owner_contact_info="team@amazon.com",
                )
            )

        mock_client.update_agent.assert_called_once_with(
            name="test-agent",
            description="Updated",
            ownerName="NewTeam",
            deprecated=True,
            ownerContactInfo="team@amazon.com",
        )

    def test_update_agent_job_orchestrator(self):
        """Test updating job orchestrator fields."""
        mock_client = MagicMock()
        mock_client.update_agent.return_value = {}
        metadata = {
            "chatUILabel": "My Agent",
            "chatAgentIdentifier": "my-agent-id",
            "a2aSupported": True,
        }

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(
                update_agent(
                    name="test-agent",
                    job_orchestrator=True,
                    job_orchestrator_metadata=metadata,
                )
            )

        mock_client.update_agent.assert_called_once_with(
            name="test-agent",
            jobOrchestrator=True,
            jobOrchestratorMetadata=metadata,
        )

    def test_update_agent_only_name_no_optional_fields(self):
        """Test calling update with only name passes minimal kwargs."""
        mock_client = MagicMock()
        mock_client.update_agent.return_value = {}

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(update_agent(name="test-agent"))

        mock_client.update_agent.assert_called_once_with(name="test-agent")

    def test_update_agent_error(self):
        """Test update agent error handling."""
        mock_client = MagicMock()
        mock_client.update_agent.side_effect = Exception("Validation failed")

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(update_agent(name="test-agent", description="x" * 501))

        assert "error" in result
        assert "Validation failed" in result["error"]
