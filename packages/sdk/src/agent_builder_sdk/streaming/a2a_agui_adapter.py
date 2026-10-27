# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Translates Strands stream events into canonical AG-UI events.

This is the only module that knows Strands' event shapes. Swapping the agent SDK
means writing a sibling adapter; nothing else in the streaming path changes.

We emit ``ag_ui.core`` event objects and let the ingress layer serialize them.
Grounded in the strands event dicts (strands/types/_events.py). Strands emits no
text-message start/end, so we synthesize them: a start on the first text token, an
end when the assistant message arrives (or the run ends with one still open).
Dispatch is by dict-key presence, not a discriminator field, because Strands
events are plain dicts by the time we see them.

At most one content block is open at a time (a reasoning message, an assistant
text message, or a tool call). Switching block type closes the open one first.
Parallel tool calls stream sequentially (start/deltas/stop for tool A, then B), so
a new toolUseId closes the previous tool and opens the next.

Tool-call args are the incremental fragment (delta.toolUse.input), not the
cumulative buffer, to avoid O(n^2) on the wire.

``StreamingConfig`` gates the reasoning and tool-call categories at each branch head:
if a category is off we return before opening its block, so no start/content/end is
emitted and nothing is left dangling. Text (narration + final answer) is always emitted.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ag_ui.core import (
    BaseEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from pydantic import BaseModel, Field

from agent_builder_sdk.streaming.a2a_frame_utils import (
    RELAY_CYCLE_SEPARATOR,
    RELAY_TOOL_NAME,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_WORKING,
    data_message,
    is_assistant_message,
    status_update,
    task_opener,
)
from agent_builder_sdk.streaming.config import DEFAULT_STREAMING_CONFIG, StreamingConfig


@dataclass
class StreamState:
    """Per-run mutable state. One instance per agent run (per turn).

    Three distinct ids ride each turn:
    - ``thread_id``  — the AG-UI threadId: a stable conversation id (rides in the AG-UI
      DataPart on run-lifecycle events).
    - ``context_id`` — the A2A contextId: the routing id the caller minted and
      stored for reply routing. The agent ECHOes it on the A2A frame envelope; it is NOT
      the conversation id and NOT agent-minted.
    - ``run_id``     — the A2A taskId / AG-UI runId for this one turn. Minted here (the
      agent is the A2A server and owns Task ids), never accepted from the caller, so a
      request id can't be reused as the run id.
    """

    thread_id: str
    context_id: str = ""
    run_id: str = field(init=False)
    run_started: bool = False
    open_message_id: str | None = None  # set while an assistant text message is streaming
    open_tool_id: str | None = None  # the toolUseId while a tool call is streaming
    open_reasoning_id: str | None = None  # set while a reasoning message is streaming
    # messageId for the current tool-use model-call; all tool_use blocks of one call
    # share it. Minted on the first tool, cleared at the model-call boundary. Persist
    # uses the same id so stream and poll reconcile.
    tool_message_id: str | None = None
    # id of the final assistant text message this turn. Unlike open_message_id (cleared
    # on block close), kept for the whole turn so persist writes the final message under
    # the same id the stream showed.
    final_message_id: str | None = None
    # id of the reasoning message for the CURRENT model-call, kept past the block close
    # so persist writes the THINKING message under the same id. Per-model-call: resets at
    # the model-call boundary; None when the call had no reasoning.
    reasoning_message_id: str | None = None
    # id of the force_stop_response answer (a terminating tool's stop_after_response). This is its
    # OWN message, distinct from any pre-tool narration the model streamed — so it gets a dedicated
    # id, NOT final_message_id (which a narration text block may already own; reusing it would
    # persist two different texts under one messageId and collide on reload). Read-or-minted by
    # whichever of the persist hook (AfterInvocationEvent, fires first) or the adapter terminal
    # branch reaches it first.
    force_stop_message_id: str | None = None
    # True once send_message_to_subagent_and_relay has streamed the terminating answer live (under
    # force_stop_message_id). The terminal branch then just closes that block instead of re-emitting
    # the whole answer, so a relayed answer isn't rendered twice (live deltas + terminal one-shot).
    force_stop_streamed: bool = False
    # True after a relayed sub-agent model call ended; the next relayed text starts a new cycle.
    relay_cycle_ended: bool = False
    # The persist hook's save of this turn's final answer, once started; resolves to whether it was
    # stored. A disconnect after it started records an interruption only if that save fails.
    final_persist: Optional["asyncio.Future[bool]"] = None
    # Events produced OUTSIDE the model token stream (e.g. suggestion interactions the response
    # hook builds at end-of-turn) that must still ride the live stream. The hook appends wire-ready
    # events here; the stream loop drains them and yields their frames before the terminal. Kept off
    # the model stream because they are known only after the turn's final message is assembled.
    side_events: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_id = str(uuid.uuid4())

    def ensure_force_stop_message_id(self) -> str:
        """Return the force_stop_response answer's message id, minting it once on first call.

        The force_stop answer is a distinct assistant message from any pre-tool narration, so it
        always gets its own id (never final_message_id, which the narration may own). BOTH the persist
        hook (on AfterInvocationEvent, fires first) and the adapter terminal branch must write under
        this ONE id so the streamed answer and its persisted copy reconcile on reload; whichever runs
        first mints, the other reads. Idempotent and single-threaded per turn (each turn owns its
        StreamState), so no lock."""
        if self.force_stop_message_id is None:
            self.force_stop_message_id = str(uuid.uuid4())
        return self.force_stop_message_id


def _is_text_delta(event: Dict[str, Any]) -> bool:
    # TextStreamEvent -> {"data": <str>, "delta": {...}}
    return isinstance(event.get("data"), str)


def _is_terminal_result(event: Dict[str, Any]) -> bool:
    # AgentResultEvent -> {"result": AgentResult}
    return "result" in event


def _is_force_stop(event: Dict[str, Any]) -> bool:
    # ForceStopEvent -> {"force_stop": True, "force_stop_reason": <str>}. Strands yields this ONLY
    # from its except blocks (each followed by a raise), so it always signals an ERROR — never a
    # clean terminating-tool stop. The clean stop_after_response case is a normal terminal result
    # (see _is_terminal_result / _force_stop_response).
    return event.get("force_stop") is True


def _force_stop_response(event: Dict[str, Any]) -> Optional[str]:
    """The terminating-tool ``force_stop_response`` on a terminal AgentResult, if any.

    A tool that ends the turn early (stop_after_response) writes the real answer to the agent/request
    state under ``force_stop_response``; it surfaces on ``AgentResult.state``. This is a
    codebase-local convention (not a Strands built-in) that the buffered path already honors
    (message_handler / queue_handler), so the streaming path reads it the same way. Returns None when
    the result carries no such state (an ordinary turn)."""
    result = event.get("result")
    state = getattr(result, "state", None)
    if isinstance(state, dict):
        text = state.get("force_stop_response")
        return text if isinstance(text, str) and text else None
    return None


def _is_tool_use_delta(event: Dict[str, Any]) -> bool:
    # ToolUseStreamEvent ->
    #   {"type": "tool_use_stream", "delta": {"toolUse": {"input": <frag>}},
    #    "current_tool_use": {"toolUseId", "name", "input"}}
    return event.get("type") == "tool_use_stream"


def _is_relayed_tool_stream(event: Dict[str, Any]) -> bool:
    # ToolStreamEvent -> {"type": "tool_stream", "tool_stream_event": {"tool_use": ..., "data": ...}}.
    # Strands emits one per yield of ANY async-generator tool (and agent-as-tool), so the type alone
    # doesn't identify the relay — match on the tool name too, or an unrelated streaming tool's yields
    # would be mis-rendered as the orchestrator's final answer.
    if event.get("type") != "tool_stream":
        return False
    tool_use = (event.get("tool_stream_event") or {}).get("tool_use") or {}
    return tool_use.get("name") == RELAY_TOOL_NAME


def _is_reasoning_text_delta(event: Dict[str, Any]) -> bool:
    # ReasoningTextStreamEvent ->
    #   {"reasoningText": <str>, "delta": {...}, "reasoning": True}
    # Only the TEXT variant carries user-facing thinking; the redacted/signature
    # reasoning variants (also reasoning=True) are not surfaced.
    return event.get("reasoning") is True and isinstance(event.get("reasoningText"), str)


def _start_run_if_needed(state: StreamState, out: List[BaseEvent]) -> None:
    if not state.run_started:
        state.run_started = True
        out.append(RunStartedEvent(thread_id=state.thread_id, run_id=state.run_id))


def _close_message_if_open(state: StreamState, out: List[BaseEvent]) -> None:
    if state.open_message_id is not None:
        out.append(TextMessageEndEvent(message_id=state.open_message_id))
        state.open_message_id = None


def _close_tool_if_open(state: StreamState, out: List[BaseEvent]) -> None:
    if state.open_tool_id is not None:
        # ToolCallEnd carries only toolCallId; it correlates to the START that
        # already carried the messageId.
        out.append(ToolCallEndEvent(tool_call_id=state.open_tool_id))
        state.open_tool_id = None


def _close_reasoning_if_open(state: StreamState, out: List[BaseEvent]) -> None:
    if state.open_reasoning_id is not None:
        out.append(ReasoningMessageEndEvent(message_id=state.open_reasoning_id))
        state.open_reasoning_id = None


def _close_open_block(state: StreamState, out: List[BaseEvent]) -> None:
    """Close whichever content block is open (reasoning, text, or tool). At most one is."""
    _close_reasoning_if_open(state, out)
    _close_message_if_open(state, out)
    _close_tool_if_open(state, out)


def _end_model_call(state: StreamState, out: List[BaseEvent]) -> None:
    """Close the open block and end the current model-call, resetting the per-model-call
    ids so the next call mints fresh ones. Parallel tools within one call share
    tool_message_id (they only trigger _close_open_block, not this)."""
    _close_open_block(state, out)
    state.tool_message_id = None
    state.reasoning_message_id = None


def adapt(
    event: Dict[str, Any],
    state: StreamState,
    cfg: StreamingConfig = DEFAULT_STREAMING_CONFIG,
) -> List[BaseEvent]:
    """Translate one Strands stream event into zero or more AG-UI events.

    Returns a list because one Strands event can synthesize several AG-UI events
    (e.g. a first text token emits RunStarted + TextMessageStart + TextMessageContent).
    Unrecognized events return [] (dropped). ``cfg`` gates the reasoning and tool-call
    categories at the branch head; run lifecycle and text are always emitted.
    """
    if not isinstance(event, dict):
        return []

    if _is_relayed_tool_stream(event):
        # A sub-agent event relayed live by send_message_to_subagent_and_relay tool: Strands wraps each of the
        # tool's yields as a tool_stream event carrying the yielded value under tool_stream_event.data.
        # Translate it as the orchestrator's own live output (see _adapt_relayed_event). Non-dict
        # payloads (e.g. the tool's final result string) are not stream content, so drop them.
        inner = (event.get("tool_stream_event") or {}).get("data")
        if isinstance(inner, dict):
            return _adapt_relayed_event(inner, state, cfg)
        return []

    out: List[BaseEvent] = []

    if _is_reasoning_text_delta(event):
        if not cfg.emit_reasoning:
            return []
        # Reasoning streams first in a turn (before any answer text/tool). Surface it
        # as its own message so the client can show "thinking" while the model works.
        _start_run_if_needed(state, out)
        if state.open_reasoning_id is None:
            state.open_reasoning_id = str(uuid.uuid4())
            # Kept for the whole turn so persist writes the THINKING message under this
            # same id (open_reasoning_id clears on close).
            state.reasoning_message_id = state.open_reasoning_id
            out.append(
                ReasoningMessageStartEvent(message_id=state.open_reasoning_id, role="reasoning")
            )
        out.append(
            ReasoningMessageContentEvent(
                message_id=state.open_reasoning_id, delta=event["reasoningText"]
            )
        )
        return out

    if _is_text_delta(event):
        _start_run_if_needed(state, out)
        _close_reasoning_if_open(state, out)  # answer text closes the reasoning block
        _close_tool_if_open(state, out)  # a text block after a tool block closes the tool
        if state.open_message_id is None:
            state.open_message_id = str(uuid.uuid4())
            # Remembered for the whole turn so persist writes the final message under
            # this same id (open_message_id itself clears on close).
            state.final_message_id = state.open_message_id
            out.append(TextMessageStartEvent(message_id=state.open_message_id, role="assistant"))
        out.append(TextMessageContentEvent(message_id=state.open_message_id, delta=event["data"]))
        return out

    if _is_tool_use_delta(event):
        if not cfg.emit_tool_calls:
            return []
        _start_run_if_needed(state, out)
        tool = event.get("current_tool_use") or {}
        tool_id = tool.get("toolUseId")
        if not tool_id:
            return out  # malformed; nothing to anchor the call to
        # One messageId per tool-use model-call: all tools of this call persist as a
        # single message, so they share it. Minted on the first tool; cleared at the
        # model-call boundary.
        if state.tool_message_id is None:
            state.tool_message_id = str(uuid.uuid4())
        if state.open_tool_id != tool_id:
            # A new tool call: close whatever block was open, then start this one.
            _close_open_block(state, out)
            state.open_tool_id = tool_id
            out.append(
                ToolCallStartEvent(
                    tool_call_id=tool_id,
                    tool_call_name=tool.get("name", ""),
                    parent_message_id=state.tool_message_id,
                )
            )
        # Args are the incremental fragment, not the cumulative current_tool_use buffer.
        delta = (event.get("delta") or {}).get("toolUse", {}).get("input", "")
        if delta:
            out.append(ToolCallArgsEvent(tool_call_id=tool_id, delta=delta))
        return out

    if is_assistant_message(event):
        # End of the model's assistant turn: close whatever block is open.
        _end_model_call(state, out)
        return out

    if _is_force_stop(event):
        # Strands yields ForceStopEvent ONLY from its except blocks, each immediately followed by a
        # raise — so this always precedes an exception that propagates to _stream_message_async's
        # outer handler, which emits ONE sanitized terminal RUN_ERROR (to_a2a_error_frames). We must
        # NOT emit a terminal here: the reason carries the RAW exception (Bedrock ARNs, account ids,
        # endpoints), and emitting it would (1) leak that detail to the client and (2) produce a
        # SECOND terminal frame after the outer handler's. Just close any open block so the wire
        # stays balanced (Start-without-End) ahead of that terminal; emit no RUN_ERROR.
        _end_model_call(state, out)
        return out

    if _is_terminal_result(event):
        # A guardrail block needs no special handling here: Bedrock requires a non-empty
        # blockedOutputsMessaging and streams it as an ordinary text delta before the terminal, so
        # the owner's block message already rode the wire as assistant text (and persists as the
        # final response) exactly like a normal answer. The terminal just closes the run.
        _end_model_call(state, out)
        _start_run_if_needed(state, out)  # empty run (no tokens) still gets a start
        # A terminating tool (stop_after_response) sets force_stop_response on the result state to
        # the REAL answer, and the buffered path returns THAT instead of the LLM's pre-tool text
        # (message_handler / queue_handler read agent_response.state["force_stop_response"]). On the
        # stream, the model only produced its pre-tool narration + the tool call; the real answer
        # lives only on the result state and would otherwise never reach the client (missing live AND
        # on refresh). If present, stream it as the final assistant text under its own dedicated
        # force_stop_message_id (NOT final_message_id, which a pre-tool narration text block may
        # already own) so the streamed + persisted response match the buffered path. Mirrors the
        # buffered force_stop_response override.
        force_stop_text = _force_stop_response(event)
        if force_stop_text and not state.force_stop_streamed:
            # Read-or-mint the dedicated id: the persist hook (AfterInvocationEvent) fires before this
            # terminal is mapped, so it may have already minted force_stop_message_id for the same
            # force_stop text — reuse it so the streamed message and its persisted copy reconcile.
            msg_id = state.ensure_force_stop_message_id()
            out.append(TextMessageStartEvent(message_id=msg_id, role="assistant"))
            out.append(TextMessageContentEvent(message_id=msg_id, delta=force_stop_text))
            out.append(TextMessageEndEvent(message_id=msg_id))
        # If force_stop_streamed, send_message_to_subagent_and_relay already streamed this answer live under
        # the same id; _end_model_call above closed that block, so we skip re-emitting it here.
        out.append(RunFinishedEvent(thread_id=state.thread_id, run_id=state.run_id))
        return out

    # Lifecycle / raw model chunks / state events — dropped.
    return []


def _adapt_relayed_event(
    inner: Dict[str, Any],
    state: StreamState,
    cfg: StreamingConfig,
) -> List[BaseEvent]:
    """Translate ONE sub-agent event that send_message_to_subagent_and_relay relayed live.

    ``inner`` is a bare Strands stream event from the sub-agent. We re-emit it as the orchestrator's
    OWN AG-UI output, so the sub-agent's reply shows up as the orchestrator's answer, live.

    Handling by event type:
      - text delta      -> emit as the orchestrator's answer text (details below)
      - reasoning delta -> reuse the normal adapt() path (renders as "thinking")
      - anything else   -> ignored (the sub-agent's own tool calls, lifecycle markers, ...)

    For a text delta (the sub-agent's answer): the relay tool ends the orchestrator's turn with this
    answer as the FINAL response (it sets force_stop_response + stop_event_loop). Two OTHER places act
    on that same force_stop_response at end-of-turn, so we must line up with both:

      1. The persist hook writes the answer to Chat under ``force_stop_message_id`` so it survives a
         reload. We stream the live deltas under that SAME id, so the live copy and the reloaded copy
         are ONE message (same id) instead of two competing ones.

      2. The terminal branch (``_is_terminal_result``) normally RE-EMITS force_stop_response as one
         final text block — needed for an ordinary terminating tool whose answer never streamed. But
         we already streamed it live here, so we set ``force_stop_streamed`` to tell that branch to
         SKIP the re-emit; otherwise the answer would render twice (our live deltas + its one-shot).
    """
    if is_assistant_message(inner):
        state.relay_cycle_ended = True
        return []
    if _is_text_delta(inner):
        # An empty delta carries no text; it must not open a cycle (or emit a separator) that the
        # persisted answer, which joins only cycles with text, would not have.
        if not inner["data"]:
            return []
        out: List[BaseEvent] = []
        _start_run_if_needed(state, out)
        # Only one content block may be open at a time, so answer text closes any open reasoning/tool.
        _close_reasoning_if_open(state, out)
        _close_tool_if_open(state, out)
        # Open (once) the answer block under the shared force_stop id; subsequent deltas reuse it.
        msg_id = state.ensure_force_stop_message_id()
        if state.open_message_id != msg_id:
            _close_message_if_open(state, out)
            state.open_message_id = msg_id
            out.append(TextMessageStartEvent(message_id=msg_id, role="assistant"))
        if state.relay_cycle_ended and state.force_stop_streamed:
            out.append(TextMessageContentEvent(message_id=msg_id, delta=RELAY_CYCLE_SEPARATOR))
        state.relay_cycle_ended = False
        out.append(TextMessageContentEvent(message_id=msg_id, delta=inner["data"]))
        state.force_stop_streamed = True  # terminal branch: don't re-emit this answer
        return out
    if _is_reasoning_text_delta(inner):
        return adapt(inner, state, cfg)
    return []


class InteractionEvent(BaseModel):
    """Actionable UI interactions for a turn, emitted on the stream.

    Carries the turn's interactions (suggestion chips, a job-creation button) so they render live
    with the response instead of only after a reload. ``interactions`` is the list the client renders
    (each with an ``actionType`` and its ``data``); ``message_id`` ties them to the assistant message
    they belong to so the live and reloaded copies reconcile.
    """

    type: str = "INTERACTION"
    message_id: Optional[str] = Field(default=None, serialization_alias="messageId")
    interactions: List[Dict[str, Any]]


def build_suggestion_interaction_events(
    chat_suggestions: Optional[List[str]],
    create_job_suggestion: Optional[Dict[str, Any]],
    message_id: Optional[str] = None,
) -> List[InteractionEvent]:
    """Build the interaction event(s) for a turn's suggestions.

    - a create-job suggestion (``{jobName, jobType, objective}``) becomes an INVOKE interaction that
      offers to create and start the job, and takes precedence over chat suggestions when both are
      present;
    - otherwise chat suggestions (``list[str]``) become one SELECT interaction whose options are the
      suggestion strings (label == value).

    Returns [] when neither is present."""
    if create_job_suggestion:
        job_name = create_job_suggestion.get("jobName")
        job_type = create_job_suggestion.get("jobType")
        objective = create_job_suggestion.get("objective")
        if job_name and job_type and objective:
            invoke = {
                "actionType": "INVOKE",
                "data": {
                    "invokeInteractionData": {
                        "invokeApi": {
                            "label": "Create job",
                            "operationName": "createAndStartJob",
                            "operationParams": {
                                "jobName": job_name,
                                "jobType": job_type,
                                "objective": objective,
                            },
                        }
                    }
                },
            }
            return [InteractionEvent(message_id=message_id, interactions=[invoke])]
    if chat_suggestions:
        options = [{"label": s, "value": s} for s in chat_suggestions]
        select = {
            "actionType": "SELECT",
            "data": {"selectInteractionData": {"options": options}},
        }
        return [InteractionEvent(message_id=message_id, interactions=[select])]
    return []


def to_wire(event: BaseModel) -> Dict[str, Any]:
    """Serialize an AG-UI (or our own InteractionEvent) event to its JSON-ready camelCase wire dict.

    ``by_alias`` gives the camelCase field names the wire contract expects
    (messageId, toolCallId, threadId); ``exclude_none`` drops unset optionals.

    One rename: ag_ui's ToolCallStartEvent carries the tool-use message id under
    ``parentMessageId`` (its field name), but on our wire every event names the
    persisted message id ``messageId``. So we surface it as ``messageId`` here,
    consistent with the text/reasoning events.
    """
    wire = event.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(event, ToolCallStartEvent) and "parentMessageId" in wire:
        wire["messageId"] = wire.pop("parentMessageId")
    return wire


# --- A2A framing layer -------------------------------------------------------
#
# adapt() above produces canonical AG-UI events. On the wire we speak A2A
# message/stream: each SSE frame is a JSON-RPC response whose result is an A2A
# type (Task / TaskStatusUpdateEvent). AG-UI content events ride verbatim inside a
# DataPart (data.agui); run-lifecycle events map to the A2A envelope (Task opener /
# terminal status-update), carrying no DataPart.
#
# State names come from the shared STATE_* constants in a2a_frame_utils (which mirror the a2a-sdk
# TaskState values), so the raw and AG-UI paths agree on one set of strings. The frames themselves
# are built as plain dicts (the codebase already speaks A2A via dicts — see custom_types.A2AMessage —
# and this keeps the wire shape explicit); the camelCase field names match a2a-sdk's aliases.
#
# Keeping adapt() AG-UI-native means this layer is the only thing that knows A2A;
# swapping either side (AG-UI encoding, or A2A envelope) stays localized here.

# The AG-UI streaming extension. The AG-UI event rides as render content in a DataPart, keyed by
# this URI, and the URI is listed in the carrier message's ``extensions`` — the same signal the
# agent's other A2A extensions use (source_information / message_type / chat_suggestions in
# utils.py), so a reader discovers it the same way: URI in ``extensions`` -> read ``data[uri]``.
# Payload stays in ``data`` (it is content, not annotation), so unlike those metadata-carried
# extensions the value lives in the DataPart rather than message ``metadata``.
_AGUI_EXT_URI = "https://aws.com/transform/ext/agui/v1"


def _agui_data_message(
    agui_wire: Dict[str, Any], message_id: str, task_id: str, context_id: str
) -> Dict[str, Any]:
    """Wrap one AG-UI event dict as an A2A agent Message carrying it in a DataPart keyed by the AG-UI
    extension URI (delegates to the shared builder)."""
    return data_message(_AGUI_EXT_URI, agui_wire, message_id, task_id, context_id)


def to_a2a_frames(agui_event: BaseModel, state: StreamState) -> List[Dict[str, Any]]:
    """Map one AG-UI (or our own InteractionEvent) event to one A2A result frame (plain dict).

    Content events (reasoning / text / tool) become a working TaskStatusUpdateEvent
    whose status.message carries the AG-UI event in a DataPart. Lifecycle events use
    the A2A envelope: RUN_STARTED -> Task(submitted); RUN_FINISHED -> terminal
    status-update(completed, final=true); RUN_ERROR -> terminal status-update(failed,
    final=true). Every lifecycle frame also carries its AG-UI event verbatim in a
    DataPart, so the fields that live only on the AG-UI event (RUN_STARTED's threadId +
    runId, RUN_ERROR's reason) survive the A2A framing and the reader can lift them out
    of status.message the same way it does for content events, rather than reconstructing
    them from the envelope.
    """
    wire = to_wire(agui_event)
    etype = wire.get("type")
    task_id = state.run_id  # the A2A task id for this turn (agent-minted)
    ctx = state.context_id  # the A2A contextId: the caller-minted routing id we echo

    if etype == "RUN_STARTED":
        msg = _agui_data_message(wire, task_id, task_id, ctx)
        return [task_opener(task_id, ctx, message=msg)]

    if etype == "RUN_FINISHED":
        msg = _agui_data_message(wire, task_id, task_id, ctx)
        return [status_update(task_id, ctx, STATE_COMPLETED, final=True, message=msg)]

    if etype == "RUN_ERROR":
        msg = _agui_data_message(wire, wire.get("messageId", task_id), task_id, ctx)
        return [status_update(task_id, ctx, STATE_FAILED, final=True, message=msg)]

    # Content event: carry the AG-UI event verbatim in a working status-update.
    message_id = wire.get("messageId", task_id)
    msg = _agui_data_message(wire, message_id, task_id, ctx)
    return [status_update(task_id, ctx, STATE_WORKING, final=False, message=msg)]


def to_a2a_error_frames(message: str, state: StreamState) -> List[Dict[str, Any]]:
    """Build the frames for a terminal streaming error, keeping the frame protocol valid.

    A raw ``RUN_ERROR`` alone emits only a terminal ``failed/final`` status-update. If the
    error fires before the run opened (no content event yet), or with a content block still
    open, that terminal frame would arrive with NO ``Task(submitted)`` opener and/or with an
    unclosed Text/Reasoning/ToolCall block — violating the same open-run / close-block
    invariant the force_stop and terminal-result paths honor. This mirrors that invariant:
    open the run if needed, close any open block, THEN emit RUN_ERROR.

    Returns fully-mapped A2A frames (dicts) ready to yield.
    """
    events: List[BaseEvent] = []
    _start_run_if_needed(state, events)  # ensure Task(submitted) opener precedes the error
    _close_open_block(state, events)  # balance any open Text/Reasoning/ToolCall block
    events.append(RunErrorEvent(message=message))
    frames: List[Dict[str, Any]] = []
    for ev in events:
        frames.extend(to_a2a_frames(ev, state))
    return frames


def to_a2a_text_reply_frames(text: str, state: StreamState) -> List[Dict[str, Any]]:
    """Build the frames of a one-shot assistant text reply: the run opener, one text block, then
    RUN_FINISHED — the same frames a normal short answer streams, so the client renders it as an
    ordinary reply (FES lifts only AG-UI DataParts; a plain text part on a terminal is dropped)."""
    events: List[BaseEvent] = []
    _start_run_if_needed(state, events)
    _close_open_block(state, events)
    message_id = str(uuid.uuid4())
    state.final_message_id = message_id  # the id a persisted copy of this reply must use
    events.append(TextMessageStartEvent(message_id=message_id, role="assistant"))
    events.append(TextMessageContentEvent(message_id=message_id, delta=text))
    events.append(TextMessageEndEvent(message_id=message_id))
    events.append(RunFinishedEvent(thread_id=state.thread_id, run_id=state.run_id))
    frames: List[Dict[str, Any]] = []
    for ev in events:
        frames.extend(to_a2a_frames(ev, state))
    return frames
