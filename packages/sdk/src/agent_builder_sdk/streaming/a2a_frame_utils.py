# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Accessors for raw A2A streaming frames (see ``raw_a2a_emitter`` for the frame structure).

Helpers shared by the emitter (callee), the AG-UI adapter, and the SSE reader (caller), so the frame
shape has one source of truth. The ``status.state`` strings are taken straight from the
``a2a.types.TaskState`` enum, so they track the A2A spec instead of hand-copied literals.
"""

from typing import Any, Dict, Optional

from a2a.types import TaskState

# Type alias — frames are bare dicts on the wire, same as ``to_a2a_frames`` returns on the
# AG-UI side. Kept as an alias (not a model) so no marshal/unmarshal is needed at the relay.
A2AFrame = Dict[str, Any]

# The raw agent-to-agent streaming extension. The Strands event rides as content in a DataPart
# keyed by this URI, and the URI is listed in the carrier message's ``extensions`` — the same
# discovery convention the AG-UI extension (``_AGUI_EXT_URI``) and the annotation extensions use:
# URI in ``extensions`` -> read ``data[URI]``. Distinct from the AG-UI URI so a reader can tell a
# raw frame from an AG-UI frame.
RAW_EXT_URI = "https://aws.com/transform/ext/strands-raw/v1"

# Strands tool name of the terminating relay tool (SendMessageTools.send_message_to_subagent_and_relay;
# Strands derives the tool name from the method name).
RELAY_TOOL_NAME = "send_message_to_subagent_and_relay"

# A2A task-state wire values, sourced from the a2a-sdk TaskState enum so they track the spec.
STATE_SUBMITTED = TaskState.submitted.value
STATE_WORKING = TaskState.working.value
STATE_COMPLETED = TaskState.completed.value
STATE_FAILED = TaskState.failed.value

_TERMINAL_STATES = frozenset({STATE_COMPLETED, STATE_FAILED})


# --- frame envelope builders (dependency-free) -------------------------------
# One source of truth for the A2A wire envelopes, shared by the raw emitter (callee), the AG-UI
# adapter, and the server's fallback terminal, so the three don't each re-build the same dicts.
# ``state`` is a STATE_* literal; ``context_id`` is optional (A2A spec 3.4.1) and omitted when None.


def _with_context_id(frame: A2AFrame, context_id: Optional[str]) -> A2AFrame:
    """Attach ``contextId`` only when present (it is optional per A2A spec 3.4.1)."""
    if context_id is not None:
        frame["contextId"] = context_id
    return frame


def status_update(
    task_id: str,
    context_id: Optional[str],
    state: str,
    *,
    final: bool,
    message: Optional[Dict[str, Any]] = None,
) -> A2AFrame:
    """Build an A2A TaskStatusUpdateEvent dict (camelCase wire shape)."""
    status: Dict[str, Any] = {"state": state}
    if message is not None:
        status["message"] = message
    return _with_context_id(
        {"kind": "status-update", "taskId": task_id, "final": final, "status": status},
        context_id,
    )


def data_message(
    uri: str,
    payload: Any,
    message_id: str,
    task_id: str,
    context_id: Optional[str],
) -> Dict[str, Any]:
    """Wrap ``payload`` as an A2A agent Message carrying it in a DataPart keyed by ``uri``.

    ``uri`` is also listed in ``extensions`` so a reader discovers it the same way as the other A2A
    extensions (URI in ``extensions`` -> read ``data[URI]``). Shared by the raw emitter (RAW_EXT_URI
    + a Strands event) and the AG-UI adapter (AG-UI URI + an AG-UI event).
    """
    return _with_context_id(
        {
            "kind": "message",
            "role": "agent",
            "messageId": message_id,
            "taskId": task_id,
            "extensions": [uri],
            "parts": [{"kind": "data", "data": {uri: payload}}],
        },
        context_id,
    )


def task_opener(
    task_id: str,
    context_id: Optional[str],
    *,
    message: Optional[Dict[str, Any]] = None,
) -> A2AFrame:
    """Build the A2A ``task`` opener (state ``submitted``), emitted once per turn.

    Optionally carries an opening ``message`` in its status (the AG-UI path puts its RUN_STARTED
    event there; the raw path emits none).
    """
    status: Dict[str, Any] = {"state": STATE_SUBMITTED}
    if message is not None:
        status["message"] = message
    return _with_context_id({"kind": "task", "id": task_id, "status": status}, context_id)


def frame_kind(frame: A2AFrame) -> Optional[str]:
    """The frame's top-level ``kind`` (``task`` | ``status-update``), or None."""
    return frame.get("kind")


def frame_state(frame: A2AFrame) -> Optional[str]:
    """The A2A task state on this frame (``submitted``/``working``/``completed``/``failed``)."""
    status = frame.get("status")
    if isinstance(status, dict):
        return status.get("state")
    return None


def is_final(frame: A2AFrame) -> bool:
    """True if the frame is flagged ``final`` (A2A pre-1.0 signal)."""
    return frame.get("final") is True


def is_terminal_state(state: Optional[str]) -> bool:
    """True if a state string is a turn-ending state (``completed`` / ``failed``)."""
    return state in _TERMINAL_STATES


def is_end_of_turn(frame: A2AFrame) -> bool:
    """True if this frame ends the turn — ``final: true`` OR a terminal state.

    Stream close (iterator exhaustion) is the third end condition and is handled by the reader
    loop terminating, not here. A2A v1.0 removed ``final``, so a robust consumer treats any of
    the three as end-of-turn.
    """
    return is_final(frame) or is_terminal_state(frame_state(frame))


def extract_raw_event(frame: A2AFrame) -> Optional[Dict[str, Any]]:
    """Lift the verbatim Strands event out of a raw frame's DataPart, or None.

    Walks ``status.message.parts`` for the ``kind == "data"`` part and returns
    ``data[RAW_EXT_URI]``. Returns None when the frame carries no raw event (e.g. an envelope-only
    terminal), so callers can skip it.
    """
    status = frame.get("status")
    if not isinstance(status, dict):
        return None
    message = status.get("message")
    if not isinstance(message, dict):
        return None
    for part in message.get("parts", []):
        if isinstance(part, dict) and part.get("kind") == "data":
            data = part.get("data")
            if isinstance(data, dict) and RAW_EXT_URI in data:
                event = data[RAW_EXT_URI]
                return event if isinstance(event, dict) else None
    return None
