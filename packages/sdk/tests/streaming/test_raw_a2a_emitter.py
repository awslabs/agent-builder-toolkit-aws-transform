# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the raw A2A emitter (Strands events -> raw A2A frames)."""

import json
import uuid

from agent_builder_sdk.streaming.a2a_frame_utils import extract_raw_event
from agent_builder_sdk.streaming.raw_a2a_emitter import (
    RawStreamState,
    _project_event,
    error_frames,
    event_frames,
    finish_frames,
    start_frames,
)


def _state():
    return RawStreamState(context_id="ctx-1")


def test_run_id_minted_and_context_echoed():
    state = _state()
    assert state.run_id  # minted
    frames = start_frames(state)
    assert len(frames) == 1
    opener = frames[0]
    assert opener["kind"] == "task"
    assert opener["id"] == state.run_id
    assert opener["contextId"] == "ctx-1"
    assert opener["status"]["state"] == "submitted"


def test_context_id_omitted_when_none():
    # contextId is optional (A2A spec 3.4.1); when absent it must not appear on any frame.
    state = RawStreamState()  # no context_id
    frames = start_frames(state)
    frames += event_frames({"data": "hi"}, state)
    frames += finish_frames(state)
    assert all("contextId" not in f for f in frames)
    # The inner message on the working frame also omits it.
    working = next(f for f in frames if f.get("status", {}).get("state") == "working")
    assert "contextId" not in working["status"]["message"]


def test_start_frames_emitted_once():
    state = _state()
    assert len(start_frames(state)) == 1
    assert start_frames(state) == []  # second call is a no-op


def test_event_frames_opens_run_then_working():
    state = _state()
    frames = event_frames({"data": "hello"}, state)
    # First event yields the opener AND the working frame.
    assert frames[0]["kind"] == "task"
    working = frames[1]
    assert working["kind"] == "status-update"
    assert working["status"]["state"] == "working"
    assert working["final"] is False
    assert working["taskId"] == state.run_id
    assert working["contextId"] == "ctx-1"
    # Strands event carried verbatim.
    assert extract_raw_event(working) == {"data": "hello"}


def test_event_frames_reasoning_and_tool_verbatim():
    state = _state()
    start_frames(state)
    reasoning = {"reasoningText": "thinking", "reasoning": True}
    tool = {"type": "tool_use_stream", "current_tool_use": {"toolUseId": "x", "name": "t"}}
    r_frames = event_frames(reasoning, state)
    t_frames = event_frames(tool, state)
    assert extract_raw_event(r_frames[0]) == reasoning
    assert extract_raw_event(t_frames[0]) == tool


def test_event_frames_drops_non_dict():
    state = _state()
    start_frames(state)
    assert event_frames("not-a-dict", state) == []


def test_event_frames_projects_out_nonserializable():
    # A real Strands text-delta event bundles the chunk with live, non-JSON-serializable objects
    # (agent, cycle id, trace, span). The emitted frame must keep only the relay-relevant fields
    # and be JSON-serializable — otherwise the SSE serialization crashes mid-stream (F1).
    state = _state()
    start_frames(state)
    event = {
        "data": "Jupiter",
        "delta": {"text": "Jupiter"},
        "agent": object(),
        "event_loop_cycle_id": uuid.uuid4(),
        "request_state": {},
        "event_loop_cycle_trace": object(),
        "event_loop_cycle_span": object(),
    }
    frames = event_frames(event, state)
    assert extract_raw_event(frames[0]) == {"data": "Jupiter", "delta": {"text": "Jupiter"}}
    json.dumps(frames[0])  # must not raise (no agent/uuid/trace/span embedded)


def test_event_frames_drops_lifecycle_and_raw_bedrock_events():
    # Strands lifecycle markers and raw Bedrock envelopes carry nothing the consumer uses; the
    # AG-UI adapter ignores them too, so the raw path emits no content frame for them.
    state = _state()
    start_frames(state)  # run already open, so no opener is produced below
    assert event_frames({"init_event_loop": True}, state) == []
    assert event_frames({"start": True}, state) == []
    assert event_frames({"event": {"messageStart": {"role": "assistant"}}}, state) == []


def test_project_event_preserves_agui_relevant_fields():
    # The projection contract, per event type the adapter recognizes. Junk keys are stripped.
    assert _project_event({"data": "x", "delta": {"t": 1}, "agent": object()}) == {
        "data": "x",
        "delta": {"t": 1},
    }
    assert _project_event({"reasoningText": "r", "reasoning": True, "agent": object()}) == {
        "reasoningText": "r",
        "reasoning": True,
    }
    tool = {
        "type": "tool_use_stream",
        "current_tool_use": {"toolUseId": "1", "name": "t"},
        "delta": {"toolUse": {"input": "{"}},
        "event_loop_cycle_span": object(),
    }
    assert _project_event(tool) == {
        "type": "tool_use_stream",
        "current_tool_use": {"toolUseId": "1", "name": "t"},
        "delta": {"toolUse": {"input": "{"}},
    }
    assert _project_event({"message": {"role": "assistant", "content": []}, "agent": object()}) == {
        "message": {"role": "assistant", "content": []}
    }


def test_projection_keeps_every_field_the_adapter_reads():
    # Guard against drift: the projection must preserve each field a2a_agui_adapter.adapt branches
    # on, so a relayed (projected) event classifies identically to the raw event.
    from agent_builder_sdk.streaming import a2a_agui_adapter as ag

    events = [
        {"data": "x", "agent": object()},
        {"reasoningText": "r", "reasoning": True, "agent": object()},
        {"type": "tool_use_stream", "current_tool_use": {"toolUseId": "1"}, "agent": object()},
        {"message": {"role": "assistant", "content": []}, "agent": object()},
    ]
    for ev in events:
        p = _project_event(ev)
        assert ag._is_text_delta(p) == ag._is_text_delta(ev)
        assert ag._is_reasoning_text_delta(p) == ag._is_reasoning_text_delta(ev)
        assert ag._is_tool_use_delta(p) == ag._is_tool_use_delta(ev)
        assert ag._is_assistant_message(p) == ag._is_assistant_message(ev)


def test_result_event_not_emitted_as_content():
    state = _state()
    start_frames(state)
    # A terminal result event should not produce a working content frame.
    frames = event_frames({"result": object()}, state)
    assert frames == []


def test_finish_frames_terminal_completed():
    state = _state()
    start_frames(state)
    frames = finish_frames(state)
    assert len(frames) == 1
    assert frames[0]["status"]["state"] == "completed"
    assert frames[0]["final"] is True
    assert state.ended is True
    # Idempotent.
    assert finish_frames(state) == []


def test_finish_frames_empty_turn_gets_opener():
    state = _state()
    frames = finish_frames(state)
    # Opener + terminal even with no events.
    assert frames[0]["kind"] == "task"
    assert frames[-1]["status"]["state"] == "completed"


def test_finish_frames_surfaces_force_stop_response():
    class _Result:
        state = {"force_stop_response": "the real answer"}

    state = _state()
    start_frames(state)
    frames = finish_frames(state, _Result())
    # A working text frame carrying the force-stop answer, then the terminal.
    text_frame = frames[0]
    assert extract_raw_event(text_frame) == {"data": "the real answer"}
    assert frames[-1]["status"]["state"] == "completed"


def test_error_frames_failed_terminal():
    state = _state()
    start_frames(state)
    frames = error_frames(state, "boom")
    terminal = frames[-1]
    assert terminal["status"]["state"] == "failed"
    assert terminal["final"] is True
    assert extract_raw_event(terminal) == {"data": "boom", "error": True}
    assert state.ended is True


def test_error_frames_opens_run_if_needed():
    state = _state()
    frames = error_frames(state, "early failure")
    assert frames[0]["kind"] == "task"  # opener precedes the failed terminal
    assert frames[-1]["status"]["state"] == "failed"


def test_finish_after_error_is_noop():
    state = _state()
    error_frames(state, "boom")
    assert finish_frames(state) == []
