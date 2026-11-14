# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""A stand-in for the Bedrock AgentCore Code Interpreter service, for the sandbox tool tests."""

import itertools
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Set
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError


class FakeSandbox:
    """The data plane as the tests see it: the sessions started and what happened in each."""

    def __init__(self) -> None:
        self.started: List[Dict[str, Any]] = []  # the arguments of every start call
        self.calls: Dict[str, List[Any]] = {}  # session id -> (method, arguments) of each call
        self.ended: Set[str] = set()  # session ids the service has terminated
        self.stopped: List[str] = []  # session ids stopped by the client
        self.result: Dict[str, Any] = {"content": [{"type": "text", "text": "ok"}], "isError": False}
        self.invoke_error: Optional[ClientError] = None  # raised by calls on a running session
        self.stop_error: Optional[Exception] = None
        self.ended_barrier: Optional[threading.Barrier] = None  # see FakeClient.invoke
        self.session_started = threading.Event()
        self._ids = itertools.count(1)

    def client(self, region: str) -> "FakeClient":
        return FakeClient(self)

    def end_all_sessions(self) -> None:
        """What the service does when a session's lifetime runs out."""
        self.ended.update(self.calls)

    def files(self) -> List[List[str]]:
        """The paths written to each session, in session start order."""
        return [
            [file["path"] for method, arguments in calls if method == "writeFiles" for file in arguments["content"]]
            for calls in self.calls.values()
        ]


class FakeClient:
    """The subset of ``bedrock_agentcore``'s ``CodeInterpreter`` client that the SDK calls."""

    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.session_id: Optional[str] = None

    def start(self, identifier: str, name: str, session_timeout_seconds: int) -> str:
        time.sleep(0.05)  # a real start takes about a second; widen the race window
        self.sandbox.started.append(
            {"identifier": identifier, "name": name, "session_timeout_seconds": session_timeout_seconds}
        )
        self.session_id = f"aws-session-{next(self.sandbox._ids)}"
        self.sandbox.calls[self.session_id] = []
        self.sandbox.session_started.set()
        return self.session_id

    def stop(self) -> bool:
        if self.sandbox.stop_error:
            raise self.sandbox.stop_error
        self.sandbox.stopped.append(str(self.session_id))
        return True

    def get_session(self) -> Dict[str, Any]:
        return {"status": "TERMINATED" if self.session_id in self.sandbox.ended else "READY"}

    def invoke(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.session_id in self.sandbox.ended:
            # With a barrier, parallel calls on the ended session meet here: one fails at
            # once, the rest only after a replacement session has started.
            if self.sandbox.ended_barrier and self.sandbox.ended_barrier.wait(timeout=5):
                self.sandbox.session_started.wait(timeout=5)
            error = {"Error": {"Code": "ResourceNotFoundException", "Message": "session ended"}}
            raise ClientError(error, "InvokeCodeInterpreter")
        if self.sandbox.invoke_error:
            raise self.sandbox.invoke_error
        self.sandbox.calls[str(self.session_id)].append((method, params))
        return {"stream": [{"result": self.sandbox.result}] if self.sandbox.result else []}


@pytest.fixture
def sandbox() -> Iterator[FakeSandbox]:
    fake = FakeSandbox()
    target = "agent_builder_sdk.experimental.code_interpreter.agentcore_interpreter.CodeInterpreterClient"
    with patch(target, fake.client):
        yield fake
