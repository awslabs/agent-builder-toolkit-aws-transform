import tempfile
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    AgentInstanceManager,
    get_agent_instance_manager,
    get_agent_instance_manager_with_context,
    get_agent_status,
    get_subagent_instances,
    initialize_agent_instance,
    initialize_base_orchestrator_agent_instance,
    set_agent_running,
    shutdown_base_orchestrator_agent_instance,
    shutdown_subagent_instance,
    wait_for_agent_non_invoking,
)


@pytest.fixture
def agent_instance_manager(monkeypatch):
    """Test fixture for AgentInstanceManager."""
    # Create temporary auth token file
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("ATX_AUTHZ_TOKEN=test-token")
        auth_file_path = f.name

    # Mock the environment variable
    monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)

    mock_client = mock.Mock()
    return AgentInstanceManager(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        client=mock_client,
    )


class TestAgentInstanceManager:
    """Test cases for AgentInstanceManager class."""

    def test_get_status_success(self, agent_instance_manager):
        """Test successful get_status operation."""
        expected_response = {"agentInstanceId": "test-agent", "status": "RUNNING"}
        agent_instance_manager.client.get_agent_instance.return_value = expected_response

        result = agent_instance_manager.get_status("test-agent")

        assert result == expected_response
        agent_instance_manager.client.get_agent_instance.assert_called_once()

        # Verify the request structure
        call_args = agent_instance_manager.client.get_agent_instance.call_args[1]
        assert call_args["agentInstanceId"] == "test-agent"
        assert "authorizationToken" in call_args["requestContext"]
        assert "jobMetadata" in call_args["requestContext"]

    def test_get_status_client_error(self, agent_instance_manager):
        """Test get_status with client error."""
        agent_instance_manager.client.get_agent_instance.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="get_agent_instance",
        )

        with pytest.raises(ClientError):
            agent_instance_manager.get_status("test-agent")

    def test_update_status_success(self, agent_instance_manager):
        """Test successful status update."""
        expected_response = {"agentInstanceId": "test-agent", "status": "RUNNING"}
        agent_instance_manager.client.update_agent_instance.return_value = expected_response

        result = agent_instance_manager.update_status("test-agent", "RUNNING")

        assert result == expected_response
        agent_instance_manager.client.update_agent_instance.assert_called_once()

        # Verify the request structure
        call_args = agent_instance_manager.client.update_agent_instance.call_args[1]
        assert call_args["agentInstanceId"] == "test-agent"
        assert call_args["agentInstanceStatus"] == "RUNNING"
        assert "authorizationToken" in call_args["requestContext"]
        assert "jobMetadata" in call_args["requestContext"]

    def test_update_status_with_reason_and_output(self, agent_instance_manager):
        """Test status update with reason and output."""
        expected_response = {"agentInstanceId": "test-agent", "status": "FAILED"}
        agent_instance_manager.client.update_agent_instance.return_value = expected_response

        result = agent_instance_manager.update_status(
            "test-agent", "FAILED", status_reason="Test failure", agent_output="Error details"
        )

        assert result == expected_response
        call_args = agent_instance_manager.client.update_agent_instance.call_args[1]
        assert call_args["agentInstanceStatusReason"] == "Test failure"
        assert call_args["agentOutput"] == "Error details"

    def test_update_status_client_error(self, agent_instance_manager):
        """Test status update with client error."""
        agent_instance_manager.client.update_agent_instance.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="update_agent_instance",
        )

        with pytest.raises(ClientError):
            agent_instance_manager.update_status("test-agent", "RUNNING")

    def test_set_running(self, agent_instance_manager):
        """Test set_running method."""
        expected_response = {"agentInstanceId": "test-agent", "status": "RUNNING"}
        agent_instance_manager.client.update_agent_instance.return_value = expected_response

        result = agent_instance_manager.set_running("test_agent")

        assert result == expected_response
        call_args = agent_instance_manager.client.update_agent_instance.call_args[1]
        assert call_args["agentInstanceStatus"] == "RUNNING"

    def test_set_stopped(self, agent_instance_manager):
        """Test set_stopped method."""
        expected_response = {"agentInstanceId": "test-agent", "status": "STOPPED"}
        agent_instance_manager.client.update_agent_instance.return_value = expected_response

        result = agent_instance_manager.set_stopped("test-agent", "Shutdown requested")

        assert result == expected_response
        call_args = agent_instance_manager.client.update_agent_instance.call_args[1]
        assert call_args["agentInstanceStatus"] == "STOPPED"
        assert call_args["agentInstanceStatusReason"] == "Shutdown requested"

    def test_set_failed(self, agent_instance_manager):
        """Test set_failed method."""
        expected_response = {"agentInstanceId": "test-agent", "status": "FAILED"}
        agent_instance_manager.client.update_agent_instance.return_value = expected_response

        result = agent_instance_manager.set_failed("test-agent", "Processing error")

        assert result == expected_response
        call_args = agent_instance_manager.client.update_agent_instance.call_args[1]
        assert call_args["agentInstanceStatus"] == "FAILED"
        assert call_args["agentInstanceStatusReason"] == "Processing error"

    def test_list_agent_instances_no_filter(self, agent_instance_manager):
        """Test list_agent_instances without filter."""
        expected_response = {
            "agentInstanceSummaries": [
                {"agentInstanceId": "agent-1", "agentType": "ORCHESTRATOR"},
                {"agentInstanceId": "agent-2", "agentType": "SUB_AGENT"},
            ]
        }
        agent_instance_manager.client.list_agent_instances.return_value = expected_response

        result = agent_instance_manager.list_agent_instances()

        assert result == expected_response
        agent_instance_manager.client.list_agent_instances.assert_called_once()
        call_args = agent_instance_manager.client.list_agent_instances.call_args[1]
        assert "agentFilter" not in call_args

    def test_list_agent_instances_with_filter(self, agent_instance_manager):
        """Test list_agent_instances with requester filter."""
        expected_response = {
            "agentInstanceSummaries": [{"agentInstanceId": "agent-2", "agentType": "SUB_AGENT"}]
        }
        agent_instance_manager.client.list_agent_instances.return_value = expected_response

        result = agent_instance_manager.list_agent_instances("requester-123")

        assert result == expected_response
        call_args = agent_instance_manager.client.list_agent_instances.call_args[1]
        assert call_args["agentFilter"] == {"requesterAgentInstanceId": "requester-123"}

    def test_stop_agent_success(self, agent_instance_manager):
        """Test successful stop_agent operation."""
        expected_response = {"agentInstanceId": "test-agent", "status": "STOPPING"}
        agent_instance_manager.client.stop_agent.return_value = expected_response

        result = agent_instance_manager.stop_agent("test-agent")

        assert result == expected_response
        agent_instance_manager.client.stop_agent.assert_called_once()
        call_args = agent_instance_manager.client.stop_agent.call_args[1]
        assert call_args["agentInstanceId"] == "test-agent"


class TestAgentLifecycleFunctions:
    """Test cases for agent lifecycle functions."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_context_from_env"
    )
    @mock.patch("agent_builder_sdk.agentic_framework.agent_lifecycle.get_agentic_api_client")
    def test_get_agent_instance_manager(self, mock_get_client, mock_get_context, monkeypatch):
        """Test get_agent_instance_manager function."""
        # Setup mocks
        mock_context = mock.Mock()
        mock_context.workspace_id = "test-workspace"
        mock_context.job_id = "test-job"
        mock_context.agent_instance_id = "test-agent"
        mock_get_context.return_value = mock_context

        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Create temporary auth token file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test-token")
            auth_file_path = f.name
        monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)

        # Clear cache before test
        get_agent_instance_manager.cache_clear()

        manager = get_agent_instance_manager()

        assert isinstance(manager, AgentInstanceManager)
        assert manager.workspace_id == "test-workspace"
        assert manager.job_id == "test-job"
        assert manager.agent_instance_id == "test-agent"
        assert manager.client == mock_client

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_initialize_agent_instance(self, mock_get_manager):
        """Test initialize_agent_instance function."""
        mock_manager = mock.Mock()
        mock_get_manager.return_value = mock_manager

        initialize_agent_instance()

        mock_get_manager.assert_called_once()
        mock_manager.set_running.assert_called_once()

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_shutdown_base_orchestrator_agent_instance(self, mock_get_manager):
        """Test shutdown_base_orchestrator_agent_instance function."""
        mock_manager = mock.Mock()
        mock_manager.agent_instance_id = "test-agent"
        mock_get_manager.return_value = mock_manager

        shutdown_base_orchestrator_agent_instance("Test shutdown")

        mock_get_manager.assert_called_once()
        mock_manager.set_stopped.assert_called_once_with(
            mock_manager.agent_instance_id, "Test shutdown"
        )

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_shutdown_base_orchestrator_agent_instance_no_reason(self, mock_get_manager):
        """Test shutdown without reason."""
        mock_manager = mock.Mock()
        mock_manager.agent_instance_id = "test-agent"
        mock_get_manager.return_value = mock_manager

        shutdown_base_orchestrator_agent_instance()

        mock_get_manager.assert_called_once()
        mock_manager.set_stopped.assert_called_once_with(mock_manager.agent_instance_id, None)

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_shutdown_subagent_instance_running(self, mock_get_manager):
        """Test shutdown_subagent_instance when agent is running."""
        mock_manager = mock.Mock()
        mock_manager.get_status.return_value = {"agentInstanceStatus": "RUNNING"}
        mock_get_manager.return_value = mock_manager

        shutdown_subagent_instance("subagent-123")

        mock_get_manager.assert_called_once()
        mock_manager.stop_agent.assert_called_once_with("subagent-123")

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_shutdown_subagent_instance_already_stopped(self, mock_get_manager):
        """Test shutdown_subagent_instance when agent is already stopped."""
        mock_manager = mock.Mock()
        mock_manager.get_status.return_value = {"agentInstanceStatus": "STOPPED"}
        mock_get_manager.return_value = mock_manager

        shutdown_subagent_instance("subagent-123")

        mock_get_manager.assert_called_once()
        mock_manager.stop_agent.assert_called_once_with("subagent-123")

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_shutdown_subagent_instance_stopping(self, mock_get_manager):
        """Test shutdown_subagent_instance when agent is already stopping."""
        mock_manager = mock.Mock()
        mock_manager.get_status.return_value = {"agentInstanceStatus": "STOPPING"}
        mock_get_manager.return_value = mock_manager

        shutdown_subagent_instance("subagent-123")

        mock_get_manager.assert_called_once()
        mock_manager.stop_agent.assert_called_once_with("subagent-123")

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_get_subagent_instances_no_filter(self, mock_get_manager):
        """Test get_subagent_instances without filter."""
        mock_manager = mock.Mock()
        mock_manager.list_agent_instances.return_value = {
            "agentInstanceSummaries": [
                {
                    "agentInstanceId": "orch-1",
                    "agentType": "ORCHESTRATOR",
                    "agentInstanceStatus": "RUNNING",
                },
                {
                    "agentInstanceId": "sub-1",
                    "agentType": "SUB_AGENT",
                    "agentInstanceStatus": "RUNNING",
                },
                {
                    "agentInstanceId": "sub-2",
                    "agentType": "SUB_AGENT",
                    "agentInstanceStatus": "STOPPED",
                },
            ]
        }
        mock_get_manager.return_value = mock_manager

        result = get_subagent_instances()

        expected = [
            {
                "agentInstanceId": "sub-1",
                "agentType": "SUB_AGENT",
                "agentInstanceStatus": "RUNNING",
            },
            {
                "agentInstanceId": "sub-2",
                "agentType": "SUB_AGENT",
                "agentInstanceStatus": "STOPPED",
            },
        ]
        assert result == expected
        mock_manager.list_agent_instances.assert_called_once_with(None)

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager"
    )
    def test_get_subagent_instances_with_filter(self, mock_get_manager):
        """Test get_subagent_instances with requester filter."""
        mock_manager = mock.Mock()
        mock_manager.list_agent_instances.return_value = {
            "agentInstanceSummaries": [
                {
                    "agentInstanceId": "sub-1",
                    "agentType": "SUB_AGENT",
                    "agentInstanceStatus": "RUNNING",
                }
            ]
        }
        mock_get_manager.return_value = mock_manager

        result = get_subagent_instances("requester-123")

        expected = [
            {"agentInstanceId": "sub-1", "agentType": "SUB_AGENT", "agentInstanceStatus": "RUNNING"}
        ]
        assert result == expected
        mock_manager.list_agent_instances.assert_called_once_with("requester-123")


class TestAgentLifecycleCaching:
    """Test cases for LRU caching behavior."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_context_from_env"
    )
    @mock.patch("agent_builder_sdk.agentic_framework.agent_lifecycle.get_agentic_api_client")
    def test_lru_cache_reuse(self, mock_get_client, mock_get_context, monkeypatch):
        """Test that LRU cache reuses the same manager instance."""
        # Setup mocks
        mock_context = mock.Mock()
        mock_context.workspace_id = "test-workspace"
        mock_context.job_id = "test-job"
        mock_context.agent_instance_id = "test-agent"
        mock_get_context.return_value = mock_context

        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Create temporary auth token file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test-token")
            auth_file_path = f.name
        monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)

        # Clear cache before test
        get_agent_instance_manager.cache_clear()

        # Get manager twice
        manager1 = get_agent_instance_manager()
        manager2 = get_agent_instance_manager()

        # Should be the same instance due to caching
        assert manager1 is manager2

        # Should only call the expensive operations once
        mock_get_context.assert_called_once()
        mock_get_client.assert_called_once()


class TestAgentLifecycleErrorHandling:
    """Test cases for error handling in agent lifecycle functions."""

    def test_list_agent_instances_client_error(self, agent_instance_manager):
        """Test list_agent_instances with client error."""
        agent_instance_manager.client.list_agent_instances.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="list_agent_instances",
        )

        with pytest.raises(ClientError):
            agent_instance_manager.list_agent_instances()

    def test_stop_agent_client_error(self, agent_instance_manager):
        """Test stop_agent with client error."""
        agent_instance_manager.client.stop_agent.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="stop_agent",
        )

        with pytest.raises(ClientError):
            agent_instance_manager.stop_agent("test-agent")


def test_initialize_base_orchestrator_agent_instance():
    """Test initialize_base_orchestrator_agent_instance with explicit parameters."""
    with mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    ) as mock_get_manager:
        mock_manager = mock.Mock()
        mock_manager.get_status.return_value = {"agentInstanceStatus": "INVOKED"}
        mock_get_manager.return_value = mock_manager

        # Call the function with explicit parameters
        result = initialize_base_orchestrator_agent_instance(
            workspace_id="test-workspace", job_id="test-job", agent_instance_id="test-agent"
        )

        # Verify manager was created with correct parameters
        mock_get_manager.assert_called_once_with("test-workspace", "test-job", "test-agent")
        # Verify get_status was called
        mock_manager.get_status.assert_called_once()
        # Verify set_running was called
        mock_manager.set_running.assert_called_once()
        # Verify function returns True
        assert result is True


def test_get_agent_instance_manager_with_context():
    """Test get_agent_instance_manager_with_context creates manager with explicit parameters."""
    with mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agentic_api_client"
    ) as mock_get_client:
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        manager = get_agent_instance_manager_with_context(
            workspace_id="test-workspace", job_id="test-job", agent_instance_id="test-agent"
        )

        # Verify manager was created with correct parameters
        assert manager.workspace_id == "test-workspace"
        assert manager.job_id == "test-job"
        assert manager.agent_instance_id == "test-agent"
        assert manager.client == mock_client


def test_initialize_base_orchestrator_agent_instance_already_running():
    """Test initialize_base_orchestrator_agent_instance when agent is already running."""
    with mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    ) as mock_get_manager:
        mock_manager = mock.Mock()
        mock_manager.get_status.return_value = {"agentInstanceStatus": "RUNNING"}
        mock_get_manager.return_value = mock_manager

        # Call the function with explicit parameters
        result = initialize_base_orchestrator_agent_instance(
            workspace_id="test-workspace", job_id="test-job", agent_instance_id="test-agent"
        )

        # Verify manager was created with correct parameters
        mock_get_manager.assert_called_once_with("test-workspace", "test-job", "test-agent")
        # Verify get_status was called
        mock_manager.get_status.assert_called_once()
        # Verify set_running was NOT called since agent is already running
        mock_manager.set_running.assert_not_called()
        # Verify function returns True
        assert result is True


class TestGetAgentStatus:
    """Test cases for get_agent_status function (simplified, no retry)."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_get_status_success(self, mock_get_manager):
        """Test successful status retrieval."""
        mock_manager = mock.Mock()
        mock_manager.get_status.return_value = {"agentInstanceStatus": "RUNNING"}
        mock_get_manager.return_value = mock_manager

        result = get_agent_status("workspace", "job", "agent")

        assert result == "RUNNING"
        mock_manager.get_status.assert_called_once_with("agent")

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_parse_status_from_terminal_resource_exception(self, mock_get_manager):
        """Test parsing status from TerminalResourceException error message."""
        mock_manager = mock.Mock()
        error = ClientError(
            {
                "Error": {
                    "Code": "TerminalResourceException",
                    "Message": "Agent instance with type ORCHESTRATOR_AGENT, status INVOKING is not allowed to perform: GetAgentInstance",
                }
            },
            "GetAgentInstance",
        )
        mock_manager.get_status.side_effect = error
        mock_get_manager.return_value = mock_manager

        result = get_agent_status("workspace", "job", "agent")

        assert result == "INVOKING"

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    @pytest.mark.parametrize(
        "error_message,expected_status",
        [
            (
                "Agent instance with type ORCHESTRATOR_AGENT, status INVOKED is not allowed to perform: GetAgentInstance",
                "INVOKED",
            ),
            ("Agent instance status is not valid: INVOKING", "INVOKING"),
        ],
    )
    def test_parse_status_from_error_messages(
        self, mock_get_manager, error_message, expected_status
    ):
        """Test parsing status from various TerminalResourceException error message formats."""
        mock_manager = mock.Mock()
        error = ClientError(
            {
                "Error": {
                    "Code": "TerminalResourceException",
                    "Message": error_message,
                }
            },
            "GetAgentInstance",
        )
        mock_manager.get_status.side_effect = error
        mock_get_manager.return_value = mock_manager

        result = get_agent_status("workspace", "job", "agent")

        assert result == expected_status

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_non_terminal_resource_exception_raises(self, mock_get_manager):
        """Test that non-TerminalResourceException errors are re-raised."""
        mock_manager = mock.Mock()
        error = ClientError(
            {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "agentInstanceId not found",
                }
            },
            "GetAgentInstance",
        )
        mock_manager.get_status.side_effect = error
        mock_get_manager.return_value = mock_manager

        with pytest.raises(ClientError):
            get_agent_status("workspace", "job", "agent")


class TestSetAgentRunning:
    """Test cases for set_agent_running function (simplified, no retry)."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_set_running_success(self, mock_get_manager):
        """Test successful set_running operation."""
        mock_manager = mock.Mock()
        mock_get_manager.return_value = mock_manager

        set_agent_running("workspace", "job", "agent")

        mock_manager.set_running.assert_called_once_with("agent")

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_instance_manager_with_context"
    )
    def test_set_running_with_client_error(self, mock_get_manager):
        """Test set_running with ClientError (no retry, should raise)."""
        mock_manager = mock.Mock()
        mock_manager.set_running.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "UpdateAgentInstance"
        )
        mock_get_manager.return_value = mock_manager

        with pytest.raises(ClientError):
            set_agent_running("workspace", "job", "agent")


class TestWaitForAgentNonInvoking:
    """Test cases for wait_for_agent_non_invoking function."""

    @mock.patch("agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_status")
    @mock.patch("asyncio.sleep")
    async def test_agent_transitions_immediately(self, mock_sleep, mock_get_status):
        """Test when agent transitions from INVOKING immediately."""
        mock_get_status.return_value = "RUNNING"

        result = await wait_for_agent_non_invoking("workspace", "job", "agent")

        assert result == "RUNNING"
        mock_get_status.assert_called_once_with("workspace", "job", "agent")
        mock_sleep.assert_not_called()

    @mock.patch("agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_status")
    @mock.patch("asyncio.sleep")
    async def test_agent_transitions_after_retry(self, mock_sleep, mock_get_status):
        """Test when agent transitions from INVOKING after a few attempts."""
        mock_get_status.side_effect = ["INVOKING", "INVOKING", "RUNNING"]

        result = await wait_for_agent_non_invoking("workspace", "job", "agent")

        assert result == "RUNNING"
        assert mock_get_status.call_count == 3
        assert mock_sleep.call_count == 2

    @mock.patch("agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_status")
    @mock.patch("asyncio.sleep")
    @mock.patch("time.monotonic")
    async def test_timeout_while_invoking(self, mock_monotonic, mock_sleep, mock_get_status):
        """Test timeout when agent remains in INVOKING state."""
        mock_get_status.return_value = "INVOKING"
        # Mock time.monotonic to simulate timeout after 2 seconds
        mock_monotonic.side_effect = [0, 0.5, 1.0, 1.5, 2.5]  # Exceeds 2 second timeout

        result = await wait_for_agent_non_invoking("workspace", "job", "agent", timeout=2)

        assert result == "INVOKING"
        assert mock_get_status.call_count >= 2

    @mock.patch("agent_builder_sdk.agentic_framework.agent_lifecycle.get_agent_status")
    @mock.patch("asyncio.sleep")
    async def test_exception_during_status_check(self, mock_sleep, mock_get_status):
        """Test handling exceptions during status checks."""
        mock_get_status.side_effect = [Exception("API Error"), "RUNNING"]

        result = await wait_for_agent_non_invoking("workspace", "job", "agent")

        assert result == "RUNNING"
        assert mock_get_status.call_count == 2
        mock_sleep.assert_called_once()
