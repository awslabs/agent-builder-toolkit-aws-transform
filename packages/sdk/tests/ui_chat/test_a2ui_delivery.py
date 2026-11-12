# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""A surface that an agent renders reaches the chat, whatever order the model calls its tools in.

Each test runs a real agent on a scripted model through the code that delivers the reply: the
queue worker and the direct handler for message/send, the stream and its persist hook for
message/stream.
"""

import asyncio
import itertools
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec, patch

import pytest
from strands import ToolContext, tool
from strands.models.model import Model

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent
from agent_builder_sdk.custom_types.common_types import A2AMessage, InvocationRequest
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.message_queue import QueueRequest, RequestQueue, RequestStatus, ResponseStore
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
    AsyncBaseOrchestrator,
    BaseOrchestrator,
)
from agent_builder_sdk.request_handler.queue_handler import QueueRequestHandler
from agent_builder_sdk.streaming.config import StreamingConfig
from agent_builder_sdk.ui_chat.a2ui import build_a2ui_block, render_a2ui_surface, suggest_replies
from agent_builder_sdk.util.suggestions_manager import clear_suggestions
from agent_builder_sdk.utils import (
    A2A_CHAT_SUGGESTIONS_EXT,
    A2A_MESSAGE_TYPE_EXT,
    convert_queue_response_to_send_message_output,
)

HOOK_MODULE = "agent_builder_sdk.streaming.response_persist_hook"
TABLE = {
    "component": "Table",
    "columnDefinitions": [{"id": "name", "header": "Name", "field": "name"}],
    "items": {"path": "/data/apps"},
}
CHIPS = ["Show only Java apps", "Explain the largest app"]
INTRO = "Here is the application inventory."
CLOSING = "Let me know if you want a closer look at one of them."
_TOOL_USE_IDS = itertools.count(1)


def _apps(*names):
    return {"data": {"apps": [{"name": name} for name in names]}}


def _block(surface_id="inventory", *names):
    return build_a2ui_block(surface_id, TABLE, _apps(*names or ("payments-api",)))


BLOCK = _block()


def _call(text=None, tool=None, stop_reason=None, **tool_input):
    """The stream events of one model call: optional text, then an optional tool call."""
    events = [{"messageStart": {"role": "assistant"}}]
    if text is not None:
        events += [{"contentBlockDelta": {"delta": {"text": text}}}, {"contentBlockStop": {}}]
    if tool:
        tool_use = {"toolUseId": f"tool-{next(_TOOL_USE_IDS)}", "name": tool}
        events += [
            {"contentBlockStart": {"start": {"toolUse": tool_use}}},
            {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}},
            {"contentBlockStop": {}},
        ]
    return [*events, {"messageStop": {"stopReason": stop_reason or ("tool_use" if tool else "end_turn")}}]


def _render(surface_id="inventory", *names, tree=TABLE, text=None):
    return _call(
        text,
        tool="render_a2ui_surface",
        surface_id=surface_id,
        component_tree=tree,
        data_model=_apps(*names or ("payments-api",)),
    )


def _suggest(text=None):
    return _call(text, tool="suggest_replies", suggestions=CHIPS)


class _ScriptedModel(Model):
    """Plays one script per model call. A script holds stream events; it raises an exception that
    it holds, and it awaits a function that it holds before it goes on."""

    def __init__(self, calls):
        self.calls = list(calls)

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {}

    def structured_output(self, *args, **kwargs):
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        for event in self.calls.pop(0):
            if isinstance(event, Exception):
                raise event
            if callable(event):
                await event()
            else:
                yield event


def _agent(*calls, cls=AsyncBaseOrchestrator, tools=()):
    return cls(
        system_prompt="",
        custom_tools=[render_a2ui_surface, suggest_replies, *tools],
        model=_ScriptedModel(calls),
        callback_handler=None,
    )


def _streaming_agent(*calls, tools=()):
    agent = _agent(*calls, tools=tools)
    for hook in agent.get_streaming_hook_providers(StreamingConfig()):
        agent.hooks.add_hook(hook)
    return agent


def _hang():
    return asyncio.sleep(60)


async def _send(agent, turns=1):
    """Run message/send turns through the queue worker. Returns the stored response of each turn."""
    requests = [QueueRequest(message="go", context={"context_id": "ctx-1", "user_id": "user-1"}) for _ in range(turns)]
    queue = create_autospec(RequestQueue, spec_set=True, instance=True)
    queue.dequeue.side_effect = [*requests, asyncio.CancelledError()]
    store = create_autospec(ResponseStore, spec_set=True, instance=True)
    await QueueRequestHandler(request_queue=queue, response_store=store).start_processing(AsyncMock(return_value=agent))
    return [stored.args[0] for stored in store.store_response.await_args_list]


def _a2a_message():
    return A2AMessage(
        role="user", parts=[{"kind": "text", "text": "go"}], messageId="message-1", kind="message", contextId="ctx-1"
    )


@pytest.fixture(autouse=True)
def no_pending_suggestions():
    clear_suggestions()
    yield
    clear_suggestions()


@pytest.fixture
def chat():
    """The chat service that a streaming turn persists its messages to."""
    manager = Mock()
    with (
        patch(f"{HOOK_MODULE}.get_a2a_manager", return_value=manager),
        patch(f"{HOOK_MODULE}.get_agent_context_from_env", return_value=SimpleNamespace(agent_instance_id="agent-1")),
    ):
        yield manager


def _persisted(chat):
    """What a reload shows: (message id, "partial_update" or "final", text, suggestions) per stored message."""
    messages = [stored.kwargs["message"] for stored in chat.send_message.call_args_list]
    return [
        (
            m.messageId,
            (m.metadata.get(A2A_MESSAGE_TYPE_EXT) or {}).get("messageType", "final"),
            m.parts[0]["text"],
            m.metadata.get(A2A_CHAT_SUGGESTIONS_EXT),
        )
        for m in messages
    ]


async def _stream(agent, context_id="ctx-1"):
    """Run one streaming turn. Returns (the text of each streamed assistant message by id, the type
    of each streamed event in order, the last frame)."""
    request = ProcessMessageRequest(
        "go", ConversationContext(user_id="user-1", a2a_context=A2AContext(context_id=context_id, task_id=None))
    )
    texts, kinds, frame = {}, [], None
    async for frame in agent.process_message_stream(request, "conversation-1", StreamingConfig()):
        for part in ((frame.get("status") or {}).get("message") or {}).get("parts") or []:
            for event in (part.get("data") or {}).values():
                kinds.append(event.get("type"))
                if event.get("type") == "TEXT_MESSAGE_CONTENT":
                    texts[event["messageId"]] = texts.get(event["messageId"], "") + event["delta"]
    return texts, kinds, frame


def _finals(chat):
    return [message for message in _persisted(chat) if message[1] == "final"]


@pytest.mark.parametrize("cls", [AsyncBaseOrchestrator, BaseOrchestrator])
async def test_block_written_before_a_later_tool_call_reaches_the_chat_message(cls):
    """The model writes the block, calls suggest_replies in the same message, and ends on a short sentence."""
    agent = _agent(_render(), _suggest(f"{BLOCK}\n{INTRO}"), _call(CLOSING), cls=cls)

    (response,) = await _send(agent)

    message = convert_queue_response_to_send_message_output(response, _a2a_message(), "agent-1").result
    assert [part["text"] for part in message.parts] == [f"{BLOCK}\n\n{CLOSING}"]
    assert message.metadata[A2A_CHAT_SUGGESTIONS_EXT] == CHIPS


async def test_block_in_the_final_message_stays_once_where_the_model_put_it():
    reply = f"{INTRO}\n\n{BLOCK}\n\n{CLOSING}"
    agent = _agent(_render(), _suggest(), _call(reply))

    (response,) = await _send(agent)

    assert response.message == reply


async def test_two_missing_surfaces_come_in_render_order_before_the_text():
    servers = _block("servers", "web-01")
    agent = _agent(_render(), _render("servers", "web-01"), _suggest(f"{BLOCK}\n\n{servers}"), _call(CLOSING))

    (response,) = await _send(agent)

    assert response.message == f"{BLOCK}\n\n{servers}\n\n{CLOSING}"


async def test_surface_the_final_message_holds_is_not_added_again():
    servers = _block("servers", "web-01")
    reply = f"{INTRO}\n\n{servers}"
    agent = _agent(_render(), _render("servers", "web-01"), _suggest(BLOCK), _call(reply))

    (response,) = await _send(agent)

    assert response.message == f"{BLOCK}\n\n{reply}"


async def test_surface_rendered_again_is_delivered_once_with_its_latest_block():
    agent = _agent(
        _render("inventory", "payments-api"), _render("inventory", "payments-api", "ledger-svc"), _call(CLOSING)
    )

    (response,) = await _send(agent)

    assert response.message == f"{_block('inventory', 'payments-api', 'ledger-svc')}\n\n{CLOSING}"


async def test_copy_of_an_earlier_render_becomes_the_latest_render_in_its_place():
    earlier, latest = _block("inventory", "payments-api"), _block("inventory", "payments-api", "ledger-svc")
    agent = _agent(
        _render("inventory", "payments-api"),
        _render("inventory", "payments-api", "ledger-svc"),
        _call(f"{INTRO}\n\n{earlier}\n\n{CLOSING}"),
    )

    (response,) = await _send(agent)

    assert response.message == f"{INTRO}\n\n{latest}\n\n{CLOSING}"


async def test_validation_error_then_a_valid_render_delivers_the_valid_block():
    agent = _agent(_render(tree={"component": "Blink"}), _render(), _call(CLOSING))

    (response,) = await _send(agent)

    assert response.message == f"{BLOCK}\n\n{CLOSING}"


async def test_render_that_only_failed_validation_adds_nothing():
    agent = _agent(_render(tree={"component": "Blink"}), _call(CLOSING))

    (response,) = await _send(agent)

    assert response.message == CLOSING


async def test_empty_final_message_delivers_the_block_alone():
    agent = _agent(_render(), _call())

    (response,) = await _send(agent)

    assert response.message == BLOCK


async def test_next_turn_gets_nothing_from_the_turn_before():
    agent = _agent(_render(), _suggest(BLOCK), _call(CLOSING), _call("Second answer."))

    first, second = await _send(agent, turns=2)

    assert first.message == f"{BLOCK}\n\n{CLOSING}"
    assert second.message == "Second answer."


async def test_next_turn_that_renders_another_surface_gets_only_its_own():
    servers = _block("servers", "web-01")
    agent = _agent(_render(), _call(CLOSING), _render("servers", "web-01"), _call("Second answer."))

    first, second = await _send(agent, turns=2)

    assert first.message == f"{BLOCK}\n\n{CLOSING}"
    assert second.message == f"{servers}\n\nSecond answer."


async def test_turn_that_fails_delivers_no_surface_and_leaves_none_for_the_next_turn():
    servers = _block("servers", "web-01")
    agent = _agent(_render(), [RuntimeError("model failure")], _render("servers", "web-01"), _call("Second answer."))

    failed, second = await _send(agent, turns=2)

    assert failed.status is RequestStatus.FAILED
    assert "atx-a2ui" not in failed.message
    assert second.message == f"{servers}\n\nSecond answer."


@pytest.mark.parametrize("stop_reason", ["guardrail_intervened", "content_filtered"])
async def test_refusal_delivers_no_surface(stop_reason):
    agent = _agent(_render(), _call("I can't help with that.", stop_reason=stop_reason))

    (response,) = await _send(agent)

    assert response.message == "I can't help with that."


@tool(context=True)
def finish(tool_context: ToolContext) -> str:
    """End the turn with a fixed answer."""
    tool_context.invocation_state["request_state"].update(force_stop_response="Forced answer.", stop_event_loop=True)
    return "done"


async def test_forced_stop_answer_gets_the_missing_block():
    agent = _agent(_render(), _call(tool="finish"), tools=[finish])

    (response,) = await _send(agent)

    assert response.message == f"{BLOCK}\n\nForced answer."


async def test_direct_reply_gets_a_block_written_before_a_later_tool_call():
    agent = _agent(_render(), _suggest(f"{BLOCK}\n{INTRO}"), _call(CLOSING), cls=AsyncBaseSubagent)

    output = await MessageHandler(agent=agent).send_message(InvocationRequest(_a2a_message()))

    assert [part["text"] for part in output.result.parts] == [f"{BLOCK}\n\n{CLOSING}"]


async def test_direct_reply_with_an_empty_final_message_is_the_block_alone():
    agent = _agent(_render(), _call(), cls=AsyncBaseSubagent)

    output = await MessageHandler(agent=agent).send_message(InvocationRequest(_a2a_message()))

    assert [part["text"] for part in output.result.parts] == [BLOCK]


async def test_direct_forced_stop_answer_gets_the_missing_block():
    agent = _agent(_render(), _call(tool="finish"), cls=AsyncBaseSubagent, tools=[finish])

    output = await MessageHandler(agent=agent).send_message(InvocationRequest(_a2a_message()))

    assert [part["text"] for part in output.result.parts] == [f"{BLOCK}\n\nForced answer."]


async def test_direct_turn_that_times_out_delivers_no_surface_and_leaves_none_for_the_next_turn():
    servers = _block("servers", "web-01")
    agent = _agent(_render(), [_hang], _render("servers", "web-01"), _call("Second answer."), cls=AsyncBaseSubagent)
    handler = MessageHandler(agent=agent, timeout=1)

    timed_out = await handler.send_message(InvocationRequest(_a2a_message()))
    second = await handler.send_message(InvocationRequest(_a2a_message()))

    assert timed_out.result is None and "on time" in timed_out.error.message
    assert [part["text"] for part in second.result.parts] == [f"{servers}\n\nSecond answer."]


async def test_streamed_block_before_a_later_tool_call_is_its_own_message_live_and_stored(chat):
    """Streaming sends the text before a tool call as its own message and stores it as a partial
    update. The surface is delivered there, so the final message gets nothing added."""
    agent = _streaming_agent(_render(), _suggest(f"{BLOCK}\n{INTRO}"), _call(CLOSING))

    texts, _, last = await _stream(agent)

    assert list(texts.values()) == [f"{BLOCK}\n{INTRO}", CLOSING]
    assert last["status"]["state"] == "completed"
    narration_id, final_id = texts
    assert (narration_id, "partial_update", f"{BLOCK}\n{INTRO}", None) in _persisted(chat)
    assert _finals(chat) == [(final_id, "final", CLOSING, CHIPS)]


async def test_streamed_block_in_the_final_message_is_delivered_once(chat):
    reply = f"{INTRO}\n\n{BLOCK}\n\n{CLOSING}"
    agent = _streaming_agent(_render(), _suggest(), _call(reply))

    texts, _, _ = await _stream(agent)

    assert list(texts.values()) == [reply]
    assert [(kind, text, chips) for _, kind, text, chips in _persisted(chat) if "```atx-a2ui" in text] == [
        ("final", reply, CHIPS)
    ]


async def test_streamed_reply_gets_a_surface_that_no_streamed_text_holds(chat):
    """The reply text is on the stream when the turn ends, so the block follows it, in the same
    message, live and stored."""
    agent = _streaming_agent(_render(), _suggest(), _call(CLOSING))

    texts, kinds, last = await _stream(agent)

    assert list(texts.values()) == [f"{CLOSING}\n\n{BLOCK}"]
    assert last["status"]["state"] == "completed"
    assert _finals(chat) == [(*texts, "final", f"{CLOSING}\n\n{BLOCK}", CHIPS)]
    assert kinds[-6:] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "INTERACTION",
        "RUN_FINISHED",
    ]


async def test_streamed_surfaces_follow_the_reply_in_render_order(chat):
    servers = _block("servers", "web-01")
    agent = _streaming_agent(_render("servers", "web-01"), _render(), _call(CLOSING))

    texts, _, _ = await _stream(agent)

    assert list(texts.values()) == [f"{CLOSING}\n\n{servers}\n\n{BLOCK}"]
    assert _finals(chat) == [(*texts, "final", f"{CLOSING}\n\n{servers}\n\n{BLOCK}", None)]


async def test_streamed_surface_rendered_again_after_its_block_was_sent_follows_the_reply(chat):
    latest = _block("inventory", "payments-api", "ledger-svc")
    agent = _streaming_agent(_render(), _render("inventory", "payments-api", "ledger-svc", text=BLOCK), _call(CLOSING))

    texts, _, _ = await _stream(agent)

    assert list(texts.values()) == [BLOCK, f"{CLOSING}\n\n{latest}"]


async def test_streamed_turn_with_no_reply_text_delivers_the_block_as_the_reply(chat):
    """The block is a message of its own: the text before the tool call keeps its message."""
    agent = _streaming_agent(_render(), _suggest("One moment."), _call())

    texts, kinds, last = await _stream(agent)

    assert list(texts.values()) == ["One moment.", BLOCK]
    assert last["status"]["state"] == "completed"
    assert _finals(chat) == [(list(texts)[1], "final", BLOCK, CHIPS)]
    assert kinds[-5:] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "INTERACTION",
        "RUN_FINISHED",
    ]


async def test_streamed_forced_stop_answer_gets_the_missing_block(chat):
    agent = _streaming_agent(_render(), _call(tool="finish"), tools=[finish])

    texts, _, last = await _stream(agent)

    assert list(texts.values()) == [f"Forced answer.\n\n{BLOCK}"]
    assert last["status"]["state"] == "completed"
    assert _finals(chat) == [(*texts, "final", f"Forced answer.\n\n{BLOCK}", None)]


@pytest.mark.parametrize("stop_reason", ["guardrail_intervened", "content_filtered"])
async def test_streamed_refusal_delivers_no_surface(chat, stop_reason):
    agent = _streaming_agent(_render(), _call("I can't help with that.", stop_reason=stop_reason))

    texts, _, last = await _stream(agent)

    assert list(texts.values()) == ["I can't help with that."]
    assert last["status"]["state"] == "completed"
    assert _finals(chat) == [(*texts, "final", "I can't help with that.", None)]


async def test_streamed_turn_that_fails_delivers_no_surface_and_leaves_none_for_the_next_turn(chat):
    servers = _block("servers", "web-01")
    agent = _streaming_agent(
        _render(), [RuntimeError("model failure")], _render("servers", "web-01"), _call("Second answer.")
    )

    failed_texts, _, failed = await _stream(agent)
    texts, _, last = await _stream(agent)

    assert failed["status"]["state"] == "failed" and failed_texts == {}
    assert last["status"]["state"] == "completed"
    assert list(texts.values()) == [f"Second answer.\n\n{servers}"]


async def test_send_turn_and_streaming_turn_at_the_same_time_each_get_their_own_surface(chat):
    """A streaming turn renders a surface while a message/send turn is between its render and its reply."""
    send_rendered, stream_rendered = asyncio.Event(), asyncio.Event()

    async def after_the_send_turn_rendered():
        send_rendered.set()
        await stream_rendered.wait()

    async def after_the_streaming_turn_rendered():
        stream_rendered.set()

    # Each agent is made in the task that runs its turn, as in the server: an agent keeps its
    # conversation in a ContextVar, so two agents made in one task would share one history.
    async def send_turn():
        return await _send(_agent(_render("alpha", "alpha"), [after_the_send_turn_rendered, *_call(CLOSING)]))

    async def streaming_turn():
        agent = _streaming_agent(
            [send_rendered.wait, *_render("beta", "beta")], [after_the_streaming_turn_rendered, *_call(CLOSING)]
        )
        return await _stream(agent, "ctx-b")

    (response,), (texts, _, last) = await asyncio.wait_for(asyncio.gather(send_turn(), streaming_turn()), timeout=10)

    assert last["status"]["state"] == "completed"
    assert response.message == f"{_block('alpha', 'alpha')}\n\n{CLOSING}"
    assert list(texts.values()) == [f"{CLOSING}\n\n{_block('beta', 'beta')}"]


async def test_streaming_turns_at_the_same_time_each_get_their_own_surface(chat):
    """The second turn starts after the first one rendered, and ends before the first one writes its reply."""
    first_rendered, second_ended = asyncio.Event(), asyncio.Event()

    async def after_the_first_turn_rendered():
        first_rendered.set()
        await second_ended.wait()

    async def first_turn():
        agent = _streaming_agent(_render("alpha", "alpha"), [after_the_first_turn_rendered, *_call(CLOSING)])
        return await _stream(agent, "ctx-a")

    async def second_turn():
        agent = _streaming_agent([first_rendered.wait, *_render("beta", "beta")], _call("Second answer."))
        try:
            return await _stream(agent, "ctx-b")
        finally:
            second_ended.set()

    (first, _, first_last), (second, _, second_last) = await asyncio.wait_for(
        asyncio.gather(first_turn(), second_turn()), timeout=10
    )

    assert first_last["status"]["state"] == second_last["status"]["state"] == "completed"
    assert list(first.values()) == [f"{CLOSING}\n\n{_block('alpha', 'alpha')}"]
    assert list(second.values()) == [f"Second answer.\n\n{_block('beta', 'beta')}"]
