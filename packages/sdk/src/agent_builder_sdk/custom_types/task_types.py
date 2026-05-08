# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Task-related types for A2A protocol compliance
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from .common_types import A2AError, A2AMessage

# TODO: Delete these and directly use Python-a2a-sdk


class TaskState(Enum):
    """Task execution states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    REJECTED = "rejected"
    AUTH_REQUIRED = "auth-required"
    UNKNOWN = "unknown"


@dataclass
class TaskStatus:
    """The current state of the task's lifecycle."""

    state: TaskState
    message: Optional[A2AMessage] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert TaskStatus to dictionary for serialization."""
        return {
            "state": self.state.value,
            "message": self.message.to_dict() if self.message else None,
            "timestamp": self.timestamp,
        }


@dataclass
class A2ATask:
    """
    Represents a task in the A2A protocol.
    Based on https://a2a-protocol.org/latest/specification/#61-task-object
    """

    id: str
    contextId: str  # noqa:815
    status: TaskStatus
    kind: Literal["task"] = "task"
    history: Optional[List[A2AMessage]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert A2ATask to dictionary for serialization."""
        return {
            "id": self.id,
            "contextId": self.contextId,
            "status": self.status.to_dict(),
            "kind": self.kind,
            "history": [msg.to_dict() for msg in self.history] if self.history else None,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }


@dataclass
class GetTaskRequest:
    """
    Request parameters for getting a task.
    Based on https://a2a-protocol.org/latest/specification/#73-tasksget
    """

    id: str


@dataclass
class GetTaskResponse:
    """Response for GetTask operation."""

    result: Optional[A2ATask] = None
    error: Optional[A2AError] = None
