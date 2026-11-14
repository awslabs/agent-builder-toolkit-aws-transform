# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
from typing import Any

from strands.hooks import (
    AfterModelCallEvent,
    BeforeInvocationEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)
from strands.types.content import Message, Messages

from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_type,
)

# HookOrder is strands >= 1.43.
try:
    from strands.hooks import HookOrder  # type: ignore[attr-defined, unused-ignore]

    _RUN_LATE: dict[str, Any] = {"order": HookOrder.DEFAULT + 100}
except ImportError:
    _RUN_LATE = {}

logger = logging.getLogger(__name__)

BLANK_REPLY_CONTINUATION_MARKER = "blank_reply_continuation"
"""Key set in ``metadata.custom`` of the continuation message (metadata never reaches the model).
``MessageAddedEvent`` hooks that treat user text as input should skip messages carrying it."""

# Strands shows the model this text in place of an empty assistant message from history; a model
# that copies it back has still written nothing.
_BLANK_TEXT_SENTINEL = "[blank text]"

_CONTINUATION_TEXT = (
    "Your last response was empty, so nothing has reached the user. Write your reply to the user "
    "now as your final message, in the language of the conversation, based on the work and tool "
    "results above. If you wrote it earlier in this turn, write it again in full: only this "
    "message is delivered. Do not call any tools, and do not mention this note."
)

_STATE_KEY = "_blank_reply_continuation"

_ANSWER_MARKER = "blank_reply_continuation_answer"


class BlankReplyHookProvider(HookProvider):
    """Ask the model once more for its reply when it ends a turn empty right after tool results.

    A model that writes its reply in the same message as a trailing tool call can have nothing left
    to say when Strands calls it again with the tool result, so the turn delivers nothing.
    Re-sending the same request gets the same empty answer; the documented remedy is a
    continuation prompt in a new user message
    (https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons).

    The continuation reaches the conversation store only once the model answers it, and that answer
    is marked as its answer: the answer's signed thinking was produced with the ask in context, so
    replayed history must keep the ask, and it is never removed. An ask whose call raises (a
    terminal model error, or the turn timing out) is never stored. One stored without its marked
    answer right after it, because something failed between storing the two or the process died
    there, stays in the store; ``drop_unanswered_continuations`` removes it from every history
    ``ConversationHookProvider`` loads, with or without this hook, so it never reaches the model
    again.

    Runs late among ``AfterModelCallEvent`` hooks (a high ``HookOrder``). After Strands'
    ``ModelRetryStrategy``, because a retry requested before the strategy runs makes it skip
    resetting its attempt count, so the continuation would inherit the empty call's throttling
    budget; and after lower-ordered hooks, so one that raises on the answer, or discards it, does
    so before the ask is stored. A message that such a hook stores on that answer lands ahead of
    the ask. Any message stored between the ask and its answer instead makes the ask look
    unanswered, and replay drops it: one that a hook ordered after this one stores on the answer,
    or any message stored before the replacement once such a hook discards the answer. Without
    ``HookOrder`` it registers unordered and accepts all of this.

    Left alone:
    - turns served over message/stream (``stream_state`` in ``invocation_state``): the streaming
      persist hook handles ``AfterModelCallEvent`` first and would consume the turn's suggestion
      chips on the discarded response, so the reply would reach chat without them;
    - turns started by a platform notification, whose replies are never delivered.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._reset)
        registry.add_callback(AfterModelCallEvent, self._continue_if_blank, **_RUN_LATE)

    def _reset(self, event: BeforeInvocationEvent) -> None:
        event.invocation_state.pop(_STATE_KEY, None)
        messages = event.agent.messages
        messages[:] = drop_unanswered_continuations(messages)

    async def _continue_if_blank(self, event: AfterModelCallEvent) -> None:
        state = event.invocation_state
        if "stream_state" in state:
            return
        if conversation_source_type.get(None) is MessageSourceType.NOTIFICATION:
            return

        response = event.stop_response
        pending = state.get(_STATE_KEY)
        if pending is True:
            # A hook ordered after this one can still discard the answer marked when the ask was
            # stored; mark the reply that replaces it while the ask is still unanswered.
            if response is not None and not event.retry:
                for message in reversed(event.agent.messages):
                    if message["role"] != "user":
                        break
                    if _is_continuation(message):
                        _mark_as_answer(response.message)
                        break
            return
        if pending is not None:
            if response is None or event.retry:
                # The call raised, or an earlier hook discarded its answer. Leave the ask in place:
                # a retry is still the continuation, and without HookOrder this runs before the
                # retry strategy has decided whether to retry. _reset drops an unanswered leftover.
                return
            state[_STATE_KEY] = True
            await event.agent.hooks.invoke_callbacks_async(
                MessageAddedEvent(agent=event.agent, message=pending)
            )
            _mark_as_answer(response.message)
            if response.stop_reason == "tool_use":
                logger.warning("Model called tools in reply to the blank-reply continuation")
            elif _is_blank(response.message):
                logger.warning("Model returned an empty reply again after the continuation")
            return

        if response is None or event.retry or response.stop_reason != "end_turn":
            return
        if not _is_blank(response.message) or not _ends_with_tool_results(event.agent.messages):
            return

        continuation: Message = {  # type: ignore[typeddict-unknown-key, unused-ignore]
            "role": "user",
            "content": [{"text": _CONTINUATION_TEXT}],
            "metadata": {"custom": {BLANK_REPLY_CONTINUATION_MARKER: True}},
        }
        event.agent.messages.append(continuation)
        state[_STATE_KEY] = continuation
        event.retry = True
        logger.info("Model returned an empty reply after tool results; asking once for the reply")


def drop_unanswered_continuations(messages: Messages) -> Messages:
    """Applied on every history load, so it must not depend on this hook being registered."""
    return [
        m
        for m, after in zip(messages, [*messages[1:], None])
        if not _is_continuation(m) or _is_answer(after)
    ]


def _is_continuation(message: Message) -> bool:
    return _has_marker(message, BLANK_REPLY_CONTINUATION_MARKER)


def _is_answer(message: Message | None) -> bool:
    return message is not None and _has_marker(message, _ANSWER_MARKER)


def _has_marker(message: Message, key: str) -> bool:
    metadata = message.get("metadata") or {}
    custom = metadata.get("custom") or {}  # type: ignore[attr-defined, unused-ignore]
    return bool(custom.get(key))


def _mark_as_answer(message: Any) -> None:
    message.setdefault("metadata", {}).setdefault("custom", {})[_ANSWER_MARKER] = True


def _is_blank(message: Message) -> bool:
    for block in message.get("content") or []:
        if "reasoningContent" in block:
            continue
        text = block.get("text")
        if text is None or text.strip() not in ("", _BLANK_TEXT_SENTINEL):
            return False
    return True


def _ends_with_tool_results(messages: Messages) -> bool:
    if not messages or messages[-1]["role"] != "user":
        return False
    content = messages[-1]["content"]
    return bool(content) and all("toolResult" in block for block in content)
