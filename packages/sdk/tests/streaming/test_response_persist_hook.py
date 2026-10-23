# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for StreamingResponsePersistHook.

Exercises the REAL hook: real AfterModelCallEvent, real A2AMessage construction, real
_extract_assistant_text. Only the network boundary is faked — the A2AManager (so no
AgenticApi call), the env-derived sender, and the suggestions store. The assertions
inspect the actual A2AMessage the hook would send, so a wrong field/branch fails here.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import A2AContext
from agent_builder_sdk.streaming import StreamState
from agent_builder_sdk.streaming.config import DEFAULT_STREAMING_CONFIG, StreamingConfig
from agent_builder_sdk.streaming.response_persist_hook import (
    _MAX_REASONING_CHARS,
    _MAX_TOOL_ARGS_CHARS,
    StreamingResponsePersistHook,
    _extract_assistant_text,
    _extract_reasoning_text,
    _format_tool_uses,
    persist_stream_error,
)
from agent_builder_sdk.utils import (
    A2A_CHAT_SUGGESTIONS_EXT,
    A2A_MESSAGE_TYPE_EXT,
    A2A_SOURCE_INFORMATION_EXT,
)

HOOK_MODULE = "agent_builder_sdk.streaming.response_persist_hook"


class FakeAgent:
    """Stand-in Strands agent; the hook only reads event.agent when it cancels (it
    never does on the persist path), so a bare object is enough."""


def make_event(
    stop_reason="end_turn",
    text="The answer is 4.",
    context_id="ctx-abc",
    final_message_id="msg-final-1",
    tool_message_id="msg-tool-1",
    reasoning_message_id="msg-reasoning-1",
    reasoning_text=None,
    extra_blocks=None,
    with_stream_state=True,
):
    """Build a real AfterModelCallEvent shaped exactly as strands' event loop builds it."""
    from strands.hooks import AfterModelCallEvent

    content = []
    if reasoning_text is not None:
        content.append({"reasoningContent": {"reasoningText": {"text": reasoning_text}}})
    if text is not None:
        content.append({"text": text})
    if extra_blocks:
        content.extend(extra_blocks)
    message = {"role": "assistant", "content": content}

    invocation_state = {}
    if context_id is not None:
        invocation_state["a2a_context"] = A2AContext(context_id=context_id, task_id="task-1")
    if with_stream_state:
        # A real StreamState (not a stub) so the hook exercises the same object production does. The
        # per-turn ids the adapter would have set as the stream ran are assigned here to mirror that
        # state.
        stream_state = StreamState(thread_id="thread-1", context_id=context_id or "ctx-1")
        stream_state.final_message_id = final_message_id
        stream_state.tool_message_id = tool_message_id
        stream_state.reasoning_message_id = reasoning_message_id
        invocation_state["stream_state"] = stream_state

    return AfterModelCallEvent(
        agent=FakeAgent(),
        invocation_state=invocation_state,
        stop_response=AfterModelCallEvent.ModelStopResponse(
            message=message, stop_reason=stop_reason
        ),
    )


class RecordingManager:
    """Captures the A2AMessage the hook sends instead of hitting AgenticApi."""

    def __init__(self):
        self.calls = []

    def send_message(self, agent_instance_id, message):
        self.calls.append((agent_instance_id, message))
        return {}


@pytest.fixture
def manager():
    mgr = RecordingManager()
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=None):
        yield mgr


# ---- _extract_assistant_text --------------------------------------------------


def test_extract_text_concatenates_text_blocks_only():
    message = {
        "content": [
            {"text": "Hello "},
            {"toolUse": {"name": "x"}},  # skipped
            {"text": "world"},
            {"reasoningContent": {"reasoningText": {"text": "thinking"}}},  # skipped
        ]
    }
    assert _extract_assistant_text(message) == "Hello world"


def test_extract_text_empty_when_no_text_blocks():
    assert _extract_assistant_text({"content": [{"toolUse": {"name": "x"}}]}) == ""


def test_extract_reasoning_reads_reasoning_content_only():
    message = {
        "content": [
            {"reasoningContent": {"reasoningText": {"text": "let me think"}}},
            {"text": "Hello"},  # skipped — not reasoning
            {"toolUse": {"name": "x"}},  # skipped
        ]
    }
    assert _extract_reasoning_text(message) == "let me think"


def test_extract_reasoning_empty_when_none():
    assert _extract_reasoning_text({"content": [{"text": "just an answer"}]}) == ""


def test_format_tool_uses_renders_name_and_args():
    message = {"content": [{"toolUse": {"name": "get_job_status", "input": {"jobId": "j-1"}}}]}
    out = _format_tool_uses(message)
    assert "Using tool `get_job_status`" in out
    assert '"jobId": "j-1"' in out


def test_format_tool_uses_lists_parallel_tools_together():
    message = {
        "content": [
            {"toolUse": {"name": "tool_a", "input": {}}},
            {"toolUse": {"name": "tool_b", "input": {}}},
        ]
    }
    out = _format_tool_uses(message)
    assert "Using tool `tool_a`" in out
    assert "Using tool `tool_b`" in out


def test_format_tool_uses_empty_when_no_tool():
    assert _format_tool_uses({"content": [{"text": "hi"}]}) == ""


def test_format_tool_uses_truncates_large_args():
    big = {"blob": "x" * (_MAX_TOOL_ARGS_CHARS + 500)}
    out = _format_tool_uses({"content": [{"toolUse": {"name": "t", "input": big}}]})
    assert "… (truncated)" in out
    # capped near the limit, not the full oversized payload
    assert len(out) < _MAX_TOOL_ARGS_CHARS + 200


def test_extract_reasoning_truncates_large_text():
    big = "z" * (_MAX_REASONING_CHARS + 1000)
    out = _extract_reasoning_text(
        {"content": [{"reasoningContent": {"reasoningText": {"text": big}}}]}
    )
    assert out.endswith("… (truncated)")
    assert len(out) < _MAX_REASONING_CHARS + 50


# ---- persist on final stop reasons -------------------------------------------


async def test_persists_final_response_to_atx_chat(manager):
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(text="The answer is 4."))

    assert len(manager.calls) == 1
    target, message = manager.calls[0]
    assert target == "ATX_CHAT"
    assert message.role == "agent"
    assert message.parts == [{"kind": "text", "text": "The answer is 4."}]
    assert message.contextId == "ctx-abc"


async def test_persists_under_stream_emitted_message_id(manager):
    """The final message must carry the SAME id the stream showed (final_message_id),
    so live and refresh reconcile by messageId."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(final_message_id="msg-stream-42"))

    _, message = manager.calls[0]
    assert message.messageId == "msg-stream-42"


async def test_final_persist_is_recorded_on_stream_state(manager):
    """Only the final answer's save is recorded on the stream state; a narration's is not."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    narration = make_event(stop_reason="tool_use", final_message_id="msg-1")
    await hook._on_after_model_call(narration)
    assert narration.invocation_state["stream_state"].final_persist is None

    final = make_event(final_message_id="msg-2")
    await hook._on_after_model_call(final)
    assert final.invocation_state["stream_state"].final_persist.result() is True


async def test_final_persist_is_recorded_before_the_send_completes(manager):
    """A disconnect during the final save cancels the hook's await, so the save must already be on
    the stream state for the disconnect handler to wait on."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_event(final_message_id="msg-1")
    seen = []

    async def persist(*args, **kwargs):
        seen.append(event.invocation_state["stream_state"].final_persist is not None)

    with patch.object(hook, "_persist", side_effect=persist):
        await hook._on_after_model_call(event)

    assert seen == [True]


async def test_final_save_survives_a_cancelled_hook(manager):
    """Cancelling the hook (a client disconnect) does not cancel the save it started."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_event(final_message_id="msg-1")
    release = asyncio.Event()

    async def persist(*args, **kwargs):
        await release.wait()

    with patch.object(hook, "_persist", side_effect=persist):
        task = asyncio.create_task(hook._on_after_model_call(event))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        final_persist = event.invocation_state["stream_state"].final_persist
        assert await final_persist is True


async def test_failed_final_persist_resolves_false(manager):
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_event(final_message_id="msg-1")
    with patch.object(hook, "_persist", side_effect=RuntimeError("chat down")):
        await hook._on_after_model_call(event)
    assert event.invocation_state["stream_state"].final_persist.result() is False


async def test_stop_sequence_also_persists(manager):
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(stop_reason="stop_sequence"))
    assert len(manager.calls) == 1


async def test_source_information_extension_attached(manager):
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event())

    _, message = manager.calls[0]
    assert message.metadata[A2A_SOURCE_INFORMATION_EXT] == {"senderAgentInstanceId": "job-agent-99"}
    assert A2A_SOURCE_INFORMATION_EXT in message.extensions


async def test_final_response_has_no_message_type_extension(manager):
    """The final response omits the message_type/v1 extension, so Chat defaults it to
    A2A_RESPONSE (FINAL_RESPONSE) — full processing (suggestions, guardrail)."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event())

    _, message = manager.calls[0]
    assert A2A_MESSAGE_TYPE_EXT not in (message.metadata or {})
    assert A2A_MESSAGE_TYPE_EXT not in (message.extensions or [])


# ---- tool-use step persists as a PARTIAL_UPDATE ------------------------------


async def test_tool_use_step_persists_as_partial_update(manager):
    """A tool-use model-call carries the assistant's thinking/narration before it calls a
    tool; it is persisted as a PARTIAL_UPDATE so it survives a refresh — NOT dropped."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(stop_reason="tool_use", text="Let me look that up."))

    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.parts == [{"kind": "text", "text": "Let me look that up."}]
    # message_type/v1 = {"messageType": "partial_update"} => Chat stores A2A_PARTIAL_UPDATE
    assert message.metadata[A2A_MESSAGE_TYPE_EXT] == {"messageType": "partial_update"}
    assert A2A_MESSAGE_TYPE_EXT in message.extensions


async def test_pre_tool_narration_uses_its_streamed_text_id(manager):
    """A pre-tool narration streams as its own text message (final_message_id), separate from
    the tool block (tool_message_id). It must persist under the id the TEXT streamed under,
    NOT the tool's id, so live and refresh reconcile the narration bubble by messageId."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(
        make_event(
            stop_reason="tool_use",
            text="Let me look that up.",
            final_message_id="narration-7",
            tool_message_id="tm-42",
        )
    )

    _, message = manager.calls[0]
    assert message.messageId == "narration-7"


async def test_narration_and_tool_persist_as_two_messages(manager):
    """A tool-use step with pre-tool narration persists TWO messages: the narration under
    its own streamed text id, and the tool call under tool_message_id — distinct ids, in
    stream order (narration then tool)."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(
        make_event(
            stop_reason="tool_use",
            text="Let me look that up.",
            extra_blocks=[{"toolUse": {"name": "get_job_status", "input": {"jobId": "j-9"}}}],
            final_message_id="narration-1",
            tool_message_id="tool-1",
        )
    )

    assert len(manager.calls) == 2
    _, narration = manager.calls[0]
    assert narration.messageId == "narration-1"
    assert narration.parts == [{"kind": "text", "text": "Let me look that up."}]

    _, tool = manager.calls[1]
    assert tool.messageId == "tool-1"
    assert "Using tool `get_job_status`" in tool.parts[0]["text"]


async def test_partial_does_not_consume_suggestions():
    """Suggestions are a whole-turn artifact finalized at end_turn; a partial step must NOT
    consume them (that would stamp chips on the wrong message and starve the final)."""
    mgr = RecordingManager()
    consumed = {"n": 0}

    def fake_consume():
        consumed["n"] += 1
        return [{"action": "SELECT", "interactionData": {}}]

    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", side_effect=fake_consume):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        await hook._on_after_model_call(make_event(stop_reason="tool_use", text="thinking"))

    assert consumed["n"] == 0  # suggestions never consumed on a partial step


# ---- reasoning persists as its own message -----------------------------------


async def test_reasoning_persists_as_own_partial_under_reasoning_id(manager):
    """Reasoning ("thinking") is a separate message from the assistant text, persisted as a
    PARTIAL_UPDATE under the id the stream showed it (reasoning_message_id)."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(
        make_event(
            reasoning_text="Let me check the status.",
            text="Your job is done.",
            reasoning_message_id="rz-9",
            final_message_id="fm-9",
        )
    )

    # two messages: reasoning (partial, rz-9) then the final answer (fm-9)
    assert len(manager.calls) == 2
    _, reasoning_msg = manager.calls[0]
    assert reasoning_msg.messageId == "rz-9"
    assert reasoning_msg.parts == [{"kind": "text", "text": "Let me check the status."}]
    assert reasoning_msg.metadata[A2A_MESSAGE_TYPE_EXT] == {"messageType": "partial_update"}

    _, final_msg = manager.calls[1]
    assert final_msg.messageId == "fm-9"
    assert final_msg.parts == [{"kind": "text", "text": "Your job is done."}]
    assert A2A_MESSAGE_TYPE_EXT not in (final_msg.metadata or {})


async def test_reasoning_not_persisted_when_absent(manager):
    """No reasoning block => no reasoning message; only the answer persists."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(reasoning_text=None, text="Just the answer."))
    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.parts == [{"kind": "text", "text": "Just the answer."}]


# ---- config emit toggles gate persistence (must match the stream) ------------


async def test_reasoning_not_persisted_when_emit_reasoning_off(manager):
    """emit_reasoning=False: the adapter drops reasoning from the stream, so the hook must not
    persist it either — else it would reappear on refresh. The answer still persists."""
    hook = StreamingResponsePersistHook(StreamingConfig(emit_reasoning=False))
    await hook._on_after_model_call(
        make_event(reasoning_text="secret thinking", text="The answer.", reasoning_message_id="rz")
    )
    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.parts == [{"kind": "text", "text": "The answer."}]  # only the answer


async def test_tool_calls_not_persisted_when_emit_tool_calls_off(manager):
    """emit_tool_calls=False: the adapter drops tool events from the stream, so the hook must
    not persist the "Using tool" message either. A pre-tool narration still persists."""
    hook = StreamingResponsePersistHook(StreamingConfig(emit_tool_calls=False))
    await hook._on_after_model_call(
        make_event(
            stop_reason="tool_use",
            text="Let me look that up.",
            extra_blocks=[{"toolUse": {"name": "get_job", "input": {}}}],
            final_message_id="narration-1",
            tool_message_id="tool-1",
        )
    )
    assert len(manager.calls) == 1  # narration only, no tool message
    _, message = manager.calls[0]
    assert message.messageId == "narration-1"
    assert "Using tool" not in message.parts[0]["text"]


# ---- empty / unroutable steps are NOT persisted ------------------------------


async def test_tool_only_step_persists_only_the_tool_message(manager):
    """A tool-only step (no narration text) persists just the tool message, under
    tool_message_id, not the text id."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(
        make_event(
            stop_reason="tool_use",
            text=None,
            extra_blocks=[{"toolUse": {"name": "get_job_status", "input": {"jobId": "j-1"}}}],
            tool_message_id="tm-77",
        )
    )
    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.messageId == "tm-77"
    tool_text = message.parts[0]["text"]
    assert "Using tool `get_job_status`" in tool_text
    assert '"jobId": "j-1"' in tool_text
    assert message.metadata[A2A_MESSAGE_TYPE_EXT] == {"messageType": "partial_update"}


async def test_no_tooluse_and_no_text_persists_nothing(manager):
    """A step with neither assistant text nor a tool call has nothing to persist."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(stop_reason="tool_use", text=None))
    assert manager.calls == []


async def test_non_persisted_stop_reasons_skipped(manager):
    """end_turn/stop_sequence and guardrail stops (final), tool_use (partial) are persisted; the
    remaining stop reasons (max_tokens, cancelled) are not persisted by this hook."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    for reason in ("max_tokens", "cancelled"):
        await hook._on_after_model_call(make_event(stop_reason=reason))
    assert manager.calls == []


# ---- guardrail block persists Bedrock's block message as the final response --


async def test_guardrail_block_persists_block_message_as_final(manager):
    """A guardrail block ends the turn like a normal final response: Bedrock returns its mandatory
    blockedOutputsMessaging as the message text, so the hook persists THAT text (owner-owned, not an
    SDK string) under final_message_id — the same id it streamed under — as a FINAL message."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    block_msg = "Sorry, this is a test custom refusal."
    event = make_event(
        stop_reason="guardrail_intervened", text=block_msg, final_message_id="block-1"
    )
    await hook._on_after_model_call(event)

    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.parts == [{"kind": "text", "text": block_msg}]
    assert message.messageId == "block-1"
    # a block is a final response, not a partial
    assert A2A_MESSAGE_TYPE_EXT not in (message.metadata or {})


# ---- force_stop_response persists as the final response (AfterInvocationEvent) --


def make_after_invocation_event(
    force_stop_response="The real answer.",
    context_id="ctx-abc",
    with_stream_state=True,
    with_state=True,
):
    """Build an AfterInvocationEvent shaped as strands' event loop builds it at end of stream_async:
    result.state carries the terminating tool's force_stop_response; invocation_state carries the
    a2a_context + the turn's StreamState."""
    from strands.hooks import AfterInvocationEvent

    state = {"force_stop_response": force_stop_response} if with_state else {}
    invocation_state = {}
    if context_id is not None:
        invocation_state["a2a_context"] = A2AContext(context_id=context_id, task_id="task-1")
    if with_stream_state:
        stream_state = StreamState(thread_id="thread-1", context_id=context_id or "ctx-1")
        invocation_state["stream_state"] = stream_state
    return AfterInvocationEvent(
        agent=FakeAgent(),
        invocation_state=invocation_state,
        result=SimpleNamespace(state=state),
    )


async def test_force_stop_response_persists_as_final_under_dedicated_id(manager):
    """A terminating tool's force_stop_response (the real answer, on result.state) is persisted as a
    FINAL response under its dedicated force_stop_message_id the adapter streams it with, so a reload
    matches the live stream. It rides AfterInvocationEvent (the answer lives only on the terminal
    result, not any per-model-call event)."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_after_invocation_event(force_stop_response="Your job has been started.")
    await hook._on_after_invocation(event)

    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.parts == [{"kind": "text", "text": "Your job has been started."}]
    # persisted under the dedicated force_stop id (the adapter reads the same via
    # ensure_force_stop_message_id)
    assert message.messageId == event.invocation_state["stream_state"].force_stop_message_id
    assert A2A_MESSAGE_TYPE_EXT not in (message.metadata or {})


async def test_force_stop_persist_is_recorded_before_the_send_completes(manager):
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_after_invocation_event(force_stop_response="Your job has been started.")
    seen = []

    async def persist(*args, **kwargs):
        seen.append(event.invocation_state["stream_state"].final_persist is not None)

    with patch.object(hook, "_persist", side_effect=persist):
        await hook._on_after_invocation(event)

    assert seen == [True]
    assert event.invocation_state["stream_state"].final_persist.result() is True


async def test_failed_force_stop_persist_resolves_false(manager):
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_after_invocation_event(force_stop_response="Your job has been started.")
    with patch.object(hook, "_persist", side_effect=RuntimeError("chat down")):
        await hook._on_after_invocation(event)
    assert event.invocation_state["stream_state"].final_persist.result() is False


async def test_force_stop_id_distinct_from_narration_final_id(manager):
    """When the turn already streamed a pre-tool narration (final_message_id is that narration's id),
    the force_stop answer must persist under its OWN id, never the narration's — else two different
    texts collide under one messageId on reload."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_after_invocation_event(force_stop_response="Your job has been started.")
    event.invocation_state["stream_state"].final_message_id = "narration-owns-this"
    await hook._on_after_invocation(event)

    _, message = manager.calls[0]
    assert message.messageId != "narration-owns-this"
    assert message.messageId == event.invocation_state["stream_state"].force_stop_message_id


async def test_no_force_stop_response_persists_nothing_on_after_invocation(manager):
    """An ordinary turn (no force_stop_response on the result state) persists nothing here — the
    normal end_turn text was already persisted by _on_after_model_call."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_invocation(make_after_invocation_event(with_state=False))
    assert manager.calls == []


async def test_force_stop_response_on_non_streaming_turn_persists_nothing(manager):
    """Streaming-only: without a stream_state (the buffered path never sets it, and returns
    force_stop_response directly) the AfterInvocation hook is a no-op."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_invocation(make_after_invocation_event(with_stream_state=False))
    assert manager.calls == []


async def test_content_filtered_block_persists_block_message_as_final(manager):
    """content_filtered is treated identically to guardrail_intervened — final response."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(
        make_event(stop_reason="content_filtered", text="Blocked.", final_message_id="block-2")
    )
    assert len(manager.calls) == 1
    _, message = manager.calls[0]
    assert message.parts == [{"kind": "text", "text": "Blocked."}]
    assert message.messageId == "block-2"


async def test_missing_context_id_skips_persist(manager):
    """Defense in depth: the hook skips when there is no contextId (the ingress already
    rejects a contextId-less streaming turn up front, so this should not occur in practice)."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(context_id=None))
    assert manager.calls == []


async def test_no_stream_state_falls_back_to_generated_id(manager):
    """If stream_state is absent the message still persists, under a minted id (never blank)."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    await hook._on_after_model_call(make_event(with_stream_state=False))

    _, message = manager.calls[0]
    assert message.messageId  # non-empty
    uuid.UUID(message.messageId)  # a valid uuid4


# ---- suggestions consumed once, on the final message -------------------------


async def test_suggestions_attached_when_present():
    mgr = RecordingManager()
    chips = [{"action": "SELECT", "interactionData": {}}]
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=chips):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        await hook._on_after_model_call(make_event())

    _, message = mgr.calls[0]
    assert message.metadata[A2A_CHAT_SUGGESTIONS_EXT] == chips
    assert A2A_CHAT_SUGGESTIONS_EXT in message.extensions


async def test_final_turn_with_no_text_drains_orphaned_suggestions():
    """A final turn with no assistant text (reasoning-only end_turn) has no message to carry
    suggestions. They must still be CONSUMED (else they leak onto the user's next turn), and
    nothing is persisted for this text-less turn."""
    mgr = RecordingManager()
    consumed = {"n": 0}

    def fake_consume():
        consumed["n"] += 1
        return [{"action": "SELECT", "interactionData": {}}]

    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", side_effect=fake_consume):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        # end_turn (final) whose message is reasoning-only: no text, no toolUse
        await hook._on_after_model_call(
            make_event(stop_reason="end_turn", text=None, reasoning_text="only thinking")
        )

    assert consumed["n"] == 1  # drained so they don't leak to the next turn
    # only the reasoning persisted (a partial); no final-text message
    assert all(A2A_CHAT_SUGGESTIONS_EXT not in (m.extensions or []) for _, m in mgr.calls)


# ---- a persist failure must never break the stream ---------------------------


async def test_persist_failure_is_swallowed():
    """The connection has already returned 200 + SSE headers; a raising persist would
    truncate the stream. The hook must swallow and log, not raise."""
    with patch(f"{HOOK_MODULE}.get_a2a_manager", side_effect=RuntimeError("boom")), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=None):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        # must not raise
        await hook._on_after_model_call(make_event())


async def test_one_message_persist_failure_does_not_skip_later_messages():
    """A turn emits up to 3 messages (reasoning, text, tool). A transient failure on the FIRST
    (reasoning) must not skip the text + tool persists — each message is isolated, so the blast
    radius of one failure is one message, not the turn's trailing messages."""

    class FailFirstThenRecord:
        def __init__(self):
            self.attempted = 0
            self.recorded = []

        def send_message(self, agent_instance_id, message):
            self.attempted += 1
            if self.attempted == 1:
                raise RuntimeError("transient 5xx on the first (reasoning) persist")
            self.recorded.append(message)
            return {}

    mgr = FailFirstThenRecord()
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=None):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        # tool_use step with reasoning + narration text + a tool call → 3 persists attempted
        await hook._on_after_model_call(
            make_event(
                stop_reason="tool_use",
                reasoning_text="thinking",
                text="Let me look that up.",
                extra_blocks=[{"toolUse": {"name": "get_job", "input": {}}}],
            )
        )

    assert mgr.attempted == 3  # all three attempted despite the first failing
    assert len(mgr.recorded) == 2  # text + tool still persisted after the reasoning failure


# ---- persist_stream_error: terminal error persists for reload parity ----------


async def test_persist_stream_error_sends_error_message():
    """A streaming turn's terminal error is persisted as an agent message under the given id, so a
    reload shows the same error the client saw live instead of a blank turn."""
    mgr = RecordingManager()
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ):
        await persist_stream_error("ctx-err", "The request took too long.", "run-123")

    assert len(mgr.calls) == 1
    target, message = mgr.calls[0]
    assert target == "ATX_CHAT"
    assert message.contextId == "ctx-err"
    assert message.messageId == "run-123"
    assert message.parts == [{"kind": "text", "text": "The request took too long."}]
    assert A2A_SOURCE_INFORMATION_EXT in message.extensions


async def test_persist_stream_error_swallows_failure():
    """Best-effort: a failure persisting the error must never raise (it would truncate the already-
    open SSE stream or mask the original error)."""
    with patch(f"{HOOK_MODULE}.get_a2a_manager", side_effect=RuntimeError("boom")), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ):
        # must not raise
        await persist_stream_error("ctx-err", "some error", "run-1")


# ---- force_stop suggestions, guardrail chips, persist cap --


async def test_force_stop_response_persists_and_streams_suggestions():
    """Terminate-and-suggest-next-step: a tool sets force_stop_response AND calls add_suggestions().
    The suggestions weren't consumed on the tool_use model call (partial), so _on_after_invocation
    must consume them, attach them to the final message (chat_suggestions ext), and queue the live
    interaction under the same id — parity with the buffered path that attaches on every final."""
    mgr = RecordingManager()
    chips = ["Show worklogs", "Stop the job"]
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=chips):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        event = make_after_invocation_event(force_stop_response="Your job has been started.")
        await hook._on_after_invocation(event)

    stream_state = event.invocation_state["stream_state"]
    # persisted final carries the chips as the chat_suggestions ext, under the dedicated force_stop id
    assert len(mgr.calls) == 1
    _, message = mgr.calls[0]
    assert message.metadata[A2A_CHAT_SUGGESTIONS_EXT] == chips
    assert message.messageId == stream_state.force_stop_message_id
    # AND a live interaction side event was queued under the same id
    assert len(stream_state.side_events) == 1
    assert stream_state.side_events[0].message_id == stream_state.force_stop_message_id


async def test_force_stop_response_no_suggestions_queues_no_side_event(manager):
    """force_stop without suggestions persists the answer only — no interaction side event."""
    hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
    event = make_after_invocation_event(force_stop_response="Done.")
    await hook._on_after_invocation(event)

    _, message = manager.calls[0]
    assert A2A_CHAT_SUGGESTIONS_EXT not in (message.metadata or {})
    assert event.invocation_state["stream_state"].side_events == []


async def test_guardrail_final_does_not_carry_suggestions():
    """A guardrail block is a content refusal: it must NOT ship follow-up chips (which could come
    from an earlier tool_use step of the same turn). The suggestions are consumed-and-dropped (so
    they don't leak onto the next turn), and neither the persisted message nor a side event carries
    them."""
    mgr = RecordingManager()
    consumed = {"n": 0}

    def fake_consume():
        consumed["n"] += 1
        return ["leftover chip"]

    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", side_effect=fake_consume):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        event = make_event(
            stop_reason="guardrail_intervened",
            text="Sorry, I can't answer that.",
            final_message_id="g1",
        )
        await hook._on_after_model_call(event)

    assert consumed["n"] == 1  # drained so they don't leak to the next turn
    _, message = mgr.calls[0]
    assert message.parts == [{"kind": "text", "text": "Sorry, I can't answer that."}]
    assert A2A_CHAT_SUGGESTIONS_EXT not in (message.metadata or {})
    assert event.invocation_state["stream_state"].side_events == []


async def test_persist_stream_error_caps_a_slow_send():
    """A slow/stuck ATX Chat send must not hold the SSE stream: persist_stream_error bounds the
    send and returns (swallowing the timeout) so the caller proceeds to emit the terminal frame."""
    import asyncio
    import time

    class SlowManager:
        def send_message(self, agent_instance_id, message):
            time.sleep(30)  # far exceeds the cap; runs on a worker thread via to_thread

    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=SlowManager()), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}._ERROR_PERSIST_TIMEOUT_SECONDS", 0.1):
        start = asyncio.get_event_loop().time()
        # must return promptly (~cap), not raise, not block for the full 30s
        await persist_stream_error("ctx-1", "err", "run-1")
        elapsed = asyncio.get_event_loop().time() - start

    assert elapsed < 5  # returned near the cap, not the 30s send


class FailingManager:
    """A2AManager whose send_message always fails, simulating a transient 5xx from ATX Chat's
    SendA2AMessage. Records that the send was attempted."""

    def __init__(self):
        self.calls = 0

    def send_message(self, agent_instance_id, message):
        self.calls += 1
        raise RuntimeError("simulated ATX Chat 5xx")


async def test_force_stop_persist_failure_drops_live_chips():
    """#7: if the force_stop persist FAILS, the live suggestion side event must NOT be queued —
    else the user sees chips live that a reload can't reproduce (no persisted backing), the exact
    live/reload divergence this feature exists to prevent. The persist is attempted, the failure is
    swallowed (stream unaffected), and side_events stays empty."""
    mgr = FailingManager()
    chips = ["Show worklogs", "Stop the job"]
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=chips):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        event = make_after_invocation_event(force_stop_response="Your job has been started.")
        await hook._on_after_invocation(event)  # must not raise

    assert mgr.calls == 1  # persist WAS attempted
    # ...but it failed, so NO live chips were queued
    assert event.invocation_state["stream_state"].side_events == []


async def test_end_turn_persist_failure_drops_live_chips():
    """#7: same gate on the _on_after_model_call end_turn final — a failed persist means no live
    suggestion side event."""
    mgr = FailingManager()
    chips = ["Do this", "Do that"]
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=chips):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        event = make_event(text="Here is your answer.", final_message_id="fm-1")
        await hook._on_after_model_call(event)  # must not raise

    assert mgr.calls == 1
    assert event.invocation_state["stream_state"].side_events == []


async def test_end_turn_persist_success_queues_live_chips():
    """#7 counter-case: when the persist SUCCEEDS, the live chips ARE queued (the gate only blocks on
    failure), so a healthy turn still renders chips live under the final message's id."""
    mgr = RecordingManager()
    chips = ["Do this", "Do that"]
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=chips):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        event = make_event(text="Here is your answer.", final_message_id="fm-1")
        await hook._on_after_model_call(event)

    assert len(mgr.calls) == 1
    side_events = event.invocation_state["stream_state"].side_events
    assert len(side_events) == 1
    assert side_events[0].message_id == "fm-1"


async def test_persist_caps_a_slow_send():
    """#2: _persist runs inside the turn's asyncio.timeout scope, so a slow ATX Chat send must be
    bounded — else it eats the turn budget and can flip a good answer into a timeout terminal. The
    cap makes _safe_persist return False (send dropped), and the live chips are gated off that."""
    import asyncio
    import time

    class SlowManager:
        def __init__(self):
            self.calls = 0

        def send_message(self, agent_instance_id, message):
            self.calls += 1
            time.sleep(30)  # far exceeds the cap; runs on a worker thread via to_thread

    mgr = SlowManager()
    with patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=mgr), patch(
        f"{HOOK_MODULE}.get_agent_context_from_env",
        return_value=SimpleNamespace(agent_instance_id="job-agent-99"),
    ), patch(f"{HOOK_MODULE}.get_and_consume_suggestions", return_value=["chip"]), patch(
        f"{HOOK_MODULE}._PERSIST_TIMEOUT_SECONDS", 0.1
    ):
        hook = StreamingResponsePersistHook(DEFAULT_STREAMING_CONFIG)
        event = make_event(text="Answer.", final_message_id="fm-1")
        start = asyncio.get_event_loop().time()
        await hook._on_after_model_call(event)  # must return near the cap, not block 30s
        elapsed = asyncio.get_event_loop().time() - start

    assert mgr.calls == 1
    assert elapsed < 5  # bounded by the cap, not the 30s send
    # the send timed out => treated as a failed persist => no live chips
    assert event.invocation_state["stream_state"].side_events == []
