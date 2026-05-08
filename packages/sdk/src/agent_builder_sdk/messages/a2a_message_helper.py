# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
A2A message helper functions for agent-to-agent communication.
"""

import asyncio
import logging
import uuid
from typing import Optional

from agent_builder_sdk.agentic_framework.a2a_manager import get_a2a_manager
from agent_builder_sdk.custom_types.common_types import A2AMessage

logger = logging.getLogger(__name__)


async def send_message(
    message: str,
    context_id: str,
    target_agent_instance_id: str,
    message_id: Optional[str] = None,
) -> None:
    """
    Send an A2A message during agent execution.

    Args:
        message: The text message to send
        context_id: The conversation context ID. Only required when target_agent_instance_id
            is ATX_CHAT. For agent-to-agent communication, this can be any identifier.
        target_agent_instance_id: The agent instance to send the message to
        message_id: Optional message ID (UUID generated if not provided)

    Raises:
        Exception: If message sending fails

    Example:
        >>> await send_message(
        ...     message="Starting data processing...",
        ...     context_id="ctx-123",
        ...     target_agent_instance_id="agent-456"
        ... )
    """
    manager = get_a2a_manager()

    a2a_message = A2AMessage(
        role="agent",
        parts=[{"kind": "text", "text": message}],
        messageId=message_id or str(uuid.uuid4()),
        kind="message",
        contextId=context_id,
    )

    logger.debug(f"Sending A2A message to {target_agent_instance_id}: {message}")

    # Run sync A2AManager method in thread pool to avoid blocking event loop
    await asyncio.to_thread(
        manager.send_message, agent_instance_id=target_agent_instance_id, message=a2a_message
    )

    logger.info(f"A2A message sent successfully to {target_agent_instance_id}")
