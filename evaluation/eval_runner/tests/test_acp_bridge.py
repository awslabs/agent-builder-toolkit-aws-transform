# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for acp_bridge.py — ACPClient JSON-RPC communication."""

from __future__ import annotations

import io
import json
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from eval_runner.execution.acp_bridge import ACPClient


class TestACPClientInit:
    """Tests for ACPClient initialization."""

    def test_init_sets_attributes(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log", cwd="/tmp")
        assert client.agent == "test-agent"
        assert client.log_path == "/tmp/test.log"
        assert client.cwd == "/tmp"
        assert client.proc is None
        assert client.session_id is None

    def test_init_defers_file_handles(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        assert client._log_fh is None
        assert client._raw_log_fh is None
        assert client._stderr_fh is None

    def test_init_default_cwd_is_none(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        assert client.cwd is None


class TestACPClientCloseFileHandles:
    """Tests for _close_file_handles."""

    def test_closes_all_handles(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        client._log_fh = io.StringIO()
        client._raw_log_fh = io.StringIO()
        client._stderr_fh = io.StringIO()
        client._close_file_handles()
        assert client._log_fh.closed
        assert client._raw_log_fh.closed
        assert client._stderr_fh.closed

    def test_handles_none_handles(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        # Should not raise
        client._close_file_handles()

    def test_handles_already_closed(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        fh = io.StringIO()
        fh.close()
        client._log_fh = fh
        # Should not raise
        client._close_file_handles()


class TestACPClientLog:
    """Tests for _log method formatting."""

    def _make_client_with_logs(self) -> tuple[ACPClient, io.StringIO, io.StringIO]:
        client = ACPClient("test-agent", "/tmp/test.log")
        log_fh = io.StringIO()
        raw_log_fh = io.StringIO()
        client._log_fh = log_fh
        client._raw_log_fh = raw_log_fh
        return client, log_fh, raw_log_fh

    def test_log_skips_when_no_handles(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        # Should not raise when handles are None
        client._log(">>>", {"method": "test"})

    def test_log_writes_raw_protocol(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {"method": "initialize", "params": {}}
        client._log(">>>", data)
        raw = raw_log_fh.getvalue()
        assert ">>>" in raw
        assert '"method": "initialize"' in raw

    def test_log_agent_message_chunk(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello "},
                }
            },
        }
        client._log("<<<", data)
        # Text is buffered, not flushed yet
        assert "Hello" not in log_fh.getvalue()
        assert "Hello" in "".join(client._agent_buf)

    def test_log_flushes_agent_buf_on_tool_call(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        # Buffer some agent text
        client._agent_buf = ["Hello ", "world"]
        # Tool call triggers flush
        data = {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "shell",
                    "kind": "execute",
                    "status": "in_progress",
                }
            },
        }
        client._log("<<<", data)
        output = log_fh.getvalue()
        assert "AGENT: Hello world" in output
        assert "TOOL:" in output

    def test_log_tool_call_update(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "title": "shell",
                    "kind": "execute",
                    "status": "completed",
                    "rawInput": {"command": "ls -la"},
                }
            },
        }
        client._log("<<<", data)
        output = log_fh.getvalue()
        assert "TOOL:" in output
        assert "completed" in output
        assert "command=" in output

    def test_log_approval_needed(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {
            "method": "session/request_permission",
            "id": "rpc-1",
            "params": {
                "toolCall": {"title": "fs_write", "toolCallId": "tc-1"},
                "options": [{"optionId": "allow_once"}, {"optionId": "reject_once"}],
            },
        }
        client._log("<<<", data)
        output = log_fh.getvalue()
        assert "APPROVAL_NEEDED" in output
        assert "fs_write" in output

    def test_log_done_with_usage(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {
            "result": {
                "stopReason": "end_turn",
                "usage": {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150},
            }
        }
        client._log("<<<", data)
        output = log_fh.getvalue()
        assert "USAGE:" in output
        assert "input=100" in output
        assert "DONE:  end_turn" in output

    def test_log_error(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {"error": {"code": -1, "message": "something broke"}}
        client._log("<<<", data)
        assert "ERROR:" in log_fh.getvalue()

    def test_log_kiro_notification(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {
            "method": "_kiro.dev/mcp/server_initialized",
            "params": {"serverName": "aws-transform-mcp-py"},
        }
        client._log("<<<", data)
        output = log_fh.getvalue()
        assert "KIRO:" in output
        assert "aws-transform-mcp-py" in output

    def test_log_outgoing_prompt(self) -> None:
        client, log_fh, raw_log_fh = self._make_client_with_logs()
        data = {
            "method": "session/prompt",
            "params": {"prompt": "Say hello"},
        }
        client._log(">>>", data)
        output = log_fh.getvalue()
        assert ">>> session/prompt:" in output


class TestACPClientPrompt:
    """Tests for prompt() method with mocked subprocess."""

    @pytest.fixture(autouse=True)
    def _patch_select(self) -> Any:
        """Patch select.select to always return ready for StringIO stdout."""
        with patch(
            "eval_runner.execution.acp_bridge.select.select"
        ) as mock_select:
            mock_select.side_effect = lambda rlist, wlist, xlist, timeout=None: (rlist, [], [])
            yield mock_select

    def _make_started_client(self, stdout_lines: list[str]) -> ACPClient:
        """Create ACPClient with mocked proc that returns the given stdout lines."""
        client = ACPClient("test-agent", "/tmp/test.log")
        client._log_fh = io.StringIO()
        client._raw_log_fh = io.StringIO()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process is alive
        mock_proc.stdout = io.StringIO("\n".join(stdout_lines) + "\n")
        mock_proc.stdin = MagicMock()
        client.proc = mock_proc
        client.session_id = "test-session"
        return client

    def test_prompt_success(self) -> None:
        lines = [
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "Hello!"},
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "result": {
                        "stopReason": "end_turn",
                        "usage": {"inputTokens": 10, "outputTokens": 5},
                    }
                }
            ),
        ]
        client = self._make_started_client(lines)
        status, data = client.prompt("Say hello", timeout=5)
        assert status == "SUCCESS"
        assert data["response"] == "Hello!"
        assert data["usage"]["inputTokens"] == 10

    def test_prompt_approval_needed(self) -> None:
        lines = [
            json.dumps(
                {
                    "method": "session/request_permission",
                    "id": "rpc-42",
                    "params": {
                        "toolCall": {"toolCallId": "tc-1", "title": "fs_write"},
                        "options": [{"optionId": "allow_once"}],
                    },
                }
            ),
        ]
        client = self._make_started_client(lines)
        status, data = client.prompt("Write a file", timeout=5)
        assert status == "APPROVAL_NEEDED"
        assert data["tool_call_id"] == "tc-1"
        assert data["tool"] == "fs_write"
        assert client._pending_approval == "rpc-42"

    def test_prompt_fires_on_event_for_tool_call(self) -> None:
        events: list[dict[str, Any]] = []
        lines = [
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call",
                            "title": "shell",
                            "kind": "execute",
                            "status": "in_progress",
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call",
                            "title": "shell",
                            "kind": "execute",
                            "status": "success",
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "Done"},
                        }
                    },
                }
            ),
            json.dumps({"result": {"stopReason": "end_turn"}}),
        ]
        client = self._make_started_client(lines)
        status, data = client.prompt("Run ls", timeout=5, on_event=events.append)
        assert status == "SUCCESS"
        tool_events = [e for e in events if e.get("type") == "status"]
        text_events = [e for e in events if e.get("type") == "agent_text"]
        assert len(tool_events) == 2
        assert tool_events[0]["status"] == "in_progress"
        assert tool_events[1]["status"] == "success"
        assert len(text_events) == 1
        assert text_events[0]["text"] == "Done"

    def test_prompt_fires_on_event_for_tool_call_update(self) -> None:
        events: list[dict[str, Any]] = []
        lines = [
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call_update",
                            "title": "@aws-transform-mcp-py/create_job",
                            "kind": "other",
                            "status": "completed",
                        }
                    },
                }
            ),
            json.dumps({"result": {"stopReason": "end_turn"}}),
        ]
        client = self._make_started_client(lines)
        status, data = client.prompt("Create job", timeout=5, on_event=events.append)
        assert status == "SUCCESS"
        assert len(events) == 1
        assert events[0]["tool"] == "@aws-transform-mcp-py/create_job"
        assert events[0]["status"] == "completed"

    def test_prompt_dead_process(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # process exited
        mock_proc.stdout = MagicMock()
        client.proc = mock_proc
        status, data = client.prompt("hello", timeout=1)
        assert status == "FAILED"
        assert "died" in data["error"]

    def test_prompt_eof(self) -> None:
        client = self._make_started_client([])
        status, data = client.prompt("hello", timeout=1)
        assert status == "FAILED"
        assert "EOF" in data["error"]


class TestACPClientSendApproval:
    """Tests for send_approval() method.

    send_approval uses select.select() for non-blocking reads, which doesn't
    work with io.StringIO. We patch select.select to always return ready.
    """

    def _make_client_with_pending(
        self, stdout_lines: list[str], rpc_id: str = "rpc-42"
    ) -> ACPClient:
        client = ACPClient("test-agent", "/tmp/test.log")
        client._log_fh = io.StringIO()
        client._raw_log_fh = io.StringIO()
        client._pending_approval = rpc_id

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        stdout = io.StringIO("\n".join(stdout_lines) + "\n")
        mock_proc.stdout = stdout
        mock_proc.stdin = MagicMock()
        client.proc = mock_proc
        client.session_id = "test-session"
        return client

    @pytest.fixture(autouse=True)
    def _patch_select(self) -> Any:
        """Patch select.select to always return ready for StringIO stdout."""
        with patch(
            "eval_runner.execution.acp_bridge.select.select"
        ) as mock_select:
            mock_select.side_effect = lambda rlist, wlist, xlist, timeout=None: (rlist, [], [])
            yield mock_select

    def test_send_approval_success(self) -> None:
        lines = [
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "File written."},
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "result": {
                        "stopReason": "end_turn",
                        "usage": {"inputTokens": 20, "outputTokens": 10},
                    }
                }
            ),
        ]
        client = self._make_client_with_pending(lines)
        status, data = client.send_approval("allow_once", timeout=5)
        assert status == "SUCCESS"
        assert data["response"] == "File written."
        assert data["usage"]["inputTokens"] == 20

    def test_send_approval_no_pending(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        client._pending_approval = None
        status, data = client.send_approval("allow_once")
        assert status == "FAILED"
        assert "No pending approval" in data["error"]

    def test_send_approval_fires_on_event(self) -> None:
        events: list[dict[str, Any]] = []
        lines = [
            json.dumps(
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call_update",
                            "title": "@aws-transform-mcp-py/get_status",
                            "kind": "other",
                            "status": "completed",
                        }
                    },
                }
            ),
            json.dumps({"result": {"stopReason": "end_turn"}}),
        ]
        client = self._make_client_with_pending(lines)
        status, data = client.send_approval("allow_once", timeout=5, on_event=events.append)
        assert status == "SUCCESS"
        assert len(events) == 1
        assert events[0]["tool"] == "@aws-transform-mcp-py/get_status"

    def test_send_approval_another_approval(self) -> None:
        lines = [
            json.dumps(
                {
                    "method": "session/request_permission",
                    "id": "rpc-99",
                    "params": {
                        "toolCall": {"toolCallId": "tc-2", "title": "read"},
                        "options": [{"optionId": "allow_once"}],
                    },
                }
            ),
        ]
        client = self._make_client_with_pending(lines)
        status, data = client.send_approval("allow_once", timeout=5)
        assert status == "APPROVAL_NEEDED"
        assert data["tool_call_id"] == "tc-2"
        assert client._pending_approval == "rpc-99"


class TestACPClientStartFailure:
    """Tests for start() cleanup on failure."""

    def test_start_failure_closes_handles(self) -> None:
        """If _initialize() raises, file handles and subprocess are cleaned up."""
        client = ACPClient("test-agent", "/tmp/nonexistent-dir/test.log")
        # start() should raise because it can't open log files or run agent-cli
        with pytest.raises(Exception):
            client.start()
        # All handles should be closed (or None if never opened)
        for fh in (client._log_fh, client._raw_log_fh, client._stderr_fh):
            assert fh is None or fh.closed

    def test_start_failure_kills_subprocess(self) -> None:
        """If _initialize() raises after Popen succeeds, subprocess is terminated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")
            client = ACPClient("test-agent", log_path)

            mock_proc = MagicMock()
            mock_proc.poll.return_value = None  # alive

            with (
                patch("subprocess.Popen", return_value=mock_proc),
                patch.object(client, "_initialize", side_effect=RuntimeError("init failed")),
                patch("os.killpg") as mock_killpg,
            ):
                with pytest.raises(RuntimeError, match="init failed"):
                    client.start()

                # Subprocess should have been killed
                mock_killpg.assert_called_once()
                # File handles should be closed
                for fh in (client._log_fh, client._raw_log_fh, client._stderr_fh):
                    assert fh is None or fh.closed


class TestACPClientKill:
    """Tests for kill() and cleanup."""

    def test_kill_closes_handles(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = f.name

        try:
            client = ACPClient("test-agent", log_path)
            client._log_fh = open(log_path, "a")
            client._raw_log_fh = open(log_path.replace(".log", "-raw.log"), "a")
            client.proc = None  # no process to kill
            client.kill()
            assert client._log_fh.closed
            assert client._raw_log_fh.closed
        finally:
            os.unlink(log_path)
            raw_path = log_path.replace(".log", "-raw.log")
            if os.path.exists(raw_path):
                os.unlink(raw_path)

    def test_kill_terminates_process(self) -> None:
        client = ACPClient("test-agent", "/tmp/test.log")
        client._log_fh = io.StringIO()
        client._raw_log_fh = io.StringIO()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 12345
        client.proc = mock_proc

        with patch("os.killpg"):
            client.kill()
        mock_proc.wait.assert_called_once_with(timeout=5)
