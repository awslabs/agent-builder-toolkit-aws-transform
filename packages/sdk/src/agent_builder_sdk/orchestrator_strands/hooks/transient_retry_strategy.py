# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Model retry strategy that also retries transient model failures, and ends a user turn that
still fails with a note telling the user how to continue."""

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Optional, Sequence

from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from strands import ModelRetryStrategy
from strands.hooks import AfterModelCallEvent, BeforeModelCallEvent, HookRegistry
from strands.types.exceptions import ModelThrottledException
from urllib3.exceptions import ProtocolError
from urllib3.exceptions import ReadTimeoutError as StreamReadTimeoutError
from urllib3.exceptions import SSLError as StreamSSLError

from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_type,
    turn_deadline,
    turn_error_note,
)

if TYPE_CHECKING:
    from agent_builder_sdk.streaming import StreamState

logger = logging.getLogger(__name__)

RESUME_NOTE = (
    "The model didn't answer, so I stopped here. Nothing was lost: reply \"Continue\" and I'll "
    "pick up from this step."
)
RESUME_SUGGESTION = "Continue"

# Time a retry leaves free before the turn's deadline, for the reply to reach the user.
_DEADLINE_MARGIN_SECONDS = 5.0

# A timeout or a dropped connection while the response stream is read reaches the caller as
# urllib3's own exception; botocore wraps only the failures of the initial request.
_TRANSIENT_CONNECTION_ERRORS = (
    ReadTimeoutError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ConnectionClosedError,
    StreamReadTimeoutError,
    ProtocolError,
    StreamSSLError,
)
# Bedrock error codes, compared lower-cased: errors raised mid-stream arrive camelCased.
_TRANSIENT_ERROR_CODES = frozenset(
    {
        "serviceunavailableexception",
        "internalserverexception",
        "modelnotreadyexception",
        "modelstreamerrorexception",
        "modeltimeoutexception",
    }
)


def is_transient(exception: BaseException) -> bool:
    """Whether ``exception`` is a connection failure or a Bedrock-side failure (one of the codes
    above, or any HTTP 5xx) that a later call may not repeat."""
    if isinstance(exception, _TRANSIENT_CONNECTION_ERRORS):
        return True
    if not isinstance(exception, ClientError):
        return False
    response = exception.response if isinstance(exception.response, dict) else {}
    error = response.get("Error")
    code = error.get("Code") if isinstance(error, dict) else None
    if isinstance(code, str) and code.lower() in _TRANSIENT_ERROR_CODES:
        return True
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return isinstance(status, int) and 500 <= status < 600


class TransientRetryStrategy(ModelRetryStrategy):
    """Strands' throttling retry, plus a short retry budget for transient model failures.

    Throttling (``ModelThrottledException``) keeps the inherited schedule. A transient failure
    (``is_transient``) gets at most ``transient_attempts`` model calls in total; before retry ``n``
    the strategy waits ``transient_delays[n - 1]`` seconds (the last delay repeats), jittered to
    between 0.5 and 1.5 times that value. A transient retry is not started when:

    - output of the failed call already reached a streaming client, or
    - the wait plus a call as long as the failed one would not end 5 s before the turn's
      deadline (``StreamState.turn_deadline`` on a streamed turn, ``turn_deadline`` on a queued
      user turn). A turn without a deadline is bounded by the attempt budget only.

    Other failures, such as validation, access or context-window errors, are not retried. When a
    throttled or transient failure ends a user turn, the strategy fills the turn's
    ``TurnErrorNote`` with ``RESUME_NOTE`` and a ``RESUME_SUGGESTION`` chip, which the code that
    delivers the turn's reply shows in place of the error. The exception still propagates.

    The retry state is per turn, so each agent needs its own instance.
    """

    def __init__(
        self,
        *,
        transient_attempts: int = 3,
        transient_delays: Sequence[float] = (5.0, 10.0),
        **kwargs: Any,
    ) -> None:
        """Initialize the strategy.

        Args:
            transient_attempts: Model calls allowed for one run of transient failures, the first
                call included; at least 1.
            transient_delays: Base waits in seconds before each transient retry; at least one,
                none negative.
            **kwargs: Passed to ``ModelRetryStrategy`` (``max_attempts``, ``initial_delay``,
                ``max_delay``); they apply to throttling.
        """
        super().__init__(**kwargs)
        if transient_attempts < 1:
            raise ValueError("transient_attempts must be at least 1")
        if not transient_delays or min(transient_delays) < 0:
            raise ValueError("transient_delays must hold at least one delay, none negative")
        self._transient_attempts = transient_attempts
        self._transient_delays = tuple(transient_delays)
        self._transient_attempt = 0
        self._attempt_started: Optional[float] = None

    def is_retryable(self, exception: Exception) -> bool:
        return super().is_retryable(exception) or is_transient(exception)

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        super().register_hooks(registry, **kwargs)
        registry.add_callback(BeforeModelCallEvent, self._on_before_model_call)

    def _on_before_model_call(self, event: BeforeModelCallEvent) -> None:
        self._attempt_started = time.monotonic()
        stream_state: Optional["StreamState"] = event.invocation_state.get("stream_state")
        if stream_state is not None:
            stream_state.content_streamed = False

    def _reset_retry_state(self) -> None:
        super()._reset_retry_state()
        self._transient_attempt = 0

    async def _handle_after_model_call(self, event: AfterModelCallEvent) -> None:
        exception = event.exception
        if event.retry or exception is None or not self.is_retryable(exception):
            await super()._handle_after_model_call(event)
            return
        if isinstance(exception, ModelThrottledException):
            await super()._handle_after_model_call(event)
            if event.retry:
                logger.warning(
                    "Model call throttled (%s); retry %d of %d",
                    exception,
                    self._current_attempt,
                    self._max_attempts - 1,
                )
        else:
            await self._retry_transient(event, exception)
        if not event.retry:
            logger.error(
                "Model call failed (%s: %s); ending the turn", type(exception).__name__, exception
            )
            self._leave_resume_note(event, exception)

    async def _retry_transient(self, event: AfterModelCallEvent, exception: Exception) -> None:
        # Strands yields this throttle event after every failed call; only the inherited handler,
        # which this path skips, clears it.
        self._backwards_compatible_event_to_yield = None
        stream_state: Optional["StreamState"] = event.invocation_state.get("stream_state")
        if stream_state is not None and stream_state.content_streamed:
            logger.warning(
                "Model call failed (%s: %s) after its output reached the client; not retried",
                type(exception).__name__,
                exception,
            )
            return
        self._transient_attempt += 1
        if self._transient_attempt >= self._transient_attempts:
            return
        delay = self._transient_delays[min(self._transient_attempt, len(self._transient_delays)) - 1]
        wait = delay * random.uniform(0.5, 1.5)
        attempt_seconds = (
            time.monotonic() - self._attempt_started if self._attempt_started is not None else 0.0
        )
        deadline = stream_state.turn_deadline if stream_state is not None else turn_deadline.get()
        if deadline is not None:
            left = deadline - time.monotonic()
            if wait + attempt_seconds + _DEADLINE_MARGIN_SECONDS > left:
                logger.warning(
                    "Model call not retried: a retry needs about %.0fs and the turn ends in %.0fs",
                    wait + attempt_seconds,
                    max(0.0, left),
                )
                return
        logger.warning(
            "Model call failed (%s: %s); retry %d of %d in %.1fs",
            type(exception).__name__,
            exception,
            self._transient_attempt,
            self._transient_attempts - 1,
            wait,
        )
        await asyncio.sleep(wait)
        event.retry = True

    @staticmethod
    def _leave_resume_note(event: AfterModelCallEvent, exception: Exception) -> None:
        source = conversation_source_type.get(None)
        if source is not MessageSourceType.USER:
            logger.info("Turn from a %s source ended; no resume note", source)
            return
        stream_state: Optional["StreamState"] = event.invocation_state.get("stream_state")
        note = stream_state.error_note if stream_state is not None else turn_error_note.get()
        if note is None:
            logger.warning("No reply is delivered for this turn; no resume note")
            return
        note.text = RESUME_NOTE
        note.suggestions = [RESUME_SUGGESTION]
        note.exception = exception
