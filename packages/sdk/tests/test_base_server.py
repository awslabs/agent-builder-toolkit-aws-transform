"""
Unit tests for Base Server implementation.

Tests the BaseServer abstract class functionality including setup_tracing.
"""

from unittest import mock

import pytest

from agent_builder_sdk.server.base_server import BaseServer


class ConcreteBaseServer(BaseServer):
    """Concrete implementation of BaseServer for testing."""

    def __init__(self):
        from fastapi import FastAPI

        self.initialized = False
        self.context = None
        self.notification_handler = None
        self.task_handler = None
        self.message_handler = None
        self.tracing = None
        self.stop_requested = False
        self.app = FastAPI()
        self.setup_common_routes()

    async def initialize_agent(self, auth_token=None):
        """Mock implementation."""
        pass

    def start(self):
        """Mock implementation."""
        pass


@pytest.fixture
def base_server():
    """Create concrete BaseServer instance for testing."""
    return ConcreteBaseServer()


class TestBaseServer:
    """Test cases for BaseServer functionality."""

    def test_setup_tracing_local(self, base_server):
        """Test setup_tracing with local Jaeger configuration."""
        with mock.patch("os.environ") as mock_env, mock.patch(
            "agent_builder_sdk.server.base_server.StrandsTelemetry"
        ) as mock_telemetry:
            mock_telemetry_instance = mock.Mock()
            mock_telemetry.return_value = mock_telemetry_instance

            base_server.setup_tracing("local")

            mock_env.__setitem__.assert_called_with(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
            )
            mock_telemetry_instance.setup_otlp_exporter.assert_called_once()
            mock_telemetry_instance.setup_console_exporter.assert_called_once()

    def test_is_jsonrpc_request_valid(self, base_server):
        """Test is_jsonrpc_request with valid JSON-RPC request."""
        request = {"jsonrpc": "2.0", "method": "test", "id": 1}
        assert base_server.is_jsonrpc_request(request) is True

    def test_is_jsonrpc_request_invalid(self, base_server):
        """Test is_jsonrpc_request with invalid request."""
        request = {"invalid": "request"}
        assert base_server.is_jsonrpc_request(request) is False

    def test_ping_endpoint_default_healthybusy(self, base_server):
        """Test ping endpoint returns HealthyBusy by default."""
        from fastapi.testclient import TestClient

        client = TestClient(base_server.app)
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"status": "HealthyBusy"}

    @pytest.mark.asyncio
    async def test_ping_endpoint_after_stop_request(self, base_server):
        """Test ping endpoint returns Healthy after stop request."""
        from fastapi.testclient import TestClient

        assert base_server.stop_requested is False

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/stop",
            "params": {"agentInstanceId": "test-agent"},
        }

        await base_server.handle_jsonrpc(request)

        assert base_server.stop_requested is True

        client = TestClient(base_server.app)
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"status": "Healthy"}

    @mock.patch.object(ConcreteBaseServer, "get_task")
    async def test_handle_tasks_get_success(self, mock_get_task, base_server):
        """Test handle_tasks_get with valid task id."""
        from agent_builder_sdk.custom_types.common_types import A2AMessage
        from agent_builder_sdk.custom_types.task_types import (
            A2ATask,
            GetTaskResponse,
            TaskState,
            TaskStatus,
        )

        # Mock successful task retrieval
        mock_task = A2ATask(
            id="task-123",
            contextId="ctx-456",
            status=TaskStatus(
                state=TaskState.WORKING,
                message=A2AMessage(
                    role="agent",
                    parts=[{"text": "Processing...", "kind": "text"}],
                    messageId="msg-789",
                    kind="message",
                    contextId="ctx-456",
                ),
            ),
        )
        mock_get_task.return_value = GetTaskResponse(result=mock_task)

        result = await base_server.handle_tasks_get({"id": "task-123"})

        assert isinstance(result, A2ATask)
        assert result.id == "task-123"
        assert result.status.state == TaskState.WORKING

    async def test_handle_tasks_get_missing_id(self, base_server):
        """Test handle_tasks_get returns error when id is missing."""
        from agent_builder_sdk.custom_types.common_types import A2AError, A2AErrorCode

        result = await base_server.handle_tasks_get({})

        assert isinstance(result, A2AError)
        assert result.code == A2AErrorCode.INVALID_REQUEST
        assert "Missing required parameter: id" in result.message

    async def test_handle_tasks_get_none_id(self, base_server):
        """Test handle_tasks_get returns error when id is None."""
        from agent_builder_sdk.custom_types.common_types import A2AError, A2AErrorCode

        result = await base_server.handle_tasks_get({"id": None})

        assert isinstance(result, A2AError)
        assert result.code == A2AErrorCode.INVALID_REQUEST
        assert "Missing required parameter: id" in result.message

    @mock.patch.object(ConcreteBaseServer, "get_task")
    async def test_handle_tasks_get_error_response(self, mock_get_task, base_server):
        """Test handle_tasks_get returns error when get_task fails."""
        from agent_builder_sdk.custom_types.common_types import A2AError, A2AErrorCode
        from agent_builder_sdk.custom_types.task_types import GetTaskResponse

        # Mock error response
        mock_error = A2AError(code=A2AErrorCode.INTERNAL_ERROR, message="Task not found")
        mock_get_task.return_value = GetTaskResponse(error=mock_error)

        result = await base_server.handle_tasks_get({"id": "task-123"})

        assert isinstance(result, A2AError)
        assert result.code == A2AErrorCode.INTERNAL_ERROR
        assert result.message == "Task not found"

    @mock.patch.object(ConcreteBaseServer, "get_task")
    async def test_handle_tasks_get_none_result(self, mock_get_task, base_server):
        """Test handle_tasks_get returns error when result is None."""
        from agent_builder_sdk.custom_types.common_types import A2AError, A2AErrorCode
        from agent_builder_sdk.custom_types.task_types import GetTaskResponse

        # Mock None result
        mock_get_task.return_value = GetTaskResponse(result=None)

        result = await base_server.handle_tasks_get({"id": "task-123"})

        assert isinstance(result, A2AError)
        assert result.code == A2AErrorCode.INTERNAL_ERROR
        assert result.message == "Task not found"
        assert result.code == A2AErrorCode.INTERNAL_ERROR
        assert result.message == "Task not found"

    @pytest.mark.asyncio
    async def test_handshake_returns_success(self, base_server):
        """Test handshake endpoint returns success without initialization."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/handshake",
            "params": {},
        }

        response = await base_server.handle_jsonrpc(request)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert response["result"] == {"status": "ok"}
        assert response.get("error") is None

    @pytest.mark.asyncio
    async def test_handshake_skips_initialization(self, base_server):
        """Test handshake does not trigger agent initialization."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/handshake",
            "params": {},
        }

        # Agent should not be initialized before
        assert base_server.initialized is False

        await base_server.handle_jsonrpc(request)

        # Agent should still not be initialized after handshake
        assert base_server.initialized is False

    @pytest.mark.asyncio
    async def test_handshake_logs_request(self, base_server, caplog):
        """Test handshake logs the request."""
        import logging

        caplog.set_level(logging.INFO)

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "atx_agent/handshake",
            "params": {},
        }

        await base_server.handle_jsonrpc(request)

        assert "Handshake request received" in caplog.text
