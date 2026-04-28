"""
Unit tests for the types module.
"""

import unittest
from datetime import datetime, timezone

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ConversationMessage,
    MemoryContext,
    MessageMetadata,
    MessageRole,
    ProcessMessageRequest,
    ProcessMessageResponse,
)


class TestMessageRole(unittest.TestCase):
    """Test the MessageRole enum."""

    def test_message_role_values(self):
        """Test that MessageRole enum has the expected values."""
        self.assertEqual(MessageRole.USER.value, "user")
        self.assertEqual(MessageRole.ASSISTANT.value, "assistant")
        self.assertEqual(MessageRole.SYSTEM.value, "system")
        self.assertEqual(MessageRole.ERROR.value, "error")
        self.assertEqual(MessageRole.TOOL_CALL.value, "tool_call")
        self.assertEqual(MessageRole.TOOL_RESULT.value, "tool_result")


class TestConversationContext(unittest.TestCase):
    """Test the ConversationContext dataclass."""

    def test_conversation_context_defaults(self):
        """Test that ConversationContext has the expected default values."""
        context = ConversationContext()
        self.assertIsNone(context.user_id)
        self.assertIsNone(context.conversation_id)
        self.assertIsNone(context.agent_instance_id)

    def test_conversation_context_initialization(self):
        """Test that ConversationContext can be initialized with values."""
        context = ConversationContext(
            user_id="user123", conversation_id="conv456", agent_instance_id="agent789"
        )
        self.assertEqual(context.user_id, "user123")
        self.assertEqual(context.conversation_id, "conv456")
        self.assertEqual(context.agent_instance_id, "agent789")


class TestMessageMetadata(unittest.TestCase):
    """Test the MessageMetadata dataclass."""

    def test_message_metadata_defaults(self):
        """Test that MessageMetadata has the expected default values."""
        metadata = MessageMetadata()
        self.assertIsInstance(metadata.timestamp, datetime)
        self.assertIsNone(metadata.tool_name)
        self.assertIsNone(metadata.tool_use_id)
        self.assertFalse(metadata.is_error)

    def test_message_metadata_initialization(self):
        """Test that MessageMetadata can be initialized with values."""
        timestamp = datetime.now(timezone.utc)
        metadata = MessageMetadata(
            timestamp=timestamp, tool_name="test_tool", tool_use_id="tool123", is_error=True
        )
        self.assertEqual(metadata.timestamp, timestamp)
        self.assertEqual(metadata.tool_name, "test_tool")
        self.assertEqual(metadata.tool_use_id, "tool123")
        self.assertTrue(metadata.is_error)


class TestConversationMessage(unittest.TestCase):
    """Test the ConversationMessage dataclass."""

    def test_conversation_message_initialization(self):
        """Test that ConversationMessage can be initialized with values."""
        message = ConversationMessage(role=MessageRole.USER, content="Hello, world!")
        self.assertEqual(message.role, MessageRole.USER)
        self.assertEqual(message.content, "Hello, world!")
        self.assertIsInstance(message.metadata, MessageMetadata)

    def test_to_claude_format(self):
        """Test conversion to Claude API format."""
        message = ConversationMessage(role=MessageRole.ASSISTANT, content="I'm an assistant")
        claude_format = message.to_claude_format()
        self.assertEqual(claude_format["role"], "assistant")
        self.assertEqual(claude_format["content"], "I'm an assistant")

    def test_from_claude_format_simple(self):
        """Test creation from simple Claude API format."""
        claude_message = {"role": "user", "content": "Hello, Claude!"}
        message = ConversationMessage.from_claude_format(claude_message)
        self.assertEqual(message.role, MessageRole.USER)
        self.assertEqual(message.content, "Hello, Claude!")

    def test_from_claude_format_complex(self):
        """Test creation from complex Claude API format with content blocks."""
        claude_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello, "}, {"type": "text", "text": "world!"}],
        }
        message = ConversationMessage.from_claude_format(claude_message)
        self.assertEqual(message.role, MessageRole.ASSISTANT)
        self.assertEqual(message.content, "Hello, world!")

    def test_from_claude_format_invalid_role(self):
        """Test creation from Claude API format with invalid role."""
        claude_message = {"role": "invalid_role", "content": "Hello, Claude!"}
        message = ConversationMessage.from_claude_format(claude_message)
        self.assertEqual(message.role, MessageRole.USER)  # Default to USER
        self.assertEqual(message.content, "Hello, Claude!")


class TestMemoryContext(unittest.TestCase):
    """Test the MemoryContext dataclass."""

    def test_memory_context_initialization(self):
        """Test that MemoryContext can be initialized with values."""
        conversation_context = ConversationContext(user_id="user123", conversation_id="conv456")
        memory_context = MemoryContext(conversation_context=conversation_context)
        self.assertEqual(memory_context.conversation_context, conversation_context)


class TestProcessMessageRequest(unittest.TestCase):
    """Test the ProcessMessageRequest dataclass."""

    def test_process_message_request_initialization(self):
        """Test that ProcessMessageRequest can be initialized with values."""
        context = ConversationContext(user_id="user123", conversation_id="conv456")
        request = ProcessMessageRequest(message="Hello, world!", context=context)
        self.assertEqual(request.message, "Hello, world!")
        self.assertEqual(request.context, context)


class TestProcessMessageResponse(unittest.TestCase):
    """Test the ProcessMessageResponse dataclass."""

    def test_process_message_response_initialization(self):
        """Test that ProcessMessageResponse can be initialized with values."""
        message = ConversationMessage(
            role=MessageRole.ASSISTANT, content="Hello, I'm an assistant!"
        )
        response = ProcessMessageResponse(response_message=message, tool_name_invoked="test_tool")
        self.assertEqual(response.response_message, message)
        self.assertEqual(response.tool_name_invoked, "test_tool")

    def test_process_message_response_defaults(self):
        """Test that ProcessMessageResponse has the expected default values."""
        message = ConversationMessage(
            role=MessageRole.ASSISTANT, content="Hello, I'm an assistant!"
        )
        response = ProcessMessageResponse(response_message=message)
        self.assertEqual(response.response_message, message)
        self.assertIsNone(response.tool_name_invoked)
