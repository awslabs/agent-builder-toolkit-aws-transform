# flake8: noqa: N815
# disabling mixedCaseNaming rule since this schema is trying to match Google's A2A

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


@dataclass
class A2AMessage:
    """A2AMessage data structure"""

    # A2AMessage sender's role
    role: Literal["user", "agent"]

    # A2AMessage content
    parts: List[Dict[str, Any]]

    # Identifier created by the message creator
    messageId: str

    # Event type
    kind: Literal["message"]

    # Extension metadata
    metadata: Optional[Dict[str, Any]] = None

    # The URIs of extensions that are present or contributed to this A2AMessage
    extensions: Optional[List[str]] = None

    # List of tasks referenced as context by this A2AMessage
    referenceTaskIds: Optional[List[str]] = None

    # Identifier of task the A2AMessage is related to
    taskId: Optional[str] = None

    # The context the A2AMessage is associated with
    contextId: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert A2AMessage to dictionary for serialization."""
        return {
            "role": self.role,
            "parts": self.parts,
            "messageId": self.messageId,
            "kind": self.kind,
            "metadata": self.metadata,
            "extensions": self.extensions,
            "referenceTaskIds": self.referenceTaskIds,
            "taskId": self.taskId,
            "contextId": self.contextId,
        }


@dataclass
class MessageSendParams:
    message: A2AMessage

    def to_dict(self) -> Dict[str, Any]:
        """Convert MessageSendParams to dictionary for serialization."""
        return {"message": self.message.to_dict()}


class A2AErrorCode(Enum):
    """A2A Protocol Standard Error Codes"""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    TASK_NOT_FOUND = -32000
    TASK_NOT_CANCELABLE = -32001
    PUSH_NOTIFICATION_NOT_SUPPORTED = -32002
    UNSUPPORTED_OPERATION = -32003


@dataclass
class A2AError:
    """A2AError response data structure"""

    # A Number that indicates the error type that occurred
    code: A2AErrorCode

    # A String providing a short description of the error
    message: str

    # A Primitive or Structured value that contains additional information about the error
    data: Optional[Any] = None


@dataclass
class InvocationRequest:
    """Request model for invocation endpoints."""

    message: A2AMessage


# Backward compatibility: SendMessageOutput moved to response_types.py
from .response_types import SendMessageOutput  # noqa: F401, E402
