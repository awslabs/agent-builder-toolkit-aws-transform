# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Emit raw A2A frames from Strands stream events (agent-to-agent, no AG-UI).

When a sub-agent streams its reply to another agent, this module turns each event the model
produces into a "frame" on the wire. This is the raw counterpart of the AG-UI path
(``a2a_agui_adapter``): the consumer is another agent (not a browser), so instead of translating
each Strands event into a typed UI event, we carry a **wire-safe projection** of the Strands event
— only the fields ``a2a_agui_adapter.adapt`` reads (see ``_RELAY_EVENT_KEYS``). A relay can pull the
event back out (``a2a_frame_utils.extract_raw_event``) and feed it straight into ``adapt`` to produce
AG-UI, with no reconstruction; the caller can also aggregate the answer text off ``data``. We project
rather than forward the raw event because a real Strands event bundles the chunk with live,
non-JSON-serializable objects (the agent itself, ``event_loop_cycle_id``, OTEL trace/span) that
would break wire serialization and are useless to the consumer.

WHAT GETS SENT — the nesting (biggest to smallest)
--------------------------------------------------
One streamed turn is a sequence of **frames** (one SSE ``data:`` line each). A frame is a plain
dict whose top-level ``kind`` is either ``task`` (the opener) or ``status-update`` (content / the
end). A ``status-update`` may carry a **message** (an A2A Message object) under ``status.message``;
that message holds a list of **parts** (content blocks); we use one ``data`` part, and the raw
Strands event lives inside it, keyed by ``RAW_EXT_URI``::

    frame  (kind = "task" | "status-update")
      └─ status
           └─ message   (kind = "message"  — an A2A Message)
                └─ parts        (a list of content blocks)
                     └─ [0]     (kind = "data")
                          └─ data
                               └─ {RAW_EXT_URI: <Strands event>}   ← the actual content

Note ``kind`` appears at THREE levels with different meanings: the frame ("task"/"status-update"),
the message ("message"), and the part ("data"). ``taskId`` appears on both the frame and the
message — not a bug: they are two distinct A2A objects that each define it (the AG-UI path nests
them the same way). ``contextId`` is optional (A2A spec 3.4.1 — it groups related tasks/messages
into one conversation); agent-to-agent has nothing to group, so it is omitted entirely here.

A raw Strands event is whatever ``stream_async`` yields — e.g. a text delta ``{"data": "..."}``,
reasoning ``{"reasoningText": "...", "reasoning": true}``, or a tool call
``{"type": "tool_use_stream", "current_tool_use": {...}}``.

WHAT A TURN LOOKS LIKE
----------------------
::

    # 1. opener — no message, just announces the run  (contextId omitted for agent-to-agent)
    {"kind": "task", "id": "<run>", "status": {"state": "submitted"}}

    # 2. one per Strands event — the event rides verbatim in a data part
    {"kind": "status-update", "taskId": "<run>", "final": false,
     "status": {"state": "working",
                "message": {"kind": "message", "role": "agent", "messageId": "...",
                            "parts": [{"kind": "data",
                                       "data": {RAW_EXT_URI: {"data": "the answer"}}}]}}}

    # 3. the last frame — completed, no message (the happy-path terminal)
    {"kind": "status-update", "taskId": "<run>", "final": true, "status": {"state": "completed"}}

ERROR PATH — what a failed turn looks like
------------------------------------------
On any error (exception, timeout, concurrent-invocation reject), ``error_frames`` replaces the
``completed`` terminal with a ``failed`` one that — unlike the happy-path terminal — DOES carry a
message: a single data part holding a generic, already-sanitized error string (the raw exception
detail stays in the log). The ``"error": true`` marker distinguishes it from ordinary answer text::

    # opener (only if the run hadn't already started) — same as the happy path
    {"kind": "task", "id": "<run>", "status": {"state": "submitted"}}

    # terminal — failed/final, carrying the sanitized error text
    {"kind": "status-update", "taskId": "<run>", "final": true,
     "status": {"state": "failed",
                "message": {"kind": "message", "role": "agent", "messageId": "...",
                            "parts": [{"kind": "data",
                                       "data": {RAW_EXT_URI: {"data": "An internal error ...",
                                                              "error": true}}}]}}}

This mirrors the AG-UI framing so both speak the same envelope; only the DataPart key and payload
differ (``RAW_EXT_URI`` + raw event, vs the AG-UI URI + a translated event). The error terminal
here is self-contained (no AG-UI dependency, unlike ``to_a2a_error_frames``).

SPECIAL CASE — a "terminating tool" (``stop_after_response``)
-------------------------------------------------------------
Such a tool ends the turn the moment it runs, so the model never speaks again. The real answer for
the user is what the tool writes to ``AgentResult.state["force_stop_response"]`` — NOT the model's
last words, which are only its pre-tool narration ("Sure, let me call the tool..."). That answer
lives only on the final result and was never streamed as an event. So at end-of-turn we pull it
out and emit it as one more text event before the terminal, so the streamed answer is the tool's
real answer — matching the buffered path, which already prefers ``force_stop_response`` over the
model's pre-tool text.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_builder_sdk.streaming.a2a_frame_utils import (
    RAW_EXT_URI,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_WORKING,
    A2AFrame,
    data_message,
    status_update,
    task_opener,
)

# The subset of Strands stream-event keys the AG-UI adapter (``a2a_agui_adapter.adapt``) actually
# reads. The raw path forwards ONLY these, so a relay can rebuild AG-UI and the caller can aggregate
# text off ``data`` — while everything else Strands attaches to an event is dropped.
_RELAY_EVENT_KEYS = frozenset(
    {
        "data",  # text delta
        "reasoning",  # reasoning flag
        "reasoningText",  # reasoning text delta
        "type",  # "tool_use_stream" discriminator
        "current_tool_use",  # tool id / name / input
        "delta",  # incremental tool-use args (delta.toolUse.input)
        "message",  # assistant message (model-call end)
        "force_stop",  # force-stop flag (reason intentionally dropped — it can leak raw detail)
    }
)


def _project_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the wire-safe, relay-relevant keys (see ``_RELAY_EVENT_KEYS``)."""
    return {k: event[k] for k in _RELAY_EVENT_KEYS if k in event}


@dataclass
class RawStreamState:
    """Per-turn mutable state for the raw emitter.

    - ``run_id`` is the A2A taskId for this turn, minted here — the agent is the A2A server and owns
    Task ids, never taking one from the request.
    - ``context_id`` is the A2A contextId, which groups related tasks/messages into one conversation (A2A spec 3.4.1);
    it is **optional** and only set when the caller supplies one.
    - ``run_started`` guards the single ``task`` opener;
    - ``ended`` guardsa double terminal.
    """

    context_id: Optional[str] = None
    run_id: str = field(init=False)
    run_started: bool = False
    ended: bool = False

    def __post_init__(self) -> None:
        self.run_id = str(uuid.uuid4())


# The frame envelope builders (status_update, data_message, task_opener) live in a2a_frame_utils so
# the raw and AG-UI paths share one implementation; they are imported above. status_update is thus
# re-exported from this module — the server imports it from here for its fallback terminal frame.


def start_frames(state: RawStreamState) -> List[A2AFrame]:
    """The ``task``(submitted) opener, emitted once. Empty if the run already started."""
    if state.run_started:
        return []
    state.run_started = True
    return [task_opener(state.run_id, state.context_id)]


def event_frames(event: Dict[str, Any], state: RawStreamState) -> List[A2AFrame]:
    """Map one Strands stream event to raw A2A frame(s).

    Opens the run on the first event, then emits one ``working`` status-update carrying the
    projected event (only the fields ``adapt`` reads — see ``_project_event``).

    Emits no content frame when there's nothing to relay: non-dict events, or events that project to
    empty (Strands lifecycle markers and raw ``{"event": ...}`` Bedrock envelopes) — same events
    ``adapt`` ignores. The ``result`` event is skipped here; ``finish_frames`` handles end-of-turn
    (including any ``force_stop_response``).
    """
    if not isinstance(event, dict):
        return []
    frames = start_frames(state)
    # The terminal AgentResult event is handled by finish_frames (it closes the run and surfaces
    # force_stop_response); do not also emit it as a working content frame.
    if "result" in event:
        return frames
    projected = _project_event(event)
    if not projected:
        # Nothing the consumer can use (lifecycle marker / raw Bedrock envelope). Drop the content
        # frame but keep any opener already produced above.
        return frames
    message_id = str(uuid.uuid4())
    msg = data_message(RAW_EXT_URI, projected, message_id, state.run_id, state.context_id)
    frames.append(
        status_update(state.run_id, state.context_id, STATE_WORKING, final=False, message=msg)
    )
    return frames


def _force_stop_response(result: Any) -> Optional[str]:
    """The terminating-tool ``force_stop_response`` on a terminal AgentResult, if any."""
    state = getattr(result, "state", None)
    if isinstance(state, dict):
        text = state.get("force_stop_response")
        return text if isinstance(text, str) and text else None
    return None


def finish_frames(state: RawStreamState, result: Any = None) -> List[A2AFrame]:
    """Close the turn with a terminal ``completed`` status-update.

    Opens the run first if no event was seen (an empty turn still gets an opener + terminal). If
    the terminal AgentResult carries a ``force_stop_response`` (a terminating tool's real answer),
    surface it as a final text event so the streamed answer matches the buffered path. Idempotent:
    returns empty if the turn already ended.
    """
    if state.ended:
        return []
    frames = start_frames(state)
    force_stop_text = _force_stop_response(result)
    if force_stop_text:
        # Emit the real answer as a synthetic text event so the consumer aggregates it as the
        # final response (mirrors adapt's terminal branch).
        text_event = {"data": force_stop_text}
        msg = data_message(
            RAW_EXT_URI, text_event, str(uuid.uuid4()), state.run_id, state.context_id
        )
        frames.append(
            status_update(state.run_id, state.context_id, STATE_WORKING, final=False, message=msg)
        )
    frames.append(status_update(state.run_id, state.context_id, STATE_COMPLETED, final=True))
    state.ended = True
    return frames


def error_frames(state: RawStreamState, message: str) -> List[A2AFrame]:
    """Terminal ``failed`` frames for an error, keeping the protocol valid.

    Ensures a ``task`` opener precedes the terminal (a failed/final frame with no opener would
    violate the open-run invariant), then emits a ``failed``/``final`` status-update whose message
    carries the error text as a raw text event. Self-contained — no AG-UI dependency (unlike
    ``to_a2a_error_frames``). Idempotent: returns empty if the turn already ended.
    """
    if state.ended:
        return []
    frames = start_frames(state)
    err_event = {"data": message, "error": True}
    msg = data_message(RAW_EXT_URI, err_event, str(uuid.uuid4()), state.run_id, state.context_id)
    frames.append(
        status_update(state.run_id, state.context_id, STATE_FAILED, final=True, message=msg)
    )
    state.ended = True
    return frames
