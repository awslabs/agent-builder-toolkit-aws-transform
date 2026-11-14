# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the AgentCore interpreter: action mapping, session handling and results."""

import importlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from agent_builder_sdk.experimental.code_interpreter.agentcore_interpreter import (
    NEW_SESSION_NOTICE,
    AgentCoreCodeInterpreter,
    CodeInterpreterInput,
)
from tests.experimental.conftest import FakeSandbox

_LIST_FILES: Dict[str, Any] = {"path": "."}


def _interpreter() -> AgentCoreCodeInterpreter:
    return AgentCoreCodeInterpreter(region="us-west-2")


@pytest.mark.parametrize(
    "action, arguments",
    [
        (
            {"type": "executeCode", "code": "print(1)"},
            {"code": "print(1)", "language": "python", "clearContext": False},
        ),
        (
            {"type": "executeCode", "code": "1", "language": "javascript", "clear_context": True},
            {"code": "1", "language": "javascript", "clearContext": True},
        ),
        ({"type": "executeCommand", "command": "ls"}, {"command": "ls"}),
        ({"type": "readFiles", "paths": ["a", "b"]}, {"paths": ["a", "b"]}),
        ({"type": "listFiles"}, {"path": "."}),
        ({"type": "removeFiles", "paths": ["a"]}, {"paths": ["a"]}),
        (
            {"type": "writeFiles", "content": [{"path": "a.txt", "text": "hi"}]},
            {"content": [{"path": "a.txt", "text": "hi"}]},
        ),
    ],
)
def test_action_is_sent_as_its_service_method(
    sandbox: FakeSandbox, action: Dict[str, Any], arguments: Dict[str, Any]
) -> None:
    result = _interpreter().run(CodeInterpreterInput.model_validate({"action": action}).action)
    assert result == {"status": "success", "content": [{"text": "[{'type': 'text', 'text': 'ok'}]"}]}
    assert sandbox.calls == {"aws-session-1": [(action["type"], arguments)]}


def test_first_call_starts_the_default_session_and_later_calls_reuse_it(sandbox: FakeSandbox) -> None:
    interpreter = AgentCoreCodeInterpreter(region="us-west-2", identifier="custom-1", session_timeout_seconds=60)
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    assert sandbox.started == [
        {"identifier": "custom-1", "name": interpreter.default_session, "session_timeout_seconds": 60}
    ]
    assert len(sandbox.calls["aws-session-1"]) == 2


def test_parallel_first_calls_share_one_session(sandbox: FakeSandbox) -> None:
    interpreter = _interpreter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: interpreter.invoke(None, "listFiles", _LIST_FILES), range(3)))
    assert [r["status"] for r in results] == ["success"] * 3
    assert len(sandbox.started) == 1


def test_a_session_name_is_private_to_its_interpreter(sandbox: FakeSandbox) -> None:
    first, second = _interpreter(), _interpreter()
    first.invoke("analysis", "listFiles", _LIST_FILES)
    second.invoke("analysis", "listFiles", _LIST_FILES)
    first.invoke("analysis", "listFiles", _LIST_FILES)
    assert [len(calls) for calls in sandbox.calls.values()] == [2, 1]


def test_a_failed_action_is_an_error_result(sandbox: FakeSandbox) -> None:
    sandbox.result = {"content": [{"type": "text", "text": "No such file"}], "isError": True}
    result = _interpreter().invoke(None, "readFiles", {"paths": ["x"]})
    assert result["status"] == "error"
    assert "No such file" in result["content"][0]["text"]


def test_a_response_without_a_result_is_an_error_result(sandbox: FakeSandbox) -> None:
    sandbox.result = {}
    result = _interpreter().invoke(None, "listFiles", _LIST_FILES)
    assert result == {"status": "error", "content": [{"text": "The sandbox returned no result."}]}


def test_ended_session_is_replaced_once_and_the_result_says_so(sandbox: FakeSandbox) -> None:
    interpreter = _interpreter()
    first = interpreter.invoke(None, "listFiles", _LIST_FILES)
    assert NEW_SESSION_NOTICE not in [block["text"] for block in first["content"]]

    sandbox.end_all_sessions()
    replaced = interpreter.invoke(None, "listFiles", _LIST_FILES)
    assert replaced["status"] == "success"
    assert replaced["content"][0] == {"text": NEW_SESSION_NOTICE}
    assert len(replaced["content"]) == 2
    assert len(sandbox.started) == 2

    later = interpreter.invoke(None, "listFiles", _LIST_FILES)
    assert len(later["content"]) == 1
    assert len(sandbox.started) == 2


def test_parallel_calls_on_an_ended_session_all_run_in_one_replacement(sandbox: FakeSandbox) -> None:
    # All four calls fail on the ended session; one starts a replacement, and the other
    # three, failing after that, must run again in it rather than re-raise.
    interpreter = _interpreter()
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    sandbox.end_all_sessions()
    sandbox.session_started.clear()
    sandbox.ended_barrier = threading.Barrier(4)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: interpreter.invoke(None, "listFiles", _LIST_FILES), range(4)))
    assert all(r["content"][0] == {"text": NEW_SESSION_NOTICE} for r in results), results
    assert len(sandbox.started) == 2
    assert len(sandbox.calls["aws-session-2"]) == 4


def test_error_on_a_running_session_is_raised_without_a_retry(sandbox: FakeSandbox) -> None:
    interpreter = _interpreter()
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    sandbox.invoke_error = ClientError({"Error": {"Code": "ThrottlingException"}}, "InvokeCodeInterpreter")
    with pytest.raises(ClientError, match="ThrottlingException"):
        interpreter.invoke(None, "listFiles", _LIST_FILES)
    assert len(sandbox.started) == 1
    assert len(sandbox.calls["aws-session-1"]) == 1


def test_stop_all_sessions_stops_each_session_and_the_next_call_starts_a_new_one(sandbox: FakeSandbox) -> None:
    interpreter = _interpreter()
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    interpreter.invoke("analysis", "listFiles", _LIST_FILES)
    interpreter.stop_all_sessions()
    assert sandbox.stopped == ["aws-session-1", "aws-session-2"]

    interpreter.stop_all_sessions()
    assert len(sandbox.stopped) == 2

    result = interpreter.invoke(None, "listFiles", _LIST_FILES)
    assert len(result["content"]) == 1
    assert len(sandbox.started) == 3


def test_a_call_in_flight_when_the_sessions_are_stopped_is_not_run_again(sandbox: FakeSandbox) -> None:
    interpreter = _interpreter()
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    sandbox.call_gate = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(interpreter.invoke, None, "executeCode", {"code": "print(1)"})
        assert sandbox.call_waiting.wait(timeout=5)
        interpreter.stop_all_sessions()
        sandbox.call_gate.set()
        with pytest.raises(ClientError, match="ResourceNotFoundException"):
            call.result(timeout=5)
    assert len(sandbox.started) == 1
    assert sandbox.calls == {"aws-session-1": [("listFiles", _LIST_FILES)]}

    # The stop does not end the retry of later calls: a session that the service ends is replaced.
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    sandbox.end_all_sessions()
    assert interpreter.invoke(None, "listFiles", _LIST_FILES)["content"][0] == {"text": NEW_SESSION_NOTICE}
    assert len(sandbox.started) == 3


@pytest.mark.parametrize(
    "error",
    [
        ClientError({"Error": {"Code": "ConflictException"}}, "StopCodeInterpreterSession"),
        EndpointConnectionError(endpoint_url="https://example.invalid"),
    ],
)
def test_a_session_that_cannot_be_stopped_is_logged_and_forgotten(
    sandbox: FakeSandbox, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    interpreter = _interpreter()
    interpreter.invoke(None, "listFiles", _LIST_FILES)
    sandbox.stop_error = error
    with caplog.at_level("WARNING"):
        interpreter.stop_all_sessions()
    assert f"Could not stop sandbox session {interpreter.default_session}" in caplog.text
    sandbox.stop_error = None
    interpreter.stop_all_sessions()
    assert sandbox.stopped == []


def test_import_error_names_the_extra() -> None:
    name = "agent_builder_sdk.experimental.code_interpreter.agentcore_interpreter"
    # patch.dict puts the real modules back when the block ends.
    with patch.dict(sys.modules, {"bedrock_agentcore.tools.code_interpreter_client": None}):
        del sys.modules[name]
        with pytest.raises(ImportError, match=r"bedrock-agentcore.*\[code-interpreter\]"):
            importlib.import_module(name)
