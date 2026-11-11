# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""End-to-end test of the raw agent-to-agent streaming loop.

Callee raw emitter -> serialize to SSE bytes -> caller SSE reader -> aggregate final text.
Exercises the full callee-emit -> caller-consume path against the exact frame bytes the callee
produces, with no AWS and no real agent.
"""

import json

from agent_builder_sdk.streaming.a2a_frame_utils import extract_raw_event, frame_state
from agent_builder_sdk.streaming.raw_a2a_emitter import (
    RawStreamState,
    event_frames,
    finish_frames,
)
from agent_builder_sdk.streaming.sse_reader import iter_frames


class _Body:
    def __init__(self, data: bytes):
        self._data = data

    def iter_chunks(self, chunk_size):
        # Deliberately tiny chunks to exercise cross-chunk line reassembly.
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i : i + chunk_size]


def _serialize(frames):
    return "".join(f"data: {json.dumps(f)}\n\n" for f in frames).encode("utf-8")


def _aggregate_final_text(frames):
    parts = []
    for f in frames:
        event = extract_raw_event(f)
        if event and isinstance(event.get("data"), str) and not event.get("error"):
            parts.append(event["data"])
    return "".join(parts).strip()


def test_callee_emit_to_caller_consume_final_text():
    # Callee produces a turn: reasoning, a tool call, then the answer, then terminal.
    state = RawStreamState(context_id="ctx-e2e")
    emitted = []
    strands_events = [
        {"reasoningText": "let me think", "reasoning": True},
        {"type": "tool_use_stream", "current_tool_use": {"toolUseId": "t1", "name": "lookup"}},
        {"data": "The answer is "},
        {"data": "42."},
    ]
    for e in strands_events:
        emitted.extend(event_frames(e, state))
    emitted.extend(finish_frames(state, result=None))

    # Serialize to SSE bytes and read back through the caller's reader (tiny chunks).
    body = _Body(_serialize(emitted))
    received = list(iter_frames(body, chunk_size=4))

    # Envelope integrity: single opener, single terminal, matching ids.
    assert received[0]["kind"] == "task"
    assert received[-1]["status"]["state"] == "completed"
    task_id = received[0]["id"]
    assert received[0]["contextId"] == "ctx-e2e"
    assert all(f["taskId"] == task_id for f in received if f["kind"] == "status-update")

    # Aggregation matches the buffered path: only final answer text, reasoning/tool dropped.
    assert _aggregate_final_text(received) == "The answer is 42."


def test_e2e_force_stop_response_is_final_text():
    class _Result:
        state = {"force_stop_response": "terminated early with answer"}

    state = RawStreamState(context_id="ctx-fs")
    emitted = list(event_frames({"data": "pre-tool narration"}, state))
    emitted.extend(finish_frames(state, result=_Result()))

    received = list(iter_frames(_Body(_serialize(emitted)), chunk_size=8))
    text = _aggregate_final_text(received)
    assert "pre-tool narration" in text
    assert "terminated early with answer" in text


def test_e2e_error_terminal_propagates():
    from agent_builder_sdk.streaming.raw_a2a_emitter import error_frames

    state = RawStreamState(context_id="ctx-err")
    emitted = list(event_frames({"data": "partial"}, state))
    emitted.extend(error_frames(state, "sub-agent blew up"))

    received = list(iter_frames(_Body(_serialize(emitted)), chunk_size=8))
    assert received[-1]["status"]["state"] == "failed"
    assert any(frame_state(f) == "failed" for f in received)
