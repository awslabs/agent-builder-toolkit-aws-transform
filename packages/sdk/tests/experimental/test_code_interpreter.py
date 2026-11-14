# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the code-interpreter tool pair: descriptions, configuration, staging and shutdown."""

import asyncio
import gc
import os
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_builder_sdk.custom_types.server_types import JsonRpcMethods
from agent_builder_sdk.experimental.code_interpreter import code_interpreter_tool
from agent_builder_sdk.experimental.code_interpreter.agentcore_interpreter import (
    NEW_SESSION_NOTICE,
    CodeInterpreterInput,
)
from agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool import (
    CODE_INTERPRETER_ID_ENV_VAR,
    SESSION_TIMEOUT_ENV_VAR,
    create_code_interpreter_tool,
    stop_all_sessions,
)
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.server.base_server import BaseServer
from agent_builder_sdk.server.stateless_agent_runtime_server import StatelessAgentRuntimeServer
from tests.experimental.conftest import FakeSandbox

pytestmark = pytest.mark.filterwarnings("ignore::FutureWarning")

_CUSTOM_ID = "my_interpreter-ABC123xyz"


def _tools(env: Optional[Dict[str, str]] = None, **kwargs: Any) -> List[Any]:
    with patch.dict("os.environ", env or {}, clear=True):
        return create_code_interpreter_tool(region="us-west-2", **kwargs)


def _description(tools: List[Any]) -> str:
    return str(tools[0].tool_spec["description"])


def _list_files(tools: List[Any], **action: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = tools[0](code_interpreter_input={"action": {"type": "listFiles", **action}})
    return result


def _stage(tools: List[Any], local_path: Path, sandbox_path: str, **kwargs: Any) -> str:
    return str(tools[1](local_path=str(local_path), sandbox_path=sandbox_path, **kwargs))


def _file(tmp_path: Path, name: str, data: bytes = b"a,b\n1,2\n") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


class TestToolDescription:
    def test_default_interpreter_is_described_as_offline(self, sandbox: FakeSandbox) -> None:
        tools = _tools()
        _list_files(tools)
        assert sandbox.started[0]["identifier"] == "aws.codeinterpreter.v1"
        assert "NO network access" in _description(tools)

    def test_custom_interpreter_is_not_described_as_online(self, sandbox: FakeSandbox) -> None:
        # A custom interpreter can be in any network mode; the model must not be told it has
        # internet access.
        tools = _tools({CODE_INTERPRETER_ID_ENV_VAR: _CUSTOM_ID})
        _list_files(tools)
        assert sandbox.started[0]["identifier"] == _CUSTOM_ID
        description = _description(tools)
        assert "depend on how that interpreter was set up" in description
        assert "NO network access" not in description
        assert "HAS" not in description

    @pytest.mark.parametrize("env", [{}, {CODE_INTERPRETER_ID_ENV_VAR: _CUSTOM_ID}])
    def test_no_description_names_a_tool_the_pair_does_not_provide(self, env: Dict[str, str]) -> None:
        tools = _tools(env)
        assert tools[0].tool_name == "code_interpreter"
        assert tools[1].tool_name == "stage_file_to_sandbox"
        for tool in tools:
            assert "execute_shell" not in tool.tool_spec["description"]

    def test_a_later_build_does_not_change_an_earlier_agents_description(self) -> None:
        first = _tools()
        _tools({CODE_INTERPRETER_ID_ENV_VAR: _CUSTOM_ID})
        assert _description(first).count("IMPORTANT ENVIRONMENT NOTES") == 1
        assert "NO network access" in _description(first)


class TestSessionTimeout:
    def test_env_value_is_capped_at_the_service_maximum(self, sandbox: FakeSandbox) -> None:
        _list_files(_tools({SESSION_TIMEOUT_ENV_VAR: "36000"}))
        _list_files(_tools({SESSION_TIMEOUT_ENV_VAR: "36000"}, session_timeout_seconds=1800))
        _list_files(_tools())
        assert [s["session_timeout_seconds"] for s in sandbox.started] == [28800, 1800, 900]

    @pytest.mark.parametrize("value", ["15m", "900.5"])
    def test_non_numeric_env_value_raises_an_error_that_names_the_variable(self, value: str) -> None:
        with pytest.raises(ValueError, match=rf"^{SESSION_TIMEOUT_ENV_VAR} must be a whole number of seconds"):
            _tools({SESSION_TIMEOUT_ENV_VAR: value})

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_env_value_below_one_raises_an_error_that_names_the_variable(self, value: str) -> None:
        # Not floored to 1: a one-second session would lose every staged file.
        with pytest.raises(ValueError, match=rf"^{SESSION_TIMEOUT_ENV_VAR} must be .* 1 or more, got '{value}'$"):
            _tools({SESSION_TIMEOUT_ENV_VAR: value})

    @pytest.mark.parametrize("value", [0, -5])
    def test_argument_below_one_raises_an_error_that_names_the_argument(self, value: int) -> None:
        with pytest.raises(ValueError, match=rf"^session_timeout_seconds must be 1 or more, got {value}$"):
            _tools(session_timeout_seconds=value)

    def test_one_second_is_accepted(self, sandbox: FakeSandbox) -> None:
        _list_files(_tools({SESSION_TIMEOUT_ENV_VAR: "1"}))
        _list_files(_tools(session_timeout_seconds=1))
        assert [s["session_timeout_seconds"] for s in sandbox.started] == [1, 1]


class TestCodeInterpreterTool:
    def test_runs_an_action_given_as_a_dict_or_as_a_model(self, sandbox: FakeSandbox) -> None:
        tools = _tools()
        as_dict = _list_files(tools, path="data")
        as_model = tools[0](
            code_interpreter_input=CodeInterpreterInput.model_validate({"action": {"type": "listFiles"}})
        )
        assert as_dict["status"] == as_model["status"] == "success"
        assert sandbox.calls == {"aws-session-1": [("listFiles", {"path": "data"}), ("listFiles", {"path": "."})]}


class TestStageFileToSandbox:
    def test_missing_file(self, sandbox: FakeSandbox, tmp_path: Path) -> None:
        result = _stage(_tools(), tmp_path / "missing.csv", "x.csv")
        assert "no such file" in result
        assert sandbox.started == []

    def test_file_over_the_limit(self, sandbox: FakeSandbox, tmp_path: Path) -> None:
        with patch.object(code_interpreter_tool, "_MAX_STAGE_BYTES", 4):
            result = _stage(_tools(), _file(tmp_path, "big.csv", b"12345"), "big.csv")
        assert "transfer limit" in result
        assert sandbox.started == []

    def test_file_bytes_are_written_to_the_sandbox_path(self, sandbox: FakeSandbox, tmp_path: Path) -> None:
        result = _stage(_tools(), _file(tmp_path, "d.bin", b"\x00\xff"), "data/d.bin")
        assert result.startswith("Staged"), result
        assert NEW_SESSION_NOTICE not in result
        assert sandbox.calls == {
            "aws-session-1": [("writeFiles", {"content": [{"path": "data/d.bin", "blob": b"\x00\xff"}]})]
        }

    def test_sandbox_error_is_reported(self, sandbox: FakeSandbox, tmp_path: Path) -> None:
        # The service flags a rejected write on the stream result, not the response.
        sandbox.result = {"content": [{"type": "text", "text": "Permission denied: /etc/x"}], "isError": True}
        result = _stage(_tools(), _file(tmp_path, "d.csv"), "/etc/x")
        assert result.startswith("Error: staging failed"), result
        assert "Permission denied" in result

    def test_both_tools_use_the_same_session_and_other_agents_do_not(
        self, sandbox: FakeSandbox, tmp_path: Path
    ) -> None:
        agent_a, agent_b = _tools(), _tools()
        _stage(agent_a, _file(tmp_path, "a.csv"), "a.csv", session_name="analysis")
        _stage(agent_b, _file(tmp_path, "b.csv"), "b.csv", session_name="analysis")
        assert _list_files(agent_a, session_name="analysis")["status"] == "success"
        assert sandbox.files() == [["a.csv"], ["b.csv"]]
        assert [len(calls) for calls in sandbox.calls.values()] == [2, 1]

    def test_staging_into_a_replacement_session_tells_the_model(self, sandbox: FakeSandbox, tmp_path: Path) -> None:
        tools = _tools()
        _stage(tools, _file(tmp_path, "a.csv"), "a.csv")
        sandbox.end_all_sessions()
        result = _stage(tools, _file(tmp_path, "b.csv"), "b.csv")
        assert result.startswith("Staged"), result
        assert result.endswith(NEW_SESSION_NOTICE)
        assert sandbox.files() == [["a.csv"], ["b.csv"]]

    def test_failed_staging_into_a_replacement_session_tells_the_model(
        self, sandbox: FakeSandbox, tmp_path: Path
    ) -> None:
        # The write was rejected, and the files staged earlier are gone as well.
        tools = _tools()
        _stage(tools, _file(tmp_path, "a.csv"), "a.csv")
        sandbox.end_all_sessions()
        sandbox.result = {"content": [{"type": "text", "text": "Permission denied: /etc/x"}], "isError": True}
        result = _stage(tools, _file(tmp_path, "b.csv"), "/etc/x")
        assert result.startswith("Error: staging failed"), result
        assert "Permission denied" in result
        assert result.endswith(NEW_SESSION_NOTICE)


class TestStopAllSessions:
    def test_stops_the_sessions_of_every_tool_pair_in_use(self, sandbox: FakeSandbox) -> None:
        agent_a, agent_b = _tools(), _tools()
        _list_files(agent_a)
        _list_files(agent_b)
        stop_all_sessions()
        assert sorted(sandbox.stopped) == ["aws-session-1", "aws-session-2"]

    def test_a_dropped_tool_pair_is_not_kept_alive(self, sandbox: FakeSandbox) -> None:
        tools = _tools()
        _list_files(tools)
        del tools
        gc.collect()
        stop_all_sessions()
        assert sandbox.stopped == []

    def test_sessions_are_stopped_when_the_interpreter_exits(self) -> None:
        script = textwrap.dedent(
            """
            import warnings
            from unittest.mock import patch
            warnings.simplefilter("ignore")
            from agent_builder_sdk.experimental.code_interpreter import create_code_interpreter_tool
            from tests.experimental.conftest import FakeClient, FakeSandbox

            class LoudClient(FakeClient):
                def stop(self) -> bool:
                    print("stopped", self.session_id)
                    return True

            sandbox = FakeSandbox()
            target = "agent_builder_sdk.experimental.code_interpreter.agentcore_interpreter.CodeInterpreterClient"
            patch(target, lambda region: LoudClient(sandbox)).start()
            tools = create_code_interpreter_tool(region="us-west-2")
            tools[0](code_interpreter_input={"action": {"type": "listFiles"}})
            print("exiting")
            """
        )
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
        out = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120)
        assert out.stdout.splitlines() == ["exiting", "stopped aws-session-1"], out.stdout + out.stderr


def _agent_runtime_server() -> AgentRuntimeServer:
    module = "agent_builder_sdk.server.agent_runtime_server"
    with patch(f"{module}.NotificationHandler"), patch(f"{module}.MessageHandler"):
        return AgentRuntimeServer(agent_factory=Mock())


def _stateless_server() -> StatelessAgentRuntimeServer:
    with patch("agent_builder_sdk.server.stateless_agent_runtime_server.MessageHandler"):
        return StatelessAgentRuntimeServer(agent_factory=Mock())


class TestServerShutdown:
    """A signal ends a served agent without running atexit handlers; the servers stop the sessions."""

    @pytest.mark.parametrize("make_server", [_agent_runtime_server, _stateless_server])
    async def test_lifespan_shutdown_stops_the_sessions(self, sandbox: FakeSandbox, make_server: Any) -> None:
        server: BaseServer = make_server()
        tools = _tools()
        with patch.object(server, "_startup"):
            async with server._lifespan(server.app):
                _list_files(tools)
                assert sandbox.stopped == []
        assert sandbox.stopped == ["aws-session-1"]

    @pytest.mark.parametrize("make_server", [_agent_runtime_server, _stateless_server])
    async def test_stop_request_stops_the_sessions_once(self, sandbox: FakeSandbox, make_server: Any) -> None:
        # A STOP request runs the cleanup, and the lifespan shutdown runs it again.
        server: BaseServer = make_server()
        tools = _tools()
        _list_files(tools)
        with patch.object(server, "handle_stop", AsyncMock(return_value={"message": "stopped"}), create=True):
            response = await server.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": JsonRpcMethods.STOP})
        assert response["error"] is None, response
        assert sandbox.stopped == ["aws-session-1"]
        await server._cleanup()
        assert sandbox.stopped == ["aws-session-1"]

    async def test_a_failed_stop_is_logged_and_does_not_fail_the_shutdown(
        self, sandbox: FakeSandbox, caplog: pytest.LogCaptureFixture
    ) -> None:
        tools = _tools()
        _list_files(tools)
        sandbox.stop_error = RuntimeError("no route to the service")
        with caplog.at_level("WARNING"):
            await _agent_runtime_server()._cleanup()
        assert "Could not stop the code-interpreter sessions: no route to the service" in caplog.text

    def test_a_stop_that_does_not_return_holds_up_neither_the_shutdown_nor_the_exit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The service endpoint does not answer: the stop request stays blocked in its thread.
        endpoint_answers, stop_returned = threading.Event(), threading.Event()
        stop_threads: List[threading.Thread] = []

        def blocked_stop() -> None:
            stop_threads.append(threading.current_thread())
            endpoint_answers.wait(timeout=5)
            stop_returned.set()

        base_server = "agent_builder_sdk.server.base_server"
        with (
            patch.object(code_interpreter_tool, "stop_all_sessions", blocked_stop),
            patch(f"{base_server}._SESSION_STOP_TIMEOUT_SECONDS", 0.05),
            caplog.at_level("WARNING"),
        ):
            try:
                # asyncio.run closes the loop as a process does at its exit: it joins the
                # threads of the loop's executor.
                asyncio.run(_agent_runtime_server()._cleanup())
                assert not stop_returned.is_set()
            finally:
                endpoint_answers.set()
        assert "The code-interpreter sessions were not stopped within 0.05 seconds" in caplog.text
        # The interpreter waits at its exit for every thread that is not a daemon.
        assert [thread.daemon for thread in stop_threads] == [True]

    def test_a_stop_that_returns_after_the_loop_closed_ends_without_an_error(self) -> None:
        endpoint_answers = threading.Event()
        stop_threads: List[threading.Thread] = []
        thread_errors: List[Any] = []

        def late_stop() -> None:
            stop_threads.append(threading.current_thread())
            endpoint_answers.wait(timeout=5)

        with (
            patch.object(code_interpreter_tool, "stop_all_sessions", late_stop),
            patch("agent_builder_sdk.server.base_server._SESSION_STOP_TIMEOUT_SECONDS", 0.05),
            patch.object(threading, "excepthook", thread_errors.append),
        ):
            asyncio.run(_agent_runtime_server()._cleanup())
            endpoint_answers.set()
            stop_threads[0].join(timeout=5)
        assert not stop_threads[0].is_alive()
        assert thread_errors == []

    async def test_the_stop_wait_ends_at_its_limit_when_the_executor_is_busy(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Blocking tool calls run on the default executor of the loop. With every worker
        # busy, a wait that needs a worker would start only when one is free.
        release = threading.Event()
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        tool_call = loop.run_in_executor(None, release.wait, 3)
        try:
            with (
                patch.object(code_interpreter_tool, "stop_all_sessions", lambda: release.wait(3)),
                patch("agent_builder_sdk.server.base_server._SESSION_STOP_TIMEOUT_SECONDS", 0.05),
                caplog.at_level("WARNING"),
            ):
                start = time.monotonic()
                await _agent_runtime_server()._cleanup()
                waited = time.monotonic() - start
        finally:
            release.set()
            await tool_call
        assert waited < 1
        assert "The code-interpreter sessions were not stopped within 0.05 seconds" in caplog.text
