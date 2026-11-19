# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Queue-based message processor for handling tasks from a request queue.

This module provides a RequestHandler implementation that integrates
with the request queue system, allowing the agent to process tasks from
a queue and store responses for later retrieval.
"""

import asyncio
import logging
import time
from contextvars import Token
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from strands.agent import AgentResult
from structlog.contextvars import bound_contextvars

from ..constants import (
    DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS,
    DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS,
)
from ..custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from ..interfaces import AnyBaseAgent
from ..message_queue import QueueRequest, QueueResponse, RequestQueue, RequestStatus, ResponseStore
from ..orchestrator_strands.conversation.constants import MessageSourceType, classify_source
from ..orchestrator_strands.conversation.repository import (
    TurnErrorNote,
    turn_deadline,
    turn_error_note,
)
from ..util.suggestions_manager import clear_suggestions
from ..utils import (
    A2A_CHAT_SUGGESTIONS_EXT,
    describe_agent_result,
    extract_text_from_strands_agent_response,
)
from .context import RequestContext
from .interface import RequestHandler

logger = logging.getLogger(__name__)


class QueueRequestHandler(RequestHandler):
    """
    Message processor that handles tasks from a queue.

    This processor integrates with the request queue system to:
    1. Receive messages from the request queue
    2. Process them through the agent
    3. Store responses in the response store
    """

    def __init__(
        self,
        request_queue: RequestQueue,
        response_store: ResponseStore,
        timeout: float = DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS,
        delayed_timeout: float = DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS,
    ):
        """
        Initialize the queue message processor.

        Args:
            request_queue: QueueRequest queue to receive messages from
            response_store: Response store to save processed results
            timeout: Seconds the server waits for a reply before it acknowledges the request
            delayed_timeout: Seconds after that acknowledgement during which the server still
                delivers the reply. A user turn runs with ``turn_deadline`` set ``delayed_timeout``
                seconds after the request's arrival (``timeout`` when the request has no sender
                to deliver a late reply to), so hooks can skip work that would end after it. The
                deadline leaves out ``timeout`` because an extension handler can acknowledge the
                request at once, which starts the delayed wait at arrival.
        """
        self.request_queue = request_queue
        self.response_store = response_store
        self.timeout = timeout
        self.delayed_timeout = delayed_timeout
        self._current_request: Optional[QueueRequest] = None

    async def receive_request(self) -> Optional[Dict[str, Any]]:
        """
        Receive a request from the request queue.

        Returns:
            Dict containing the request data and context, or None if no message available
        """
        try:
            # Get next request from queue (with timeout to avoid blocking forever)
            request = await self.request_queue.dequeue(timeout=1.0)  # keep returning None

            if request is None:
                return None

            self._current_request = request
            logger.info(
                "Received request %s from queue",
                request.request_id,
                extra={
                    "queue.request.id": request.request_id,
                    "transaction.id": request.context.get("transaction_id"),
                },
            )

            # Convert request to message format expected by agent
            return {
                "request_id": request.request_id,
                "message": request.message,
                "context": RequestContext(
                    context_id=request.context.get("context_id"),
                    user_id=request.context.get("user_id"),
                    agent_instance_id=request.context.get("agent_instance_id"),
                    sender=request.context.get("sender", "queue"),
                    task_id=request.context.get("task_id"),
                ),
                "priority": request.priority.value,
                "created_at": request.created_at.isoformat(),
                "transaction_id": request.context.get("transaction_id"),
            }
        except Exception as e:
            logger.error(f"Error receiving request from queue: {e}")
            return None

    async def store_response(
        self,
        message: str,
        recipient_id: Optional[str] = None,
        suggestions: Optional[List[str]] = None,
    ) -> bool:
        """
        Store response for the current request.

        Args:
            message: The response message content
            recipient_id: Not used in queue processor (responses are stored by request ID)
            suggestions: Chat suggestion chips carried on this response only, so a reply that
                nobody reads leaves no chip behind for the next one

        Returns:
            True if response was stored successfully, False otherwise
        """
        if self._current_request is None:
            logger.error("No current request to send response for")
            return False

        try:
            # Create response object
            response = QueueResponse(
                request_id=self._current_request.request_id,
                context_id=self._current_request.context.get("context_id"),
                task_id=self._current_request.context.get("task_id"),
                message=message,
                status=RequestStatus.COMPLETED,
                metadata={A2A_CHAT_SUGGESTIONS_EXT: list(suggestions)} if suggestions else {},
                extensions=[A2A_CHAT_SUGGESTIONS_EXT] if suggestions else [],
            )

            # Store response
            success = await self.response_store.store_response(response)

            if success:
                # Update request status to completed
                await self.request_queue.update_request_status(
                    self._current_request.request_id, RequestStatus.COMPLETED
                )
                logger.info(f"Stored response for request {self._current_request.request_id}")
            else:
                # Update request status to failed
                await self.request_queue.update_request_status(
                    self._current_request.request_id,
                    RequestStatus.FAILED,
                    "Failed to store response",
                )
                logger.error(
                    f"Failed to store response for request {self._current_request.request_id}"
                )

            # Clear current request
            self._current_request = None
            return success

        except Exception as e:
            logger.error(f"Error sending message: {e}")

            # Update request status to failed
            if self._current_request:
                await self.request_queue.update_request_status(
                    self._current_request.request_id, RequestStatus.FAILED, str(e)
                )
                self._current_request = None

            return False

    async def handle_request_error(self, error: Exception) -> bool:
        """
        Handle an error that occurred while processing the current request.

        Args:
            error: The error that occurred

        Returns:
            True if error was handled successfully, False otherwise
        """
        if self._current_request is None:
            return False

        try:
            error_message = f"Error processing request: {str(error)}"
            # Create error response (no retries currently implemented)
            error_response = QueueResponse(
                request_id=self._current_request.request_id,
                context_id=self._current_request.context.get("context_id"),
                task_id=self._current_request.context.get("task_id"),
                message=error_message,
                status=RequestStatus.FAILED,
                error_message=str(error),
            )

            # Store error response
            await self.response_store.store_response(error_response)

            # Update request status
            await self.request_queue.update_request_status(
                self._current_request.request_id, RequestStatus.FAILED, str(error)
            )

            logger.error(f"Handled error for request {self._current_request.request_id}: {error}")
            self._current_request = None
            return True

        except Exception as e:
            logger.error(f"Error handling request error: {e}")
            return False

    def _reply_deadline(self, created_at: Optional[str], has_sender: bool) -> float:
        """time.monotonic() value at which the reply window of a request that arrived at
        ``created_at`` (an ISO 8601 time with offset; None for now) ends."""
        arrival = datetime.fromisoformat(created_at).timestamp() if created_at else time.time()
        window = self.delayed_timeout if has_sender else self.timeout
        return time.monotonic() + (arrival + window - time.time())

    async def start_processing(
        self,
        get_agent_func: Callable[[], Awaitable[AnyBaseAgent[ProcessMessageRequest, AgentResult]]],
        checkpoint_callback_provider: Optional[Callable[[], Optional[Callable]]] = None,
    ) -> None:
        """Start processing messages from the queue."""
        logger.info("Starting queue message processing...")
        log_context = {}
        deadline_token: Optional[Token[Optional[float]]] = None
        note_token: Optional[Token[Optional[TurnErrorNote]]] = None

        try:
            while True:
                try:
                    # Receive message from queue
                    message_data = await self.receive_request()
                    if message_data is None:
                        continue

                    log_context = {
                        "queue.request.id": message_data["request_id"],
                        "transaction.id": message_data["transaction_id"],
                    }

                    with bound_contextvars(**log_context):
                        logger.info(f"Processing request {message_data['request_id']}")

                        # Get ready agent (waits if needed)
                        agent = await get_agent_func()

                        logger.info("Fetched agent")
                        # Convert RequestContext to ConversationContext
                        req_context = message_data["context"]
                        conv_context = ConversationContext(
                            user_id=req_context.user_id,
                            agent_instance_id=req_context.agent_instance_id,
                            a2a_context=A2AContext(
                                context_id=req_context.context_id, task_id=req_context.task_id
                            ),
                        )

                        if classify_source(conv_context)[1] is MessageSourceType.USER:
                            deadline_token = turn_deadline.set(
                                self._reply_deadline(
                                    message_data.get("created_at"), bool(req_context.sender)
                                )
                            )
                            note_token = turn_error_note.set(TurnErrorNote())

                        # Process the message in thread pool to avoid blocking event loop
                        request = ProcessMessageRequest(message_data["message"], conv_context)
                        if hasattr(agent, "process_message_async"):
                            result = await agent.process_message_async(request)
                        else:
                            result = await asyncio.to_thread(agent.process_message, request)

                        logger.info("Agent result: %s", describe_agent_result(result))

                        # Handle checkpointing after successful processing
                        if checkpoint_callback_provider:
                            callback = checkpoint_callback_provider()
                            if callback:
                                logger.info("Invoking checkpoint_callback")
                                callback()

                        # Extract and store response
                        extracted_text = extract_text_from_strands_agent_response(result)
                        # If a tool set force_stop_response, use it directly as the response
                        # (stop_after_response optimization — skip LLM summarization)
                        force_stop_text = (
                            result.state.get("force_stop_response") if result.state else None
                        )
                        if force_stop_text:
                            extracted_text = force_stop_text
                            logger.info("Using force_stop_response as agent result text")
                        elif not extracted_text:
                            logger.info("Agent result text is empty")
                        else:
                            logger.debug("Agent result text: %s", extracted_text)

                        await self.store_response(extracted_text)

                except asyncio.CancelledError:
                    logger.info("Queue processing cancelled", extra=log_context)
                    break
                except Exception as e:
                    with bound_contextvars(**log_context):
                        logger.error(f"Error processing request: {e}")
                        note = turn_error_note.get()
                        if note is not None and note.text is not None and note.explains(e):
                            # Chips a tool left pending belong to a step the model never showed,
                            # and the reply converter would put them in place of the note's chip.
                            clear_suggestions()
                            await self.store_response(note.text, suggestions=note.suggestions)
                        else:
                            await self.handle_request_error(e)
                finally:
                    if note_token is not None:
                        turn_error_note.reset(note_token)
                        note_token = None
                    if deadline_token is not None:
                        turn_deadline.reset(deadline_token)
                        deadline_token = None
                    log_context.clear()

        except Exception as e:
            logger.error(f"Queue processing failed: {e}")

    async def handle_request_timeout(self) -> bool:
        """
        Handle a timeout that occurred while processing the current request.

        Returns:
            True if timeout was handled successfully, False otherwise
        """
        if self._current_request is None:
            return False

        try:
            timeout_message = "QueueRequest processing timed out"
            # Create timeout response
            timeout_response = QueueResponse(
                request_id=self._current_request.request_id,
                context_id=self._current_request.context.get("context_id"),
                message=timeout_message,
                status=RequestStatus.TIMEOUT,
                error_message="Processing timeout exceeded",
            )

            # Store timeout response
            await self.response_store.store_response(timeout_response)

            # Update request status
            await self.request_queue.update_request_status(
                self._current_request.request_id,
                RequestStatus.TIMEOUT,
                "Processing timeout exceeded",
            )

            logger.warning(f"Handled timeout for request {self._current_request.request_id}")
            self._current_request = None
            return True

        except Exception as e:
            logger.error(f"Error handling request timeout: {e}")
            return False

    def get_current_request_id(self) -> Optional[str]:
        """
        Get the ID of the currently processing request.

        Returns:
            QueueRequest ID if there's a current request, None otherwise
        """
        return self._current_request.request_id if self._current_request else None
