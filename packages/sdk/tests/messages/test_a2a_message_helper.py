# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for A2A message helper functions.
"""

import uuid
from unittest import mock

import pytest

from agent_builder_sdk.messages.a2a_message_helper import send_message


class TestA2AMessageHelper:
    """Test cases for A2A message helper functions."""

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.get_a2a_manager")
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.asyncio.to_thread")
    async def test_send_message_success(self, mock_to_thread, mock_get_manager):
        """Test successful A2A message sending."""
        # Setup
        mock_manager = mock.Mock()
        mock_get_manager.return_value = mock_manager
        mock_to_thread.return_value = None

        # Call function
        await send_message(
            message="Test message",
            context_id="ctx-123",
            target_agent_instance_id="agent-456",
        )

        # Verify manager was retrieved
        mock_get_manager.assert_called_once()

        # Verify message was sent via thread pool
        mock_to_thread.assert_called_once()
        call_args = mock_to_thread.call_args
        assert call_args[0][0] == mock_manager.send_message
        assert call_args[1]["agent_instance_id"] == "agent-456"

        # Verify message structure
        message_arg = call_args[1]["message"]
        assert message_arg.role == "agent"
        assert message_arg.parts == [{"kind": "text", "text": "Test message"}]
        assert message_arg.kind == "message"
        assert message_arg.contextId == "ctx-123"
        assert message_arg.messageId is not None

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.get_a2a_manager")
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.asyncio.to_thread")
    async def test_send_message_with_custom_message_id(self, mock_to_thread, mock_get_manager):
        """Test A2A message sending with custom message ID."""
        # Setup
        mock_manager = mock.Mock()
        mock_get_manager.return_value = mock_manager
        mock_to_thread.return_value = None
        custom_message_id = str(uuid.uuid4())

        # Call function
        await send_message(
            message="Test message",
            context_id="ctx-123",
            target_agent_instance_id="agent-456",
            message_id=custom_message_id,
        )

        # Verify custom message ID was used
        call_args = mock_to_thread.call_args
        message_arg = call_args[1]["message"]
        assert message_arg.messageId == custom_message_id

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.get_a2a_manager")
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.asyncio.to_thread")
    async def test_send_message_raises_exception(self, mock_to_thread, mock_get_manager):
        """Test A2A message sending propagates exceptions to caller."""
        # Setup
        mock_manager = mock.Mock()
        mock_get_manager.return_value = mock_manager
        mock_to_thread.side_effect = Exception("Network error")

        # Call function - should raise exception
        with pytest.raises(Exception, match="Network error"):
            await send_message(
                message="Test message",
                context_id="ctx-123",
                target_agent_instance_id="agent-456",
            )

        # Verify manager was called before error
        mock_get_manager.assert_called_once()
        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.get_a2a_manager")
    @mock.patch("agent_builder_sdk.messages.a2a_message_helper.asyncio.to_thread")
    async def test_send_message_to_atx_chat(self, mock_to_thread, mock_get_manager):
        """Test A2A message sending to ATX_CHAT."""
        # Setup
        mock_manager = mock.Mock()
        mock_get_manager.return_value = mock_manager
        mock_to_thread.return_value = None

        # Call function
        await send_message(
            message="Progress update",
            context_id="ctx-789",
            target_agent_instance_id="ATX_CHAT",
        )

        # Verify message was sent to ATX_CHAT
        call_args = mock_to_thread.call_args
        assert call_args[1]["agent_instance_id"] == "ATX_CHAT"

        # Verify message structure
        message_arg = call_args[1]["message"]
        assert message_arg.contextId == "ctx-789"
        assert message_arg.parts == [{"kind": "text", "text": "Progress update"}]
