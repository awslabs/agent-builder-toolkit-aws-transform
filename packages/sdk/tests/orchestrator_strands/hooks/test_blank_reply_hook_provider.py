# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
import strands.hooks
from strands import ModelRetryStrategy, tool
from strands.event_loop._recover_message_on_max_tokens_reached import (
    recover_message_on_max_tokens_reached,
)
from strands.hooks import AfterModelCallEvent, BeforeInvocationEvent, MessageAddedEvent
from strands.models import Model
from strands.types.exceptions import (
    EventLoopException,
    MaxTokensReachedException,
    ModelThrottledException,
)

from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_type,
)
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider
from agent_builder_sdk.orchestrator_strands.hooks.blank_reply_hook_provider import (
    _ANSWER_MARKER,
    _CONTINUATION_TEXT,
    _RUN_LATE,
    _STATE_KEY,
    BLANK_REPLY_CONTINUATION_MARKER,
    BlankReplyHookProvider,
    _is_answer,
    _is_continuation,
)
from agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider import (
    MemoryHookProvider,
)
from agent_builder_sdk.utils import extract_text_from_strands_agent_response


@tool
def record_note(note: str) -> str:
    """Record a note."""
    return "{}"


_THROTTLE = "throttle"

_HOOK_ORDER = getattr(strands.hooks, "HookOrder", None)  # added in strands 1.43


def _text(text: str, stop_reason: str = "end_turn") -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": stop_reason}},
    ]


def _tool(tool_use_id: str) -> list[dict[str, Any]]:
    return [
        {
            "contentBlockStart": {
                "start": {"toolUse": {"toolUseId": tool_use_id, "name": "record_note"}}
            }
        },
        {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps({"note": "n"})}}}},
        {"contentBlockStop": {}},
    ]


def _text_and_tool(text: str) -> list[dict[str, Any]]:
    return [
        *_text(text)[:-1],
        *_tool("t1"),
        {"messageStop": {"stopReason": "tool_use"}},
    ]


def _tool_only(tool_use_id: str) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        *_tool(tool_use_id),
        {"messageStop": {"stopReason": "tool_use"}},
    ]


_EMPTY = [{"messageStart": {"role": "assistant"}}, {"messageStop": {"stopReason": "end_turn"}}]
_REASONING_ONLY = [
    {"messageStart": {"role": "assistant"}},
    {"contentBlockDelta": {"delta": {"reasoningContent": {"text": "All done."}}}},
    {"contentBlockDelta": {"delta": {"reasoningContent": {"signature": "sig"}}}},
    {"contentBlockStop": {}},
    {"messageStop": {"stopReason": "end_turn"}},
]


def _orchestrator(
    scripts: list[Any], tmpdir: Any, blank_reply: str = "after"
) -> AsyncBaseOrchestrator:
    orchestrator = AsyncBaseOrchestrator(
        "",
        custom_tools=[record_note],
        retry_strategy=ModelRetryStrategy(initial_delay=0, max_attempts=6),
    )
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = create_autospec(Model, spec_set=True, instance=True)
    responses = iter(scripts)

    async def stream(events: Any) -> AsyncGenerator[dict[str, Any], None]:
        if events == _THROTTLE:
            raise ModelThrottledException("slow down")
        for event in events:
            yield event

    payloads = _PAYLOADS.setdefault(orchestrator, [])

    def record_and_stream(messages: Any, *args: Any, **kwargs: Any) -> Any:
        payloads.append(copy.deepcopy(messages))
        return stream(next(responses))

    orchestrator.model.stream.side_effect = record_and_stream
    conversation = ConversationHookProvider(storage_dir=str(tmpdir))
    hooks = {
        "after": [conversation, BlankReplyHookProvider()],
        "before": [BlankReplyHookProvider(), conversation],
        "none": [conversation],
    }[blank_reply]
    for hook in hooks:
        orchestrator.hooks.add_hook(hook)
    return orchestrator


def _history(tmpdir: Any) -> list[dict[str, Any]]:
    with open(tmpdir.join("conversations.json")) as f:
        conversations = json.load(f)["conversations"]
    return [
        m["message"] for source in conversations.values() for msgs in source.values() for m in msgs
    ]


def _stored_shape(tmpdir: Any) -> list[tuple[str, list[str]]]:
    return [(m["role"], [next(iter(b)) for b in m["content"]]) for m in _history(tmpdir)]


_PAYLOADS: dict[AsyncBaseOrchestrator, list[Any]] = {}


def _sent(orchestrator: AsyncBaseOrchestrator, call: int) -> list[dict[str, Any]]:
    """The messages the model received on the given call.

    Copied when the model is called: some strands versions pass the live ``agent.messages`` list,
    so the mock's recorded arguments would alias whatever that list holds at inspection time.
    """
    return _PAYLOADS[orchestrator][call]


async def test_empty_reply_after_tool_results_is_asked_for_again(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Here is the plan."), _EMPTY, _text("Here is the plan: three steps.")],
        tmpdir,
    )

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == "Here is the plan: three steps."
    assert orchestrator.model.stream.call_count == 3
    continuation_sent = _sent(orchestrator, 2)[-1]
    assert continuation_sent["role"] == "user"
    assert continuation_sent["content"] == [{"text": _CONTINUATION_TEXT}]
    assert continuation_sent["content"][0]["text"].startswith("Your last response was empty")
    assert _stored_shape(tmpdir) == [
        ("user", ["text"]),
        ("assistant", ["text", "toolUse"]),
        ("user", ["toolResult"]),
        ("user", ["text"]),
        ("assistant", ["text"]),
    ]
    assert _history(tmpdir)[3]["metadata"]["custom"][BLANK_REPLY_CONTINUATION_MARKER] is True


async def test_second_empty_reply_ends_the_turn_empty(tmpdir):
    orchestrator = _orchestrator([_text_and_tool("Here is the plan."), _EMPTY, _EMPTY], tmpdir)

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == ""
    assert orchestrator.model.stream.call_count == 3
    assert _stored_shape(tmpdir) == [
        ("user", ["text"]),
        ("assistant", ["text", "toolUse"]),
        ("user", ["toolResult"]),
        ("user", ["text"]),
        ("assistant", []),
    ]


async def test_asks_at_most_once_even_after_more_tool_calls(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _tool_only("t2"), _EMPTY, _text("asked again")], tmpdir
    )

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == ""
    assert orchestrator.model.stream.call_count == 4
    assert _stored_shape(tmpdir) == [
        ("user", ["text"]),
        ("assistant", ["text", "toolUse"]),
        ("user", ["toolResult"]),
        ("user", ["text"]),
        ("assistant", ["toolUse"]),
        ("user", ["toolResult"]),
        ("assistant", []),
    ]


@pytest.mark.parametrize(
    "empty_reply",
    (_text("[blank text]"), _text(" \n"), _REASONING_ONLY),
    ids=["blank-text-placeholder", "whitespace", "reasoning-only"],
)
async def test_replies_without_visible_text_count_as_empty(tmpdir, empty_reply):
    orchestrator = _orchestrator(
        [_text_and_tool("Here is the plan."), empty_reply, _text("Three steps.")], tmpdir
    )

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == "Three steps."


@pytest.mark.parametrize(
    ("scripts", "model_calls"),
    (
        ([_EMPTY], 1),
        ([_text("Three steps.")], 1),
        ([_text_and_tool("Checking."), _text("Three steps.")], 2),
    ),
    ids=["empty-without-tool-results", "text", "tool-then-text"],
)
async def test_other_turns_are_untouched(tmpdir, scripts, model_calls):
    orchestrator = _orchestrator(scripts, tmpdir)

    await orchestrator.invoke_async("What is the plan?")

    assert orchestrator.model.stream.call_count == model_calls
    assert not any(m.get("metadata", {}).get("custom") for m in _history(tmpdir))


async def test_streaming_turns_are_untouched(tmpdir):
    orchestrator = _orchestrator([_text_and_tool("Here is the plan."), _EMPTY], tmpdir)

    await orchestrator.invoke_async("What is the plan?", invocation_state={"stream_state": Mock()})

    assert orchestrator.model.stream.call_count == 2


async def test_notification_turns_are_untouched(tmpdir):
    orchestrator = _orchestrator([_text_and_tool("Approval received."), _EMPTY], tmpdir)
    token = conversation_source_type.set(MessageSourceType.NOTIFICATION)
    try:
        await orchestrator.invoke_async("HITL Task t-1 is submitted")
    finally:
        conversation_source_type.reset(token)

    assert orchestrator.model.stream.call_count == 2


async def test_each_invocation_may_ask_once(tmpdir):
    turn = [_text_and_tool("Plan."), _EMPTY, _text("Three steps.")]
    orchestrator = _orchestrator(turn + turn, tmpdir)
    invocation_state: dict[str, Any] = {}

    first = await orchestrator.invoke_async("What is the plan?", invocation_state=invocation_state)
    second = await orchestrator.invoke_async("And again?", invocation_state=invocation_state)

    assert extract_text_from_strands_agent_response(first) == "Three steps."
    assert extract_text_from_strands_agent_response(second) == "Three steps."
    assert orchestrator.model.stream.call_count == 6
    # The second turn replays the first one's answered ask: the answer's signed thinking needs it.
    assert _sent(orchestrator, 3)[3]["content"] == [{"text": _CONTINUATION_TEXT}]


@pytest.mark.parametrize(
    "answer",
    ([_text("Done.")], [_tool_only("t2"), _text("Done.")], [_EMPTY], [_REASONING_ONLY]),
    ids=["text", "tool-call", "empty", "reasoning-only"],
)
async def test_an_answered_ask_is_replayed_whatever_the_answer(tmpdir, answer):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, *answer, _text("Turn 2.")], tmpdir
    )

    await orchestrator.invoke_async("What is the plan?")
    await orchestrator.invoke_async("Second question?")

    assert _sent(orchestrator, 2 + len(answer))[3]["content"] == [{"text": _CONTINUATION_TEXT}]
    assert [i for i, m in enumerate(_history(tmpdir)) if _is_answer(m)] == [4]


@pytest.mark.skipif(
    _HOOK_ORDER is None,
    reason="no HookOrder on this strands: the continuation cannot be ordered after the retry strategy",
)
async def test_continuation_gets_its_own_throttling_budget(tmpdir):
    """The empty call used up five of six attempts; the continuation must still be retried."""
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), *[_THROTTLE] * 5, _EMPTY, _THROTTLE, _text("Three steps.")],
        tmpdir,
    )

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == "Three steps."


@pytest.mark.skipif(_HOOK_ORDER is None, reason="no HookOrder on this strands: hooks are unordered")
async def test_a_partner_hook_that_raises_on_the_answer_leaves_no_ask_stored(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Answer."), _text("Turn 2."), _text("Turn 3.")],
        tmpdir,
    )
    answers: list[Any] = []

    def partner(event: AfterModelCallEvent) -> None:
        if event.stop_response is not None:
            answers.append(event.stop_response)
            if len(answers) == 3:
                raise RuntimeError("partner hook failed on the continuation's answer")

    orchestrator.hooks.add_callback(AfterModelCallEvent, partner, order=_HOOK_ORDER.DEFAULT + 2)

    with pytest.raises(EventLoopException):
        await orchestrator.invoke_async("What is the plan?")
    await orchestrator.invoke_async("Second question?")
    await orchestrator.invoke_async("Third question?")

    assert not any((m.get("metadata") or {}).get("custom") for m in _history(tmpdir))
    assert not any(m["content"] == [{"text": _CONTINUATION_TEXT}] for m in _sent(orchestrator, 4))


def _discard_the_third_answer(
    orchestrator: AsyncBaseOrchestrator, feedback: tuple[str, ...] = (), **order: Any
) -> None:
    answers: list[Any] = []

    def discard(event: AfterModelCallEvent) -> None:
        if event.stop_response is not None:
            answers.append(event.stop_response)
            if len(answers) == 3:
                event.retry = True
                event.agent.messages.extend(
                    {"role": "user", "content": [{"text": text}]} for text in feedback
                )

    orchestrator.hooks.add_callback(AfterModelCallEvent, discard, **order)


@pytest.mark.skipif(_HOOK_ORDER is None, reason="no HookOrder on this strands: hooks are unordered")
@pytest.mark.parametrize(
    "feedback", [(), ("Reply in English.", "Be brief.")], ids=["discard", "with-feedback"]
)
async def test_an_answer_a_later_hook_discards_leaves_its_replacement_marked(tmpdir, feedback):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Discarded."), _text("Kept."), _text("Turn 2.")],
        tmpdir,
    )
    _discard_the_third_answer(orchestrator, feedback, order=_HOOK_ORDER.DEFAULT + 200)

    await orchestrator.invoke_async("What is the plan?")
    await orchestrator.invoke_async("Second question?")

    assert _sent(orchestrator, 4)[3]["content"] == [{"text": _CONTINUATION_TEXT}]


async def test_a_discarded_answer_then_a_failed_call_stores_no_ask(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Answer."), *[_THROTTLE] * 6], tmpdir
    )
    _discard_the_third_answer(orchestrator)

    with pytest.raises(EventLoopException):
        await orchestrator.invoke_async("What is the plan?")

    assert not any((m.get("metadata") or {}).get("custom") for m in _history(tmpdir))


async def test_a_discarded_answer_then_a_reply_stores_the_ask_once(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Answer."), _text("Three steps.")], tmpdir
    )
    _discard_the_third_answer(orchestrator)

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == "Three steps."
    assert _sent(orchestrator, 3) == _sent(orchestrator, 2)
    assert _sent(orchestrator, 3)[-1]["content"] == [{"text": _CONTINUATION_TEXT}]
    assert _stored_shape(tmpdir) == [
        ("user", ["text"]),
        ("assistant", ["text", "toolUse"]),
        ("user", ["toolResult"]),
        ("user", ["text"]),
        ("assistant", ["text"]),
    ]
    assert _history(tmpdir)[3]["metadata"]["custom"][BLANK_REPLY_CONTINUATION_MARKER] is True


async def test_memory_recall_skips_the_ask_through_a_discarded_answer(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Answer."), _text("Three steps.")], tmpdir
    )
    memory = create_autospec(MemoryManager, spec_set=True, instance=True)
    memory.get_context_for_message.return_value = "remembered"
    orchestrator.hooks.add_hook(MemoryHookProvider(memory_manager=memory))
    _discard_the_third_answer(orchestrator)

    await orchestrator.invoke_async("What is the plan?")

    recalled_for = [c.kwargs["message"] for c in memory.get_context_for_message.call_args_list]
    assert recalled_for == ["What is the plan?"]
    assert _history(tmpdir)[3]["content"] == [{"text": _CONTINUATION_TEXT}]


def test_registers_unordered_when_strands_has_no_hookorder(monkeypatch):
    if _HOOK_ORDER is not None:
        assert _RUN_LATE == {"order": _HOOK_ORDER.DEFAULT + 100}
    spec = importlib.util.find_spec(BlankReplyHookProvider.__module__)
    assert spec is not None and spec.loader is not None
    monkeypatch.delattr(strands.hooks, "HookOrder", raising=False)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)  # a separate module object: the class under test is untouched

    assert fresh._RUN_LATE == {}


async def test_failed_continuation_call_keeps_the_pending_prompt():
    continuation = {"role": "user", "content": [{"text": "continue"}]}
    state: dict[str, Any] = {_STATE_KEY: continuation}
    event = AfterModelCallEvent(
        agent=Mock(messages=[continuation]),
        invocation_state=state,
        stop_response=None,
        exception=ModelThrottledException("x"),
    )

    await BlankReplyHookProvider()._continue_if_blank(event)

    assert event.agent.messages == [continuation]
    assert state[_STATE_KEY] is continuation
    assert event.retry is False


async def test_throttled_continuation_is_retried_with_the_ask(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _THROTTLE, _text("Three steps.")], tmpdir
    )

    result = await orchestrator.invoke_async("What is the plan?")

    assert extract_text_from_strands_agent_response(result) == "Three steps."
    assert _sent(orchestrator, 3)[-1]["content"] == [{"text": _CONTINUATION_TEXT}]
    assert _stored_shape(tmpdir) == [
        ("user", ["text"]),
        ("assistant", ["text", "toolUse"]),
        ("user", ["toolResult"]),
        ("user", ["text"]),
        ("assistant", ["text"]),
    ]


async def test_terminally_failed_continuation_is_not_persisted(tmpdir):
    orchestrator = _orchestrator([_text_and_tool("Plan."), _EMPTY, *[_THROTTLE] * 6], tmpdir)

    with pytest.raises(EventLoopException):
        await orchestrator.invoke_async("What is the plan?")

    history = _history(tmpdir)
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert not any((m.get("metadata") or {}).get("custom") for m in history)


def test_reset_drops_every_unanswered_continuation():
    ask = {
        "role": "user",
        "content": [{"text": _CONTINUATION_TEXT}],
        "metadata": {"custom": {BLANK_REPLY_CONTINUATION_MARKER: True}},
    }
    question = {"role": "user", "content": [{"text": "q"}], "metadata": {"custom": {"other": 1}}}
    answer = {"role": "assistant", "content": [], "metadata": {"custom": {_ANSWER_MARKER: True}}}
    denied = {"role": "assistant", "content": [{"text": "DENIED"}]}
    agent = Mock(messages=[question, ask, question, ask, answer, ask, denied, ask])

    BlankReplyHookProvider()._reset(BeforeInvocationEvent(agent=agent, invocation_state={}))
    assert agent.messages == [question, question, ask, answer, denied]

    BlankReplyHookProvider()._reset(BeforeInvocationEvent(agent=agent, invocation_state={}))
    assert agent.messages == [question, question, ask, answer, denied]


def _fail_after_storing_the_ask(event: MessageAddedEvent) -> None:
    if _is_continuation(event.message):
        raise RuntimeError("partner hook failed after the ask was stored")


@pytest.mark.parametrize("second_prompt", ["Second question?", None], ids=["question", "no-input"])
async def test_an_ask_stored_without_its_answer_is_never_sent_again(tmpdir, second_prompt):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Answer."), _text("Turn 2."), _text("Turn 3.")],
        tmpdir,
    )

    orchestrator.hooks.add_callback(MessageAddedEvent, _fail_after_storing_the_ask)

    with pytest.raises(EventLoopException):
        await orchestrator.invoke_async("What is the plan?")
    await orchestrator.invoke_async(second_prompt)
    await orchestrator.invoke_async("Third question?")

    assert not any(m["content"] == [{"text": _CONTINUATION_TEXT}] for m in _sent(orchestrator, 4))


@pytest.mark.parametrize(
    ("blank_reply", "source"),
    [
        ("none", MessageSourceType.USER),
        ("before", MessageSourceType.USER),
        ("none", MessageSourceType.SUBAGENT),
    ],
    ids=["hook-off", "hook-registered-first", "subagent-hook-off"],
)
async def test_loading_history_drops_an_ask_stored_without_its_answer(tmpdir, blank_reply, source):
    token = conversation_source_type.set(source)
    try:
        stranding = _orchestrator([_text_and_tool("Plan."), _EMPTY, _text("Answer.")], tmpdir)
        stranding.hooks.add_callback(MessageAddedEvent, _fail_after_storing_the_ask)
        with pytest.raises(EventLoopException):
            await stranding.invoke_async("What is the plan?")

        later = _orchestrator([_text("Turn 2."), _text("Turn 3.")], tmpdir, blank_reply)
        await later.invoke_async("Second question?")
        await later.invoke_async("Third question?")
    finally:
        conversation_source_type.reset(token)

    sent = _sent(later, 0) + _sent(later, 1)
    assert not any(m["content"] == [{"text": _CONTINUATION_TEXT}] for m in sent)


_RECOVERY_KEEPS_METADATA = "metadata" in recover_message_on_max_tokens_reached(
    {"role": "assistant", "content": [], "metadata": {}}
)


@pytest.mark.skipif(
    not _RECOVERY_KEEPS_METADATA,
    reason="this strands drops message metadata when it recovers from max_tokens",
)
async def test_an_answer_cut_off_by_max_tokens_keeps_its_ask(tmpdir):
    orchestrator = _orchestrator(
        [_text_and_tool("Plan."), _EMPTY, _text("Answer.", "max_tokens"), _text("Turn 2.")], tmpdir
    )

    with pytest.raises(MaxTokensReachedException):
        await orchestrator.invoke_async("What is the plan?")
    await orchestrator.invoke_async("Second question?")

    assert _sent(orchestrator, 3)[3]["content"] == [{"text": _CONTINUATION_TEXT}]


async def test_failed_model_call_is_left_to_the_retry_strategy():
    event = AfterModelCallEvent(
        agent=Mock(),
        invocation_state={},
        stop_response=None,
        exception=ModelThrottledException("x"),
    )

    await BlankReplyHookProvider()._continue_if_blank(event)

    assert event.retry is False


_TOOL_RESULTS = {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "content": []}}]}


@pytest.mark.parametrize(
    ("stop_reason", "last_message", "retry"),
    (
        ("max_tokens", _TOOL_RESULTS, False),
        ("end_turn", _TOOL_RESULTS, True),
        (
            "end_turn",
            {"role": "user", "content": [*_TOOL_RESULTS["content"], {"text": "and also"}]},
            False,
        ),
    ),
    ids=["not-end-turn", "already-retrying", "tool-results-mixed-with-text"],
)
async def test_does_not_ask_outside_an_empty_end_turn_after_tool_results(
    stop_reason, last_message, retry
):
    agent = Mock(messages=[last_message], hooks=Mock(invoke_callbacks_async=AsyncMock()))
    event = AfterModelCallEvent(
        agent=agent,
        invocation_state={},
        stop_response=AfterModelCallEvent.ModelStopResponse(
            message={"role": "assistant", "content": []}, stop_reason=stop_reason
        ),
        retry=retry,
    )

    await BlankReplyHookProvider()._continue_if_blank(event)

    assert agent.messages == [last_message]
    assert event.retry is retry
