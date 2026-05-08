# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Send message tools for Strands agents.

This module provides tools to send messages to other agents via the ATX platform.
"""

import asyncio
import logging
import uuid

from strands.tools import tool

from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.env_var import get_agent_context_from_env
from agent_builder_sdk.utils import A2A_SOURCE_INFORMATION_EXT

logger = logging.getLogger(__name__)


class SendMessageTools:
    """Send message tools for communicating with other agents via ATX platform."""

    def __init__(self):
        """Initialize the send message tools."""
        logger.info("Initialized SendMessageTools")

    @staticmethod
    def _construct_message(text: str, sender: str) -> A2AMessage:
        """Construct an A2AMessage from text.

        Args:
            text: The message text to send

        Returns:
            Constructed A2AMessage
        """
        return A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": text}],
            messageId=str(uuid.uuid4()),
            kind="message",
            metadata={A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}},
            extensions=[A2A_SOURCE_INFORMATION_EXT],
        )

    @tool
    def send_message_to_subagent(
        self,
        subagent_instance_id: str,
        message: str,
    ):
        """Send a message to a subagent.

        Args:
            subagent_instance_id: The ID of the subagent to send the message to
            message: The text message to send to the subagent

        Returns:
            Response from the subagent

        Example:
            response = send_message_to_subagent("subagent-123", "What is the status?")
        """
        try:
            client = get_agentic_api_client()
            context = get_agent_context_from_env()

            message_obj = self._construct_message(message, context.agent_instance_id)

            response = client.send_message(
                agentInstanceId=subagent_instance_id,
                params={"message": message_obj.to_dict()},
                requestContext=context.to_dict(),
            )
            logger.info(f"Message sent to subagent {subagent_instance_id}.")
            return response

        except Exception as e:
            logger.exception(f"Send message operation error: {e}")
            raise e

    @tool
    async def async_send_message_to_subagent(
        self,
        subagent_instance_id: str,
        message: str,
    ):
        """Send a message to a subagent asynchronously.

        Args:
            subagent_instance_id: The ID of the subagent to send the message to
            message: The text message to send to the subagent

        Returns:
            Response from the subagent

        Example:
            response = await async_send_message_to_subagent("subagent-123", "What is the status?")
        """
        try:
            client = get_agentic_api_client()
            context = get_agent_context_from_env()

            message_obj = self._construct_message(message, context.agent_instance_id)

            response = await asyncio.to_thread(
                client.send_message,
                agentInstanceId=subagent_instance_id,
                params={"message": message_obj.to_dict()},
                requestContext=context.to_dict(),
            )
            logger.info(f"Message sent to subagent {subagent_instance_id}.")
            return response

        except Exception as e:
            logger.exception(f"Async send message operation error: {e}")
            raise e
