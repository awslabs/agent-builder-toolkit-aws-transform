# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from typing import Any, Dict

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.custom_types.message_types import A2AMessageTarget
from agent_builder_agentic_mcp.server._inject_qt_request_context import _inject_qt_request_context

# from agent_builder_agentic_mcp.server._server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/qt-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


# disable send_message by default
# @mcp.tool(
#    name="send_message_to_user",
#    description="Send agent-initiated message to a specific user in chat",
# )
async def send_message_to_user(
    message_text: str, a2a_message_target: A2AMessageTarget
) -> Dict[str, Any]:
    """
    Send an agent-initiated message to a specific user in the chat interface.

    This tool enables agents to proactively send messages to users without requiring
    an existing conversation context. The message will be routed to the specified
    target user based on the targeting configuration.

    Args:
        message_text: The text content of the message to send
        a2a_message_target: Targeting configuration specifying which user to send the message to.
                           Can target job creator, HITL task submitter, or specific user by ID.

    Returns:
        API response containing the result of the message send operation
    """
    try:
        client = atx_agenticapi_client()

        # Build targeting metadata
        json_input = (
            a2a_message_target
            if isinstance(a2a_message_target, dict)
            else a2a_message_target.model_dump(exclude_none=True)
        )
        extension_uri = "https://aws.com/transform/ext/message-targeting/v1"
        metadata = {extension_uri: json_input}

        # Build A2A message
        message = {
            "contextId": f"agent:{str(uuid.uuid4())}",
            "kind": "message",
            "parts": [{"kind": "text", "text": message_text}],
            "role": "agent",
            "metadata": metadata,
            "extensions": [extension_uri],
        }

        kwargs = {"agentInstanceId": "ATX_CHAT", "params": {"message": message}}

        response = client.send_message(**_inject_qt_request_context(kwargs))
        if response["result"]:
            return {"result": response["result"]}
        if response["error"]:
            return {"error": response["error"]}
        return {}

    except Exception as e:
        logger.error(f"Error sending message to chat: {str(e)}")
        raise


# Disable the tool for now until we pass the context_id in the server
# @mcp.tool(name="reply_message_to_user", description="Reply to an existing user chat conversation")
async def reply_message_to_user(context_id: str, message_text: str) -> Dict[str, Any]:
    """
    Send a reply message to an existing chat conversation.

    This tool is used to reply within an ongoing conversation where the agent
    has already received a message from the chat interface. The context_id
    identifies the specific conversation thread to respond to.

    Args:
        context_id: The conversation context ID received from a previous chat message
        message_text: The text content of the response message

    Returns:
        API response containing the result of the message send operation
    """
    try:
        client = atx_agenticapi_client()

        # Build A2A message
        message = {
            "kind": "message",
            "parts": [{"kind": "text", "text": message_text}],
            "role": "agent",
            "contextId": context_id,
        }

        kwargs = {"agentInstanceId": "ATX_CHAT", "params": {"message": message}}

        response = client.send_message(**_inject_qt_request_context(kwargs))

        if response["result"]:
            return {"result": response["result"]}
        if response["error"]:
            return {"error": response["error"]}
        return {}

    except Exception as e:
        logger.error(f"Error sending message to chat: {str(e)}")
        raise
