# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Strands -> AG-UI -> A2A adapter.

Fixtures use the REAL dict shapes Strands yields from stream_async, captured
verbatim from the installed source (strands/types/_events.py). This doubles as a
contract test: if a future Strands version changes an event's dict shape, the
adapt() assertions here fail loudly instead of the adapter silently mis-dispatching.
"""

from ag_ui.core import (
    ReasoningMessageContentEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallStartEvent,
)

from agent_builder_sdk.streaming import (
    StreamingConfig,
    StreamState,
    adapt,
    to_a2a_error_frames,
    to_a2a_frames,
    to_wire,
)
from agent_builder_sdk.streaming.a2a_agui_adapter import build_suggestion_interaction_events


def types(events):
    return [type(e) for e in events]


# The AG-UI extension URI the adapter keys the DataPart payload by (and lists in message.extensions).
AGUI_EXT_URI = "https://aws.com/transform/ext/agui/v1"


def agui_of(frame):
    """Lift the AG-UI event out of a frame's DataPart, keyed by the extension URI."""
    return frame["status"]["message"]["parts"][0]["data"][AGUI_EXT_URI]


# ---- real Strands dict shapes (verbatim from installed _events.py) ----


def text_event(token, delta=None):
    return {"data": token, "delta": delta or {"text": token}}


def assistant_message_event(text="hi"):
    return {"message": {"role": "assistant", "content": [{"text": text}]}}


def result_event():
    # AgentResultEvent wraps an AgentResult; the adapter only checks the key to close the run.
    return {"result": object()}


class _ResultWithState:
    """Minimal stand-in for a terminal AgentResult carrying .state (== request_state), the dict a
    terminating tool writes force_stop_response into (see agent_result.py / event_loop.py)."""

    def __init__(self, state):
        self.state = state


def force_stop_result_event(text):
    # Terminal AgentResultEvent whose result.state carries a terminating-tool force_stop_response.
    return {"result": _ResultWithState({"force_stop_response": text})}


def force_stop_event(reason="ContextWindowOverflowException: too long"):
    return {"force_stop": True, "force_stop_reason": reason}


def tool_use_event(tool_id="t1", name="get_weather", input_frag='{"ci'):
    # ToolUseStreamEvent: delta carries the INCREMENTAL fragment; current_tool_use
    # carries the cumulative buffer + id + name.
    return {
        "type": "tool_use_stream",
        "delta": {"toolUse": {"input": input_frag}},
        "current_tool_use": {"toolUseId": tool_id, "name": name, "input": input_frag},
    }


def reasoning_event(token="thinking..."):
    return {
        "reasoningText": token,
        "delta": {"reasoningContent": {"text": token}},
        "reasoning": True,
    }


# Non-content events the adapter must DROP (real shapes).
INIT_LOOP = {"init_event_loop": True}


def fresh_state():
    # thread_id = conversation (AG-UI), context_id = A2A routing id echoed on the envelope.
    # run_id is minted by StreamState (the agent owns Task ids); tests read state.run_id.
    return StreamState(thread_id="thread-1", context_id="ctx-1")


# ---- adapt(): Strands event -> AG-UI events ----


class TestAdapt:
    def test_first_text_token_emits_run_started_then_text_start_content(self):
        state = fresh_state()
        out = adapt(text_event("Hello"), state)
        assert types(out) == [RunStartedEvent, TextMessageStartEvent, TextMessageContentEvent]
        assert out[-1].delta == "Hello"

    def test_second_text_token_only_content(self):
        state = fresh_state()
        adapt(text_event("Hello"), state)
        out = adapt(text_event(" world"), state)
        assert types(out) == [TextMessageContentEvent]
        assert out[0].delta == " world"

    def test_reasoning_emits_start_then_content(self):
        state = fresh_state()
        out = adapt(reasoning_event("hmm"), state)
        assert types(out) == [
            RunStartedEvent,
            ReasoningMessageStartEvent,
            ReasoningMessageContentEvent,
        ]

    def test_tool_use_emits_start_then_args(self):
        state = fresh_state()
        out = adapt(tool_use_event(name="get_plan"), state)
        assert types(out) == [RunStartedEvent, ToolCallStartEvent, ToolCallArgsEvent]
        start = out[1]
        assert start.tool_call_name == "get_plan"

    def test_tool_args_are_incremental_fragment_not_cumulative(self):
        state = fresh_state()
        adapt(tool_use_event(tool_id="t1", input_frag='{"ci'), state)
        out = adapt(tool_use_event(tool_id="t1", input_frag='ty":'), state)
        args = [e for e in out if isinstance(e, ToolCallArgsEvent)]
        assert args and args[0].delta == 'ty":'

    def test_terminal_result_emits_run_finished(self):
        state = fresh_state()
        adapt(text_event("hi"), state)
        out = adapt(result_event(), state)
        assert RunFinishedEvent in types(out)

    def test_force_stop_response_streams_final_text_before_run_finished(self):
        # A terminating tool (stop_after_response) puts the real answer on result.state
        # ["force_stop_response"]; on the stream the model only produced pre-tool narration + the
        # tool call, so the adapter must surface that answer as the final assistant text (trio) under
        # its dedicated force_stop_message_id, then RUN_FINISHED. Mirrors the buffered
        # force_stop_response override.
        state = fresh_state()
        answer = "Your job has been started successfully."
        out = adapt(force_stop_result_event(answer), state)
        t = types(out)
        assert t[-1] is RunFinishedEvent
        assert RunErrorEvent not in t
        trio = [
            e
            for e in out
            if isinstance(e, (TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent))
        ]
        assert [type(e) for e in trio] == [
            TextMessageStartEvent,
            TextMessageContentEvent,
            TextMessageEndEvent,
        ]
        content = [e for e in out if isinstance(e, TextMessageContentEvent)][0]
        assert content.delta == answer
        # streamed under the dedicated force_stop id so the persisted copy reconciles on reload
        assert content.message_id == state.force_stop_message_id

    def test_force_stop_response_reuses_preset_force_stop_id(self):
        # The persist hook (AfterInvocationEvent) fires first and mints force_stop_message_id for the
        # same force_stop text; the adapter must reuse it (read-or-mint), not mint a second id.
        state = fresh_state()
        state.force_stop_message_id = "persist-minted-id"
        out = adapt(force_stop_result_event("done"), state)
        starts = [e for e in out if isinstance(e, TextMessageStartEvent)]
        assert starts and starts[0].message_id == "persist-minted-id"

    def test_force_stop_id_does_not_collide_with_narration(self):
        # If the turn already streamed a pre-tool narration text block, final_message_id is that
        # narration's id. The force_stop answer is a DISTINCT assistant message, so it must stream
        # under its own force_stop_message_id — never reuse final_message_id (which would persist two
        # different texts under one id and collide on reload).
        state = fresh_state()
        adapt(text_event("Let me start that for you..."), state)  # narration owns final_message_id
        narration_id = state.final_message_id
        assert narration_id is not None
        out = adapt(force_stop_result_event("Your job has been started successfully."), state)
        starts = [e for e in out if isinstance(e, TextMessageStartEvent)]
        assert starts and starts[0].message_id != narration_id
        assert starts[0].message_id == state.force_stop_message_id

    def test_ordinary_terminal_result_no_force_stop_emits_no_text(self):
        # A plain terminal (no force_stop_response on state) opens no text block — just closes the run.
        out = adapt(result_event(), fresh_state())
        assert TextMessageStartEvent not in types(out)
        assert types(out)[-1] is RunFinishedEvent

    def test_guardrail_block_terminal_needs_no_special_handling(self):
        # A guardrail block ends the turn with a normal terminal AgentResult. Bedrock streamed its
        # mandatory blockedOutputsMessaging as an ordinary text delta beforehand (like any answer),
        # so the terminal branch just closes the run — the adapter treats the terminal identically
        # whether the turn ended on end_turn or on a guardrail block. No RUN_ERROR, no synthesized
        # extra text on the terminal itself.
        state = fresh_state()
        owner_msg = "Sorry, this is a test custom refusal."
        pre = adapt(text_event(owner_msg), state)  # the block message streams as normal text
        terminal = adapt(result_event(), state)
        assert RunErrorEvent not in types(terminal)
        assert types(terminal)[-1] is RunFinishedEvent
        # The terminal opens no NEW text block — the block message already streamed above.
        assert TextMessageStartEvent not in types(terminal)
        assert [e.delta for e in pre if isinstance(e, TextMessageContentEvent)] == [owner_msg]

    def test_force_stop_emits_no_terminal_and_no_raw_reason(self):
        # ForceStopEvent is yielded ONLY from Strands' except blocks, each followed by a raise, so it
        # always precedes an exception that reaches _stream_message_async's outer handler — which emits
        # the ONE sanitized terminal. The adapter must therefore emit NO terminal here (no second
        # RUN_ERROR) and must NOT leak the raw reason (which can carry ARNs/account ids). It only
        # closes any open block so the wire stays balanced ahead of that terminal.
        state = fresh_state()
        adapt(text_event("hi"), state)  # opens a text block
        out = adapt(force_stop_event("boom: arn:aws:bedrock:secret"), state)
        assert RunErrorEvent not in types(out)
        assert RunFinishedEvent not in types(out)
        # the raw reason never appears on any emitted event
        assert all("secret" not in str(getattr(e, "message", "")) for e in out)
        # the previously-open text block is closed (balanced wire)
        assert TextMessageEndEvent in types(out)

    def test_force_stop_before_any_content_emits_nothing(self):
        # A force-stop as the very first event: no open block to close, and the terminal is owned by
        # the outer handler — so the adapter emits nothing at all here.
        state = fresh_state()
        out = adapt(force_stop_event("boom"), state)
        assert out == []

    def test_unknown_event_dropped(self):
        assert adapt(INIT_LOOP, fresh_state()) == []

    def test_non_dict_dropped(self):
        assert adapt("not a dict", fresh_state()) == []


# ---- cfg gating: a disabled category emits nothing (no dangling block) ----


class TestGating:
    def test_reasoning_off_drops_reasoning(self):
        cfg = StreamingConfig(emit_reasoning=False)
        assert adapt(reasoning_event(), fresh_state(), cfg) == []

    def test_tool_calls_off_drops_tools(self):
        cfg = StreamingConfig(emit_tool_calls=False)
        assert adapt(tool_use_event(), fresh_state(), cfg) == []

    def test_text_always_emitted_even_with_categories_off(self):
        # Text (narration + final answer) has no toggle: it is always emitted, even when both
        # gated categories are off.
        cfg = StreamingConfig(emit_reasoning=False, emit_tool_calls=False)
        assert adapt(text_event("hi"), fresh_state(), cfg) != []

    def test_lifecycle_never_gated(self):
        # Even with the gated categories off, a terminal result still finishes the run.
        cfg = StreamingConfig(emit_reasoning=False, emit_tool_calls=False)
        out = adapt(result_event(), fresh_state(), cfg)
        assert RunFinishedEvent in types(out)


# ---- to_a2a_frames: AG-UI event -> A2A frame dict ----


class TestStreamStateIds:
    """The three per-turn ids are distinct: run_id (A2A taskId) is agent-minted and cannot be
    supplied by the caller; context_id (A2A routing id) and thread_id (conversation) are."""

    def test_run_id_is_minted_and_not_a_constructor_arg(self):
        import pytest

        # run_id is init=False — passing it is a TypeError, so a caller can't reuse a
        # request id (e.g. the contextId) as the task id.
        with pytest.raises(TypeError):
            StreamState(thread_id="t", context_id="c", run_id="oops")  # type: ignore[call-arg]

    def test_each_state_mints_a_distinct_uuid_run_id(self):
        import uuid

        a, b = StreamState(thread_id="t", context_id="c"), StreamState(
            thread_id="t", context_id="c"
        )
        assert a.run_id != b.run_id
        uuid.UUID(a.run_id)  # a valid uuid4, not the contextId

    def test_context_id_and_thread_id_are_independent(self):
        state = StreamState(thread_id="conv-1", context_id="ctx-1")
        # frame envelope carries the A2A contextId (routing), NOT the conversation id
        [frame] = to_a2a_frames(TextMessageContentEvent(message_id="m1", delta="x"), state)
        assert frame["contextId"] == "ctx-1"


class TestToA2AFrames:
    def test_run_started_becomes_task_submitted(self):
        state = fresh_state()
        [frame] = to_a2a_frames(RunStartedEvent(thread_id="thread-1", run_id=state.run_id), state)
        assert frame["kind"] == "task"
        assert frame["id"] == state.run_id  # the agent-minted task id
        assert frame["contextId"] == "ctx-1"
        assert frame["status"]["state"] == "submitted"

    def test_run_started_carries_agui_with_thread_and_run_ids(self):
        # threadId + runId live only on the AG-UI RUN_STARTED, not the A2A envelope, so the
        # frame carries the AG-UI event in a DataPart for the reader to lift them out of.
        state = fresh_state()
        [frame] = to_a2a_frames(RunStartedEvent(thread_id="thread-1", run_id=state.run_id), state)
        message = frame["status"]["message"]
        # the AG-UI extension is signaled in message.extensions and the payload is keyed by its URI
        assert message["extensions"] == [AGUI_EXT_URI]
        agui = agui_of(frame)
        assert agui["type"] == "RUN_STARTED"
        assert agui["threadId"] == "thread-1"
        assert agui["runId"] == state.run_id

    def test_run_finished_becomes_terminal_completed(self):
        state = fresh_state()
        [frame] = to_a2a_frames(RunFinishedEvent(thread_id="thread-1", run_id=state.run_id), state)
        assert frame["kind"] == "status-update"
        assert frame["final"] is True
        assert frame["status"]["state"] == "completed"

    def test_run_finished_carries_agui_in_datapart(self):
        state = fresh_state()
        [frame] = to_a2a_frames(RunFinishedEvent(thread_id="thread-1", run_id=state.run_id), state)
        agui = agui_of(frame)
        assert agui["type"] == "RUN_FINISHED"

    def test_run_error_terminal_failed_carries_agui_in_datapart(self):
        state = fresh_state()
        [frame] = to_a2a_frames(RunErrorEvent(message="timeout"), state)
        assert frame["final"] is True
        assert frame["status"]["state"] == "failed"
        part = frame["status"]["message"]["parts"][0]
        assert part["kind"] == "data"
        assert part["data"][AGUI_EXT_URI]["type"] == "RUN_ERROR"

    def test_content_event_is_working_with_agui_datapart(self):
        state = fresh_state()
        [frame] = to_a2a_frames(TextMessageContentEvent(message_id="m1", delta="hi"), state)
        assert frame["kind"] == "status-update"
        assert frame["final"] is False
        assert frame["status"]["state"] == "working"
        agui = agui_of(frame)
        assert agui["type"] == "TEXT_MESSAGE_CONTENT"
        assert agui["delta"] == "hi"

    def test_frame_carries_task_and_context_ids(self):
        state = fresh_state()
        [frame] = to_a2a_frames(TextMessageContentEvent(message_id="m1", delta="x"), state)
        assert frame["taskId"] == state.run_id
        assert frame["contextId"] == "ctx-1"


# ---- to_wire: AG-UI event -> camelCase dict; ToolCallStart parentMessageId->messageId ----


class TestToWire:
    def test_tool_call_start_renames_parent_message_id_to_message_id(self):
        wire = to_wire(
            ToolCallStartEvent(tool_call_id="c1", tool_call_name="f", parent_message_id="m1")
        )
        assert wire["messageId"] == "m1"
        assert "parentMessageId" not in wire

    def test_text_content_wire_has_camelcase(self):
        wire = to_wire(TextMessageContentEvent(message_id="m1", delta="hi"))
        assert wire["messageId"] == "m1"
        assert wire["type"] == "TEXT_MESSAGE_CONTENT"


class TestToA2AErrorFrames:
    """to_a2a_error_frames must keep the frame protocol valid on error paths: open the run
    (Task opener) if not started, close any open content block, THEN emit terminal RUN_ERROR."""

    def test_error_before_run_started_emits_task_opener_first(self):
        state = fresh_state()  # run_started = False, no content yet
        frames = to_a2a_error_frames("boom", state)
        # first frame is the Task(submitted) opener, last is the terminal failed/final
        assert frames[0]["kind"] == "task"
        assert frames[0]["status"]["state"] == "submitted"
        last = frames[-1]
        assert last["status"]["state"] == "failed"
        assert last["final"] is True
        # the RUN_ERROR reason survives in the terminal frame's DataPart
        agui = agui_of(last)
        assert agui["type"] == "RUN_ERROR"
        assert agui["message"] == "boom"

    def test_error_after_run_started_does_not_reopen(self):
        state = fresh_state()
        # simulate a run already opened by prior content
        to_a2a_frames(TextMessageContentEvent(message_id="m1", delta="hi"), state)
        # (adapt would have set run_started; emulate that state precisely)
        state.run_started = True
        frames = to_a2a_error_frames("late failure", state)
        # no second Task opener — first frame is NOT a task opener
        assert all(f.get("kind") != "task" for f in frames)
        assert frames[-1]["status"]["state"] == "failed"
        assert frames[-1]["final"] is True

    def test_error_closes_open_text_block_before_terminal(self):
        state = fresh_state()
        state.run_started = True
        state.open_message_id = "m1"  # a text block left open
        frames = to_a2a_error_frames("mid-block failure", state)
        # a TEXT_MESSAGE_END is emitted (block closed) before the terminal RUN_ERROR
        types_seen = [agui_of(f)["type"] for f in frames if f.get("status", {}).get("message")]
        assert "TEXT_MESSAGE_END" in types_seen
        assert types_seen[-1] == "RUN_ERROR"
        assert state.open_message_id is None  # block state cleared


# ---- suggestion interaction events (live chips / job-creation button) ----


class TestSuggestionInteractionEvents:
    def test_chat_suggestions_become_one_select_interaction(self):
        events = build_suggestion_interaction_events(
            chat_suggestions=["Show worklogs", "Stop the job"],
            create_job_suggestion=None,
            message_id="msg-1",
        )
        assert len(events) == 1
        wire = to_wire(events[0])
        assert wire["type"] == "INTERACTION"
        assert wire["messageId"] == "msg-1"
        [interaction] = wire["interactions"]
        assert interaction["actionType"] == "SELECT"
        options = interaction["data"]["selectInteractionData"]["options"]
        # label == value, order preserved
        assert options == [
            {"label": "Show worklogs", "value": "Show worklogs"},
            {"label": "Stop the job", "value": "Stop the job"},
        ]

    def test_create_job_suggestion_becomes_invoke_and_takes_precedence(self):
        events = build_suggestion_interaction_events(
            chat_suggestions=["ignored when create-job present"],
            create_job_suggestion={
                "jobName": "Migrate DB",
                "jobType": "some-job-type",
                "objective": "Move to Aurora",
            },
            message_id="msg-2",
        )
        assert len(events) == 1
        [interaction] = to_wire(events[0])["interactions"]
        assert interaction["actionType"] == "INVOKE"
        invoke = interaction["data"]["invokeInteractionData"]["invokeApi"]
        assert invoke["operationName"] == "createAndStartJob"
        # jobType passed through verbatim (no internal jobType/agentId resolution in the agent)
        assert invoke["operationParams"] == {
            "jobName": "Migrate DB",
            "jobType": "some-job-type",
            "objective": "Move to Aurora",
        }

    def test_incomplete_create_job_falls_back_to_chat_suggestions(self):
        # A create-job dict missing a required field is ignored; chat suggestions win.
        events = build_suggestion_interaction_events(
            chat_suggestions=["fallback"],
            create_job_suggestion={"jobName": "x"},  # missing jobType/objective
            message_id="m",
        )
        [interaction] = to_wire(events[0])["interactions"]
        assert interaction["actionType"] == "SELECT"

    def test_no_suggestions_yields_no_events(self):
        assert build_suggestion_interaction_events(None, None, "m") == []
        assert build_suggestion_interaction_events([], None, "m") == []

    def test_interaction_event_frames_as_working_status_update(self):
        # An interaction event is not lifecycle, so to_a2a_frames carries it as a working
        # status-update with the AG-UI event verbatim in the DataPart (like any content event).
        state = fresh_state()
        [event] = build_suggestion_interaction_events(["a"], None, "msg-9")
        [frame] = to_a2a_frames(event, state)
        assert frame["kind"] == "status-update"
        assert frame["final"] is False
        assert agui_of(frame)["type"] == "INTERACTION"
        assert agui_of(frame)["messageId"] == "msg-9"

    def test_message_id_omitted_when_none(self):
        wire = to_wire(build_suggestion_interaction_events(["a"], None, None)[0])
        assert "messageId" not in wire  # exclude_none drops it


def tool_stream_event(inner, tool_name="send_message_to_subagent_and_relay"):
    """A Strands tool_stream event wrapping a value the named async-generator tool yielded."""
    return {
        "type": "tool_stream",
        "tool_stream_event": {
            "tool_use": {"toolUseId": "t1", "name": tool_name},
            "data": inner,
        },
    }


class TestRelayedSubagentStream:
    """adapt()'s tool_stream branch: a sub-agent's frames relayed live to the user."""

    def test_relayed_text_delta_streams_under_force_stop_id(self):
        state = fresh_state()
        out = adapt(tool_stream_event({"data": "Hi"}), state)
        # First relayed token opens the run + a text block under the shared force_stop id.
        assert types(out) == [RunStartedEvent, TextMessageStartEvent, TextMessageContentEvent]
        assert state.force_stop_streamed is True
        assert out[1].message_id == state.force_stop_message_id
        assert out[2].delta == "Hi"

    def test_other_streaming_tool_yield_is_not_treated_as_relay(self):
        # A DIFFERENT async-generator tool also emits tool_stream events. Its yields must NOT be
        # rendered as the orchestrator's final answer, and must not set force_stop_streamed.
        state = fresh_state()
        out = adapt(tool_stream_event({"data": "log line"}, tool_name="search_logs"), state)
        assert out == []
        assert state.force_stop_streamed is False

    def test_relayed_non_dict_payload_dropped(self):
        # The tool's final yield (its result string) also arrives as a tool_stream event; it is not
        # stream content, so it is dropped (the real answer persists via force_stop_response).
        state = fresh_state()
        assert adapt(tool_stream_event("Jupiter is largest"), state) == []

    def test_terminal_skips_reemit_after_live_relay(self):
        # After the answer streamed live, the terminating tool's force_stop_response must NOT be
        # re-emitted as a whole message — the terminal just closes the live block and finishes.
        state = fresh_state()
        adapt(tool_stream_event({"data": "Jupiter"}), state)
        adapt(tool_stream_event({"data": " is largest"}), state)
        assert state.force_stop_streamed is True

        out = adapt(force_stop_result_event("Jupiter is largest"), state)
        assert types(out) == [TextMessageEndEvent, RunFinishedEvent]
        assert out[0].message_id == state.force_stop_message_id
