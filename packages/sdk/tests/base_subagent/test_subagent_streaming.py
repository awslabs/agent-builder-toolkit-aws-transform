# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for AsyncBaseSubagent.process_message_stream (raw A2A streaming)."""

from unittest import mock

from strands.models import Model

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.streaming.a2a_frame_utils import extract_raw_event, frame_state
from agent_builder_sdk.streaming.config import StreamingConfig


def _subagent():
    agent = AsyncBaseSubagent("test prompt")
    agent.callback_handler = lambda *a, **k: None
    agent.model = mock.create_autospec(Model, spec_set=True, instance=True)
    return agent


def _request(context_id="ctx-1"):
    return ProcessMessageRequest(
        "hello",
        ConversationContext(a2a_context=A2AContext(context_id=context_id)),
    )


def _make_stream(events):
    async def _stream(*args, **kwargs):
        for e in events:
            yield e

    return _stream


async def test_missing_context_id_is_omitted_not_rejected():
    # Agent-to-agent has no chat context; a contextId-less request must NOT be rejected. contextId
    # is optional (A2A spec 3.4.1), so it is simply omitted from the frames (parity with the
    # buffered send path, which never sets it).
    agent = _subagent()
    agent.stream_async = _make_stream([{"data": "x"}, {"result": mock.Mock(state={})}])
    req = ProcessMessageRequest("hi", ConversationContext())  # no a2a_context
    frames = [f async for f in agent.process_message_stream(req, conversation_id="conv")]
    assert frames[0]["kind"] == "task"
    assert frames[-1]["status"]["state"] == "completed"
    # No contextId key anywhere — it was neither required nor invented.
    assert all("contextId" not in f for f in frames)


async def test_happy_path_opener_working_terminal():
    agent = _subagent()
    events = [
        {"reasoningText": "thinking", "reasoning": True},
        {"data": "the answer"},
        {"result": mock.Mock(state={})},
    ]
    agent.stream_async = _make_stream(events)

    frames = [f async for f in agent.process_message_stream(_request(), conversation_id="conv")]

    assert frames[0]["kind"] == "task"
    assert frames[0]["status"]["state"] == "submitted"
    assert frames[-1]["status"]["state"] == "completed"
    assert frames[-1]["final"] is True
    # Reasoning + text carried verbatim in working frames.
    working_events = [extract_raw_event(f) for f in frames if frame_state(f) == "working"]
    assert {"reasoningText": "thinking", "reasoning": True} in working_events
    assert {"data": "the answer"} in working_events


async def test_context_id_echoed_run_id_minted():
    agent = _subagent()
    agent.stream_async = _make_stream([{"data": "x"}, {"result": mock.Mock(state={})}])
    frames = [
        f async for f in agent.process_message_stream(_request("ctx-echo"), conversation_id="conv")
    ]
    task_id = frames[0]["id"]
    assert all(f.get("contextId") == "ctx-echo" for f in frames)
    # taskId on the status-updates matches the agent-minted run id (the opener's id).
    assert all(f["taskId"] == task_id for f in frames if f["kind"] == "status-update")


async def test_error_during_stream_yields_failed_terminal():
    agent = _subagent()

    async def _boom(*args, **kwargs):
        yield {"data": "partial"}
        raise RuntimeError("model exploded")

    agent.stream_async = _boom
    frames = [f async for f in agent.process_message_stream(_request(), conversation_id="conv")]
    assert frames[-1]["status"]["state"] == "failed"
    assert frames[-1]["final"] is True
    # Detail is not leaked; a generic message is used.
    assert "internal error" in extract_raw_event(frames[-1])["data"].lower()


async def test_concurrency_exception_yields_failed_terminal():
    from strands.types.exceptions import ConcurrencyException

    agent = _subagent()

    async def _busy(*args, **kwargs):
        raise ConcurrencyException("already running")
        yield  # pragma: no cover - makes this an async generator

    agent.stream_async = _busy
    frames = [f async for f in agent.process_message_stream(_request(), conversation_id="conv")]
    assert frames[-1]["status"]["state"] == "failed"
    assert "already processing" in extract_raw_event(frames[-1])["data"].lower()


async def test_timeout_yields_failed_terminal():
    import asyncio

    agent = _subagent()

    async def _slow(*args, **kwargs):
        await asyncio.sleep(10)
        yield {"data": "never"}

    agent.stream_async = _slow
    cfg = StreamingConfig(turn_timeout_seconds=0.05)
    frames = [
        f async for f in agent.process_message_stream(_request(), conversation_id="conv", cfg=cfg)
    ]
    assert frames[-1]["status"]["state"] == "failed"
    assert "too long" in extract_raw_event(frames[-1])["data"].lower()


async def test_force_stop_response_surfaced_as_final_text():
    agent = _subagent()
    result = mock.Mock(state={"force_stop_response": "terminating answer"})
    agent.stream_async = _make_stream([{"data": "pre-tool narration"}, {"result": result}])
    frames = [f async for f in agent.process_message_stream(_request(), conversation_id="conv")]
    working_texts = [
        extract_raw_event(f).get("data")
        for f in frames
        if frame_state(f) == "working" and extract_raw_event(f)
    ]
    assert "terminating answer" in working_texts


def test_streaming_policy_is_neutral():
    # A sub-agent replies to another agent, not Chat: no hooks, contextId optional.
    from agent_builder_sdk.interfaces import StreamingCapable

    agent = _subagent()
    assert isinstance(agent, StreamingCapable)
    assert agent.get_streaming_hook_providers(StreamingConfig()) == []
    assert agent.requires_context_id() is False
