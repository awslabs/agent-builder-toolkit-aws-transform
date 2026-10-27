# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Persist a streaming turn's messages back to ATX Chat, the streaming counterpart of
the message/send return-value persist.

On message/send the agent RETURNS a SendMessageOutput and ATX Chat persists it. On
message/stream the response is a live SSE stream with no return-value catcher, so the
agent must persist its own reply, keyed by the turn's contextId so Chat routes it to
the right user.

A turn is a sequence of model calls, and within a call the stream shows, in order: an
optional reasoning ("thinking") message, an optional assistant text message (a pre-tool
narration on a tool-use step, or the final answer on the end-turn step), and tool calls.
This hook fires once per model call and persists each streamed MESSAGE as its own Chat
message under the SAME id the stream showed it, so a refresh reconstructs the trajectory
the user watched, not just the final answer, and each streamed message reconciles with
its persisted copy by messageId:

- reasoning under ``StreamState.reasoning_message_id`` (PARTIAL_UPDATE),
- assistant text under ``StreamState.final_message_id`` (the id of the text block the
  adapter streamed in this call): PARTIAL_UPDATE for a pre-tool narration, the final
  response on end-turn,
- tool calls under ``StreamState.tool_message_id`` (the id the stream's ToolCallStart
  carried): one PARTIAL_UPDATE per model-call, rendered as a formatted "Using tool"
  line so the tool step replays on refresh. The persist channel carries text only, so
  the structured card the stream showed is flattened to text here; a client can special-
  render it later off the same id.

Registered ONLY on the per-user streaming agents (see agent_runtime_server
_setup_concurrent_streaming). The shared singleton agent that serves message/send never
gets this hook, so the buffered path's persistence is unchanged.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from strands.hooks import AfterInvocationEvent, AfterModelCallEvent, HookProvider, HookRegistry

from agent_builder_sdk.agentic_framework.a2a_manager import get_a2a_manager
from agent_builder_sdk.constants import GUARDRAIL_STOP_REASONS
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.env_var import get_agent_context_from_env
from agent_builder_sdk.streaming.config import StreamingConfig
from agent_builder_sdk.util.suggestions_manager import get_and_consume_suggestions
from agent_builder_sdk.utils import (
    A2A_CHAT_SUGGESTIONS_EXT,
    A2A_MESSAGE_TYPE_EXT,
    A2A_SOURCE_INFORMATION_EXT,
)

logger = logging.getLogger(__name__)

# Chat persists (and routes to the user) A2A messages addressed to this instance id.
_CHAT_AGENT_INSTANCE_ID = "ATX_CHAT"

# Stop reasons that end a turn with the FINAL assistant response. A guardrail block
# (guardrail_intervened / content_filtered) is treated as one of these: the block message Bedrock
# returns is the turn's final text, so it persists like a normal end_turn answer. A guardrail final
# never carries suggestion chips — see the consume logic in _on_after_model_call.
_FINAL_STOP_REASONS = ("end_turn", "stop_sequence") + GUARDRAIL_STOP_REASONS

# A model call that stops on "tool_use" is an INTERMEDIATE step: the assistant said
# something (its thinking / narration) and is about to call a tool. We persist that as a
# partial update so it survives a refresh, exactly like the live stream showed it.
_PARTIAL_STOP_REASONS = ("tool_use",)

# Value Chat expects on the message_type/v1 extension to treat a message as a partial
# update (thinking/progress) rather than a final response. Absent => Chat defaults to
# final (A2A_RESPONSE). Verified against Chat SendA2AMessageActivity.extractAgentResponseType.
_PARTIAL_UPDATE_METADATA = {"messageType": "partial_update"}

# Cap each tool call's serialized args in the persisted "Using tool" text, so a large tool
# input (e.g. a pasted file or long code blob) can't bloat chat history. The live stream
# still shows the full args; this only bounds the history replay.
_MAX_TOOL_ARGS_CHARS = 2000

# Cap the persisted reasoning text for the same reason: a reasoning-heavy turn can emit tens
# of KB of thinking, and persisting it verbatim would bloat chat history. The live stream
# still shows the full reasoning; this only bounds the history replay.
_MAX_REASONING_CHARS = 4000

# Cap each per-turn persist send. _persist runs INSIDE the turn's asyncio.timeout scope (the hook
# fires during stream_async), so an uncapped slow ATX Chat send would consume the remaining turn
# budget and, when the outer timer fires, flip a successful answer into a synthetic timeout terminal.
# Bound the send so a slow persist can't cannibalise the turn — symmetric with persist_stream_error's
# cap. A send that misses the window is dropped (best-effort, like any other persist failure); the
# live stream the user already saw is unaffected.
_PERSIST_TIMEOUT_SECONDS = 5.0


def _extract_assistant_text(message: Dict[str, Any]) -> str:
    """Concatenate the text blocks of a model message (the assistant's answer).

    Detected by the ``text`` key on a content block; tool-use / reasoning blocks carry
    no ``text`` and are skipped. Returns "" when the message has no text (e.g. a
    tool-only end), which is the signal to persist nothing."""
    parts = []
    for block in message.get("content", []):
        if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip():
            parts.append(block["text"])
    return "".join(parts)


def _extract_reasoning_text(message: Dict[str, Any]) -> str:
    """Concatenate the reasoning ("thinking") text of a model message.

    Detected by the ``reasoningContent`` key (Strands shape:
    ``{"reasoningContent": {"reasoningText": {"text": ...}}}``), position-agnostic: a
    model may place reasoning anywhere or omit it. Returns "" when there is none, which
    is the signal to persist no reasoning message. Capped at ``_MAX_REASONING_CHARS`` so a
    reasoning-heavy turn can't bloat chat history (symmetric with the tool-args cap)."""
    parts = []
    for block in message.get("content", []):
        if not isinstance(block, dict):
            continue
        reasoning = block.get("reasoningContent")
        if isinstance(reasoning, dict):
            text = (reasoning.get("reasoningText") or {}).get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    joined = "".join(parts)
    if len(joined) > _MAX_REASONING_CHARS:
        joined = joined[:_MAX_REASONING_CHARS] + "… (truncated)"
    return joined


def _format_tool_uses(message: Dict[str, Any]) -> str:
    """Render a model call's tool_use blocks as a formatted "Using tool" text block.

    The persist channel carries text only, so the structured tool card the stream showed
    is flattened here to a Markdown line per tool ("Using tool `name`" + a fenced JSON of
    its args), so the tool step replays on refresh. Parallel tools in one model call are
    listed together (they share one ``tool_message_id``). Returns "" when the call made no
    tool call. Each tool's args are capped at ``_MAX_TOOL_ARGS_CHARS`` so a large input
    can't bloat history."""
    lines: List[str] = []
    for block in message.get("content", []):
        if not isinstance(block, dict):
            continue
        tool_use = block.get("toolUse")
        if not isinstance(tool_use, dict):
            continue
        name = tool_use.get("name") or "unknown"
        try:
            args = json.dumps(tool_use.get("input", {}), ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            args = str(tool_use.get("input", {}))
        if len(args) > _MAX_TOOL_ARGS_CHARS:
            args = args[:_MAX_TOOL_ARGS_CHARS] + "… (truncated)"
        lines.append(f"Using tool `{name}`\n```json\n{args}\n```")
    return "\n\n".join(lines)


class StreamingResponsePersistHook(HookProvider):
    """Persists a streaming turn's messages to ATX Chat.

    Everything it needs per turn (contextId, the stream-emitted messageIds) comes off the
    turn's ``invocation_state``, so one instance serves every turn of a reused per-user agent.
    The ``StreamingConfig`` is turn-invariant (set once at construction); its emit toggles gate
    persistence so history matches what the live stream showed — reasoning is not persisted when
    ``emit_reasoning`` is off, tool calls not persisted when ``emit_tool_calls`` is off."""

    def __init__(self, config: StreamingConfig) -> None:
        self._config = config

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterModelCallEvent, self._on_after_model_call)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)

    async def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Persist a terminating-tool's force_stop_response as the FINAL response.

        A tool that ends the turn early (stop_after_response) writes the real answer to the request
        state under ``force_stop_response`` (the buffered path returns THAT over the LLM's pre-tool
        text). It lives only on the terminal ``AgentResult.state`` — no AfterModelCallEvent carries it
        (the tool runs after the last model call, then the loop stops) — so it is persisted here, at
        end of invocation, under the SAME id the adapter streams it with. AfterInvocationEvent fires
        before the adapter maps the terminal, so this mints force_stop_message_id and the adapter reads
        it (StreamState.ensure_force_stop_message_id — its OWN id, distinct from any pre-tool narration
        that owns final_message_id). Persist failure must never raise (would truncate the live
        stream)."""
        try:
            invocation_state = event.invocation_state or {}
            stream_state = invocation_state.get("stream_state")
            if stream_state is None:
                # Streaming-only: only a message/stream turn sets stream_state. On the buffered path
                # (message/send) the handler returns force_stop_response directly, so there is nothing
                # to persist here — return before touching the result.
                return

            result = event.result
            state = getattr(result, "state", None)
            force_stop_text = state.get("force_stop_response") if isinstance(state, dict) else None
            if not force_stop_text:
                return

            a2a_context = invocation_state.get("a2a_context")
            context_id = a2a_context.context_id if a2a_context else None
            if not context_id:
                return

            # A terminating tool can both set force_stop_response AND call add_suggestions() (the
            # terminate-and-suggest-next-step pattern). The suggestions were NOT consumed on the
            # tool_use model call (that step is a partial), so consume them here and attach them to
            # this final message + emit the live interaction — same handling as the end_turn final in
            # _on_after_model_call, so chips render live and on reload (parity with the buffered
            # path, which attaches suggestions on every final response).
            force_stop_message_id = stream_state.ensure_force_stop_message_id()
            suggestions = get_and_consume_suggestions()
            persisted = await self._persist_final(
                stream_state,
                force_stop_text,
                context_id,
                force_stop_message_id,
                suggestions=suggestions,
            )
            # Gate the live chips on the persist succeeding — same reason as the end_turn final in
            # _on_after_model_call: a failed persist means the chips have no reload backing, so
            # emitting them live would render chips that disappear on refresh.
            if persisted and suggestions:
                self._queue_suggestion_side_event(stream_state, suggestions, force_stop_message_id)
        except Exception:
            logger.exception("Failed to persist force_stop_response (stream unaffected)")

    async def _on_after_model_call(self, event: AfterModelCallEvent) -> None:
        # A persist failure must never break the live stream: the connection has already
        # returned 200 + SSE headers, so raising here would truncate the stream. Log and
        # move on — the turn still completes for the user.
        try:
            stop_response = event.stop_response
            if stop_response is None:
                return
            stop_reason = stop_response.stop_reason

            invocation_state = event.invocation_state or {}
            a2a_context = invocation_state.get("a2a_context")
            context_id = a2a_context.context_id if a2a_context else None
            if not context_id:
                # No contextId => Chat can't route this to a user. Skip rather than
                # emit an unroutable message (it would fall to the agent-initiated lane).
                logger.warning("Streaming persist skipped: no contextId on the turn")
                return

            stream_state = invocation_state.get("stream_state")

            # A turn is a sequence of model calls: a tool-use step carries a PARTIAL_UPDATE
            # (the assistant's pre-tool narration), and the final step (end_turn) carries the
            # FINAL response. Reasoning can ride either. A guardrail block needs no special case: it
            # ends the turn with stop_reason "guardrail_intervened"/"content_filtered" carrying
            # Bedrock's mandatory blockedOutputsMessaging as the message text, which persists as the
            # final response like any other end-of-turn answer (see _FINAL_STOP_REASONS). Anything
            # else (max_tokens / cancelled) is not persisted here.
            if stop_reason in _FINAL_STOP_REASONS:
                is_partial = False
            elif stop_reason in _PARTIAL_STOP_REASONS:
                is_partial = True
            else:
                return

            message = dict(stop_response.message)

            # Persist each streamed MESSAGE of this model call as its own Chat message under
            # the SAME id the adapter put on the stream, so a refresh reconciles with what the
            # user saw. The ids are freshly-minted uuid4s the adapter holds on StreamState (NOT
            # the toolUseId): reasoning_message_id for the thinking message, final_message_id
            # for the assistant text block streamed in this call (a pre-tool narration on a
            # tool-use step, the final answer on end-turn).

            # Reasoning ("thinking"): its own PARTIAL_UPDATE message, kept separate from the
            # assistant text exactly as the stream showed it. Only when the call carried
            # reasoning AND the adapter minted an id for it — and only when emit_reasoning is on,
            # so persistence matches the stream (the adapter drops reasoning events when off).
            if self._config.emit_reasoning:
                reasoning_text = _extract_reasoning_text(message)
                reasoning_id = getattr(stream_state, "reasoning_message_id", None)
                if reasoning_text and reasoning_id:
                    await self._safe_persist(
                        reasoning_text, context_id, reasoning_id, is_partial=True
                    )

            # Suggestions are a whole-turn artifact finalized at end_turn — consume them ONCE here
            # (not inside _persist), so the same set feeds both the persisted final message (as the
            # chat_suggestions ext, for reload) and the live interaction event on the stream. Only on
            # a NON-guardrail final message: a guardrail block is a content refusal, so it must not
            # carry follow-up chips (which would otherwise come from an earlier tool_use step of the
            # same turn). Consume-and-drop on a guardrail stop so they don't leak onto the next turn.
            # Scoped per streaming turn via the ContextVar in _stream_message_async.
            is_guardrail = stop_reason in GUARDRAIL_STOP_REASONS
            if is_partial:
                suggestions = None
            elif is_guardrail:
                get_and_consume_suggestions()  # drop; a refusal carries no chips
                suggestions = None
            else:
                suggestions = get_and_consume_suggestions()

            # Assistant text: a pre-tool narration (partial) or the final answer. Persist under
            # final_message_id, the id of the text block the adapter streamed in this call. A
            # tool-only step (no narration) has no text and persists nothing here.
            text = _extract_assistant_text(message)
            if text:
                text_id = getattr(stream_state, "final_message_id", None) or str(uuid.uuid4())
                if is_partial or stream_state is None:
                    persisted = await self._safe_persist(
                        text, context_id, text_id, is_partial=is_partial, suggestions=suggestions
                    )
                else:
                    persisted = await self._persist_final(
                        stream_state, text, context_id, text_id, suggestions=suggestions
                    )
                # On a final message that carried suggestions, ALSO emit them live: build the
                # interaction event under the SAME id (final_message_id) and hand it to the stream
                # loop via side_events, so chips render with the response instead of only on reload.
                # Gate on the persist succeeding: if it failed, the chips have no persisted backing,
                # so emitting them live would show chips that vanish on reload — the live/reload
                # divergence this feature exists to prevent. Drop them instead (they were already
                # consumed, so they won't leak onto the next turn).
                if persisted and suggestions and stream_state is not None:
                    self._queue_suggestion_side_event(stream_state, suggestions, text_id)
            elif not is_partial and suggestions:
                # A final turn with no assistant text (reasoning-only / tool-only end_turn). Chat
                # renders suggestions only on a final response, and there is no message this turn to
                # carry them, so they are dropped — consumed above (so they don't leak onto the next
                # turn) and logged rather than dropped silently. Rare: a final turn normally has text.
                logger.warning(
                    "Streaming turn ended with suggestions but no final text to attach them "
                    "to (contextId=%s); dropping %d suggestion(s).",
                    context_id,
                    len(suggestions),
                )

            # Tool calls: one PARTIAL_UPDATE per model-call under tool_message_id (the id the
            # stream's ToolCallStart carried), rendered as a formatted "Using tool" text block
            # so the tool step replays on refresh. Only on a tool-use call that actually made a
            # tool call AND for which the adapter minted a tool id — and only when emit_tool_calls
            # is on, so persistence matches the stream (the adapter drops tool events when off).
            if self._config.emit_tool_calls:
                tool_text = _format_tool_uses(message)
                tool_id = getattr(stream_state, "tool_message_id", None)
                if tool_text and tool_id:
                    await self._safe_persist(tool_text, context_id, tool_id, is_partial=True)
        except Exception:
            logger.exception("Failed to persist streaming response (stream unaffected)")

    def _queue_suggestion_side_event(
        self, stream_state: Any, suggestions: List[str], message_id: str
    ) -> None:
        """Queue the turn's suggestions as a live interaction event on the stream.

        Builds the interaction (a SELECT of the suggestion strings) under the final message's id and
        appends it to the turn's side_events, which the stream loop drains before the terminal — so
        the chips ride the live stream, reconciled with the persisted copy by id. Lazy import keeps
        the adapter (ag_ui/a2a) off the non-streaming import path."""
        from agent_builder_sdk.streaming.a2a_agui_adapter import (
            build_suggestion_interaction_events,
        )

        side_events = getattr(stream_state, "side_events", None)
        if side_events is None:
            return
        side_events.extend(
            build_suggestion_interaction_events(
                chat_suggestions=suggestions,
                create_job_suggestion=None,
                message_id=message_id,
            )
        )

    async def _persist_final(
        self,
        stream_state: Any,
        text: str,
        context_id: str,
        message_id: str,
        suggestions: Optional[List[str]] = None,
    ) -> bool:
        """Persist the turn's final answer as a task on ``stream_state``. A client disconnect cancels
        this await but not the send already running in its thread, so the stream's disconnect
        handler waits on the same task and records an interruption only if the answer was not
        stored."""
        final_persist = asyncio.ensure_future(
            self._safe_persist(
                text, context_id, message_id, is_partial=False, suggestions=suggestions
            )
        )
        stream_state.final_persist = final_persist
        return await asyncio.shield(final_persist)

    async def _safe_persist(
        self,
        text: str,
        context_id: str,
        message_id: str,
        is_partial: bool,
        suggestions: Optional[List[str]] = None,
    ) -> bool:
        """Persist one message of the turn, isolating its failure. A turn now emits up to three
        messages (reasoning, text, tool); wrapping each so a transient failure on one (e.g. a
        5xx from SendA2AMessage) loses only that message and the turn's remaining messages are
        still attempted — rather than the whole turn's trailing messages being skipped by the
        outer handler.

        Returns True if the message was persisted, False if the persist failed (or timed out).
        Callers that ALSO emit a live artifact backed by this persisted copy (the suggestion
        interaction side event) gate that emission on the return value, so a failed persist never
        leaves chips on the live stream that a reload can't reproduce."""
        try:
            await self._persist(
                text, context_id, message_id, is_partial=is_partial, suggestions=suggestions
            )
            return True
        except Exception:
            logger.exception(
                "Streaming persist failed for one message (contextId=%s, messageId=%s); "
                "later messages in this turn are still attempted.",
                context_id,
                message_id,
            )
            return False

    async def _persist(
        self,
        text: str,
        context_id: str,
        message_id: str,
        is_partial: bool,
        suggestions: Optional[List[str]] = None,
    ) -> None:
        """Send one step of the turn to ATX Chat, keyed by contextId.

        Mirrors the sync response builder (text + source-information ext), plus:
        - a partial step (tool-use) sets the message_type/v1 extension to
          ``{"messageType": "partial_update"}`` so Chat stores it as A2A_PARTIAL_UPDATE
          (thinking/progress) instead of a final response;
        - the final step omits that extension (Chat defaults to A2A_RESPONSE) and carries
          the turn's one-time ``suggestions`` (already consumed by the caller so the live stream
          and this persisted copy share the same set).
        """
        sender = get_agent_context_from_env().agent_instance_id

        metadata: Dict[str, Any] = {A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}}
        extensions = [A2A_SOURCE_INFORMATION_EXT]

        if is_partial:
            # Chat's extractAgentResponseType reads metadata[message_type/v1]["messageType"];
            # "partial_update" => A2A_PARTIAL_UPDATE. Absent => A2A_RESPONSE (final).
            metadata[A2A_MESSAGE_TYPE_EXT] = _PARTIAL_UPDATE_METADATA
            extensions.append(A2A_MESSAGE_TYPE_EXT)
        elif suggestions:
            # Final message carries the turn's suggestions as the chat_suggestions ext (the caller
            # consumed them once, so the live interaction event and this persisted copy match).
            metadata[A2A_CHAT_SUGGESTIONS_EXT] = suggestions
            extensions.append(A2A_CHAT_SUGGESTIONS_EXT)

        message = A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": text}],
            messageId=message_id,
            kind="message",
            contextId=context_id,
            metadata=metadata,
            extensions=extensions,
        )

        manager = get_a2a_manager()
        # Run the blocking A2AManager call off the event loop so a persist in one streaming
        # turn doesn't stall other concurrent turns sharing this loop. Cap it: this runs inside the
        # turn's asyncio.timeout scope, so an uncapped slow send would eat the turn budget and could
        # flip a good answer into a timeout terminal. On timeout wait_for raises TimeoutError, which
        # _safe_persist catches like any other failure (message dropped, stream unaffected).
        await asyncio.wait_for(
            asyncio.to_thread(
                manager.send_message,
                agent_instance_id=_CHAT_AGENT_INSTANCE_ID,
                message=message,
            ),
            timeout=_PERSIST_TIMEOUT_SECONDS,
        )
        logger.info(
            "Persisted streaming %s to %s (contextId=%s, messageId=%s)",
            "partial_update" if is_partial else "final response",
            _CHAT_AGENT_INSTANCE_ID,
            context_id,
            message_id,
        )


# Cap on the terminal-error persist. The streaming turn body calls persist_stream_error AFTER the
# turn's asyncio.timeout scope has exited, so a slow/stuck ATX Chat send here would hold the SSE
# stream open with no terminal frame. Bound it so the caller always proceeds to emit the terminal
# promptly; a persist that misses the window is dropped (best-effort, like any other failure).
_ERROR_PERSIST_TIMEOUT_SECONDS = 5.0


async def persist_stream_error(context_id: str, text: str, message_id: str) -> None:
    """Persist a terminal error message for a streaming turn, so a reload shows the same error the
    client saw live (rather than a blank turn). The per-model-call persist hook does not fire on a
    turn that errored before/without a model message, so the streaming turn body calls this from its
    terminal-error paths (model/MCP error, timeout, concurrency reject); the orchestrator's
    job-busy reply uses it too. Best-effort: a persist
    failure OR a slow send must never mask the original error or hold the already-open SSE stream, so
    it is bounded by a short timeout and any failure is logged and swallowed. ``message_id`` is the id
    the terminal RUN_ERROR streamed under, so the live error and this persisted copy reconcile."""
    try:
        sender = get_agent_context_from_env().agent_instance_id
        message = A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": text}],
            messageId=message_id,
            kind="message",
            contextId=context_id,
            metadata={A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}},
            extensions=[A2A_SOURCE_INFORMATION_EXT],
        )
        manager = get_a2a_manager()
        await asyncio.wait_for(
            asyncio.to_thread(
                manager.send_message,
                agent_instance_id=_CHAT_AGENT_INSTANCE_ID,
                message=message,
            ),
            timeout=_ERROR_PERSIST_TIMEOUT_SECONDS,
        )
        logger.info(
            "Persisted streaming error to %s (contextId=%s, messageId=%s)",
            _CHAT_AGENT_INSTANCE_ID,
            context_id,
            message_id,
        )
    except Exception:
        # Includes TimeoutError from wait_for. The terminal frame the caller emits next is what the
        # client actually needs; a missed error-persist only costs reload fidelity for this turn.
        logger.exception(
            "Failed to persist streaming error message (contextId=%s); stream unaffected",
            context_id,
        )
