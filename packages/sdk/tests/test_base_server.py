# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Base Server implementation.

Tests the BaseServer abstract class functionality including setup_tracing.
"""

import asyncio
from unittest import mock

import pytest

from agent_builder_sdk.server.base_server import BaseServer
from agent_builder_sdk.streaming.a2a_agui_adapter import _AGUI_EXT_URI as AGUI_EXT_URI
from agent_builder_sdk.streaming.a2a_frame_utils import RAW_EXT_URI


class ConcreteBaseServer(BaseServer):
    """Concrete implementation of BaseServer for testing."""

    def __init__(self):
        from fastapi import FastAPI

        from agent_builder_sdk.streaming.config import StreamingConfig

        self.initialized = False
        self.context = None
        self.notification_handler = None
        self.task_handler = None
        self.message_handler = None
        self.tracing = None
        self.stop_requested = False
        # Streaming-enabled by default so the _handle_streaming tests exercise the streaming path.
        self.streaming_config = StreamingConfig()
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


class TestHandleStreamingPartsParity:
    """message/stream must feed the agent the SAME full parts as message/send (no silent
    drop of data/file parts). Regression guard for the text-only-filter bug."""

    async def test_all_parts_reach_agent_as_json(self):
        import json

        server = ConcreteBaseServer()

        captured = {}

        class _CapturingAgent:
            async def process_message_stream(self, req, conversation_id=None, cfg=None):
                captured["message"] = req.message
                captured["context"] = req.context
                captured["conversation_id"] = conversation_id
                # empty async generator (no frames needed for this assertion)
                return
                yield  # pragma: no cover

        async def _get_agent(source_id, source_type):
            return _CapturingAgent()

        server._get_agent_for_streaming = _get_agent  # type: ignore[assignment]

        params = {
            "message": {
                "role": "user",
                "kind": "message",
                "messageId": "m-1",
                "contextId": "ctx-1",
                "parts": [
                    {"kind": "text", "text": "hello"},
                    {"kind": "file", "file": {"uri": "s3://bucket/key", "name": "a.txt"}},
                    {"kind": "data", "data": {"foo": "bar"}},
                ],
            }
        }

        resp = await server._handle_streaming(params)
        # drain the SSE generator so process_message_stream runs
        async for _ in resp.body_iterator:
            pass

        parts = json.loads(captured["message"])
        kinds_or_types = [p.get("type") or p.get("kind") for p in parts]
        # all three parts survived — data and file were NOT dropped
        assert len(parts) == 3
        assert "file" in kinds_or_types and "data" in kinds_or_types and "text" in kinds_or_types
        # first part normalized kind->type (parity with extract_message_info / message/send)
        assert parts[0]["type"] == "text"
        assert "kind" not in parts[0]


class TestHandleStreamingIds:
    """The streaming ingress: contextId is required, and the threadId (conversation id) is
    derived from the caller's identity, not taken from the request."""

    @staticmethod
    def _server_with_capture(
        captured, workspace_id="ws-1", job_id="job-1", requires_context_id=True
    ):
        from agent_builder_sdk.interfaces import StreamingCapable
        from agent_builder_sdk.server.server_models import AgentRuntimeContext

        server = ConcreteBaseServer()
        server.context = AgentRuntimeContext(
            workspace_id=workspace_id,
            job_id=job_id,
            agent_instance_id="agent-1",
            tenant_account_id="acct-1",
        )

        class _CapturingAgent(StreamingCapable):
            async def process_message_stream(self, req, conversation_id=None, cfg=None):
                captured["conversation_id"] = conversation_id
                return
                yield  # pragma: no cover

            def get_streaming_hook_providers(self, cfg):
                return []

            def requires_context_id(self):
                return requires_context_id

        async def _get_agent(source_id, source_type):
            return _CapturingAgent()

        server._get_agent_for_streaming = _get_agent  # type: ignore[assignment]
        return server

    @staticmethod
    def _params(context_id="ctx-1", user_id="user-1"):
        msg = {
            "role": "user",
            "kind": "message",
            "messageId": "m-1",
            "parts": [{"kind": "text", "text": "hi"}],
            "extensions": ["https://aws.com/transform/ext/source_information/v1"],
            "metadata": {
                "https://aws.com/transform/ext/source_information/v1": {
                    "senderAgentInstanceId": "ATX_CHAT",
                    "onBehalfOfUser": user_id,
                }
            },
        }
        if context_id is not None:
            msg["contextId"] = context_id
        return {"message": msg}

    def test_streaming_off_jsonrpc_is_method_not_found(self):
        """Without a StreamingConfig, message/stream answers -32601 Method not found, as before
        streaming existed."""
        from fastapi.testclient import TestClient

        server = self._server_with_capture({})
        server.streaming_config = None
        server.initialized = True
        response = TestClient(server.app).post(
            "/invocations",
            json={"jsonrpc": "2.0", "id": 7, "method": "message/stream", "params": self._params()},
        )

        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32601
        assert response.json()["id"] == 7

    def test_streaming_rest_route_returns_an_error_body_when_the_agent_is_not_ready(self):
        from fastapi.testclient import TestClient

        server = self._server_with_capture({})

        async def not_ready(source_id, source_type):
            raise RuntimeError("Agent is not ready to stream")

        server._get_agent_for_streaming = not_ready  # type: ignore[assignment]
        response = TestClient(server.app).post("/message/stream", json=self._params())

        assert response.status_code == 200
        assert response.json() == {"error": "Agent is not ready to stream"}

    def test_streaming_off_rest_route_is_404(self):
        """Without a StreamingConfig, REST /message/stream is a 404, as before the route existed."""
        from fastapi.testclient import TestClient

        server = self._server_with_capture({})
        server.streaming_config = None
        response = TestClient(server.app).post("/message/stream", json=self._params())

        assert response.status_code == 404

    async def test_missing_context_id_raises_when_agent_requires_it(self):
        """When the resolved agent requires a contextId (orchestrator policy), a turn without one
        is rejected up front (before the SSE response starts) rather than streamed unpersistably."""
        server = self._server_with_capture({}, requires_context_id=True)
        with pytest.raises(ValueError, match="contextId is required"):
            await server._handle_streaming(self._params(context_id=None))

    async def test_missing_context_id_allowed_when_agent_does_not_require_it(self):
        """When the agent does not require a contextId (sub-agent policy), a turn without one is
        served — the requirement is the agent's policy, not the shared transport's."""
        captured = {}
        server = self._server_with_capture(captured, requires_context_id=False)
        resp = await server._handle_streaming(self._params(context_id=None))
        async for _ in resp.body_iterator:
            pass
        assert "conversation_id" in captured  # reached the agent, no raise

    async def test_thread_id_derived_from_identity_not_context(self):
        """The conversation/thread id is <userId>#<workspaceId>#<jobId> — derived from the
        caller's identity, NOT the request's contextId."""
        captured = {}
        server = self._server_with_capture(captured, workspace_id="ws-9", job_id="job-9")

        resp = await server._handle_streaming(self._params(context_id="ctx-1", user_id="user-9"))
        async for _ in resp.body_iterator:
            pass

        assert captured["conversation_id"] == "user-9#ws-9#job-9"
        assert captured["conversation_id"] != "ctx-1"  # NOT the A2A contextId


class TestHandleStreamingTerminalGuarantee:
    """A streaming turn must ALWAYS end with a terminal frame. If an error escapes the agent's own
    handling (or the serialize/yield loop), _handle_streaming emits a fallback failed terminal
    rather than dropping the connection with no terminal (the F1 failure mode)."""

    @staticmethod
    def _parse_frames(body: str):
        import json

        return [
            json.loads(line[len("data: ") :])
            for line in body.split("\n\n")
            if line.startswith("data: ")
        ]

    async def test_stream_ends_with_failed_terminal_when_agent_raises(self):
        server = ConcreteBaseServer()

        class _BoomAgent:
            async def process_message_stream(self, req, conversation_id=None, cfg=None):
                # Emit the opener, then raise WITHOUT emitting a terminal (simulating an error that
                # escapes the agent — e.g. a serialization crash pre-fix, or an unexpected bug).
                yield {
                    "kind": "task",
                    "id": "t-1",
                    "status": {"state": "submitted"},
                    "contextId": "ctx-1",
                }
                raise RuntimeError("kaboom")

        async def _get_agent(source_id, source_type):
            return _BoomAgent()

        server._get_agent_for_streaming = _get_agent  # type: ignore[assignment]

        params = {
            "message": {
                "role": "user",
                "kind": "message",
                "messageId": "m-1",
                "contextId": "ctx-1",
                "parts": [{"kind": "text", "text": "hi"}],
            }
        }
        resp = await server._handle_streaming(params)
        body = "".join([c async for c in resp.body_iterator])

        frames = self._parse_frames(body)
        # opener made it out, then a synthesized terminal failed frame reusing the wire ids.
        assert frames[0]["kind"] == "task"
        assert frames[-1]["status"]["state"] == "failed"
        assert frames[-1]["final"] is True
        assert frames[-1]["taskId"] == "t-1"
        assert frames[-1]["contextId"] == "ctx-1"

    async def test_nonserializable_frame_does_not_crash_stream(self):
        # Backstop: even a frame carrying a non-serializable value streams (default=str) and still
        # reaches a terminal, rather than aborting mid-stream with no terminal.
        server = ConcreteBaseServer()

        class _JunkAgent:
            async def process_message_stream(self, req, conversation_id=None, cfg=None):
                yield {"kind": "task", "id": "t-2", "status": {"state": "submitted"}}
                yield {
                    "kind": "status-update",
                    "taskId": "t-2",
                    "final": False,
                    "status": {"state": "working", "obj": object()},
                }
                yield {
                    "kind": "status-update",
                    "taskId": "t-2",
                    "final": True,
                    "status": {"state": "completed"},
                }

        async def _get_agent(source_id, source_type):
            return _JunkAgent()

        server._get_agent_for_streaming = _get_agent  # type: ignore[assignment]

        params = {
            "message": {
                "role": "user",
                "kind": "message",
                "messageId": "m-2",
                "contextId": "ctx-2",
                "parts": [{"kind": "text", "text": "hi"}],
            }
        }
        resp = await server._handle_streaming(params)
        body = "".join([c async for c in resp.body_iterator])
        frames = self._parse_frames(body)
        assert frames[-1]["status"]["state"] == "completed"  # stream completed, no crash


class TestHandleStreamingTurnLock:
    """A streaming turn waits for the job's turn lock; past the bound it ends with a busy frame."""

    @staticmethod
    def _server(calls):
        server = ConcreteBaseServer()

        class _Agent:
            async def process_message_stream(self, req, conversation_id=None, cfg=None):
                calls.append(server._turn_lock.locked())
                yield {"kind": "status-update", "taskId": "t-1", "final": True, "status": {}}

        async def _get_agent(source_id, source_type):
            return _Agent()

        server._get_agent_for_streaming = _get_agent  # type: ignore[assignment]
        server._turn_lock = asyncio.Lock()
        return server

    @staticmethod
    def _params():
        return {
            "message": {
                "role": "user",
                "kind": "message",
                "messageId": "m-1",
                "contextId": "ctx-1",
                "parts": [{"kind": "text", "text": "hi"}],
            }
        }

    async def test_turn_runs_holding_the_lock_and_releases_it(self):
        calls = []
        server = self._server(calls)
        resp = await server._handle_streaming(self._params())
        body = "".join([c async for c in resp.body_iterator])
        assert calls == [True]
        assert '"taskId": "t-1"' in body
        assert not server._turn_lock.locked()

    async def test_busy_frame_when_lock_held_past_the_bound(self, monkeypatch):
        import json

        from agent_builder_sdk.server import base_server as base_server_module

        monkeypatch.setattr(base_server_module, "STREAMING_TURN_LOCK_WAIT_SECONDS", 0.05)
        calls = []
        server = self._server(calls)
        await server._turn_lock.acquire()
        resp = await server._handle_streaming(self._params())
        body = "".join([c async for c in resp.body_iterator])
        frames = [json.loads(c[len("data: ") :]) for c in body.split("\n\n") if c]
        assert frames[0]["kind"] == "task" and frames[0]["id"] == frames[1]["taskId"]
        frame = frames[1]
        assert calls == []
        assert frame["status"]["state"] == "failed" and frame["final"] is True
        assert frame["contextId"] == "ctx-1"
        # Not a StreamingCapable agent: the raw failed terminal, its text where a relay reads it.
        raw = frame["status"]["message"]["parts"][0]["data"][RAW_EXT_URI]
        assert raw["data"] == base_server_module.BUSY_MESSAGE
        assert server._turn_lock.locked()  # still held by the other turn, not released by us

    async def test_busy_reply_is_a_normal_text_reply_for_the_orchestrator(self, monkeypatch):
        import json

        from agent_builder_sdk.interfaces import StreamingCapable
        from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
            AsyncBaseOrchestrator,
        )
        from agent_builder_sdk.server import base_server as base_server_module
        from agent_builder_sdk.streaming import response_persist_hook

        monkeypatch.setattr(base_server_module, "STREAMING_TURN_LOCK_WAIT_SECONDS", 0.05)
        persisted = mock.AsyncMock()
        monkeypatch.setattr(response_persist_hook, "persist_stream_error", persisted)
        server = ConcreteBaseServer()

        class _Orchestrator(StreamingCapable):
            async def process_message_stream(self, req, conversation_id=None, cfg=None):
                raise AssertionError("must not run while the job is busy")
                yield  # pragma: no cover

            def get_streaming_hook_providers(self, cfg):
                return []

            def requires_context_id(self):
                return True

            reply_frames = AsyncBaseOrchestrator.reply_frames

        async def _get_agent(source_id, source_type):
            return _Orchestrator()

        server._get_agent_for_streaming = _get_agent  # type: ignore[assignment]
        server._turn_lock = asyncio.Lock()
        await server._turn_lock.acquire()
        resp = await server._handle_streaming(self._params())
        body = "".join([c async for c in resp.body_iterator])
        frames = [json.loads(c[len("data: ") :]) for c in body.split("\n\n") if c]
        # What FES reads: the AG-UI event in each frame's DataPart (A2AFrameUnwrapper).
        agui = [f["status"]["message"]["parts"][0]["data"][AGUI_EXT_URI] for f in frames]
        assert [e["type"] for e in agui] == [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "RUN_FINISHED",
        ]
        assert agui[2]["delta"] == base_server_module.BUSY_MESSAGE
        assert frames[0]["kind"] == "task"
        assert {f.get("taskId", f.get("id")) for f in frames} == {frames[0]["id"]}
        assert all(f["contextId"] == "ctx-1" for f in frames)
        assert frames[-1]["status"]["state"] == "completed" and frames[-1]["final"] is True
        # Saved to Chat as this turn's final reply, under the id the stream showed.
        persisted.assert_awaited_once_with(
            "ctx-1", base_server_module.BUSY_MESSAGE, agui[1]["messageId"]
        )
        assert server._turn_lock.locked()
