# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the evolver's write-path confinement callback.

The evolver runs with permission_mode="acceptEdits", which auto-approves every
Write/Edit. The can_use_tool callback is the only thing keeping an
LLM-driven (and thus prompt-injectable) file_path from writing outside the
editable target directory.
"""

import tempfile
from pathlib import Path

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from harness_evolver.evolver import evolver as evolver_mod
from harness_evolver.evolver.evolver import _make_confine_to_target, _run_evolver_step


@pytest.fixture
def confined():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "agent_under_test"
        target.mkdir()
        yield target, _make_confine_to_target(target)


async def test_allows_relative_path_inside_target(confined):
    target, cb = confined
    res = await cb("Edit", {"file_path": "AGENT.md"}, None)
    assert isinstance(res, PermissionResultAllow)


async def test_allows_absolute_path_inside_target(confined):
    target, cb = confined
    res = await cb("Write", {"file_path": str(target / "sub" / "mcp.json")}, None)
    assert isinstance(res, PermissionResultAllow)


async def test_allows_non_write_tools(confined):
    _, cb = confined
    res = await cb("Read", {"file_path": "/etc/passwd"}, None)
    assert isinstance(res, PermissionResultAllow)


async def test_denies_absolute_path_outside_target(confined):
    _, cb = confined
    res = await cb("Write", {"file_path": "/home/user/.aws/credentials"}, None)
    assert isinstance(res, PermissionResultDeny)


async def test_denies_dotdot_escape(confined):
    target, cb = confined
    res = await cb("Edit", {"file_path": "../../other_repo/file.py"}, None)
    assert isinstance(res, PermissionResultDeny)


async def test_denies_multiedit_escape(confined):
    _, cb = confined
    res = await cb("MultiEdit", {"file_path": "/tmp/evil"}, None)
    assert isinstance(res, PermissionResultDeny)


async def test_denies_missing_file_path(confined):
    _, cb = confined
    res = await cb("Write", {}, None)
    assert isinstance(res, PermissionResultDeny)


# --- _run_evolver_step wiring ---------------------------------------------
#
# can_use_tool sends its verdict back to the CLI over stdin, so the evolver must
# drive the agent via ClaudeSDKClient (session-lived stdin), not the one-shot
# query() (which closes stdin when the prompt iterator drains and only keeps it
# open for sdk_mcp_servers/hooks). These tests pin that wiring with a fake client
# so a regression back to query() is caught offline.


class _FakeClient:
    """Stand-in for ClaudeSDKClient that records how it was driven."""

    last_instance = None

    def __init__(self, options=None):
        self.options = options
        self.queried = None
        self.entered = False
        self.exited = False
        _FakeClient.last_instance = self

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *exc):
        self.exited = True
        return False

    async def query(self, prompt, session_id="default"):
        self.queried = prompt

    async def receive_response(self):
        # Two parsed messages, mimicking what the real client yields.
        for msg in ({"type": "assistant", "text": "editing"}, {"type": "result"}):
            yield msg


async def test_run_evolver_step_uses_client_and_writes_trace(monkeypatch):
    monkeypatch.setattr(evolver_mod, "ClaudeSDKClient", _FakeClient)

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "agent_under_test"
        target.mkdir()
        trace = Path(tmp) / "trace.jsonl"

        await _run_evolver_step(target, "do the edit", trace)

        client = _FakeClient.last_instance
        # Driven as a context manager, with the prompt forwarded and the
        # response fully drained into the trace.
        assert client.entered and client.exited
        assert client.queried == "do the edit"
        # The confinement callback is wired onto the options actually used.
        assert client.options.can_use_tool is not None
        lines = [line for line in trace.read_text().splitlines() if line.strip()]
        assert len(lines) == 2
