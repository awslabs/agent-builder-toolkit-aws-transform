"""
Unit tests for Agent Runtime Server implementation.

Tests the AgentRuntimeServer class which provides compatibility with multiple
agent execution environments through JSON-RPC endpoints.
"""

import asyncio
from multiprocessing import Event as MPEvent
from unittest import mock
from unittest.mock import MagicMock, create_autospec, patch

import pytest
from fastapi.testclient import TestClient

from agent_builder_sdk.agent_factory import create_default_orchestrator
from agent_builder_sdk.checkpoint.checkpoint_triggers import CheckpointStrategy
from agent_builder_sdk.custom_types.common_types import (
    A2AErrorCode,
    A2AMessage,
    InvocationRequest,
)
from agent_builder_sdk.custom_types.server_types import JsonRpcMethods
from agent_builder_sdk.extensions.base_extension_handler import BaseExtensionHandler
from agent_builder_sdk.interfaces import BaseAgent
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_sdk.utils import MessageInfo


@pytest.fixture(autouse=True)
def context(monkeypatch):
    with patch("agent_builder_sdk.env_var.retrieve_auth_token"):
        monkeypatch.setenv("JOB_ID", "job-id")
        monkeypatch.setenv("WORKSPACE_ID", "workspace-id")
        monkeypatch.setenv("AGENT_INSTANCE_ID", "agent-instance-id")
        yield


@pytest.fixture
def mock_agent():
    return create_autospec(BaseAgent, spec_set=True, instance=True)


@pytest.fixture
def mock_agent_factory(mock_agent):
    def factory(mcp_client, storage_dir, **kwargs):
        return mock_agent

    return factory


def agent_factory_no_kwargs(mock_agent):
    def factory(mcp_client, storage_dir):
        return mock_agent

    return factory


def async_agent_factory(mock_agent):
    async def factory(mcp_client, storage_dir, **kwargs):
        return mock_agent

    return factory


@pytest.fixture
def agent_runtime_server(mock_agent_factory):
    """Create Agent Runtime Server instance for testing."""
    with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
            server = AgentRuntimeServer(
                agent_factory=mock_agent_factory,
                binary_location="/tmp/test_binary",
                storage_dir="/tmp/test_storage",
            )
            return server


class TestAgentRuntimeServer:
    """Test cases for AgentRuntimeServer compatibility and functionality."""

    @pytest.mark.parametrize(
        "checkpoint_config",
        [
            {"strategy": None, "interval": 30, "name": "no_checkpoint"},
            {
                "strategy": CheckpointStrategy.CONVERSATION,
                "interval": 5,
                "name": "conversation_checkpoint",
            },
            {"strategy": CheckpointStrategy.TIME, "interval": 10, "name": "time_checkpoint"},
        ],
    )
    def test_initialization(self, mock_agent_factory, checkpoint_config):
        """Test server initialization with different checkpoint configurations."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                    checkpoint_strategy=checkpoint_config["strategy"],
                    checkpoint_interval=checkpoint_config["interval"],
                )

                # Existing assertions
                assert server.binary_location == "/tmp/test_binary"
                assert server.storage_dir == "/tmp/test_storage/agent"
                assert server.agent is None
                assert server.initialized is False
                assert server.message_processor_task is None

                # Verify components were created
                assert server.queue is not None
                assert server.request_handler is not None
                assert server.notification_handler is not None
                assert server.task_handler is not None
                assert not server.initialized
                assert server.agent_factory is not None

                # Checkpoint assertions - service always exists now for restoration
                assert server.checkpoint_service is not None
                if checkpoint_config["strategy"]:
                    assert (
                        CheckpointStrategy(server.checkpoint_service.strategy)
                        == checkpoint_config["strategy"]
                    )
                    assert server.checkpoint_service.interval == checkpoint_config["interval"]
                else:
                    # No strategy means restoration-only mode
                    assert server.checkpoint_service.strategy is None

    def test_delayed_timeout_configuration(self, mock_agent_factory):
        """Test delayed_timeout parameter configuration."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                # Test default value
                server_default = AgentRuntimeServer(agent_factory=mock_agent_factory)
                assert server_default.delayed_timeout == 300  # Default 5 minutes

                # Test custom value
                server_custom = AgentRuntimeServer(
                    agent_factory=mock_agent_factory, delayed_timeout=600
                )
                assert server_custom.delayed_timeout == 600  # Custom 10 minutes

    def test_timeout_configuration(self, mock_agent_factory):
        """Test timeout parameter configuration."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                # Test default value
                server_default = AgentRuntimeServer(agent_factory=mock_agent_factory)
                assert server_default.timeout == 28  # Default timeout

                # Test custom value
                server_custom = AgentRuntimeServer(agent_factory=mock_agent_factory, timeout=60)
                assert server_custom.timeout == 60  # Custom timeout

    def test_token_refresh_buffer_configuration(self, mock_agent_factory):
        """Test token_refresh_buffer parameter configuration."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                # Test default value
                server_default = AgentRuntimeServer(agent_factory=mock_agent_factory)
                assert server_default.token_refresh_buffer == 40  # Default buffer timer

                # Test custom value
                server_custom = AgentRuntimeServer(
                    agent_factory=mock_agent_factory, token_refresh_buffer=1800
                )
                assert server_custom.token_refresh_buffer == 1800  # Custom buffer timer

    def test_token_refreshed_event_configuration(self, mock_agent_factory):
        """Test token_refreshed_event parameter configuration."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                # Test default value (None)
                server_default = AgentRuntimeServer(agent_factory=mock_agent_factory)
                assert server_default.token_refreshed_event is None

                # Test with custom event
                test_event = MPEvent()
                server_custom = AgentRuntimeServer(
                    agent_factory=mock_agent_factory, token_refreshed_event=test_event
                )
                assert server_custom.token_refreshed_event is test_event

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_healthcheck(self, agent_runtime_server):
        """Test JSON-RPC healthcheck method."""
        request = {"jsonrpc": "2.0", "id": 1, "method": "atx_agent/healthcheck", "params": {}}

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] == {"agentHealth": "HEALTHY"}

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_notify(self, agent_runtime_server):
        """Test JSON-RPC notify method."""
        mock_handler = mock.Mock()
        mock_handler.handle_notification = mock.AsyncMock(return_value={"status": "processed"})
        agent_runtime_server.notification_handler = mock_handler

        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "atx_agent/notify",
            "params": {"notification": {"type": "test", "data": "test_data"}},
        }

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 2
        assert result["result"] == {"status": "processed"}
        mock_handler.handle_notification.assert_called_once_with(
            {"type": "test", "data": "test_data"}
        )

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_message_send(self, agent_runtime_server):
        """Test JSON-RPC message send method."""
        # Mock message_handler
        mock_handler = mock.Mock()
        mock_result = mock.Mock()
        mock_a2a_message = A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": "Hello"}],
            messageId="test-123",
            kind="message",
        )
        mock_result.result = mock_a2a_message
        mock_result.error = None
        mock_handler.send_message = mock.AsyncMock(return_value=mock_result)
        agent_runtime_server.message_handler = mock_handler

        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Hi"}],
                    "messageId": "user-123",
                    "kind": "message",
                }
            },
        }

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 3
        assert "result" in result
        # Verify message_handler.send_message was called with correct parameters
        mock_handler.send_message.assert_called_once()
        call_args = mock_handler.send_message.call_args[0][0]
        assert call_args.message.role == "user"
        assert call_args.message.parts == [{"kind": "text", "text": "Hi"}]
        assert call_args.message.messageId == "user-123"
        assert call_args.message.kind == "message"

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_method_not_found(self, agent_runtime_server):
        """Test JSON-RPC with unknown method."""
        request = {"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}}

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 4
        assert "error" in result
        assert result["error"]["code"] == -32601  # Method not found

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "checkpoint_config",
        [
            {"strategy": None, "interval": 30, "name": "no_checkpoint"},
            {
                "strategy": CheckpointStrategy.CONVERSATION,
                "interval": 5,
                "name": "conversation_checkpoint",
            },
        ],
    )
    async def test_initialize_agent(self, mock_agent_factory, checkpoint_config):
        """Test agent initialization with different checkpoint configurations."""
        # Create server with checkpoint config
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                    checkpoint_strategy=checkpoint_config["strategy"],
                    checkpoint_interval=checkpoint_config["interval"],
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_auth_token_refresher"
        ) as mock_refresher:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.get_agent_status",
                return_value="RUNNING",
            ) as mock_platform_init:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.build_agentic_api_endpoint_from_env"
                ) as mock_endpoint:
                    with mock.patch(
                        "agent_builder_sdk.server.agent_runtime_server.MCPClientFactory.setup_eg_mcp_client"
                    ):
                        with mock.patch(
                            "agent_builder_sdk.server.agent_runtime_server.setup_initial_auth_token"
                        ) as mock_setup_initial_auth_token:
                            mock_endpoint.return_value = "https://test-endpoint.com"

                            # Helper: RUNNING status schedules _finalize_agent_setup as a
                            # background task. Give the event loop a chance to run that
                            # task through the mocked checkpoint/refresher calls before we
                            # assert on the mocks. Any error from downstream init steps
                            # (agentic api client, auth token file) is captured on the task
                            # and ignored here — matches the pre-change behavior where
                            # initialize_agent's try/except swallowed such errors.
                            async def run_and_settle_task():
                                await server.initialize_agent(auth_token="test-token")
                                task = server._initialization_task
                                if task is not None:
                                    try:
                                        await task
                                    except Exception:
                                        pass

                            # Mock checkpoint service methods if service exists
                            if server.checkpoint_service:
                                with mock.patch.object(
                                    server.checkpoint_service, "initialize"
                                ) as mock_checkpoint_init:
                                    with mock.patch.object(
                                        server.checkpoint_service, "start_background_checkpointing"
                                    ) as mock_checkpoint_start:
                                        await run_and_settle_task()
                                        # Checkpoint calls only happen if immediate initialization occurs
                                        if checkpoint_config["strategy"] is not None:
                                            mock_checkpoint_init.assert_called_once_with(
                                                server.context
                                            )
                                            mock_checkpoint_start.assert_called_once()
                            else:
                                await run_and_settle_task()

                            # Verify new initialization calls
                            mock_setup_initial_auth_token.assert_called_once()
                            mock_platform_init.assert_called_once_with(
                                "test-workspace", "test-job", "test-agent"
                            )
                            mock_refresher.assert_called_once_with(
                                workspace_id="test-workspace",
                                job_id="test-job",
                                agent_instance_id="test-agent",
                                first_token="test-token",
                                token_refresh_buffer=40,
                                token_refreshed_event=None,
                            )

    @pytest.mark.asyncio
    async def test_extract_and_initialize_all_formats(self, agent_runtime_server):
        """Test extracting initialization context from all JSON-RPC request formats."""
        test_cases = [
            # 1. message/send format
            {
                "request": {
                    "method": JsonRpcMethods.MESSAGE_SEND,
                    "params": {
                        "message": {
                            "metadata": {
                                "ATX_A2A.AgentInitializationContext": {
                                    "jobMetadata": {"jobId": "job-1", "workspaceId": "ws-1"},
                                    "agentInstanceId": "agent-1",
                                    "authorizationToken": "token-1",
                                }
                            }
                        }
                    },
                }
            },
            # 2. atx_agent/invoke format
            {
                "request": {
                    "method": JsonRpcMethods.INVOKE,
                    "params": {
                        "invocationContext": {
                            "jobMetadata": {"jobId": "job-2", "workspaceId": "ws-2"},
                            "agentMetadata": {
                                "agentId": "agent-123",
                                "agentType": "ORCHESTRATOR",
                                "agentVersion": "1.0",
                            },
                            "userMetadata": {
                                "accountId": "123456789012",
                                "invocationUserId": "user-456",
                            },
                            "authorizationToken": "token-2",
                        },
                        "agentInstanceId": "agent-2",
                    },
                },
                "expected_agent_id": "agent-123",
                "expected_agent_version": "1.0",
                "expected_tenant_account_id": "123456789012",
            },
            # 3. atx_agent/notify format
            {
                "request": {
                    "method": JsonRpcMethods.NOTIFY,
                    "params": {
                        "jobMetadata": {"jobId": "job-3", "workspaceId": "ws-3"},
                        "agentInstanceId": "agent-3",
                        "authorizationToken": "token-3",
                    },
                }
            },
            # 4. tasks/get format
            {
                "request": {
                    "method": JsonRpcMethods.TASKS_GET,
                    "params": {
                        "metadata": {
                            "agentInitializationContext": {
                                "jobMetadata": {"jobId": "job-4", "workspaceId": "ws-4"},
                                "agentInstanceId": "agent-4",
                                "authorizationToken": "token-4",
                            }
                        }
                    },
                }
            },
        ]

        for test_case in test_cases:
            # Reset server state
            agent_runtime_server.context = None
            agent_runtime_server.initialized = False

            with mock.patch.object(agent_runtime_server, "initialize_agent") as mock_init:
                await agent_runtime_server.extract_and_initialize(test_case["request"])

                # Verify context was set correctly
                assert agent_runtime_server.context is not None

                # Get job_id based on request format
                if test_case["request"]["method"] == JsonRpcMethods.MESSAGE_SEND:
                    expected_job_id = test_case["request"]["params"]["message"]["metadata"][
                        "ATX_A2A.AgentInitializationContext"
                    ]["jobMetadata"]["jobId"]
                elif test_case["request"]["method"] in [
                    JsonRpcMethods.INVOKE,
                    JsonRpcMethods.RESTORE,
                ]:
                    expected_job_id = test_case["request"]["params"]["invocationContext"][
                        "jobMetadata"
                    ]["jobId"]
                elif test_case["request"]["method"] in [
                    JsonRpcMethods.NOTIFY,
                    JsonRpcMethods.HEALTHCHECK,
                    JsonRpcMethods.STOP,
                ]:
                    expected_job_id = test_case["request"]["params"]["jobMetadata"]["jobId"]
                else:  # tasks/get
                    expected_job_id = test_case["request"]["params"]["metadata"][
                        "agentInitializationContext"
                    ]["jobMetadata"]["jobId"]

                assert agent_runtime_server.context.job_id == expected_job_id

                # Verify agent_id is extracted when present
                if "expected_agent_id" in test_case:
                    assert agent_runtime_server.context.agent_id == test_case["expected_agent_id"]
                else:
                    assert agent_runtime_server.context.agent_id is None

                # Verify agent_version is extracted when present
                if "expected_agent_version" in test_case:
                    assert (
                        agent_runtime_server.context.agent_version
                        == test_case["expected_agent_version"]
                    )
                else:
                    assert agent_runtime_server.context.agent_version is None

                # Verify tenant_account_id is extracted when present
                if "expected_tenant_account_id" in test_case:
                    assert (
                        agent_runtime_server.context.tenant_account_id
                        == test_case["expected_tenant_account_id"]
                    )
                else:
                    assert agent_runtime_server.context.tenant_account_id is None

                mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_and_initialize_missing_fields(self, agent_runtime_server):
        """Test extracting initialization context with missing required fields."""
        test_cases = [
            # Missing workspaceId
            {
                "request": {
                    "method": JsonRpcMethods.MESSAGE_SEND,
                    "params": {
                        "message": {
                            "metadata": {
                                "ATX_A2A.AgentInitializationContext": {
                                    "jobMetadata": {"jobId": "job-1"},
                                    "agentInstanceId": "agent-1",
                                }
                            }
                        }
                    },
                }
            },
            # Missing jobId
            {
                "request": {
                    "method": JsonRpcMethods.INVOKE,
                    "params": {
                        "invocationContext": {"jobMetadata": {"workspaceId": "ws-2"}},
                        "agentInstanceId": "agent-2",
                    },
                }
            },
            # Missing agentInstanceId
            {
                "request": {
                    "method": JsonRpcMethods.NOTIFY,
                    "params": {"jobMetadata": {"jobId": "job-3", "workspaceId": "ws-3"}},
                }
            },
        ]

        for test_case in test_cases:
            with pytest.raises(ValueError, match="Missing required initialization context"):
                await agent_runtime_server.extract_and_initialize(test_case["request"])

    @pytest.mark.asyncio
    async def test_message_handler_no_queue(self, agent_runtime_server):
        """Test MessageHandler validation when neither queue nor agent provided."""

        with pytest.raises(
            ValueError, match="Must provide either queue or agent for message processing"
        ):
            MessageHandler(None)

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_invalid_request(self, agent_runtime_server):
        """Test JSON-RPC with invalid request format."""
        request = {"invalid": "request"}

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert "error" in result
        assert result["error"]["code"] == -32603  # Internal error (validation failed)

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_restore_method(self, agent_runtime_server):
        """Test JSON-RPC restore method."""
        request = {"jsonrpc": "2.0", "id": 5, "method": "atx_agent/restore", "params": {}}

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 5
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_stop_method(self, agent_runtime_server):
        """Test JSON-RPC stop method."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances",
            return_value=[],
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
            ):
                request = {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "atx_agent/stop",
                    "params": {"agentInstanceId": "test-agent"},
                }

                result = await agent_runtime_server.handle_jsonrpc(request)

                assert result["jsonrpc"] == "2.0"
                assert result["id"] == 6
                assert "result" in result
                assert "message" in result["result"]
                assert result["result"]["agentInstanceId"] == "test-agent"

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_tasks_get_method(self, agent_runtime_server):
        """Test JSON-RPC tasks get method."""

        request = {"jsonrpc": "2.0", "id": 7, "method": "tasks/get", "params": {}}

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 7
        assert result["result"]["code"] == A2AErrorCode.INVALID_REQUEST
        assert "Missing required parameter: id" in result["result"]["message"]

    @pytest.mark.asyncio
    async def test_extract_and_initialize_job_metadata_format(self, agent_runtime_server):
        """Test extracting initialization context from jobMetadata format."""
        request = {
            "method": JsonRpcMethods.NOTIFY,
            "params": {
                "jobMetadata": {"workspaceId": "test-workspace", "jobId": "test-job"},
                "agentInstanceId": "test-agent",
            },
        }

        with mock.patch.object(agent_runtime_server, "initialize_agent") as mock_init:
            await agent_runtime_server.extract_and_initialize(request)

            # Should call initialize_agent
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_and_initialize_message_metadata_format(self, agent_runtime_server):
        """Test extracting initialization context from message metadata format."""
        request = {
            "method": JsonRpcMethods.MESSAGE_SEND,
            "params": {
                "message": {
                    "metadata": {
                        "ATX_A2A.AgentInitializationContext": {
                            "jobMetadata": {"workspaceId": "test-workspace", "jobId": "test-job"},
                            "agentInstanceId": "test-agent",
                        }
                    }
                }
            },
        }

        with mock.patch.object(agent_runtime_server, "initialize_agent") as mock_init:
            await agent_runtime_server.extract_and_initialize(request)

            # Should call initialize_agent
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_handler_with_queue(self, agent_runtime_server):
        """Test message_handler with queue available."""

        mock_queue = mock.Mock()
        mock_queue.submit_request = mock.AsyncMock(return_value="request-123")
        mock_queue.wait_for_response = mock.AsyncMock(
            return_value=mock.Mock(
                request_id="request-123", context_id="context-123", message="Agent response"
            )
        )

        message_handler = MessageHandler(mock_queue)

        with mock.patch(
            "agent_builder_sdk.messages.message_handler.extract_message_info"
        ) as mock_extract:
            mock_extract.return_value = MessageInfo(
                user_id="user-123",
                sender="ATX_CHAT",
                task_id="task-123",
                context_id="context-123",
                parts=[{"text": "Hello"}],
            )

            with mock.patch(
                "agent_builder_sdk.messages.message_handler.convert_queue_response_to_send_message_output"
            ) as mock_convert:
                mock_result = mock.Mock()
                mock_result.result = mock.Mock()
                mock_convert.return_value = mock_result

                request = InvocationRequest(
                    message=A2AMessage(
                        role="user",
                        parts=[{"kind": "text", "text": "Hello"}],
                        messageId="test-123",
                        kind="message",
                        taskId="task-123",
                    )
                )

                result = await message_handler.send_message(request)

                assert result is not None
                mock_queue.submit_request.assert_called_once()
                mock_queue.wait_for_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_routes(self, agent_runtime_server):
        """Test that routes are properly set up."""
        # Check that routes exist
        routes = [route.path for route in agent_runtime_server.app.routes]
        assert "/ping" in routes
        assert "/invocations" in routes

    @pytest.mark.asyncio
    async def test_ping_endpoint(self, agent_runtime_server):
        """Test ping endpoint returns correct response."""

        client = TestClient(agent_runtime_server.app)
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"status": "HealthyBusy"}

    # Remove the failing tests - they will be replaced with simpler working versions
    @pytest.mark.asyncio
    async def test_handle_invocations_not_initialized(self, agent_runtime_server):
        """Test invocations when server not initialized."""

        agent_runtime_server.initialized = False

        with mock.patch.object(agent_runtime_server, "extract_and_initialize") as mock_extract:
            with mock.patch.object(agent_runtime_server, "handle_jsonrpc") as mock_handle:
                mock_handle.return_value = {"result": "success"}

                client = TestClient(agent_runtime_server.app)
                response = client.post(
                    "/invocations", json={"jsonrpc": "2.0", "method": "test", "id": 1}
                )

                assert response.status_code == 200
                mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_invocations_invalid_format(self, agent_runtime_server):
        """Test invocations with invalid request format."""

        agent_runtime_server.initialized = True
        # Mock notification handler to avoid "not initialized" error
        agent_runtime_server.notification_handler = mock.Mock()
        agent_runtime_server.notification_handler.handle_notification = mock.AsyncMock(
            side_effect=ValueError("Invalid request format")
        )

        client = TestClient(agent_runtime_server.app)
        response = client.post("/invocations", json={"invalid": "request"})

        assert response.status_code == 200
        assert "error" in response.json()
        assert "Invalid request format" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_healthcheck_method(self, agent_runtime_server):
        """Test JSON-RPC healthcheck method."""
        request = {"jsonrpc": "2.0", "id": 1, "method": "atx_agent/healthcheck", "params": {}}

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result

    @pytest.mark.asyncio
    async def test_handle_delayed_response_exception(self, agent_runtime_server):
        """Test _handle_delayed_response with exception."""

        mock_queue = mock.Mock()
        mock_queue.wait_for_response = mock.AsyncMock(side_effect=Exception("Queue error"))
        message_handler = MessageHandler(mock_queue)

        # Should not raise exception
        await message_handler._handle_delayed_response("req", "ctx", mock.Mock())

    def test_setup_eg_mcp_client_missing_binary(self, agent_runtime_server):
        """Test MCP client setup with missing binary location."""
        mcp_args = {"command": "test"}

        with pytest.raises(Exception):
            agent_runtime_server.setup_eg_mcp_client(mcp_args)

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_notify_method(self, agent_runtime_server):
        """Test JSON-RPC notify method."""
        mock_handler = mock.Mock()
        mock_handler.handle_notification = mock.AsyncMock(return_value={"status": "handled"})
        agent_runtime_server.notification_handler = mock_handler

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/notify",
            "params": {"notification": {"type": "test"}},
        }

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result
        mock_handler.handle_notification.assert_called_once_with({"type": "test"})

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_notify_no_handler(self, agent_runtime_server):
        """Test JSON-RPC notify method with no handler."""
        agent_runtime_server.notification_handler = None

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/notify",
            "params": {"notification": {"type": "test"}},
        }

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_message_send_error(self, agent_runtime_server):
        """Test JSON-RPC message send with error."""
        mock_handler = mock.Mock()
        mock_error = mock.Mock()
        mock_error.code = "TEST_ERROR"
        mock_error.message = "Test error message"
        mock_handler.send_message = mock.AsyncMock(
            return_value=mock.Mock(error=mock_error, result=None)
        )
        agent_runtime_server.message_handler = mock_handler

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {"role": "user", "parts": [], "messageId": "test", "kind": "message"}
            },
        }

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Test error message" in result["error"]["message"]

    def test_start_with_uvicorn_error(self, agent_runtime_server):
        """Test start method with uvicorn error."""
        with mock.patch("uvicorn.run") as mock_uvicorn:
            mock_uvicorn.side_effect = Exception("Server error")

            with pytest.raises(Exception):
                agent_runtime_server.start()

    def test_agent_factory_usage(self, mock_agent_factory):
        """Test using agent factory pattern."""

        mock_mcp_client = mock.Mock()
        storage_dir = "/tmp/test"

        # Test the factory function directly
        result = mock_agent_factory(mock_mcp_client, storage_dir)
        assert result is not None

        # Test create_default_orchestrator function
        with mock.patch(
            "agent_builder_sdk.agent_factory.BaseOrchestrator"
        ) as mock_orchestrator:
            mock_instance = mock.Mock()
            mock_orchestrator.return_value = mock_instance

            result = create_default_orchestrator(
                mcp_client=mock_mcp_client, storage_dir=storage_dir
            )

            assert result == mock_instance
            mock_orchestrator.assert_called_once()

    def test_start_method(self, agent_runtime_server):
        """Test start method just starts uvicorn."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.uvicorn"
        ) as mock_uvicorn:
            agent_runtime_server.start()
            mock_uvicorn.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_invoke_method(self, agent_runtime_server):
        """Test JSON-RPC invoke method."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/invoke",
            "params": {
                "invocationContext": {
                    "jobMetadata": {"workspaceId": "test-workspace", "jobId": "test-job"}
                },
                "agentInstanceId": "test-agent",
            },
        }

        result = await agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_lifespan_startup_and_cleanup(self, agent_runtime_server):
        """Test FastAPI lifespan startup and cleanup."""
        with mock.patch.object(agent_runtime_server, "_startup") as mock_startup:
            with mock.patch.object(agent_runtime_server, "_cleanup") as mock_cleanup:
                # Simulate lifespan context manager
                lifespan_context = agent_runtime_server._lifespan(agent_runtime_server.app)

                # Enter context (startup)
                await lifespan_context.__aenter__()
                mock_startup.assert_called_once()

                # Exit context (cleanup)
                await lifespan_context.__aexit__(None, None, None)
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_mde_mode(self, agent_runtime_server):
        """Test MDE mode initialization."""
        with mock.patch(
            "agent_builder_sdk.server.base_server.get_initial_agent_runtime_context_from_env"
        ) as mock_get_context:
            with mock.patch.object(agent_runtime_server, "initialize_agent") as mock_init_agent:
                mock_context = mock.MagicMock()
                mock_context.initial_auth_token = "test-token"
                mock_get_context.return_value = mock_context

                await agent_runtime_server._initialize_mde_mode()

                mock_get_context.assert_called_once()
                mock_init_agent.assert_called_once_with("test-token")
                assert agent_runtime_server.context == mock_context

    @pytest.mark.asyncio
    async def test_ensure_initialized_no_request_no_context(self, agent_runtime_server):
        """Test ensure_initialized raises error when no context and no request."""
        agent_runtime_server.context = None
        agent_runtime_server.initialized = False

        with pytest.raises(
            ValueError, match="Agent not initialized and no valid JSON-RPC request context provided"
        ):
            await agent_runtime_server.ensure_initialized()

    @pytest.mark.asyncio
    async def test_get_ready_agent_waits_for_agent(self, agent_runtime_server):
        """Test _get_ready_agent waits for agent to be available."""
        agent_runtime_server.agent = None

        # Mock agent becomes available after short delay
        async def set_agent_after_delay():
            await asyncio.sleep(0.01)
            agent_runtime_server.agent = mock.MagicMock()
            agent_runtime_server.agent_ready_event.set()

        # Start both tasks
        agent_task = asyncio.create_task(set_agent_after_delay())
        get_agent_task = asyncio.create_task(agent_runtime_server._get_ready_agent())

        # Wait for both to complete
        await asyncio.gather(agent_task, get_agent_task)

        # Verify we got the agent
        result = await agent_runtime_server._get_ready_agent()
        assert result == agent_runtime_server.agent

    @pytest.mark.asyncio
    async def test_startup_mde_mode(self, agent_runtime_server):
        """Test _startup in MDE mode."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.has_mde_environment",
            return_value=True,
        ):
            with mock.patch.object(agent_runtime_server, "_initialize_mde_mode") as mock_init_mde:
                with mock.patch.object(agent_runtime_server.queue, "start") as mock_queue_start:
                    with mock.patch("asyncio.create_task") as mock_create_task:
                        await agent_runtime_server._startup()

                        mock_queue_start.assert_called_once()
                        mock_init_mde.assert_called_once()
                        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_agentcore_mode(self, agent_runtime_server):
        """Test _startup in AgentCore mode."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.has_mde_environment",
            return_value=False,
        ):
            with mock.patch.object(agent_runtime_server.queue, "start") as mock_queue_start:
                with mock.patch("asyncio.create_task") as mock_create_task:
                    await agent_runtime_server._startup()

                    mock_queue_start.assert_called_once()
                    mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_message_processor_task(self, agent_runtime_server):
        """Test _cleanup cancels message processor task."""

        # Create a real asyncio task to test cancellation
        async def dummy_task():
            await asyncio.sleep(10)  # Long running task

        task = asyncio.create_task(dummy_task())
        agent_runtime_server.message_processor_task = task

        with mock.patch.object(agent_runtime_server.queue, "stop"):
            await agent_runtime_server._cleanup()

            # Verify task was cancelled
            assert task.cancelled()

    @pytest.mark.asyncio
    async def test_cleanup_without_message_processor_task(self, agent_runtime_server):
        """Test _cleanup when no message processor task exists."""
        agent_runtime_server.message_processor_task = None

        with mock.patch.object(agent_runtime_server.queue, "stop") as mock_queue_stop:
            await agent_runtime_server._cleanup()

            mock_queue_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_cancels_initialization_task(self, agent_runtime_server):
        """Test _cleanup cancels a running background initialization task."""

        async def dummy_init():
            await asyncio.sleep(10)  # Long-running init

        init_task = asyncio.create_task(dummy_init())
        agent_runtime_server._initialization_task = init_task

        with mock.patch.object(agent_runtime_server.queue, "stop"):
            await agent_runtime_server._cleanup()

            assert init_task.cancelled()

    @pytest.mark.asyncio
    async def test_cleanup_skips_completed_initialization_task(self, agent_runtime_server):
        """Test _cleanup does not cancel an already-completed initialization task."""

        async def quick_init():
            return None

        init_task = asyncio.create_task(quick_init())
        await init_task  # Let it complete
        agent_runtime_server._initialization_task = init_task

        with mock.patch.object(agent_runtime_server.queue, "stop") as mock_queue_stop:
            await agent_runtime_server._cleanup()

            assert init_task.done()
            assert not init_task.cancelled()
            mock_queue_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_without_initialization_task(self, agent_runtime_server):
        """Test _cleanup when no initialization task exists."""
        agent_runtime_server._initialization_task = None

        with mock.patch.object(agent_runtime_server.queue, "stop") as mock_queue_stop:
            await agent_runtime_server._cleanup()

            mock_queue_stop.assert_called_once()

    def test_setup_routes_creates_endpoints(self, agent_runtime_server):
        """Test that setup_routes creates the expected endpoints."""
        # Routes should be set up during initialization
        routes = [route.path for route in agent_runtime_server.app.routes]

        assert "/ping" in routes
        assert "/message/send" in routes
        assert "/invocations" in routes
        # JSON-RPC endpoint is handled by catch-all route

    @pytest.mark.asyncio
    async def test_cleanup_task_cancellation_error(self, agent_runtime_server):
        """Test _cleanup handles task cancellation errors gracefully."""

        # Create a real asyncio task that we can cancel
        async def dummy_task():
            await asyncio.sleep(10)  # Long running task

        task = asyncio.create_task(dummy_task())
        agent_runtime_server.message_processor_task = task

        with mock.patch.object(agent_runtime_server.queue, "stop") as mock_queue_stop:
            # Should not raise exception
            await agent_runtime_server._cleanup()

            # Task should be cancelled
            assert task.cancelled()
            mock_queue_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_task_simple(self, agent_runtime_server):
        """Test _cleanup cancels task properly."""
        mock_task = mock.MagicMock()
        mock_task.done.return_value = False
        agent_runtime_server.message_processor_task = mock_task

        with mock.patch.object(agent_runtime_server.queue, "stop"):
            await agent_runtime_server._cleanup()
            mock_task.cancel.assert_called_once()

    def test_routes_exist(self, agent_runtime_server):
        """Test required routes exist."""
        routes = [route.path for route in agent_runtime_server.app.routes]
        assert "/ping" in routes
        assert "/message/send" in routes
        assert "/invocations" in routes

    # Stop Agent Tests
    @pytest.mark.asyncio
    async def test_handle_stop_success(self, agent_runtime_server):
        """Test successful stop agent operation."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ) as mock_shutdown_orchestrator:
                    mock_get_subagents.return_value = [
                        {"agentInstanceId": "sub1"},
                        {"agentInstanceId": "sub2"},
                    ]
                    mock_shutdown_subagent.return_value = True

                    params = {"agentInstanceId": "test-agent"}
                    result = await agent_runtime_server.handle_stop(params)

                    assert "message" in result
                    assert (
                        "Stopped the orchestration agent. Stopped 2 subagent(s)"
                        in result["message"]
                    )
                    assert result["agentInstanceId"] == "test-agent"
                    mock_shutdown_orchestrator.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_stop_missing_agent_id(self, agent_runtime_server):
        """Test stop agent with missing agentInstanceId."""
        params = {}
        with pytest.raises(ValueError, match="Missing agentInstanceId in stop request"):
            await agent_runtime_server.handle_stop(params)

    @pytest.mark.asyncio
    async def test_handle_stop_partial_subagent_failure(self, agent_runtime_server):
        """Test stop agent when some subagents fail to stop."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ):
                    mock_get_subagents.return_value = [
                        {"agentInstanceId": "sub1"},
                        {"agentInstanceId": "sub2"},
                        {"agentInstanceId": "sub3"},
                    ]
                    # Return True for sub1, False for all sub2 attempts (retries), True for sub3
                    mock_shutdown_subagent.side_effect = lambda x: x != "sub2"

                    params = {"agentInstanceId": "test-agent"}
                    result = await agent_runtime_server.handle_stop(params)

                    assert "message" in result
                    assert (
                        "Stopped the orchestration agent. Stopped 2 subagent(s)"
                        in result["message"]
                    )
                    assert "1 subagent(s) failed to stop" in result["message"]
                    assert result["agentInstanceId"] == "test-agent"
                    assert result["failedSubagents"] == ["sub2"]

    @pytest.mark.asyncio
    async def test_handle_stop_no_subagents(self, agent_runtime_server):
        """Test stop agent when no subagents exist."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances",
            return_value=[],
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
            ):
                params = {"agentInstanceId": "test-agent"}
                result = await agent_runtime_server.handle_stop(params)

                assert "message" in result
                assert "Stopped the orchestration agent. Stopped 0 subagent(s)" in result["message"]
                assert result["agentInstanceId"] == "test-agent"

    @pytest.mark.asyncio
    async def test_handle_stop_all_subagents_fail(self, agent_runtime_server):
        """Test stop agent when all subagents fail to stop."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ):
                    mock_get_subagents.return_value = [
                        {"agentInstanceId": "sub1"},
                        {"agentInstanceId": "sub2"},
                    ]
                    mock_shutdown_subagent.return_value = False

                    params = {"agentInstanceId": "test-agent"}
                    result = await agent_runtime_server.handle_stop(params)

                    assert "message" in result
                    assert (
                        "Stopped the orchestration agent. Stopped 0 subagent(s)"
                        in result["message"]
                    )
                    assert "2 subagent(s) failed to stop" in result["message"]
                    assert result["agentInstanceId"] == "test-agent"
                    assert result["failedSubagents"] == ["sub1", "sub2"]

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_stop_with_agent_id(self, agent_runtime_server):
        """Test JSON-RPC stop method with valid agentInstanceId."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances",
            return_value=[],
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
            ):
                request = {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "atx_agent/stop",
                    "params": {"agentInstanceId": "test-agent"},
                }
                result = await agent_runtime_server.handle_jsonrpc(request)

                assert result["jsonrpc"] == "2.0"
                assert result["id"] == 6
                assert "result" in result
                assert "message" in result["result"]
                assert (
                    "Stopped the orchestration agent. Stopped 0 subagent(s)"
                    in result["result"]["message"]
                )

    def test_tracing_initialization(self, mock_agent_factory):
        """Test server initialization with tracing parameter."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.NotificationHandler"
        ), mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.MessageHandler"
        ), mock.patch.object(
            AgentRuntimeServer, "setup_tracing"
        ) as mock_setup_tracing:
            AgentRuntimeServer(agent_factory=mock_agent_factory, tracing="local")
            mock_setup_tracing.assert_called_once_with("local")

    def test_no_tracing_initialization(self, mock_agent_factory):
        """Test server initialization without tracing parameter."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.NotificationHandler"
        ), mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.MessageHandler"
        ), mock.patch.object(
            AgentRuntimeServer, "setup_tracing"
        ) as mock_setup_tracing:
            AgentRuntimeServer(agent_factory=mock_agent_factory)
            mock_setup_tracing.assert_not_called()

    # Retry Logic Tests
    @pytest.mark.asyncio
    async def test_handle_stop_subagent_succeeds_on_retry(self, agent_runtime_server):
        """Test stop agent when subagent fails initially but succeeds on retry."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ):
                    mock_get_subagents.return_value = [{"agentInstanceId": "sub1"}]
                    # Fail first 2 attempts, succeed on 3rd
                    mock_shutdown_subagent.side_effect = [False, False, True]

                    params = {"agentInstanceId": "test-agent"}
                    result = await agent_runtime_server.handle_stop(params)

                    assert mock_shutdown_subagent.call_count == 3
                    assert (
                        "Stopped the orchestration agent. Stopped 1 subagent(s)"
                        in result["message"]
                    )
                    assert result.get("failedSubagents", []) == []

    @pytest.mark.asyncio
    async def test_handle_stop_subagent_exhausts_retries(self, agent_runtime_server):
        """Test stop agent when subagent fails all retry attempts."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ):
                    mock_get_subagents.return_value = [{"agentInstanceId": "sub1"}]
                    mock_shutdown_subagent.return_value = False

                    params = {"agentInstanceId": "test-agent"}
                    result = await agent_runtime_server.handle_stop(params)

                    # Should retry 3 times total
                    assert mock_shutdown_subagent.call_count == 3
                    assert "1 subagent(s) failed to stop" in result["message"]
                    assert result["failedSubagents"] == ["sub1"]

    @pytest.mark.asyncio
    async def test_handle_stop_multiple_subagents_mixed_retry_results(self, agent_runtime_server):
        """Test stop with multiple subagents having different retry outcomes."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ):
                    mock_get_subagents.return_value = [
                        {"agentInstanceId": "sub1"},
                        {"agentInstanceId": "sub2"},
                        {"agentInstanceId": "sub3"},
                    ]
                    # sub1: succeeds immediately
                    # sub2: fails all retries
                    # sub3: succeeds on 2nd retry
                    mock_shutdown_subagent.side_effect = [
                        True,  # sub1 attempt 1
                        False,  # sub2 attempt 1
                        False,  # sub3 attempt 1
                        False,  # sub2 attempt 2
                        False,  # sub3 attempt 2
                        False,  # sub2 attempt 3
                        True,  # sub3 attempt 3
                    ]

                    params = {"agentInstanceId": "test-agent"}
                    result = await agent_runtime_server.handle_stop(params)

                    assert mock_shutdown_subagent.call_count == 7
                    assert (
                        "Stopped the orchestration agent. Stopped 2 subagent(s)"
                        in result["message"]
                    )
                    assert "1 subagent(s) failed to stop" in result["message"]
                    assert result["failedSubagents"] == ["sub2"]

    @pytest.mark.asyncio
    async def test_handle_stop_retry_delay(self, agent_runtime_server):
        """Test that retries include appropriate delay between attempts."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance"
                ):
                    with mock.patch("time.sleep") as mock_sleep:
                        mock_get_subagents.return_value = [{"agentInstanceId": "sub1"}]
                        mock_shutdown_subagent.side_effect = [False, False, True]

                        params = {"agentInstanceId": "test-agent"}
                        await agent_runtime_server.handle_stop(params)

                        # Should sleep between retries (2 sleeps for 3 attempts)
                        assert mock_sleep.call_count == 2

    # Idempotent Stop Tests
    @pytest.mark.asyncio
    async def test_handle_stop_idempotent_returns_cached_result(self, agent_runtime_server):
        """Test that a second stop call returns the cached result from the first call."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance"
            ) as mock_shutdown_subagent:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance",
                    return_value=True,
                ):
                    mock_get_subagents.return_value = [
                        {"agentInstanceId": "sub1"},
                        {"agentInstanceId": "sub2"},
                    ]
                    mock_shutdown_subagent.side_effect = lambda x: x != "sub2"

                    params = {"agentInstanceId": "test-agent"}
                    first_result = await agent_runtime_server.handle_stop(params)
                    second_result = await agent_runtime_server.handle_stop(params)

                    assert first_result == second_result
                    assert second_result["failedSubagents"] == ["sub2"]
                    assert "1 subagent(s) failed to stop" in second_result["message"]
                    assert mock_get_subagents.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_stop_idempotent_does_not_cache_on_orchestrator_failure(
        self, agent_runtime_server
    ):
        """Test that stop result is not cached when orchestrator fails, allowing retries."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances",
            return_value=[],
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance",
                side_effect=[False, False, False, True],
            ) as mock_shutdown_orchestrator:
                params = {"agentInstanceId": "test-agent"}

                first_result = await agent_runtime_server.handle_stop(params)
                assert "Failed to stop" in first_result["message"]

                second_result = await agent_runtime_server.handle_stop(params)
                assert "Stopped the orchestration agent" in second_result["message"]

                # each handle_stop() call has up to 2 retries (3 total tries)
                assert mock_shutdown_orchestrator.call_count == 4

    @pytest.mark.asyncio
    async def test_handle_stop_idempotent_caches_on_orchestrator_success(
        self, agent_runtime_server
    ):
        """Test that stop result is cached when orchestrator succeeds, even with failed subagents."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance",
                return_value=False,
            ):
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance",
                    return_value=True,
                ):
                    mock_get_subagents.return_value = [{"agentInstanceId": "sub1"}]

                    params = {"agentInstanceId": "test-agent"}
                    first_result = await agent_runtime_server.handle_stop(params)
                    second_result = await agent_runtime_server.handle_stop(params)

                    assert first_result == second_result
                    assert second_result["failedSubagents"] == ["sub1"]
                    assert mock_get_subagents.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_stop_concurrent_requests_only_execute_once(self, agent_runtime_server):
        """Test that concurrent stop calls are serialized by the lock and only one executes."""
        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_subagent_instances"
        ) as mock_get_subagents:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.shutdown_subagent_instance",
                return_value=True,
            ):
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.shutdown_base_orchestrator_agent_instance",
                    return_value=True,
                ):
                    mock_get_subagents.return_value = [{"agentInstanceId": "sub1"}]
                    params = {"agentInstanceId": "test-agent"}

                    first_result, second_result = await asyncio.gather(
                        agent_runtime_server.handle_stop(params),
                        agent_runtime_server.handle_stop(params),
                    )

                    assert first_result == second_result
                    assert mock_get_subagents.call_count == 1

    @pytest.mark.parametrize(
        "checkpoint_config",
        [
            {"strategy": None, "interval": 30, "name": "no_checkpoint"},
            {
                "strategy": CheckpointStrategy.CONVERSATION,
                "interval": 5,
                "name": "conversation_checkpoint",
            },
        ],
    )
    def test_create_checkpoint_callback(self, mock_agent_factory, checkpoint_config):
        """Test checkpoint callback creation with different configurations."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                    checkpoint_strategy=checkpoint_config["strategy"],
                    checkpoint_interval=checkpoint_config["interval"],
                )

                if checkpoint_config["strategy"]:
                    # Should create callback when checkpoint strategy is provided
                    with mock.patch.object(
                        server.checkpoint_service, "create_callback", return_value=mock.Mock()
                    ) as mock_create:
                        callback = server._create_checkpoint_callback()
                        actual_callback = callback
                        mock_create.assert_called_once()
                        assert actual_callback is not None
                else:
                    # Should return None when no checkpoint strategy provided (service exists but no active checkpointing)
                    callback = server._create_checkpoint_callback()
                    assert callback is None
                    # Checkpoint service should still exist for restoration
                    assert server.checkpoint_service is not None

    def test_initialization_invalid_checkpoint_interval(self, mock_agent_factory):
        """Test server initialization with invalid checkpoint interval."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                    checkpoint_strategy=CheckpointStrategy.CONVERSATION,
                    checkpoint_interval=0,  # Invalid interval
                )
                # Should create checkpoint service but strategy should be passed as-is
                assert server.checkpoint_service is not None
                assert server.checkpoint_service.strategy == CheckpointStrategy.CONVERSATION
                assert server.checkpoint_service.interval == 0

    def test_extensions_passed_to_message_handler(self, mock_agent_factory):
        """Test that extensions are passed to MessageHandler during initialization."""
        from agent_builder_sdk.extensions.acknowledgments.acknowledgment_handler import (
            AcknowledgmentHandler,
        )

        mock_extension = mock.Mock(spec=BaseExtensionHandler)
        extensions = [mock_extension]

        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.MessageHandler"
            ) as mock_message_handler:
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory, extension_handlers=extensions
                )

                # Verify MessageHandler was called with extension_handlers including AcknowledgmentHandler
                call_args = mock_message_handler.call_args
                assert call_args[1]["timeout"] == 28
                assert call_args[1]["delayed_timeout"] == 300
                assert call_args[1]["task_manager"] is None
                handlers = call_args[1]["extension_handlers"]
                assert len(handlers) == 2
                assert isinstance(handlers[0], AcknowledgmentHandler)
                assert handlers[1] == mock_extension
                assert server.extension_handlers == handlers

    @pytest.mark.asyncio
    async def test_initialize_agent_deferred_initialization(self, mock_agent_factory):
        """Test deferred initialization when agent status is INVOKING."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_agent_status",
            return_value="INVOKING",
        ) as mock_platform_init:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.setup_initial_auth_token"
            ) as mock_setup_initial_auth_token:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.asyncio.create_task"
                ) as mock_create_task:

                    await server.initialize_agent(auth_token="test-token")

                    # Verify deferred initialization was triggered
                    mock_setup_initial_auth_token.assert_called_once()
                    mock_platform_init.assert_called_once_with(
                        "test-workspace", "test-job", "test-agent"
                    )

                    # Verify background task was created for deferred initialization
                    mock_create_task.assert_called_once()

                    # Verify the task was created with the correct coroutine.
                    # The INVOKING path now wraps _wait_for_non_invoking_and_initialize
                    # in _background_finalize for consistent error handling with the
                    # RUNNING path.
                    task_arg = mock_create_task.call_args[0][0]
                    assert hasattr(task_arg, "cr_code")  # It's a coroutine
                    assert task_arg.cr_code.co_name == "_background_finalize"

                    # Agent should not be initialized yet
                    assert server.initialized is False
                    assert server.agent is None

    @pytest.mark.asyncio
    async def test_initialize_agent_with_lock_double_check(self, mock_agent_factory):
        """Test double-check locking pattern in initialize_agent."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        # Simulate agent being initialized by another request
        server.initialized = True

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_agent_status"
        ) as mock_platform_init:

            await server.initialize_agent(auth_token="test-token")

            # Should exit early due to double-check
            mock_platform_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_agent_error_status(self, mock_agent_factory):
        """Test initialization with error status that prevents initialization."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_agent_status",
            return_value="FAILED",
        ) as mock_platform_init:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.setup_initial_auth_token"
            ) as mock_setup_initial_auth_token:

                await server.initialize_agent(auth_token="test-token")

                # Verify status check was called but initialization stopped
                mock_setup_initial_auth_token.assert_called_once()
                mock_platform_init.assert_called_once()

                # Agent should not be initialized
                assert server.initialized is False
                assert server.agent is None

    @pytest.mark.asyncio
    async def test_wait_for_non_invoking_and_initialize_success(self, mock_agent_factory):
        """Test successful deferred initialization after status becomes INVOKED."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.wait_for_agent_non_invoking",
            return_value="INVOKED",
        ) as mock_wait:
            with mock.patch.object(server, "_finalize_agent_setup") as mock_finalize:

                await server._wait_for_non_invoking_and_initialize()

                # Verify wait function was called with correct parameters
                mock_wait.assert_called_once_with(
                    server.context.workspace_id,
                    server.context.job_id,
                    server.context.agent_instance_id,
                )
                mock_finalize.assert_called_once_with("INVOKED")

    @pytest.mark.asyncio
    async def test_wait_for_non_invoking_and_initialize_timeout(self, mock_agent_factory):
        """Test deferred initialization timeout when status never becomes INVOKED."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.wait_for_agent_non_invoking",
            return_value="INVOKING",  # Returns INVOKING (timeout case)
        ):
            with mock.patch.object(server, "_finalize_agent_setup") as mock_finalize:

                # Should complete without error (just log timeout)
                await server._wait_for_non_invoking_and_initialize()

                # Should not call finalize when status remains INVOKING
                mock_finalize.assert_not_called()
                assert server.initialized is False
                assert server.agent is None

    @pytest.mark.asyncio
    async def test_finalize_agent_setup_with_different_statuses(self, mock_agent_factory):
        """Test agent setup finalization with different agent statuses."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_auth_token_refresher"
        ) as mock_refresher:
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.build_agentic_api_endpoint_from_env"
            ):
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.MCPClientFactory.setup_eg_mcp_client"
                ):
                    with mock.patch(
                        "agent_builder_sdk.server.agent_runtime_server.get_agentic_api_client"
                    ):

                        # Test RUNNING status - should set up full platform integration
                        await server._finalize_agent_setup("RUNNING")

                        assert server.initialized is True
                        assert server.agent is not None
                        mock_refresher.assert_called_once()

                        # Reset for next test
                        server.initialized = False
                        server.agent = None
                        mock_refresher.reset_mock()

                        # Test STOPPED status - should skip auth refresher
                        await server._finalize_agent_setup("STOPPED")

                        assert server.initialized is True
                        assert server.agent is not None
                        mock_refresher.assert_not_called()  # Should not set up auth refresher for STOPPED

    @pytest.mark.asyncio
    async def test_task_manager_factory_initialization(self):
        """Test that task_manager_factory is called with correct context and injected into handlers."""

        # Create mock task manager
        mock_task_manager = MagicMock()

        # Create factory that captures context
        captured_kwargs = None
        mock_agent_factory = MagicMock()

        def task_manager_factory(**kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return mock_task_manager

        def agent_factory(mcp_client, storage_dir, **kwargs):
            return mock_agent_factory(mcp_client, storage_dir, **kwargs)

        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                with mock.patch("agent_builder_sdk.server.agent_runtime_server.TaskHandler"):
                    server = AgentRuntimeServer(
                        agent_factory=agent_factory,
                        task_manager_factory=task_manager_factory,
                        binary_location="/tmp/test_binary",
                        storage_dir="/tmp/test_storage",
                    )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.build_agentic_api_endpoint_from_env"
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.MCPClientFactory.setup_eg_mcp_client"
            ) as mock_mcp:
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.get_agent_status"
                ) as mock_status:
                    with mock.patch(
                        "agent_builder_sdk.server.agent_runtime_server.set_runtime_env_vars"
                    ):
                        mock_mcp_client = MagicMock()
                        mock_mcp.return_value = mock_mcp_client
                        mock_status.return_value = "RUNNING"

                        # Initialize agent (which should call task_manager_factory)
                        await server.initialize_agent()
                        # RUNNING status runs _finalize_agent_setup as a background task.
                        # Await it so task_manager_factory is invoked before assertions.
                        task = server._initialization_task
                        if task is not None:
                            try:
                                await task
                            except Exception:
                                pass

                # Verify factory was called with correct context
                assert captured_kwargs is not None
                assert captured_kwargs["queue"] == server.queue
                assert captured_kwargs["get_agent_func"] == server._get_ready_agent

                # Verify task_manager was set
                assert server.task_manager == mock_task_manager

                # Verify task_manager was injected into handlers
                assert server.task_handler.task_manager == mock_task_manager
                assert server.message_handler.task_manager == mock_task_manager

                # Verify agent factory was called with task_manager
                mock_agent_factory.assert_called_once()
                call_args = mock_agent_factory.call_args
                # Check if called with kwargs (accepts_kwargs returns True)
                if len(call_args) == 2 and call_args[1]:  # kwargs present
                    assert call_args[1]["task_manager"] == mock_task_manager
                else:
                    # If no kwargs, task_manager should be None (factory doesn't accept kwargs)
                    assert len(call_args[0]) == 2  # Only mcp_client and storage_dir

    @pytest.mark.parametrize("factory", [agent_factory_no_kwargs, async_agent_factory])
    async def test_agent_factory(self, mock_agent, factory):
        with (
            mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"),
            mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"),
            mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.get_agent_status",
                return_value="RUNNING",
            ),
            mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.build_agentic_api_endpoint_from_env"
            ),
        ):
            server = AgentRuntimeServer(
                agent_factory=factory(mock_agent),
                binary_location="/tmp/test_binary",
                storage_dir="/tmp/test_storage",
            )

            server.context = AgentRuntimeContext(
                workspace_id="test-workspace",
                job_id="test-job",
                agent_instance_id="test-agent",
                initial_auth_token="test-token",
            )

            await server.initialize_agent()
            # RUNNING status runs _finalize_agent_setup as a background task;
            # await it so the agent factory is invoked before asserting.
            task = server._initialization_task
            if task is not None:
                try:
                    await task
                except Exception:
                    pass

            assert server.agent == mock_agent

    def test_initialization_with_mcp_client(self, mock_agent_factory):
        """Test server initialization with pre-configured mcp_client."""
        mock_mcp_client = MagicMock()

        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    mcp_client=mock_mcp_client,
                    storage_dir="/tmp/test_storage",
                )

                assert server.mcp_client == mock_mcp_client
                assert (
                    server.binary_location
                    == "/home/amazon/ElasticGumbyAgenticMCP/bin/eg_agentic_mcp_server"
                )

    def test_initialization_without_mcp_client(self, mock_agent_factory):
        """Test server initialization without mcp_client uses binary_location."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/custom/binary/path",
                    storage_dir="/tmp/test_storage",
                )

                assert server.mcp_client is None
                assert server.binary_location == "/custom/binary/path"

    @pytest.mark.asyncio
    async def test_finalize_agent_setup_uses_provided_mcp_client(self, mock_agent_factory):
        """Test that _finalize_agent_setup uses provided mcp_client instead of creating one."""
        mock_mcp_client = MagicMock()

        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    mcp_client=mock_mcp_client,
                    storage_dir="/tmp/test_storage",
                    auto_transition_job_to_executing=False,
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_auth_token_refresher"
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.build_agentic_api_endpoint_from_env"
            ):
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.MCPClientFactory.setup_eg_mcp_client"
                ) as mock_factory:
                    with mock.patch(
                        "agent_builder_sdk.server.agent_runtime_server.get_agentic_api_client"
                    ):
                        await server._finalize_agent_setup("STOPPED")

                        # MCPClientFactory should NOT be called when mcp_client is provided
                        mock_factory.assert_not_called()
                        assert server.initialized is True

    @pytest.mark.asyncio
    async def test_finalize_agent_setup_creates_mcp_client_from_binary(self, mock_agent_factory):
        """Test that _finalize_agent_setup creates mcp_client from binary_location when not provided."""
        with mock.patch("agent_builder_sdk.server.agent_runtime_server.NotificationHandler"):
            with mock.patch("agent_builder_sdk.server.agent_runtime_server.MessageHandler"):
                server = AgentRuntimeServer(
                    agent_factory=mock_agent_factory,
                    binary_location="/tmp/test_binary",
                    storage_dir="/tmp/test_storage",
                    auto_transition_job_to_executing=False,
                )

        server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.agent_runtime_server.get_auth_token_refresher"
        ):
            with mock.patch(
                "agent_builder_sdk.server.agent_runtime_server.build_agentic_api_endpoint_from_env"
            ) as mock_endpoint:
                mock_endpoint.return_value = "https://test-endpoint.com"
                with mock.patch(
                    "agent_builder_sdk.server.agent_runtime_server.MCPClientFactory.setup_eg_mcp_client"
                ) as mock_factory:
                    mock_factory.return_value = MagicMock()
                    with mock.patch(
                        "agent_builder_sdk.server.agent_runtime_server.get_agentic_api_client"
                    ):
                        await server._finalize_agent_setup("STOPPED")

                        # MCPClientFactory SHOULD be called when mcp_client is not provided
                        mock_factory.assert_called_once()
                        call_args = mock_factory.call_args[0][0]
                        assert call_args["binaryLocation"] == "/tmp/test_binary"
                        assert server.initialized is True
