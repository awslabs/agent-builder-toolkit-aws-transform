# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Stateless Agent Runtime Server implementation.

Tests the StatelessAgentRuntimeServer class which provides compatibility with multiple
agent execution environments through JSON-RPC endpoints.
"""

from unittest import mock

import pytest

from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.server.stateless_agent_runtime_server import StatelessAgentRuntimeServer


@pytest.fixture
def mock_subagent():
    """Mock subagent for testing."""
    subagent = mock.Mock()
    subagent.process_message.return_value = mock.Mock()
    return subagent


@pytest.fixture
def mock_subagent_factory():
    """Mock subagent factory for testing."""

    def factory(mcp_client, storage_dir):
        subagent = mock.Mock()
        subagent.process_message.return_value = mock.Mock()
        return subagent

    return factory


@pytest.fixture
def stateless_agent_runtime_server(mock_subagent_factory):
    """Create Stateless Agent Runtime Server instance for testing."""
    with mock.patch("agent_builder_sdk.server.stateless_agent_runtime_server.MessageHandler"):
        server = StatelessAgentRuntimeServer(
            agent_factory=mock_subagent_factory,
            binary_location="/tmp/test_binary",
            storage_dir="/tmp/test_storage",
        )
        return server


class TestStatelessAgentRuntimeServer:
    """Test cases for StatelessAgentRuntimeServer compatibility and functionality."""

    def test_initialization(self, stateless_agent_runtime_server):
        """Test server initialization."""
        assert stateless_agent_runtime_server.binary_location == "/tmp/test_binary"
        assert stateless_agent_runtime_server.storage_dir == "/tmp/test_storage"
        assert stateless_agent_runtime_server.agent is None
        assert stateless_agent_runtime_server.initialized is False
        assert stateless_agent_runtime_server.agent_factory is not None

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_healthcheck(self, stateless_agent_runtime_server):
        """Test JSON-RPC healthcheck method."""
        request = {"jsonrpc": "2.0", "id": 1, "method": "atx_agent/healthcheck", "params": {}}

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] == {"agentHealth": "HEALTHY"}

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_message_send(self, stateless_agent_runtime_server):
        """Test JSON-RPC message send method."""
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
        stateless_agent_runtime_server.message_handler = mock_handler

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

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 3
        assert "result" in result
        mock_handler.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_method_not_found(self, stateless_agent_runtime_server):
        """Test JSON-RPC with unknown method."""
        request = {"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}}

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 4
        assert "error" in result
        assert result["error"]["code"] == -32601  # Method not found

    @pytest.mark.asyncio
    async def test_initialize_agent(self, stateless_agent_runtime_server):
        """Test agent initialization."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch.dict(
            "os.environ",
            {
                "QT_AGENTIC_API_ENDPOINT": "https://test-endpoint.com",
                "AUTH_TOKEN_FILE": "/tmp/test-token",
            },
        ):
            with mock.patch("builtins.open", mock.mock_open(read_data="test-token")):
                with mock.patch("pathlib.Path.exists", return_value=True):
                    with mock.patch(
                        "agent_builder_sdk.server.stateless_agent_runtime_server.setup_initial_auth_token"
                    ) as mock_setup_token:
                        with mock.patch(
                            "agent_builder_sdk.server.stateless_agent_runtime_server.get_agent_status",
                            return_value="RUNNING",
                        ) as mock_get_status:
                            with mock.patch(
                                "agent_builder_sdk.server.stateless_agent_runtime_server.build_agentic_api_endpoint_from_env"
                            ) as mock_endpoint:
                                mock_endpoint.return_value = "https://test-endpoint.com"
                                with mock.patch(
                                    "agent_builder_sdk.server.stateless_agent_runtime_server.MCPClientFactory.setup_ab_mcp_client"
                                ) as mock_mcp:
                                    with mock.patch(
                                        "agent_builder_sdk.server.stateless_agent_runtime_server.get_agentic_api_client"
                                    ):
                                        with mock.patch(
                                            "agent_builder_sdk.server.stateless_agent_runtime_server.JobManager"
                                        ) as mock_job_manager_class:
                                            mock_job_manager = mock.Mock()
                                            mock_job_manager.transition_to_executing_if_assessing = (
                                                mock.Mock()
                                            )
                                            mock_job_manager_class.return_value = mock_job_manager
                                            mock_mcp.return_value = mock.Mock()

                                            await stateless_agent_runtime_server.initialize_agent(
                                                auth_token="test-token"
                                            )

                                            mock_setup_token.assert_called_once_with("test-token")
                                            mock_get_status.assert_called_once()
                                            assert (
                                                stateless_agent_runtime_server.initialized is True
                                            )

    @pytest.mark.asyncio
    async def test_extract_and_initialize_valid_request(self, stateless_agent_runtime_server):
        """Test extracting initialization context from valid request."""
        request = {
            "method": "atx_agent/invoke",
            "params": {
                "invocationContext": {
                    "jobMetadata": {"workspaceId": "test-workspace", "jobId": "test-job"},
                    "authorizationToken": "test-token",
                },
                "agentInstanceId": "test-agent",
            },
        }

        with mock.patch.object(stateless_agent_runtime_server, "initialize_agent") as mock_init:
            await stateless_agent_runtime_server.extract_and_initialize(request)
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_and_initialize_missing_fields(self, stateless_agent_runtime_server):
        """Test extracting initialization context with missing fields."""
        request = {
            "method": "atx_agent/invoke",
            "params": {
                "invocationContext": {
                    "jobMetadata": {
                        "workspaceId": None,  # Missing required field
                        "jobId": "test-job",
                    }
                },
                "agentInstanceId": "test-agent",
            },
        }

        with mock.patch.object(stateless_agent_runtime_server, "initialize_agent") as mock_init:
            with pytest.raises(ValueError, match="Missing required initialization context"):
                await stateless_agent_runtime_server.extract_and_initialize(request)
            mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_invalid_request(self, stateless_agent_runtime_server):
        """Test JSON-RPC with invalid request format."""
        request = {"invalid": "request"}

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert "error" in result
        assert result["error"]["code"] == -32603  # Internal error

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_restore_method(self, stateless_agent_runtime_server):
        """Test JSON-RPC restore method."""
        request = {"jsonrpc": "2.0", "id": 5, "method": "atx_agent/restore", "params": {}}

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 5
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_tasks_get_method(self, stateless_agent_runtime_server):
        """Test JSON-RPC tasks get method."""
        from agent_builder_sdk.custom_types.common_types import A2AErrorCode

        request = {"jsonrpc": "2.0", "id": 7, "method": "tasks/get", "params": {}}

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 7
        assert result["result"]["code"] == A2AErrorCode.INVALID_REQUEST
        assert "Missing required parameter: id" in result["result"]["message"]

    @pytest.mark.asyncio
    async def test_setup_routes(self, stateless_agent_runtime_server):
        """Test that routes are properly set up."""
        routes = [route.path for route in stateless_agent_runtime_server.app.routes]
        assert "/ping" in routes
        assert "/invocations" in routes

    @pytest.mark.asyncio
    async def test_ping_endpoint(self, stateless_agent_runtime_server):
        """Test ping endpoint returns correct response."""
        from fastapi.testclient import TestClient

        client = TestClient(stateless_agent_runtime_server.app)
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"status": "HealthyBusy"}

    @pytest.mark.asyncio
    async def test_handle_invocations_not_initialized(self, stateless_agent_runtime_server):
        """Test invocations when server not initialized."""
        from fastapi.testclient import TestClient

        stateless_agent_runtime_server.initialized = False

        with mock.patch.object(
            stateless_agent_runtime_server, "extract_and_initialize"
        ) as mock_extract:
            with mock.patch.object(stateless_agent_runtime_server, "handle_jsonrpc") as mock_handle:
                mock_handle.return_value = {"result": "success"}

                client = TestClient(stateless_agent_runtime_server.app)
                response = client.post(
                    "/invocations", json={"jsonrpc": "2.0", "method": "test", "id": 1}
                )

                assert response.status_code == 200
                mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_invocations_invalid_format(self, stateless_agent_runtime_server):
        """Test invocations with invalid request format."""
        from fastapi.testclient import TestClient

        stateless_agent_runtime_server.initialized = True

        client = TestClient(stateless_agent_runtime_server.app)
        response = client.post("/invocations", json={"invalid": "request"})

        assert response.status_code == 200
        assert response.json() == {"status": "acknowledged"}

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_message_send_error(self, stateless_agent_runtime_server):
        """Test JSON-RPC message send with error."""
        mock_handler = mock.Mock()
        mock_error = mock.Mock()
        mock_error.code = "TEST_ERROR"
        mock_error.message = "Test error message"
        mock_handler.send_message = mock.AsyncMock(
            return_value=mock.Mock(error=mock_error, result=None)
        )
        stateless_agent_runtime_server.message_handler = mock_handler

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {"role": "user", "parts": [], "messageId": "test", "kind": "message"}
            },
        }

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_invoke_method(self, stateless_agent_runtime_server):
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

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] is None

    def test_start_method(self, stateless_agent_runtime_server):
        """Test start method starts uvicorn."""
        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.uvicorn"
        ) as mock_uvicorn:
            stateless_agent_runtime_server.start()
            mock_uvicorn.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_and_initialize_job_metadata_format(self, stateless_agent_runtime_server):
        """Test extracting initialization context from jobMetadata format."""
        request = {
            "method": "atx_agent/notify",
            "params": {
                "jobMetadata": {"workspaceId": "test-workspace", "jobId": "test-job"},
                "agentInstanceId": "test-agent",
            },
        }

        with mock.patch.object(stateless_agent_runtime_server, "initialize_agent") as mock_init:
            await stateless_agent_runtime_server.extract_and_initialize(request)
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_and_initialize_message_metadata_format(
        self, stateless_agent_runtime_server
    ):
        """Test extracting initialization context from message metadata format."""
        request = {
            "method": "message/send",
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

        with mock.patch.object(stateless_agent_runtime_server, "initialize_agent") as mock_init:
            await stateless_agent_runtime_server.extract_and_initialize(request)
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_agent_no_context(self, stateless_agent_runtime_server):
        """Test initialize_agent raises error when no context set."""
        stateless_agent_runtime_server.context = None

        with pytest.raises(ValueError, match="Agent context not set"):
            await stateless_agent_runtime_server.initialize_agent()

    @pytest.mark.asyncio
    async def test_initialize_agent_status_check_exception(self, stateless_agent_runtime_server):
        """Test initialize_agent when get_agent_status raises exception."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.setup_initial_auth_token"
        ):
            with mock.patch(
                "agent_builder_sdk.server.stateless_agent_runtime_server.get_agent_status",
                side_effect=Exception("Status check failed"),
            ):

                await stateless_agent_runtime_server.initialize_agent(auth_token="test-token")

                # Should not be initialized when status check fails
                assert stateless_agent_runtime_server.initialized is False

    @pytest.mark.asyncio
    async def test_agent_factory_with_kwargs(self, stateless_agent_runtime_server):
        """Test agent factory that accepts kwargs."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        def factory_with_kwargs(mcp_client, storage_dir, **kwargs):
            agent = mock.Mock()
            agent.workspace_id = kwargs.get("workspace_id")
            return agent

        stateless_agent_runtime_server.agent_factory = factory_with_kwargs
        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch.dict(
            "os.environ",
            {
                "QT_AGENTIC_API_ENDPOINT": "https://test-endpoint.com",
                "AUTH_TOKEN_FILE": "/tmp/test-token",
            },
        ):
            with mock.patch("builtins.open", mock.mock_open(read_data="test-token")):
                with mock.patch("pathlib.Path.exists", return_value=True):
                    with mock.patch(
                        "agent_builder_sdk.server.stateless_agent_runtime_server.setup_initial_auth_token"
                    ):
                        with mock.patch(
                            "agent_builder_sdk.server.stateless_agent_runtime_server.get_agent_status",
                            return_value="RUNNING",
                        ):
                            with mock.patch(
                                "agent_builder_sdk.server.stateless_agent_runtime_server.build_agentic_api_endpoint_from_env"
                            ) as mock_endpoint:
                                mock_endpoint.return_value = "https://test-endpoint.com"
                                with mock.patch(
                                    "agent_builder_sdk.server.stateless_agent_runtime_server.MCPClientFactory.setup_ab_mcp_client"
                                ) as mock_mcp:
                                    with mock.patch(
                                        "agent_builder_sdk.server.stateless_agent_runtime_server.get_agentic_api_client"
                                    ):
                                        with mock.patch(
                                            "agent_builder_sdk.server.stateless_agent_runtime_server.JobManager"
                                        ) as mock_job_manager_class:
                                            mock_job_manager = mock.Mock()
                                            mock_job_manager.transition_to_executing_if_assessing = (
                                                mock.Mock()
                                            )
                                            mock_job_manager_class.return_value = mock_job_manager
                                            mock_mcp.return_value = mock.Mock()

                                            await stateless_agent_runtime_server.initialize_agent(
                                                auth_token="test-token"
                                            )

                                            assert (
                                                stateless_agent_runtime_server.agent.workspace_id
                                                == "test-workspace"
                                            )

    @pytest.mark.asyncio
    async def test_handle_jsonrpc_message_send_no_handler(self, stateless_agent_runtime_server):
        """Test JSON-RPC message send with no message handler."""
        stateless_agent_runtime_server.message_handler = None

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {"role": "user", "parts": [], "messageId": "test", "kind": "message"}
            },
        }

        result = await stateless_agent_runtime_server.handle_jsonrpc(request)

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_extract_and_initialize_tasks_metadata_format(
        self, stateless_agent_runtime_server
    ):
        """Test extracting initialization context from tasks metadata format."""
        request = {
            "method": "tasks/get",
            "params": {
                "metadata": {
                    "agentInitializationContext": {
                        "jobMetadata": {"workspaceId": "test-workspace", "jobId": "test-job"},
                        "agentInstanceId": "test-agent",
                        "authorizationToken": "test-token",
                    }
                }
            },
        }

        with mock.patch.object(stateless_agent_runtime_server, "initialize_agent") as mock_init:
            await stateless_agent_runtime_server.extract_and_initialize(request)
            mock_init.assert_called_once()

    def test_tracing_initialization(self, mock_subagent_factory):
        """Test server initialization with tracing parameter."""
        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.MessageHandler"
        ), mock.patch.object(StatelessAgentRuntimeServer, "setup_tracing") as mock_setup_tracing:
            StatelessAgentRuntimeServer(agent_factory=mock_subagent_factory, tracing="local")
            mock_setup_tracing.assert_called_once_with("local")

    def test_no_tracing_initialization(self, mock_subagent_factory):
        """Test server initialization without tracing parameter."""
        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.MessageHandler"
        ), mock.patch.object(StatelessAgentRuntimeServer, "setup_tracing") as mock_setup_tracing:
            StatelessAgentRuntimeServer(agent_factory=mock_subagent_factory)
            mock_setup_tracing.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_agent_invoked_status(self, stateless_agent_runtime_server):
        """Test agent initialization when status is INVOKED - should set to RUNNING."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.get_agent_status",
            return_value="INVOKED",
        ) as mock_get_status:
            with mock.patch(
                "agent_builder_sdk.server.stateless_agent_runtime_server.build_agentic_api_endpoint_from_env"
            ) as mock_endpoint:
                mock_endpoint.return_value = "https://test-endpoint.com"

                with mock.patch(
                    "agent_builder_sdk.server.stateless_agent_runtime_server.MCPClientFactory.setup_ab_mcp_client"
                ) as mock_mcp:
                    with mock.patch(
                        "agent_builder_sdk.server.stateless_agent_runtime_server.set_agent_running"
                    ) as mock_set_running:
                        with mock.patch(
                            "agent_builder_sdk.server.stateless_agent_runtime_server.get_agentic_api_client"
                        ):
                            with mock.patch(
                                "agent_builder_sdk.server.stateless_agent_runtime_server.JobManager"
                            ) as mock_job_manager_class:
                                mock_job_manager = mock.Mock()
                                mock_job_manager.transition_to_executing_if_assessing = mock.Mock()
                                mock_job_manager_class.return_value = mock_job_manager
                                mock_mcp.return_value = mock.Mock()

                                await stateless_agent_runtime_server.initialize_agent(
                                    auth_token="test-token"
                                )

                                # Verify immediate initialization
                                mock_get_status.assert_called_once_with(
                                    "test-workspace", "test-job", "test-agent"
                                )

                                # Verify set_agent_running WAS called for INVOKED status
                                mock_set_running.assert_called_once_with(
                                    "test-workspace", "test-job", "test-agent"
                                )

                                # Agent should be initialized
                                assert stateless_agent_runtime_server.initialized is True
                                assert stateless_agent_runtime_server.agent is not None

    @pytest.mark.asyncio
    async def test_initialize_agent_deferred_initialization(self, stateless_agent_runtime_server):
        """Test deferred initialization when agent status is INVOKING."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.get_agent_status",
            return_value="INVOKING",
        ) as mock_get_status:
            with mock.patch(
                "agent_builder_sdk.server.stateless_agent_runtime_server.setup_initial_auth_token"
            ) as mock_setup_initial_auth_token:
                with mock.patch(
                    "agent_builder_sdk.server.stateless_agent_runtime_server.asyncio.create_task"
                ) as mock_create_task:

                    await stateless_agent_runtime_server.initialize_agent(auth_token="test-token")

                    # Verify deferred initialization was triggered
                    mock_setup_initial_auth_token.assert_called_once()
                    mock_get_status.assert_called_once_with(
                        "test-workspace", "test-job", "test-agent"
                    )

                    # Verify background task was created for deferred initialization
                    mock_create_task.assert_called_once()

                    # Verify the task was created with the correct coroutine
                    task_arg = mock_create_task.call_args[0][0]
                    assert hasattr(task_arg, "cr_code")  # It's a coroutine
                    assert task_arg.cr_code.co_name == "_wait_for_non_invoking_and_initialize"

                    # Agent should not be initialized yet
                    assert stateless_agent_runtime_server.initialized is False
                    assert stateless_agent_runtime_server.agent is None

    @pytest.mark.asyncio
    async def test_wait_for_non_invoking_and_initialize(self, stateless_agent_runtime_server):
        """Test _wait_for_non_invoking_and_initialize method."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.wait_for_agent_non_invoking",
            return_value="INVOKED",
        ) as mock_wait:
            with mock.patch.object(
                stateless_agent_runtime_server, "_finalize_agent_setup"
            ) as mock_finalize:

                await stateless_agent_runtime_server._wait_for_non_invoking_and_initialize()

                mock_wait.assert_called_once_with("test-workspace", "test-job", "test-agent")
                mock_finalize.assert_called_once_with("INVOKED")

    @pytest.mark.asyncio
    async def test_finalize_agent_setup_invoked_status(self, stateless_agent_runtime_server):
        """Test _finalize_agent_setup with INVOKED status."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.build_agentic_api_endpoint_from_env"
        ) as mock_endpoint:
            mock_endpoint.return_value = "https://test-endpoint.com"
            with mock.patch(
                "agent_builder_sdk.server.stateless_agent_runtime_server.MCPClientFactory.setup_ab_mcp_client"
            ) as mock_mcp:
                with mock.patch(
                    "agent_builder_sdk.server.stateless_agent_runtime_server.set_agent_running"
                ) as mock_set_running:
                    with mock.patch(
                        "agent_builder_sdk.server.stateless_agent_runtime_server.get_agentic_api_client"
                    ):
                        with mock.patch(
                            "agent_builder_sdk.server.stateless_agent_runtime_server.JobManager"
                        ) as mock_job_manager_class:
                            mock_job_manager = mock.Mock()
                            mock_job_manager.transition_to_executing_if_assessing = mock.Mock()
                            mock_job_manager_class.return_value = mock_job_manager
                            mock_mcp.return_value = mock.Mock()

                            await stateless_agent_runtime_server._finalize_agent_setup("INVOKED")

                            # Verify set_agent_running was called for INVOKED status
                            mock_set_running.assert_called_once_with(
                                "test-workspace", "test-job", "test-agent"
                            )
                            assert stateless_agent_runtime_server.initialized is True

    @pytest.mark.asyncio
    async def test_finalize_agent_setup_running_status(self, stateless_agent_runtime_server):
        """Test _finalize_agent_setup with RUNNING status."""
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        stateless_agent_runtime_server.context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        with mock.patch(
            "agent_builder_sdk.server.stateless_agent_runtime_server.build_agentic_api_endpoint_from_env"
        ) as mock_endpoint:
            mock_endpoint.return_value = "https://test-endpoint.com"
            with mock.patch(
                "agent_builder_sdk.server.stateless_agent_runtime_server.MCPClientFactory.setup_ab_mcp_client"
            ) as mock_mcp:
                with mock.patch(
                    "agent_builder_sdk.server.stateless_agent_runtime_server.set_agent_running"
                ) as mock_set_running:
                    with mock.patch(
                        "agent_builder_sdk.server.stateless_agent_runtime_server.get_agentic_api_client"
                    ):
                        with mock.patch(
                            "agent_builder_sdk.server.stateless_agent_runtime_server.JobManager"
                        ) as mock_job_manager_class:
                            mock_job_manager = mock.Mock()
                            mock_job_manager.transition_to_executing_if_assessing = mock.Mock()
                            mock_job_manager_class.return_value = mock_job_manager
                            mock_mcp.return_value = mock.Mock()

                            await stateless_agent_runtime_server._finalize_agent_setup("RUNNING")

                            # Verify set_agent_running was NOT called for RUNNING status
                            mock_set_running.assert_not_called()
                            assert stateless_agent_runtime_server.initialized is True
