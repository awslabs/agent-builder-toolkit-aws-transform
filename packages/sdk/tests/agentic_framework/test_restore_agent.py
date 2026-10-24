# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import tempfile
from unittest import mock

import pytest

from agent_builder_sdk.agentic_framework.agent_lifecycle import restore_agent


@pytest.fixture
def mock_env(monkeypatch):
    """Set up auth token file for tests."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("ATX_AUTHZ_TOKEN=test-token")
        auth_file_path = f.name
    monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)


class TestRestoreAgent:
    """Test cases for restore_agent function."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_restore_agent_success(self, mock_get_manager, mock_env):
        """Test successful restore_agent call."""
        mock_manager = mock.Mock()
        mock_manager.restore.return_value = {}
        mock_get_manager.return_value = mock_manager

        restore_agent(
            workspace_id="ws-123",
            job_id="job-456",
            agent_instance_id="inst-789",
            agent_id="my-agent",
            agent_type="ORCHESTRATOR_AGENT",
        )

        mock_get_manager.assert_called_once_with("ws-123", "job-456", "inst-789")
        mock_manager.restore.assert_called_once_with("my-agent", "ORCHESTRATOR_AGENT")

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_restore_agent_api_failure_raises(self, mock_get_manager, mock_env):
        """Test restore_agent propagates exceptions from the API."""
        mock_manager = mock.Mock()
        mock_manager.restore.side_effect = Exception("Service unavailable")
        mock_get_manager.return_value = mock_manager

        with pytest.raises(Exception, match="Service unavailable"):
            restore_agent(
                workspace_id="ws-123",
                job_id="job-456",
                agent_instance_id="inst-789",
                agent_id="my-agent",
                agent_type="ORCHESTRATOR_AGENT",
            )

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_restore_agent_idempotency_token_is_unique(self, mock_get_manager, mock_env):
        """Test each restore call generates a unique idempotency token."""
        mock_manager = mock.Mock()
        mock_manager.restore.return_value = {}
        mock_get_manager.return_value = mock_manager

        restore_agent(
            workspace_id="ws-123",
            job_id="job-456",
            agent_instance_id="inst-789",
            agent_id="my-agent",
            agent_type="ORCHESTRATOR_AGENT",
        )

        restore_agent(
            workspace_id="ws-123",
            job_id="job-456",
            agent_instance_id="inst-789",
            agent_id="my-agent",
            agent_type="ORCHESTRATOR_AGENT",
        )

        # Verify restore was called twice
        assert mock_manager.restore.call_count == 2
