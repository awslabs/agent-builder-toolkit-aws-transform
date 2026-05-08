# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Messages handler for A2A message processing
"""

import asyncio
import json
import logging
import uuid
from typing import Optional, Sequence

from strands.agent import AgentResult
from structlog.contextvars import bound_contextvars

from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.common_types import (
    A2AError,
    A2AErrorCode,
    A2AMessage,
    InvocationRequest,
    MessageSendParams,
)
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus
from agent_builder_sdk.env_var import get_agent_context_from_env
from agent_builder_sdk.extensions.base_extension_handler import BaseExtensionHandler
from agent_builder_sdk.interfaces import AnyBaseAgent
from agent_builder_sdk.message_queue import QueueResponse, QueueService
from agent_builder_sdk.message_queue.interface import RequestPriority
from agent_builder_sdk.task.task_manager import TaskManager
from agent_builder_sdk.utils import (
    convert_queue_response_to_send_message_output,
    convert_subagent_response_to_send_message_output,
    extract_message_info,
    extract_text_from_strands_agent_response,
    process_extension_handlers,
)

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles A2A message processing operations with extension handler support.

    Processes incoming A2A messages through configured extension handlers (e.g., acknowledgment)
    before routing to agent processing. Extension handlers can intercept requests to provide
    immediate responses while allowing background processing to continue.

    Extension Negotiation:
    - Parses extension URIs from incoming message.extensions
    - Matches against supported extension handlers by URI
    - Logs supported extensions that are processed
    - Logs and ignores unsupported extensions
    """

    def __init__(
        self,
        queue: Optional[QueueService] = None,
        agent: Optional[AnyBaseAgent[str, AgentResult]] = None,
        timeout: int = 28,
        delayed_timeout: int = 300,
        extension_handlers: Optional[Sequence[BaseExtensionHandler]] = None,
        task_manager: Optional[TaskManager] = None,
    ):
        """
        Initialize MessageHandler for either queued or direct processing.

        Args:
            queue: QueueService for orchestrator agents (optional, mutually exclusive with agent)
            agent: BaseAgent for direct processing (optional, mutually exclusive with queue)
            timeout: Request timeout in seconds
            delayed_timeout: Extended timeout for delayed responses
            extension_handlers: List of extension handlers for processing A2A extensions (e.g., acknowledgment)
            task_manager: TaskManager for task creation and management (optional, experimental)

        Note:
            Only one of queue or agent should be provided, not both.
        """

        # Validation to prevent both or neither queue or agent being provided
        if queue is not None and agent is not None:
            raise ValueError(
                "Cannot provide both queue and agent - specify only one processing mode"
            )

        if queue is None and agent is None:
            raise ValueError("Must provide either queue or agent for message processing")

        self.queue = queue
        self.agent = agent
        self._timeout = timeout
        self._delayed_timeout = delayed_timeout
        self.extension_handlers = extension_handlers
        self.task_manager = task_manager

    async def send_message(self, request: InvocationRequest) -> SendMessageOutput:
        """Process a message request and return the agent's response."""

        if await self._should_process_task(request):
            return await self._process_task(request)

        # Check if we should create a task instead of processing immediately
        if await self._should_create_task(request):
            return await self._create_task(request)

        if self.agent is not None:
            return await self._process_direct(request, self.agent)

        elif self.queue is not None:
            return await self._process_queued(request, self.queue)

        else:
            logger.error("Neither queue service nor agent available")
            return SendMessageOutput(
                error=A2AError(
                    code=A2AErrorCode.INTERNAL_ERROR, message="No processing capability available"
                )
            )

    async def _should_create_task(self, request: InvocationRequest) -> bool:
        """Determine if task should be created based on TaskManager logic."""
        if self.task_manager:
            return await self.task_manager.should_create_task(request)
        return False

    async def _should_process_task(self, request: InvocationRequest) -> bool:
        """Determine if task should be processed by TaskManager logic."""
        if self.task_manager:
            return await self.task_manager.should_process_task(request)
        return False

    async def _create_task(self, request: InvocationRequest) -> SendMessageOutput:
        """Create a task and return task response."""
        if not self.task_manager:
            logger.error("TaskManager not configured but task creation requested")
            return SendMessageOutput(
                error=A2AError(
                    code=A2AErrorCode.INTERNAL_ERROR, message="Task management not enabled"
                )
            )

        ack_message = self.task_manager.get_task_creation_message(request)

        task = A2ATask(
            id=str(uuid.uuid4()),
            contextId=request.message.contextId or str(uuid.uuid4()),
            status=TaskStatus(state=TaskState.SUBMITTED, message=ack_message),
        )

        await self.task_manager.on_send_task(task, request)

        return SendMessageOutput(result=task)

    async def _process_task(self, request: InvocationRequest) -> SendMessageOutput:
        """Process the given request using the TaskManager"""
        if not self.task_manager:
            logger.error("TaskManager not configured but task processing requested")
            return SendMessageOutput(
                error=A2AError(
                    code=A2AErrorCode.INTERNAL_ERROR, message="Task management not enabled"
                )
            )

        ack_message = self.task_manager.get_task_process_message(request)

        task = A2ATask(
            id=request.message.taskId or str(uuid.uuid4()),
            contextId=request.message.contextId or str(uuid.uuid4()),
            status=TaskStatus(state=TaskState.WORKING, message=ack_message),
        )

        await self.task_manager.on_receive_task(task, request)

        return SendMessageOutput(result=task)

    async def _process_direct(
        self, request: InvocationRequest, agent: AnyBaseAgent[str, AgentResult]
    ) -> SendMessageOutput:
        """Process message directly with agent (no queue)."""
        context_id: str | None = None

        try:
            logger.info("Message request received by the agent")

            # Extract message information
            message_info = extract_message_info(request)
            context_id = message_info.context_id

            message = json.dumps(message_info.parts)
            logger.debug("Processing message: %s", message)

            async with asyncio.timeout(self._timeout):
                if hasattr(agent, "process_message_async"):
                    agent_response = await agent.process_message_async(message)
                else:
                    agent_response = await asyncio.to_thread(agent.process_message, message)

            logger.debug("Agent result: %r", agent_response)

            extracted_agent_response = extract_text_from_strands_agent_response(agent_response)
            # If a tool set force_stop_response, use it directly as the response
            # (stop_after_response optimization — skip LLM summarization)
            force_stop_text = (
                agent_response.state.get("force_stop_response") if agent_response.state else None
            )
            if force_stop_text:
                extracted_agent_response = force_stop_text
                logger.info("Using force_stop_response as agent result text")
            elif not extracted_agent_response:
                logger.info("Agent result text is empty")
            else:
                logger.debug("Agent result text: %s", extracted_agent_response)

            return convert_subagent_response_to_send_message_output(
                context_id, request.message, response=extracted_agent_response
            )

        except asyncio.TimeoutError:
            logger.error(f"Agent processing timed out after {self._timeout} seconds")
            return convert_subagent_response_to_send_message_output(
                context_id,
                request.message,
                error_message="I was not able to generate a response on time.",
            )

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return convert_subagent_response_to_send_message_output(
                context_id, request.message, error_message=f"Error processing message: {str(e)}"
            )

    async def _process_queued(
        self, request: InvocationRequest, queue: QueueService
    ) -> SendMessageOutput:
        """Process message with queue service (orchestrator agent)."""
        context_id: str | None = None
        request_id = "unknown"
        log_context = {}

        try:
            logger.info("Message request received by the message queue processor")
            context = get_agent_context_from_env()

            # Extract message information
            message_info = extract_message_info(request)
            context_id = message_info.context_id

            message = json.dumps(message_info.parts)
            logger.debug("Processing message: %s", message)

            request_id = await queue.submit_request(
                message=message,
                user_id=message_info.user_id,
                sender=message_info.sender,
                context_id=message_info.context_id,
                priority=RequestPriority.NORMAL,
                agent_instance_id=message_info.sender,
                task_id=message_info.task_id,
            )

            log_context = {"queue.request.id": request_id}
            with bound_contextvars(**log_context):
                logger.info(f"Submitted request {request_id} for message processing")

                # Process extension handlers
                handler_response = process_extension_handlers(
                    request=request,
                    request_id=request_id,
                    context_id=message_info.context_id,
                    sender=message_info.sender,
                    user_id=message_info.user_id,
                    extension_handlers=self.extension_handlers,
                )

                if handler_response and message_info.sender:
                    asyncio.create_task(
                        self._handle_delayed_response(
                            request_id, message_info.sender, request.message
                        )
                    )
                    # Convert ExtensionResponse to QueueResponse
                    queue_response = QueueResponse(
                        request_id=request_id,
                        context_id=message_info.context_id,
                        message=handler_response.message,
                        metadata=handler_response.metadata or {},
                        extensions=handler_response.extensions or [],
                    )
                    return convert_queue_response_to_send_message_output(
                        queue_response, request.message, context.agent_instance_id
                    )

                response = await queue.wait_for_response(
                    request_id=request_id,
                    timeout=self._timeout,
                    poll_interval=0.1,  # Check every 100ms for faster response
                )

                if response is None and message_info.sender:
                    logger.info("SendMessage API timeout reached")

                    # TODO: store a reference to this task so it isn't garbage collected
                    asyncio.create_task(
                        self._handle_delayed_response(
                            request_id, message_info.sender, request.message
                        )
                    )
                    response = QueueResponse(
                        request_id=request_id,
                        context_id=message_info.context_id,
                        message="I'm working on your request and will get back to you shortly.",
                    )

                result = convert_queue_response_to_send_message_output(
                    response, request.message, context.agent_instance_id
                )
                logger.info(f"Responding to request_id={request_id}")
                logger.debug(f"request_id={request_id} response={result}")
                return result
        except Exception as e:
            with bound_contextvars(**log_context):
                logger.error(f"Error processing message: {str(e)}")
                result = convert_queue_response_to_send_message_output(
                    QueueResponse(
                        request_id=request_id,
                        context_id=context_id,
                        error_message=f"Failed to process message: {str(e)}",
                    ),
                    request.message,
                )
                logger.info(f"Responding to request_id={request_id} with exception")
                logger.debug(f"request_id={request_id} response={result}")
                return result

    async def _handle_delayed_response(
        self, request_id: str, sender: str, original_message: A2AMessage
    ):
        """Handle delayed agent responses that exceed the initial timeout period."""
        try:
            if self.queue is None:
                logger.error("Queue is not available for delayed response handling")
                return

            logger.info(f"Starting delayed response monitoring for request {request_id}")

            context = get_agent_context_from_env()
            delayed_response = await self.queue.wait_for_response(
                request_id=request_id, timeout=self._delayed_timeout, poll_interval=1
            )

            if delayed_response:
                logger.info(f"Received delayed response for request: {request_id}")
                logger.debug(f"request_id={request_id} response={delayed_response}")
                agent_response = convert_queue_response_to_send_message_output(
                    delayed_response, original_message, context.agent_instance_id
                )
            else:
                logger.info(
                    f"Timed out while waiting for delayed agent response for request: {request_id}"
                )
                timeout_response = QueueResponse(
                    request_id=request_id,
                    context_id=original_message.contextId,
                    message="I was not able to generate a response on time.",
                )
                agent_response = convert_queue_response_to_send_message_output(
                    timeout_response, original_message, context.agent_instance_id
                )

            if agent_response.result:
                # Tasks should only be returned as direct responses, not sent as new messages
                if isinstance(agent_response.result, A2ATask):
                    logger.warning(
                        f"Cannot send A2ATask in delayed response path for request: {request_id}"
                    )
                    return

                logger.info(f"Sending delayed response for request: {request_id}")

                # Send message back to chat agent asynchronously
                try:
                    client = get_agentic_api_client()
                    client.send_message(
                        agentInstanceId=sender,
                        params=MessageSendParams(message=agent_response.result).to_dict(),
                        requestContext=context.to_dict(),
                    )
                    logger.info(f"Successfully sent delayed response for request: {request_id}")
                except Exception as send_error:
                    logger.error(
                        f"Failed to send delayed response for request {request_id}: {send_error}"
                    )

        except Exception as e:
            logger.error(f"Error waiting for response: {e}")
            return
