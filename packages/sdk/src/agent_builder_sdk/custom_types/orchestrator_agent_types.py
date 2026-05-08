# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Type definitions for the orchestrator agent.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class MessageRole(Enum):
    """Enumeration of message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class A2AContext:
    """
    Context for A2A (Agent-to-Agent) communication.
    """

    context_id: Optional[str] = None
    task_id: Optional[str] = None


@dataclass
class ConversationContext:
    """
    Context for identifying and managing conversations.
    """

    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_instance_id: Optional[str] = None
    a2a_context: Optional[A2AContext] = None


@dataclass
class MessageMetadata:
    """Metadata associated with a message."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    tool_name: Optional[str] = None
    tool_use_id: Optional[str] = None
    is_error: bool = False


@dataclass
class ConversationMessage:
    """
    A message in a conversation with proper typing.

    This replaces the generic Dict[str, Any] message format.
    """

    role: MessageRole
    content: str
    metadata: MessageMetadata = field(default_factory=MessageMetadata)

    def to_claude_format(self) -> Dict[str, Any]:
        """Convert to Claude API format."""
        return {"role": self.role.value, "content": self.content}

    @classmethod
    def from_claude_format(cls, claude_message: Dict[str, Any]) -> "ConversationMessage":
        """Create from Claude API format."""
        role_str = claude_message.get("role", "user")
        try:
            role = MessageRole(role_str)
        except ValueError:
            role = MessageRole.USER

        content = claude_message.get("content", "")
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = "".join(text_parts)

        return cls(role=role, content=content)


@dataclass
class MemoryContext:
    """
    Context for memory operations.

    This provides structured context for memory retrieval and storage.
    The actual query/message is passed separately to the memory manager methods.
    """

    conversation_context: ConversationContext


@dataclass
class ProcessMessageRequest:
    """
    Request structure for event_loop messages.

    This provides a strongly typed interface for message event_loop.
    """

    message: str
    context: ConversationContext


@dataclass
class ProcessMessageResponse:
    """
    Response structure for processed messages.

    This provides a strongly typed response format.
    """

    response_message: ConversationMessage
    tool_name_invoked: Optional[str] = None
