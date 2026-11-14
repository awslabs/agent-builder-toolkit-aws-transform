# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Send message tools for Strands agents.

This module provides tools to send messages to other agents via the ATX platform.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from strands import ToolContext
from strands.tools import tool

from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.env_var import get_agent_context_from_env
from agent_builder_sdk.utils import A2A_SOURCE_INFORMATION_EXT

logger = logging.getLogger(__name__)


@dataclass
class _SubagentStreamOutcome:
    """Accumulated result of consuming a subagent's A2A stream (see ``_consume_subagent_stream``).

    The consuming loop fills these fields; ``resolve`` reduces them to the tool result. Shared by
    both streaming tools so the terminal/failure decision and its messages stay in one place.
    """

    # Text deltas of the current model cycle, and the text of each finished cycle (empty ones too).
    text_parts: List[str] = field(default_factory=list)
    cycles: List[str] = field(default_factory=list)
    failed: bool = False
    saw_terminal: bool = False
    # Error text off a `failed` terminal frame (raw_a2a_emitter.error_frames), if any.
    error_text: Optional[str] = None

    def end_cycle(self) -> None:
        """A model call finished: its text, possibly none, is one cycle."""
        self.cycles.append("".join(self.text_parts))
        self.text_parts = []

    def resolve(
        self, subagent_instance_id: str, *, last_cycle_only: bool = False
    ) -> Tuple[bool, str]:
        """Reduce the stream outcome to ``(is_success, message)``.

        ``message`` is always the string to surface as the tool result. When ``is_success`` is True
        it is the aggregated answer; otherwise it is an error description for a non-terminating
        outcome (failure, truncation, empty completion) the caller should hand back WITHOUT ending
        its turn.
        """
        if self.failed:
            # NON-TERMINATING: hand the error back to the orchestrator (turn continues) so it decides
            # the next step. A relaying caller may have already streamed partial content live and
            # can't un-stream it; the orchestrator then handles the error on top of that.
            logger.warning(
                f"Subagent {subagent_instance_id} failed; handing the error to the orchestrator "
                f"as a non-terminating tool result."
            )
            return False, self.error_text or f"Subagent {subagent_instance_id} reported a failure."
        if not self.saw_terminal:
            # NON-TERMINATING: no terminal frame means a truncated answer (dropped connection,
            # timeout, subagent died mid-turn). Treating it as success would silently persist a
            # mid-sentence reply as the final answer, so hand it back instead.
            logger.warning(
                f"Subagent {subagent_instance_id} stream ended without a terminal frame; "
                f"treating the partial response as a truncation failure."
            )
            return False, (
                f"Subagent {subagent_instance_id} stream ended without a terminal frame (truncated)."
            )
        cycles = [*self.cycles, "".join(self.text_parts)] if self.text_parts else self.cycles
        if last_cycle_only:
            # The answer is the last model call, even when it had no text (same as the buffered
            # send_message_to_subagent), so an empty last cycle never falls back to earlier narration.
            text = cycles[-1].strip() if cycles else ""
        else:
            from agent_builder_sdk.streaming.a2a_frame_utils import RELAY_CYCLE_SEPARATOR

            # Only cycles with text, matching the live stream, which separates only those.
            text = RELAY_CYCLE_SEPARATOR.join(c for c in cycles if c).strip()
        if not text:
            # NON-TERMINATING: completed but empty. force_stop_response="" would stop the loop and
            # persist nothing (every consumer treats "" as falsy) — a completed-but-silent turn — so
            # hand it back instead.
            logger.warning(f"Subagent {subagent_instance_id} completed with no content.")
            return False, f"Subagent {subagent_instance_id} completed but returned no content."
        logger.info(f"Aggregated streamed answer from subagent {subagent_instance_id}.")
        return True, text


class SendMessageTools:
    """Send message tools for communicating with other agents via ATX platform."""

    def __init__(self):
        """Initialize the send message tools."""
        logger.info("Initialized SendMessageTools")

    @staticmethod
    def _construct_message(text: str, sender: str) -> A2AMessage:
        """Construct an A2AMessage from text.

        Args:
            text: The message text to send

        Returns:
            Constructed A2AMessage
        """
        return A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": text}],
            messageId=str(uuid.uuid4()),
            kind="message",
            metadata={A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}},
            extensions=[A2A_SOURCE_INFORMATION_EXT],
        )

    @tool
    def send_message_to_subagent(
        self,
        subagent_instance_id: str,
        message: str,
    ):
        """Send a message to a subagent and get its reply back so YOU keep working.

        Use this to ask a subagent something and then act on its reply yourself (reason over it,
        call more tools, compose your own answer). The reply comes back as this tool's result and
        your turn continues; nothing is streamed to the user. The reply is fetched in one blocking
        call (no incremental progress).

        Args:
            subagent_instance_id: The ID of the subagent to send the message to
            message: The text message to send to the subagent

        Returns:
            Response from the subagent

        Example:
            response = send_message_to_subagent("subagent-123", "What is the status?")
        """
        try:
            client = get_agentic_api_client()
            context = get_agent_context_from_env()

            message_obj = self._construct_message(message, context.agent_instance_id)

            response = client.send_message(
                agentInstanceId=subagent_instance_id,
                params={"message": message_obj.to_dict()},
                requestContext=context.to_dict(),
            )
            logger.info(f"Message sent to subagent {subagent_instance_id}.")
            return response

        except Exception as e:
            logger.exception(f"Send message operation error: {e}")
            raise e

    @tool
    async def async_send_message_to_subagent(
        self,
        subagent_instance_id: str,
        message: str,
    ):
        """Send a message to a subagent asynchronously.

        Args:
            subagent_instance_id: The ID of the subagent to send the message to
            message: The text message to send to the subagent

        Returns:
            Response from the subagent

        Example:
            response = await async_send_message_to_subagent("subagent-123", "What is the status?")
        """
        try:
            client = get_agentic_api_client()
            context = get_agent_context_from_env()

            message_obj = self._construct_message(message, context.agent_instance_id)

            response = await asyncio.to_thread(
                client.send_message,
                agentInstanceId=subagent_instance_id,
                params={"message": message_obj.to_dict()},
                requestContext=context.to_dict(),
            )
            logger.info(f"Message sent to subagent {subagent_instance_id}.")
            return response

        except Exception as e:
            logger.exception(f"Async send message operation error: {e}")
            raise e

    # Streaming counterpart of `async_send_message_to_subagent`, opt-in via the factory's
    # `custom_tools` (not registered by default). Streaming aggregates the reply as it arrives, so
    # the response comes back on the same call with no separate follow-up to fetch it; the trade-off
    # is that the orchestrator blocks until the subagent finishes. It is mainly a reference example
    # that the platform supports A2A streaming — partners pick whichever variant fits.
    @tool
    async def stream_message_to_subagent(
        self,
        subagent_instance_id: str,
        message: str,
    ) -> str:
        """Stream a subagent's reply, aggregate its final answer, and return it so YOU keep working.

        Use this to ask a subagent something and then act on its reply yourself (reason over it,
        call more tools, compose your own answer). You get the full aggregated answer back as this
        tool's result and your turn continues; nothing is streamed to the user.

        Args:
            subagent_instance_id: The ID of the subagent to send the message to
            message: The text message to send to the subagent

        Returns:
            The subagent's aggregated final-answer text, or a short error description (this tool never
            raises) if the subagent failed, timed out, was truncated, or returned no content — in
            which case you continue normally and decide the next step.

        Example:
            answer = await stream_message_to_subagent("subagent-123", "Summarize the log.")
        """
        outcome = _SubagentStreamOutcome()
        try:
            # Aggregate-only: the answer is collected into `outcome`; the yielded events are
            # discarded (nothing is streamed to the user). The relay tool instead re-yields them.
            async for _event in self._consume_subagent_stream(
                subagent_instance_id, message, outcome
            ):
                pass
        except Exception as e:
            logger.exception(f"Stream error for subagent {subagent_instance_id}: {e}")
            return f"Error streaming from subagent {subagent_instance_id}: {e}"

        # Return only the last model cycle (the answer), like the buffered send_message_to_subagent.
        _is_success, message_out = outcome.resolve(subagent_instance_id, last_cycle_only=True)
        return message_out

    async def _consume_subagent_stream(
        self,
        subagent_instance_id: str,
        message: str,
        outcome: "_SubagentStreamOutcome",
    ) -> AsyncIterator[Dict[str, Any]]:
        """Open the subagent's A2A stream and yield each raw content event.

        Shared consumption loop for both streaming tools. Records terminal/failure state and the
        aggregated answer text into ``outcome`` (which the caller then ``resolve``s), and yields the
        raw Strands content events so a caller can relay them live if it wants; the aggregate-only
        caller just discards them.

        The stream is bounded upstream — the callee's own turn budget emits a terminal frame and the
        streaming client's read/idle timeout severs a silent connection — so this loop needs no
        caller-side total cap. Errors surface to the caller (they wrap the iteration in try/except).
        """
        from agent_builder_sdk.agentic_framework.a2a_manager import get_a2a_manager
        from agent_builder_sdk.streaming.a2a_frame_utils import (
            STATE_FAILED,
            extract_raw_event,
            frame_state,
            is_assistant_message,
            is_end_of_turn,
        )
        from agent_builder_sdk.streaming.sse_reader import async_iter_from_sync

        context = get_agent_context_from_env()
        message_obj = self._construct_message(message, context.agent_instance_id)
        manager = get_a2a_manager()

        # `frames` from the subagent's SSE stream. On the subagent side, raw_a2a_emitter already
        # wrapped each raw Strands event in a raw A2A frame. extract_raw_event does the reverse:
        # it unwraps that envelope back to the bare Strands event we then relay.
        frames = await asyncio.to_thread(
            manager.stream_send_message,
            agent_instance_id=subagent_instance_id,
            message=message_obj,
        )
        async for frame in async_iter_from_sync(frames):
            if frame_state(frame) == STATE_FAILED:
                outcome.failed = True
            # A frame is "end of turn" when it is the subagent's terminal frame (completed or
            # failed). Content frames are NOT end-of-turn.
            end = is_end_of_turn(frame)
            event = extract_raw_event(frame)
            if event and not end:
                # CONTENT frame: aggregate the text and yield the raw event. `data` is a str only for
                # text deltas, so reasoning/tool-use frames are skipped from the aggregate (matching
                # extract_text_from_strands_agent_response). A relaying caller re-yields it live; the
                # aggregate-only caller discards it.
                if isinstance(event.get("data"), str):
                    outcome.text_parts.append(event["data"])
                elif is_assistant_message(event):
                    # A finished model call (same test as the live adapter) closes its cycle.
                    outcome.end_cycle()
                yield event
            elif event and end and isinstance(event.get("data"), str):
                # TERMINAL error frame (raw_a2a_emitter.error_frames): capture the sanitized error
                # text for the orchestrator, but do NOT yield it — the adapter would render it as
                # normal answer text to the user.
                outcome.error_text = event["data"]
            if end:
                outcome.saw_terminal = True
                break

    # Opt-in via the factory's `custom_tools` (not registered by default).
    @tool(context=True)
    async def send_message_to_subagent_and_relay(
        self,
        subagent_instance_id: str,
        message: str,
        tool_context: ToolContext,
    ) -> AsyncIterator[Any]:
        """Send a message to a subagent and stream its answer LIVE to the user as YOUR final answer.

        Use this ONLY when the subagent's answer IS the answer the user should receive and you have
        nothing to add — you are just the channel. The subagent's reply streams to the user in real
        time and this ENDS your turn: you will NOT get to respond again (its reply is still recorded
        in your context).

        If instead you need to read the subagent's answer and then keep working (reason over it, call
        more tools, or compose your own reply), use a tool that returns the answer to you rather than
        relaying it.

        Args:
            subagent_instance_id: The ID of the subagent to send the message to
            message: The text message to send to the subagent

        Returns:
            The subagent's final answer (which becomes your final answer to the user), or an error
            description if the subagent failed or did not respond in time — in which case your turn
            continues normally.

        Example:
            answer = await send_message_to_subagent_and_relay("subagent-123", "Weather in NYC?")
        """
        request_state = tool_context.invocation_state["request_state"]

        # Strands async-generator tool contract we rely on: every yield becomes a ToolStreamEvent
        # (reaches adapt() -> the user's live stream), and the LAST yield is ALSO wrapped as the
        # ToolResultEvent (recorded into agent.messages -> the LLM's context, not shown to the user).
        # So: content yields are event DICTS (rendered live), and the final yield is a plain str that
        # adapt() ignores but the LLM still gets as the tool result. Keep the final yield a string or
        # it would double-render to the user.

        outcome = _SubagentStreamOutcome()
        try:
            async for event in self._consume_subagent_stream(
                subagent_instance_id, message, outcome
            ):
                yield event
        except Exception as e:
            logger.exception(f"Relay stream error for subagent {subagent_instance_id}: {e}")
            yield f"Error streaming from subagent {subagent_instance_id}: {e}"
            return

        # TERMINATING (success): make the subagent's answer the orchestrator's final answer verbatim,
        # with no extra LLM turn.
        #   - force_stop_response: durably persists the answer (the live stream is ephemeral — gone on
        #     refresh, never written to Chat); the persist hook reads it.
        #   - stop_event_loop: ends the loop now so the LLM doesn't re-summarize (extra call, risks
        #     rewriting the answer).
        # A non-terminating outcome (is_success False) leaves request_state untouched, so the turn
        # continues. The final `yield message_out` records the answer/error as this tool's result.
        is_success, message_out = outcome.resolve(subagent_instance_id)
        if is_success:
            request_state["force_stop_response"] = message_out
            request_state["stop_event_loop"] = True
            logger.info(f"Relayed subagent {subagent_instance_id} answer as final response.")
        yield message_out
