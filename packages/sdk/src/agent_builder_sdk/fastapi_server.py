"""
FastAPI server for the ATX Base Orchestrator Agent
"""

import asyncio
import json
import logging
from typing import Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI

from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.common_types import (
    A2AError,
    A2AErrorCode,
    A2AMessage,
    InvocationRequest,
    MessageSendParams,
)
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.custom_types.task_types import A2ATask, GetTaskRequest, GetTaskResponse
from agent_builder_sdk.env_var import get_agent_context_from_env
from agent_builder_sdk.message_queue import QueueResponse, QueueService
from agent_builder_sdk.message_queue.interface import RequestPriority
from agent_builder_sdk.notification.notification_handler import NotificationHandler
from agent_builder_sdk.task_handler import TaskHandler
from agent_builder_sdk.utils import (
    convert_queue_response_to_send_message_output,
    extract_message_info,
)

queue: Optional[QueueService] = None

logger = logging.getLogger(__name__)

app = FastAPI(title="ATX Base Orchestration Agent API")


def get_notification_handler() -> NotificationHandler:
    """Dependency function to get notification handler from app state."""
    return app.state.notification_handler


def get_task_handler() -> TaskHandler:
    """Dependency injection for TaskHandler."""
    return TaskHandler()


_TIMEOUT = 28
_DELAYED_TIMEOUT = 60 * 5


async def handle_delayed_response(
    request_id: str, context_id: str | None, original_message: A2AMessage, sender: str = "ATX_CHAT"
):
    """
    Handle delayed agent responses that exceed the initial timeout period.

    Args:
        request_id: Unique identifier for the request
        context_id: Context identifier for the conversation
        original_message: The original A2A message that triggered the request
        sender: The agent instance ID of the sender of the original message

    Returns:
        None
    """
    try:
        if queue is None:
            logger.error("Queue is not available for delayed response handling")
            return

        logger.info(f"Starting delayed response monitoring for request {request_id}")
        timeout_length = _DELAYED_TIMEOUT

        delayed_response = await queue.wait_for_response(
            request_id=request_id, timeout=timeout_length, poll_interval=1
        )

        if delayed_response:
            logger.info(f"Received delayed response for request: {request_id}")
            logger.debug(f"{request_id}: {delayed_response}")
            agent_response = convert_queue_response_to_send_message_output(
                delayed_response, original_message
            )
        else:
            logger.info(
                f"Timedout while waiting for delayed agent response for request: {request_id}"
            )
            timeout_response = QueueResponse(
                request_id=request_id,
                context_id=context_id,
                message="I was not able to generate a response on time.",
            )
            agent_response = convert_queue_response_to_send_message_output(
                timeout_response, original_message
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
            client = get_agentic_api_client()
            context = get_agent_context_from_env()
            client.send_message(
                agentInstanceId=sender,
                params=MessageSendParams(message=agent_response.result).to_dict(),
                requestContext=context.to_dict(),
            )

    except Exception as e:
        logger.error(f"Error waiting for response: {e}")
        return


@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/invocations")
async def send_notification(
    request: Dict[str, str],
    handler: NotificationHandler = Depends(get_notification_handler),
) -> Dict[str, str]:
    """Handle notification invocations from the platform."""
    return await handler.handle_notification(request)


@app.post("/tasks/get")
async def get_task(
    request: GetTaskRequest, task_handler: TaskHandler = Depends(get_task_handler)
) -> GetTaskResponse:
    """
    Retrieve a task by ID following A2A protocol.

    Args:
        request: GetTask request parameters
        task_handler: Injected TaskHandler dependency

    Returns:
        GetTaskResponse with task data or error
    """
    logger.info(f"GetTask request received for task: {request.id}")

    try:
        response = await task_handler.get_task(request)
        logger.info(
            f"GetTask completed for task_id: {request.id}, status: {'success' if response.result else 'error'}"
        )
        return response
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error processing GetTask request: {error_msg}")
        return GetTaskResponse(
            error=A2AError(
                code=A2AErrorCode.INTERNAL_ERROR,
                message="Internal error getting task details",
            )
        )


@app.post("/message/send")
async def send_message(request: InvocationRequest) -> SendMessageOutput:
    """
    Process a message request and return the agent's response.

    This endpoint passes the input to the agent and returns the response.
    """
    global queue

    if queue is None:
        logger.error("No Queue")
        return SendMessageOutput(
            error=A2AError(code=A2AErrorCode.INTERNAL_ERROR, message="No Queue available")
        )

    context_id: str | None = None
    request_id = "unknown"

    try:
        logger.info("Message request received by the orchestrator agent")

        # Extract message information
        message_info = extract_message_info(request)
        context_id = message_info.context_id

        logger.debug(f"Processing message: {json.dumps(message_info.parts)}")

        request_id = await queue.submit_request(
            message=json.dumps(message_info.parts),
            user_id=message_info.user_id,
            sender=message_info.sender,
            context_id=message_info.context_id,
            priority=RequestPriority.NORMAL,
            task_id=message_info.task_id,
        )

        logger.info(f"Submitted request {request_id} for message processing")

        # Wait for response with timeout
        response = await queue.wait_for_response(
            request_id=request_id,
            timeout=_TIMEOUT,
            poll_interval=0.1,  # Check every 100ms for faster response
        )

        if response is None and message_info.sender:
            logger.info("SendMessage API timeout reached")

            asyncio.create_task(
                handle_delayed_response(
                    request_id, message_info.context_id, request.message, message_info.sender
                )
            )

            response = QueueResponse(
                request_id=request_id,
                context_id=message_info.context_id,
                message="I'm working on your request and will get back to you shortly.",
            )

        else:
            logger.info("Message processing complete")

        result = convert_queue_response_to_send_message_output(response, request.message)
        logger.info(f"Responding to request_id={request_id}")
        return result
    except Exception as e:
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


def start_api_server(
    queue_service: QueueService,
    notification_handler: Optional[NotificationHandler] = None,
    host: str = "0.0.0.0",
    port: int = 8080,
):
    """Start the FastAPI server."""
    logger.info(f"Starting API server on {host}:{port}")

    global queue
    queue = queue_service
    app.state.notification_handler = notification_handler or NotificationHandler(queue_service)

    uvicorn.run(app, host=host, port=port)
