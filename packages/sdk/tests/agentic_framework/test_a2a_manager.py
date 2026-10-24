# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for A2AManager."""

import tempfile
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from agent_builder_sdk.agentic_framework.a2a_manager import A2AManager
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus


@pytest.fixture
def mock_client():
    """Create a mock boto3 client (the sync agentic API client)."""
    return mock.Mock()


@pytest.fixture
def mock_streaming_client():
    """Mock the dedicated streaming (ConverseStream) client, injected into the manager."""
    return mock.Mock()


@pytest.fixture
def a2a_manager(mock_client, mock_streaming_client, monkeypatch):
    """Create an A2AManager instance with mocked dependencies."""
    # Create temporary auth token file
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("ATX_AUTHZ_TOKEN=test-token")
        auth_file_path = f.name

    # Mock the environment variable
    monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)

    return A2AManager(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent-instance",
        client=mock_client,
        streaming_client=mock_streaming_client,
    )


@pytest.fixture
def sample_message():
    """Create a sample A2AMessage."""
    return A2AMessage(
        role="agent",
        parts=[{"kind": "text", "text": "Test message"}],
        messageId="msg-123",
        kind="message",
        contextId="ctx-456",
    )


@pytest.fixture
def sample_task():
    """Create a sample A2ATask."""
    return A2ATask(
        id="task-123",
        contextId="ctx-456",
        status=TaskStatus(
            state=TaskState.SUBMITTED, message=None, timestamp="2025-10-08T17:00:00Z"
        ),
    )


class TestSendMessage:
    """Tests for send_message method."""

    def test_send_message_success(self, a2a_manager, mock_client, sample_message):
        """Test successful message sending."""
        mock_client.send_message.return_value = {"result": {"messageId": "msg-123"}}

        result = a2a_manager.send_message(
            agent_instance_id="target-agent",
            message=sample_message,
        )

        assert result == {"result": {"messageId": "msg-123"}}
        mock_client.send_message.assert_called_once()

    def test_send_message_constructs_correct_params(self, a2a_manager, mock_client, sample_message):
        """Test that send_message constructs correct API parameters."""
        mock_client.send_message.return_value = {}

        a2a_manager.send_message(
            agent_instance_id="target-agent",
            message=sample_message,
        )

        call_args = mock_client.send_message.call_args[1]
        assert call_args["agentInstanceId"] == "target-agent"
        assert call_args["params"]["message"]["role"] == "agent"
        assert call_args["params"]["message"]["contextId"] == "ctx-456"

    def test_send_message_includes_request_context(self, a2a_manager, mock_client, sample_message):
        """Test that send_message includes request context."""
        mock_client.send_message.return_value = {}

        a2a_manager.send_message(
            agent_instance_id="target-agent",
            message=sample_message,
        )

        call_args = mock_client.send_message.call_args[1]
        assert "requestContext" in call_args
        assert call_args["requestContext"]["agentInstanceId"] == "test-agent-instance"

    def test_send_message_client_error(self, a2a_manager, mock_client, sample_message):
        """Test send_message handles ClientError."""
        mock_client.send_message.side_effect = ClientError(
            {"Error": {"Code": "InvalidRequest", "Message": "Invalid message"}},
            "SendMessage",
        )

        with pytest.raises(ClientError):
            a2a_manager.send_message(
                agent_instance_id="target-agent",
                message=sample_message,
            )


class TestSendTask:
    """Tests for send_task method."""

    def test_send_task_success(self, a2a_manager, mock_client, sample_task):
        """Test successful task sending."""
        mock_client.send_message.return_value = {"result": {"taskId": "task-123"}}

        result = a2a_manager.send_task(
            agent_instance_id="target-agent",
            task=sample_task,
        )

        assert result == {"result": {"taskId": "task-123"}}
        mock_client.send_message.assert_called_once()

    def test_send_task_constructs_correct_params(self, a2a_manager, mock_client, sample_task):
        """Test that send_task constructs correct API parameters."""
        mock_client.send_message.return_value = {}

        a2a_manager.send_task(
            agent_instance_id="target-agent",
            task=sample_task,
        )

        call_args = mock_client.send_message.call_args[1]
        assert call_args["agentInstanceId"] == "target-agent"
        assert call_args["params"]["task"]["id"] == "task-123"
        assert call_args["params"]["task"]["contextId"] == "ctx-456"

    def test_send_task_includes_request_context(self, a2a_manager, mock_client, sample_task):
        """Test that send_task includes request context."""
        mock_client.send_message.return_value = {}

        a2a_manager.send_task(
            agent_instance_id="target-agent",
            task=sample_task,
        )

        call_args = mock_client.send_message.call_args[1]
        assert "requestContext" in call_args
        assert call_args["requestContext"]["agentInstanceId"] == "test-agent-instance"

    def test_send_task_client_error(self, a2a_manager, mock_client, sample_task):
        """Test send_task handles ClientError."""
        mock_client.send_message.side_effect = ClientError(
            {"Error": {"Code": "InvalidRequest", "Message": "Invalid task"}},
            "SendMessage",
        )

        with pytest.raises(ClientError):
            a2a_manager.send_task(
                agent_instance_id="target-agent",
                task=sample_task,
            )


class TestGetTask:
    """Tests for get_task method."""

    def test_get_task_success(self, a2a_manager, mock_client):
        """Test successful task retrieval."""
        mock_client.get_task.return_value = {
            "result": {
                "id": "task-123",
                "status": {"state": "completed"},
            }
        }

        result = a2a_manager.get_task(
            task_id="task-123",
            agent_instance_id="target-agent",
        )

        assert result["result"]["id"] == "task-123"
        mock_client.get_task.assert_called_once()

    def test_get_task_constructs_correct_params(self, a2a_manager, mock_client):
        """Test that get_task constructs correct API parameters."""
        mock_client.get_task.return_value = {}

        a2a_manager.get_task(
            task_id="task-123",
            agent_instance_id="target-agent",
        )

        call_args = mock_client.get_task.call_args[1]
        assert call_args["agentInstanceId"] == "target-agent"
        assert call_args["params"]["id"] == "task-123"

    def test_get_task_includes_request_context(self, a2a_manager, mock_client):
        """Test that get_task includes request context."""
        mock_client.get_task.return_value = {}

        a2a_manager.get_task(
            task_id="task-123",
            agent_instance_id="target-agent",
        )

        call_args = mock_client.get_task.call_args[1]
        assert "requestContext" in call_args
        assert call_args["requestContext"]["agentInstanceId"] == "test-agent-instance"

    def test_get_task_client_error(self, a2a_manager, mock_client):
        """Test get_task handles ClientError."""
        mock_client.get_task.side_effect = ClientError(
            {"Error": {"Code": "TaskNotFound", "Message": "Task not found"}},
            "GetTask",
        )

        with pytest.raises(ClientError):
            a2a_manager.get_task(
                task_id="task-123",
                agent_instance_id="target-agent",
            )


class TestA2AManagerFactory:
    """Test cases for A2AManager factory function."""

    def test_get_a2a_manager(self, monkeypatch):
        """Test get_a2a_manager creates singleton from environment."""
        # Create temporary auth token file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("ATX_AUTHZ_TOKEN=test-token")
            auth_file_path = f.name

        # Mock environment variables
        monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)
        monkeypatch.setenv("WORKSPACE_ID", "test-workspace")
        monkeypatch.setenv("JOB_ID", "test-job")
        monkeypatch.setenv("AGENT_INSTANCE_ID", "test-agent")
        monkeypatch.setenv("QT_AGENTIC_API_ENDPOINT", "https://test.endpoint.com")

        # Mock both client factories to avoid real boto3 client creation
        mock_client = mock.Mock()
        mock_streaming_client = mock.Mock()
        with mock.patch(
            "agent_builder_sdk.agentic_framework.a2a_manager.get_agentic_api_client",
            return_value=mock_client,
        ), mock.patch(
            "agent_builder_sdk.agentic_framework.a2a_manager.get_streaming_agentic_api_client",
            return_value=mock_streaming_client,
        ):
            from agent_builder_sdk.agentic_framework.a2a_manager import get_a2a_manager

            manager = get_a2a_manager()

            assert manager.workspace_id == "test-workspace"
            assert manager.job_id == "test-job"
            assert manager.agent_instance_id == "test-agent"
            assert manager.client is mock_client
            # Built lazily, so buffered-only callers never need the streaming service model.
            assert manager.streaming_client is None

            mock_streaming_client.converse_stream.return_value = {"stream": _FakeBody(b"")}
            with mock.patch(
                "agent_builder_sdk.agentic_framework.a2a_manager.get_streaming_agentic_api_client",
                return_value=mock_streaming_client,
            ):
                list(manager.stream_send_message(agent_instance_id="sub-1", message=mock.Mock()))
            assert manager.streaming_client is mock_streaming_client


def test_streaming_client_built_once_under_concurrent_first_calls(a2a_manager):
    """stream_send_message runs in worker threads; concurrent first calls build one client."""
    import threading
    import time

    a2a_manager.streaming_client = None
    client = mock.Mock()
    client.converse_stream.return_value = {"stream": _FakeBody(b"")}
    builds = []

    def build():
        builds.append(1)
        time.sleep(0.05)
        return client

    with mock.patch(
        "agent_builder_sdk.agentic_framework.a2a_manager.get_streaming_agentic_api_client",
        side_effect=build,
    ):
        threads = [
            threading.Thread(
                target=lambda: list(
                    a2a_manager.stream_send_message(agent_instance_id="sub-1", message=mock.Mock())
                )
            )
            for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(builds) == 1
    assert a2a_manager.streaming_client is client


class _FakeBody:
    """Minimal StreamingBody stand-in yielding SSE bytes."""

    def __init__(self, data: bytes):
        self._data = data

    def iter_chunks(self, chunk_size):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i : i + chunk_size]


def _sse(*objs):
    import json

    return "".join(f"data: {json.dumps(o)}\n\n" for o in objs).encode("utf-8")


class TestStreamSendMessage:
    """Tests for stream_send_message (ConverseStream)."""

    def test_stream_send_message_uses_streaming_client(
        self, a2a_manager, mock_client, mock_streaming_client, sample_message
    ):
        """ConverseStream must be issued on the streaming client, never the sync client."""
        body = _FakeBody(_sse({"kind": "task"}, {"status": {"state": "completed"}}))
        mock_streaming_client.converse_stream.return_value = {"stream": body}

        frames = list(
            a2a_manager.stream_send_message(
                agent_instance_id="target-agent", message=sample_message
            )
        )

        assert frames[0] == {"kind": "task"}
        assert frames[-1] == {"status": {"state": "completed"}}
        mock_streaming_client.converse_stream.assert_called_once()
        mock_client.converse_stream.assert_not_called()

    def test_stream_send_message_injects_context_and_params(
        self, a2a_manager, mock_streaming_client, sample_message
    ):
        mock_streaming_client.converse_stream.return_value = {
            "stream": _FakeBody(_sse({"final": True}))
        }

        list(
            a2a_manager.stream_send_message(
                agent_instance_id="target-agent", message=sample_message
            )
        )

        call_args = mock_streaming_client.converse_stream.call_args[1]
        assert call_args["agentInstanceId"] == "target-agent"
        assert call_args["params"]["message"]["contextId"] == "ctx-456"
        assert "requestContext" in call_args

    def test_stream_send_message_raises_on_client_error(
        self, a2a_manager, mock_streaming_client, sample_message
    ):
        mock_streaming_client.converse_stream.side_effect = ClientError(
            {"Error": {"Code": "Boom", "Message": "no"}}, "ConverseStream"
        )
        with pytest.raises(ClientError):
            list(
                a2a_manager.stream_send_message(
                    agent_instance_id="target-agent", message=sample_message
                )
            )
