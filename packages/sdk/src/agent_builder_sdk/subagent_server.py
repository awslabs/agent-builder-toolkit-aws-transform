# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
FastAPI server for the ATX Base Subagent
"""

import asyncio
import json
import logging
from typing import Dict

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from typing_extensions import deprecated

from agent_builder_sdk.base_subagent.base_subagent import BaseSubagent
from agent_builder_sdk.custom_types.common_types import (
    A2AError,
    A2AErrorCode,
    InvocationRequest,
)
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.utils import (
    convert_subagent_response_to_send_message_output,
    extract_message_info,
    extract_text_from_strands_agent_response,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="ATX Base Subagent API")

_TIMEOUT = 28


def get_subagent() -> BaseSubagent:
    """Dependency to get the subagent instance."""
    if not hasattr(app.state, "subagent") or app.state.subagent is None:
        raise HTTPException(status_code=500, detail="Subagent is not initialized")
    return app.state.subagent


@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/invocations")
async def send_notification(request: Dict[str, str]) -> Dict[str, str]:
    """Handle notification invocations from the platform."""
    # TODO
    logger.info("Notification received by the subagent")
    return {"message": "Notification received by the subagent"}


@deprecated(
    "This file is deprecated. Use `AgentRuntimeServer` or `StatelessAgentRuntimeServer` instead"
)
@app.post("/message/send")
async def send_message(request: InvocationRequest, subagent: BaseSubagent = Depends(get_subagent)):
    """
    Process a message request and return the agent's response.

    This endpoint passes the input to the agent and returns the response.
    """

    if subagent is None:
        logger.error("Subagent is not initialized")
        return SendMessageOutput(
            error=A2AError(
                code=A2AErrorCode.INTERNAL_ERROR,
                message="Subagent is not initialized",
            )
        )

    context_id: str | None = None

    try:
        logger.info("Message request received by the subagent")

        # Extract message information
        message_info = extract_message_info(request)
        context_id = message_info.context_id

        logger.info("Processing message")
        logger.debug(f"Message: {json.dumps(message_info.parts)}")

        # Extract text from parts
        message_text = (
            message_info.parts[0]["text"]
            if message_info.parts and "text" in message_info.parts[0]
            else ""
        )

        # Create ProcessMessageRequest
        process_request = ProcessMessageRequest(
            message=message_text,
            context=ConversationContext(
                user_id=message_info.user_id, agent_instance_id=message_info.sender
            ),
        )

        # Process message with subagent with timeout
        subagent_response = await asyncio.wait_for(
            asyncio.to_thread(subagent.process_message, process_request), timeout=_TIMEOUT
        )

        extracted_subagent_response = extract_text_from_strands_agent_response(subagent_response)

        return convert_subagent_response_to_send_message_output(
            message_info.context_id, request.message, response=extracted_subagent_response
        )

    except asyncio.TimeoutError:
        logger.error(f"Subagent processing timed out after {_TIMEOUT} seconds")
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


def start_subagent_api_server(
    subagent_instance: BaseSubagent,
    host: str = "0.0.0.0",
    port: int = 8080,
):
    """Start the FastAPI server."""
    logger.info(f"Starting Subagent API server on {host}:{port}")

    app.state.subagent = subagent_instance

    uvicorn.run(app, host=host, port=port)
