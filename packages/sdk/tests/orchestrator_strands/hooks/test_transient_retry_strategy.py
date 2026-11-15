# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
import time
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, Mock, create_autospec, patch

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    EventStreamError,
    ReadTimeoutError,
)
from strands import tool
from strands.models import Model
from strands.types.exceptions import ContextWindowOverflowException, ModelThrottledException
from urllib3.exceptions import ProtocolError
from urllib3.exceptions import ReadTimeoutError as StreamReadTimeoutError
from urllib3.exceptions import SSLError as StreamSSLError

from agent_builder_sdk.custom_types.orchestrator_agent_types import A2AContext
from agent_builder_sdk.message_queue import (
    QueueRequest,
    QueueResponse,
    RequestQueue,
    RequestStatus,
    ResponseStore,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
    AsyncBaseOrchestrator,
    BaseOrchestrator,
)
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    TurnErrorNote,
    conversation_source_type,
    turn_deadline,
    turn_error_note,
)
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider
from agent_builder_sdk.orchestrator_strands.hooks.blank_reply_hook_provider import (
    BLANK_REPLY_CONTINUATION_MARKER,
    BlankReplyHookProvider,
)
from agent_builder_sdk.orchestrator_strands.hooks.transient_retry_strategy import (
    RESUME_NOTE,
    RESUME_SUGGESTION,
    TransientRetryStrategy,
    is_transient,
)
from agent_builder_sdk.request_handler.queue_handler import QueueRequestHandler
from agent_builder_sdk.streaming.a2a_agui_adapter import StreamState
from agent_builder_sdk.util.suggestions_manager import (
    clear_suggestions,
    get_and_consume_suggestions,
)
from agent_builder_sdk.utils import extract_text_from_strands_agent_response

MODULE = "agent_builder_sdk.orchestrator_strands.hooks.transient_retry_strategy"

_CONTEXT = A2AContext(context_id="ctx-1", task_id=None)


def _text(text: str, stop_reason: str = "end_turn") -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": stop_reason}},
    ]


def _text_and_tool(text: str) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": "record_note"}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps({"note": "n"})}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
    ]


def _client_error(code: Any, status: Any, cls: type = ClientError) -> ClientError:
    error: ClientError = cls(
        {"Error": {"Code": code, "Message": "m"}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "ConverseStream",
    )
    return error


def _broken_response(response: Any) -> ClientError:
    error = _client_error("serviceUnavailableException", 503)
    error.response = response
    return error


def _read_timeout() -> ReadTimeoutError:
    return ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com")


@tool
def record_note(note: str) -> str:
    """Record a note."""
    return "{}"


def _orchestrator(
    scripts: list[Any],
    cls: type = AsyncBaseOrchestrator,
    hooks: Optional[list[Any]] = None,
    **strategy_kwargs: Any,
) -> Any:
    """An orchestrator whose model plays one script per call: an exception raises at once; a list
    yields its events, raising an exception entry and calling a callable entry in place."""
    strategy_kwargs.setdefault("initial_delay", 0)
    strategy_kwargs.setdefault("transient_delays", (0,))
    orchestrator = cls(
        "",
        custom_tools=[record_note],
        hooks=hooks,
        retry_strategy=TransientRetryStrategy(**strategy_kwargs),
    )
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = create_autospec(Model, spec_set=True, instance=True)
    responses = iter(scripts)

    async def stream(script: Any) -> AsyncGenerator[dict[str, Any], None]:
        if isinstance(script, BaseException):
            raise script
        for event in script:
            if isinstance(event, BaseException):
                raise event
            if callable(event):
                event()
                continue
            yield event

    orchestrator.model.stream.side_effect = lambda *args, **kwargs: stream(next(responses))
    orchestrator.hooks.add_hook(BlankReplyHookProvider())
    return orchestrator


@pytest.fixture
def note() -> Iterator[TurnErrorNote]:
    """The empty note a queue worker hands a user turn whose reply it delivers."""
    holder = TurnErrorNote()
    token = turn_error_note.set(holder)
    yield holder
    turn_error_note.reset(token)


@pytest.fixture(autouse=True)
def user_turn() -> Iterator[None]:
    token = conversation_source_type.set(MessageSourceType.USER)
    yield
    conversation_source_type.reset(token)


@pytest.mark.parametrize(
    "exception",
    [
        _read_timeout(),
        ConnectTimeoutError(endpoint_url="https://x"),
        EndpointConnectionError(endpoint_url="https://x"),
        ConnectionClosedError(endpoint_url="https://x"),
        StreamReadTimeoutError(None, "/model/x/converse-stream", "Read timed out."),
        ProtocolError("Connection broken: IncompleteRead(0 bytes read)"),
        StreamSSLError("EOF occurred in violation of protocol"),
        _client_error("serviceUnavailableException", 503),
        _client_error("ServiceUnavailableException", 503),
        _client_error("internalServerException", 500),
        _client_error("modelNotReadyException", 429),
        _client_error("modelStreamErrorException", 424, EventStreamError),
        _client_error("ModelTimeoutException", 408),
        _client_error("SomethingNew", 502),
    ],
)
def test_transient_failures_are_classified_by_type_or_code(exception: BaseException) -> None:
    assert is_transient(exception)


@pytest.mark.parametrize(
    "exception",
    [
        _client_error("AccessDeniedException", 403),
        _client_error("ValidationException", 400),
        _client_error("ResourceNotFoundException", 404),
        _client_error("throttlingException", 429, EventStreamError),
        ClientError({}, "ConverseStream"),  # type: ignore[arg-type]
        _client_error(503, None),
        _client_error(None, None),
        _client_error(None, "503"),
        _broken_response(None),
        _broken_response("oops"),
        _broken_response({"Error": None}),
        _broken_response({"Error": {"Code": "ThrottlingException"}, "ResponseMetadata": None}),
        ContextWindowOverflowException("too long"),
        ModelThrottledException("slow"),
        RuntimeError("read timed out"),
        asyncio.TimeoutError(),
    ],
)
def test_other_failures_and_malformed_errors_are_not_transient(exception: BaseException) -> None:
    assert not is_transient(exception)


def test_throttling_and_transient_failures_are_retryable() -> None:
    strategy = TransientRetryStrategy()
    assert strategy.is_retryable(ModelThrottledException("slow"))
    assert strategy.is_retryable(_read_timeout())
    assert not strategy.is_retryable(_client_error("AccessDeniedException", 403))


@pytest.mark.parametrize(
    "kwargs",
    [{"transient_delays": ()}, {"transient_delays": (5, -1)}, {"transient_attempts": 0}],
)
def test_invalid_budgets_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TransientRetryStrategy(**kwargs)


@pytest.mark.parametrize(
    "failure",
    [
        _read_timeout(),
        StreamReadTimeoutError(None, "/converse-stream", "Read timed out."),
        _client_error("ServiceUnavailableException", 503),
    ],
)
async def test_transient_failure_once_is_retried_and_the_answer_delivered(
    note: TurnErrorNote, failure: BaseException
) -> None:
    orchestrator = _orchestrator([failure, _text("Done.")])

    result = await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 2
    assert note.text is None


async def test_transient_budget_spent_leaves_the_note_and_reraises(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator([_read_timeout()] * 3)

    with pytest.raises(ReadTimeoutError) as raised:
        await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert orchestrator.model.stream.call_count == 3
    assert (note.text, note.suggestions) == (RESUME_NOTE, [RESUME_SUGGESTION])
    assert note.exception is raised.value
    assert all(message["role"] == "user" for message in orchestrator.messages)
    assert RESUME_NOTE not in str(orchestrator.messages)
    assert BLANK_REPLY_CONTINUATION_MARKER not in str(orchestrator.messages)


async def test_transient_delays_apply_in_order_and_the_last_repeats(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator(
        [_read_timeout()] * 4, transient_attempts=4, transient_delays=(5, 10)
    )
    with patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock) as sleep, patch(
        f"{MODULE}.random.uniform", return_value=1.0
    ):
        with pytest.raises(ReadTimeoutError):
            await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert [call.args[0] for call in sleep.await_args_list] == [5, 10, 10]


async def test_transient_waits_are_jittered_within_half_the_delay(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator([_read_timeout()] * 3, transient_delays=(10,))
    with patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(ReadTimeoutError):
            await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    waits = [call.args[0] for call in sleep.await_args_list]
    assert len(waits) == 2 and all(5 <= wait <= 15 for wait in waits)


async def test_cancellation_during_a_retry_wait_propagates_at_once(note: TurnErrorNote) -> None:
    waiting = asyncio.Event()

    async def wait_forever(seconds: float) -> None:
        waiting.set()
        await asyncio.Event().wait()

    orchestrator = _orchestrator([_read_timeout(), _text("Done.")], transient_delays=(60,))
    with patch(f"{MODULE}.asyncio.sleep", side_effect=wait_forever):
        turn = asyncio.create_task(
            orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})
        )
        await asyncio.wait_for(waiting.wait(), 5)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(turn, 1)

    assert orchestrator.model.stream.call_count == 1
    assert note.text is None


async def test_retry_requested_by_an_earlier_hook_is_left_alone() -> None:
    strategy = TransientRetryStrategy()
    strategy._backwards_compatible_event_to_yield = Mock()
    event = Mock(retry=True, exception=_read_timeout(), stop_response=None, invocation_state={})

    await strategy._handle_after_model_call(event)

    assert event.retry is True
    assert strategy._backwards_compatible_event_to_yield is None


async def test_transient_budget_resets_after_a_successful_call_and_per_turn(
    note: TurnErrorNote,
) -> None:
    orchestrator = _orchestrator(
        [
            _read_timeout(),
            _read_timeout(),
            _text("One."),
            _read_timeout(),
            _read_timeout(),
            _text("Two."),
        ]
    )

    first = await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})
    second = await orchestrator.invoke_async("Again", invocation_state={"a2a_context": _CONTEXT})

    assert extract_text_from_strands_agent_response(first) == "One."
    assert extract_text_from_strands_agent_response(second) == "Two."
    assert note.text is None


def test_reset_retry_state_clears_both_budgets() -> None:
    strategy = TransientRetryStrategy()
    strategy._current_attempt = 2
    strategy._transient_attempt = 1
    strategy._reset_retry_state()
    assert (strategy._current_attempt, strategy._transient_attempt) == (0, 0)


async def test_throttling_keeps_the_inherited_budget(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator([ModelThrottledException("slow")] * 5 + [_text("Done.")])

    result = await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 6
    assert note.text is None


async def test_throttling_budget_spent_leaves_the_note(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator([ModelThrottledException("slow")] * 6)

    with pytest.raises(ModelThrottledException):
        await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert orchestrator.model.stream.call_count == 6
    assert note.text == RESUME_NOTE


async def test_throttling_and_transient_budgets_are_independent(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator(
        [ModelThrottledException("slow")] * 5 + [_read_timeout(), _read_timeout(), _text("Done.")]
    )
    throttle_events: list[float] = []

    def callback_handler(**kwargs: Any) -> None:
        if "event_loop_throttled_delay" in kwargs:
            throttle_events.append(kwargs["event_loop_throttled_delay"])

    orchestrator.callback_handler = callback_handler

    result = await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 8
    assert len(throttle_events) == 5


@pytest.mark.parametrize(
    "failure",
    [
        _client_error("ValidationException", 400),
        _client_error("AccessDeniedException", 403),
        ContextWindowOverflowException("Input is too long for requested model"),
    ],
)
async def test_permanent_errors_are_not_retried_and_get_no_note(
    note: TurnErrorNote, failure: Exception
) -> None:
    orchestrator = _orchestrator([failure, _text("Done.")])

    with pytest.raises(type(failure)):
        await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert orchestrator.model.stream.call_count == 1
    assert note.text is None


async def test_a_guardrail_stop_is_not_retried(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator([_text("Blocked.", stop_reason="guardrail_intervened")])

    result = await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert result.stop_reason == "guardrail_intervened"
    assert orchestrator.model.stream.call_count == 1
    assert note.text is None


@pytest.mark.parametrize("source", [MessageSourceType.NOTIFICATION, MessageSourceType.SUBAGENT])
async def test_only_user_turns_get_the_note(note: TurnErrorNote, source: MessageSourceType) -> None:
    orchestrator = _orchestrator([_read_timeout()] * 3)
    conversation_source_type.set(source)

    with pytest.raises(ReadTimeoutError):
        await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})

    assert note.text is None


async def test_a_turn_whose_reply_nobody_delivers_still_ends_with_the_error() -> None:
    orchestrator = _orchestrator([_read_timeout()] * 3)

    with pytest.raises(ReadTimeoutError):
        await orchestrator.invoke_async("Go")

    assert orchestrator.model.stream.call_count == 3


async def test_streamed_turn_gets_the_note_on_its_stream_state(note: TurnErrorNote) -> None:
    orchestrator = _orchestrator([_read_timeout()] * 3)
    state = StreamState(thread_id="conv-1", context_id="ctx-1")

    with pytest.raises(ReadTimeoutError) as raised:
        await orchestrator.invoke_async(
            "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
        )

    assert (state.error_note.text, state.error_note.suggestions) == (
        RESUME_NOTE,
        [RESUME_SUGGESTION],
    )
    assert state.error_note.explains(raised.value)
    assert note.text is None


async def test_streamed_turn_is_not_retried_once_its_output_reached_the_client() -> None:
    state = StreamState(thread_id="conv-1", context_id="ctx-1")

    def client_got_output() -> None:
        state.content_streamed = True

    orchestrator = _orchestrator([[client_got_output, _read_timeout()], _text("Done.")])

    with pytest.raises(ReadTimeoutError):
        await orchestrator.invoke_async(
            "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
        )

    assert orchestrator.model.stream.call_count == 1
    assert state.error_note.text == RESUME_NOTE


async def test_streamed_turn_is_retried_while_nothing_reached_the_client() -> None:
    orchestrator = _orchestrator([_read_timeout(), _text("Done.")])
    state = StreamState(thread_id="conv-1", context_id="ctx-1")

    result = await orchestrator.invoke_async(
        "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
    )

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 2
    assert state.error_note.text is None


async def test_content_a_relayed_tool_streamed_does_not_block_the_next_calls_retry() -> None:
    orchestrator = _orchestrator([_read_timeout(), _text("Done.")])
    state = StreamState(thread_id="conv-1", context_id="ctx-1")
    state.content_streamed = True

    result = await orchestrator.invoke_async(
        "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
    )

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 2


async def test_throttling_after_streamed_output_keeps_strands_schedule() -> None:
    state = StreamState(thread_id="conv-1", context_id="ctx-1")

    def client_got_output() -> None:
        state.content_streamed = True

    orchestrator = _orchestrator(
        [[client_got_output, ModelThrottledException("slow")], _text("Done.")]
    )

    result = await orchestrator.invoke_async(
        "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
    )

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 2


async def test_transient_retry_whose_wait_would_pass_the_turn_deadline_is_skipped() -> None:
    """The 5 s margin alone fits the 8 s left; the 5 s wait on top of it does not."""
    orchestrator = _orchestrator([_read_timeout(), _text("Done.")], transient_delays=(5,))
    state = StreamState(thread_id="conv-1", context_id="ctx-1")
    state.turn_deadline = time.monotonic() + 8

    with patch(f"{MODULE}.random.uniform", return_value=1.0), patch(
        f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
    ):
        with pytest.raises(ReadTimeoutError):
            await orchestrator.invoke_async(
                "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
            )

    assert orchestrator.model.stream.call_count == 1
    assert state.error_note.text == RESUME_NOTE


@pytest.mark.parametrize("failure", [_read_timeout(), ModelThrottledException("slow")])
async def test_retry_that_fits_the_turn_deadline_proceeds(failure: Exception) -> None:
    orchestrator = _orchestrator([failure, _text("Done.")])
    state = StreamState(thread_id="conv-1", context_id="ctx-1")
    state.turn_deadline = time.monotonic() + 600

    result = await orchestrator.invoke_async(
        "Go", invocation_state={"a2a_context": _CONTEXT, "stream_state": state}
    )

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 2


async def test_deadline_check_counts_the_failed_attempt_duration() -> None:
    strategy = TransientRetryStrategy(transient_delays=(0,))
    state = StreamState(thread_id="conv-1", context_id="ctx-1")
    state.turn_deadline = time.monotonic() + 30
    strategy._attempt_started = time.monotonic() - 100
    event = Mock(
        retry=False,
        exception=_read_timeout(),
        stop_response=None,
        invocation_state={"a2a_context": _CONTEXT, "stream_state": state},
    )

    await strategy._handle_after_model_call(event)

    assert event.retry is False
    assert state.error_note.text == RESUME_NOTE


async def test_queued_turn_transient_retry_that_would_pass_its_deadline_is_skipped(
    note: TurnErrorNote,
) -> None:
    orchestrator = _orchestrator([_read_timeout(), _text("Done.")], transient_delays=(5,))

    with patch(f"{MODULE}.random.uniform", return_value=1.0), patch(
        f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
    ):
        token = turn_deadline.set(time.monotonic() + 8)
        try:
            with pytest.raises(ReadTimeoutError):
                await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})
        finally:
            turn_deadline.reset(token)

    assert orchestrator.model.stream.call_count == 1
    assert note.text == RESUME_NOTE


def _fake_clock() -> tuple[dict[str, float], Callable[[float], Callable[[], None]]]:
    clock = {"now": 1000.0}

    def model_call_takes(seconds: float) -> Callable[[], None]:
        def advance() -> None:
            clock["now"] += seconds

        return advance

    return clock, model_call_takes


async def test_queued_turn_retry_budget_stays_inside_the_reply_window(note: TurnErrorNote) -> None:
    """Attempts that each take 120 s cannot all fit a 300 s window: the second failure ends the
    turn with the note."""
    clock, model_call_takes = _fake_clock()

    async def sleep_advances(seconds: float) -> None:
        clock["now"] += seconds

    orchestrator = _orchestrator(
        [[model_call_takes(120), _read_timeout()]] * 3, transient_delays=(5, 10)
    )
    token = turn_deadline.set(clock["now"] + 300)
    with patch(f"{MODULE}.time") as fake_time, patch(
        f"{MODULE}.random.uniform", return_value=1.5
    ), patch(f"{MODULE}.asyncio.sleep", side_effect=sleep_advances):
        fake_time.monotonic.side_effect = lambda: clock["now"]
        try:
            with pytest.raises(ReadTimeoutError):
                await orchestrator.invoke_async("Go", invocation_state={"a2a_context": _CONTEXT})
        finally:
            turn_deadline.reset(token)

    assert orchestrator.model.stream.call_count == 2
    assert note.text == RESUME_NOTE


@pytest.mark.parametrize("deadline", ["none", "passed"])
async def test_throttling_keeps_strands_budget_whatever_the_turn_deadline(
    note: TurnErrorNote, deadline: str
) -> None:
    """Two 150 s tool steps then a throttle: the throttle is retried on Strands' schedule whether
    the turn has no deadline or its reply window has already passed."""
    clock, model_call_takes = _fake_clock()
    orchestrator = _orchestrator(
        [
            [model_call_takes(150), *_text_and_tool("Step one.")],
            [model_call_takes(150), *_text_and_tool("Step two.")],
            ModelThrottledException("slow"),
            _text("Done."),
        ]
    )
    token = turn_deadline.set(clock["now"] + 300) if deadline == "passed" else None
    with patch(f"{MODULE}.time") as fake_time:
        fake_time.monotonic.side_effect = lambda: clock["now"]
        try:
            result = await orchestrator.invoke_async(
                "Go", invocation_state={"a2a_context": _CONTEXT}
            )
        finally:
            if token is not None:
                turn_deadline.reset(token)

    assert extract_text_from_strands_agent_response(result) == "Done."
    assert orchestrator.model.stream.call_count == 4
    assert note.text is None


def test_sync_orchestrator_turn_honours_the_workers_deadline_and_note() -> None:
    """A sync orchestrator runs its turn on an executor thread that carries the caller's context,
    so the worker's deadline bounds its retries and the note reaches the worker's holder."""
    orchestrator = _orchestrator([_read_timeout()] * 3, cls=BaseOrchestrator)
    holder = TurnErrorNote()
    tokens = (turn_deadline.set(time.monotonic() + 1), turn_error_note.set(holder))
    try:
        with pytest.raises(ReadTimeoutError):
            orchestrator.invoke_with_source(
                "Go", "user-1", MessageSourceType.USER, a2a_context=_CONTEXT
            )
    finally:
        turn_error_note.reset(tokens[1])
        turn_deadline.reset(tokens[0])

    assert orchestrator.model.stream.call_count == 1
    assert (holder.text, holder.suggestions) == (RESUME_NOTE, [RESUME_SUGGESTION])


class _ReplyStore(ResponseStore):
    def __init__(self) -> None:
        self.responses: dict[str, QueueResponse] = {}

    async def store_response(self, response: QueueResponse) -> bool:
        self.responses[response.request_id] = response
        return True

    async def get_response(self, request_id: str) -> Optional[QueueResponse]:
        return self.responses.get(request_id)

    async def delete_response(self, request_id: str) -> bool:
        return self.responses.pop(request_id, None) is not None

    async def list_responses(self, limit: Optional[int] = None) -> list[QueueResponse]:
        return list(self.responses.values())

    async def cleanup_old_responses(self, max_age_hours: int = 24) -> int:
        return 0

    async def health_check(self) -> bool:
        return True


async def _run_queued_turns(orchestrator: Any, *requests: QueueRequest) -> _ReplyStore:
    store = _ReplyStore()
    handler = QueueRequestHandler(
        request_queue=create_autospec(RequestQueue, spec_set=True, instance=True),
        response_store=store,
    )
    handler.request_queue.dequeue.side_effect = [*requests, asyncio.CancelledError()]
    await handler.start_processing(AsyncMock(return_value=orchestrator))
    return store


def _user_request(message: str) -> QueueRequest:
    return QueueRequest(
        message=message, context=dict(context_id="ctx-1", user_id="user-1", sender="ATX_CHAT")
    )


async def test_queued_turn_failing_after_a_tool_call_stores_the_note_as_its_reply() -> None:
    """Strands raises a model error that follows a tool call inside EventLoopException; the queue
    worker still stores the note as the turn's COMPLETED reply, with its chip, never the error."""
    clear_suggestions()
    orchestrator = _orchestrator([_text_and_tool("Working.")] + [_read_timeout()] * 3)
    request = _user_request("Go")

    store = await _run_queued_turns(orchestrator, request)

    response = store.responses[request.request_id]
    assert orchestrator.model.stream.call_count == 4
    assert response.status is RequestStatus.COMPLETED
    assert response.message == RESUME_NOTE
    assert response.error_message is None
    assert get_and_consume_suggestions() == [RESUME_SUGGESTION]


async def test_the_note_never_enters_the_stored_history_or_the_next_prompt(
    tmp_path: Path,
) -> None:
    """The note is a reply to the user only: the stored conversation and the model input of the
    "Continue" turn hold the user's messages and no note."""
    clear_suggestions()
    repository = FileMultiSourceConversationRepository(storage_dir=str(tmp_path))
    orchestrator = _orchestrator(
        [_read_timeout()] * 3 + [_text("Picked up.")],
        hooks=[ConversationHookProvider(repository=repository)],
    )
    first, second = _user_request("Go"), _user_request(RESUME_SUGGESTION)

    store = await _run_queued_turns(orchestrator, first, second)

    assert store.responses[first.request_id].message == RESUME_NOTE
    assert store.responses[second.request_id].message == "Picked up."
    stored = [message.to_message() for message in repository.conversations["USER"]["user-1"]]
    assert [message["role"] for message in stored] == ["user", "user", "assistant"]
    assert RESUME_NOTE not in str(stored)
    continue_prompt = orchestrator.model.stream.call_args_list[-1].args[0]
    assert RESUME_NOTE not in str(continue_prompt)
    clear_suggestions()
