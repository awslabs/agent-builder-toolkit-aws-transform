"""
Abstract interfaces for request queue and response storage.

This module defines the abstract base classes for request queues and response stores,
allowing different implementations for various storage backends while maintaining
a consistent interface.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class RequestStatus(Enum):
    """Status of a request in the queue."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class RequestPriority(Enum):
    """Priority of a request in the queue."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class QueueRequest:
    """
    Represents a request to be processed by the agent.

    This class encapsulates all the information needed to process a request,
    including the message content, context, and metadata.
    """

    # Unique identifier for the request
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # The actual message/request
    message: str = ""

    # Context information (user_id, sender, etc.)
    context: Dict[str, Any] = field(default_factory=dict)

    # Request metadata
    priority: RequestPriority = RequestPriority.NORMAL
    status: RequestStatus = RequestStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Processing information
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Retry information
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "message": self.message,
            "context": self.context,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueRequest":
        """Create request from dictionary."""
        request = cls(
            request_id=data["request_id"],
            message=data["message"],
            context=data["context"],
            priority=RequestPriority(data["priority"]),
            status=RequestStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            error_message=data.get("error_message", ""),
            retry_count=data["retry_count"],
            max_retries=data["max_retries"],
        )

        if data.get("started_at"):
            request.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            request.completed_at = datetime.fromisoformat(data["completed_at"])

        return request


@dataclass
class QueueResponse:
    """
    Represents a response to a processed request.

    This class encapsulates the response from processing a request,
    including the result message and metadata.
    """

    # Request identifier this response belongs to
    request_id: str

    context_id: Optional[str] = None

    task_id: Optional[str] = None

    # QueueResponse message
    message: str = ""

    # QueueResponse metadata
    status: RequestStatus = RequestStatus.COMPLETED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Additional response data
    metadata: Dict[str, Any] = field(default_factory=dict)
    extensions: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "context_id": self.context_id,
            "task_id": self.task_id,
            "message": self.message,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "extensions": self.extensions,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueResponse":
        """Create response from dictionary."""
        return cls(
            request_id=data["request_id"],
            context_id=data.get("context_id"),
            task_id=data.get("task_id"),
            message=data["message"],
            status=RequestStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
            extensions=data.get("extensions", []),
            error_message=data.get("error_message"),
        )


class RequestQueue(ABC):
    """
    Abstract base class for request queue implementations.

    This interface defines the contract for request queue implementations,
    supporting operations like enqueue, dequeue, and request status management.
    """

    @abstractmethod
    async def enqueue(self, request: QueueRequest) -> bool:
        """
        Add a request to the queue.

        Args:
            request: The request to add to the queue

        Returns:
            True if request was successfully enqueued, False otherwise
        """
        pass

    @abstractmethod
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueRequest]:
        """
        Remove and return the next request from the queue.

        Args:
            timeout: Maximum time to wait for a request (None for no timeout)

        Returns:
            The next request to process, or None if no request available within timeout
        """
        pass

    @abstractmethod
    async def peek(self) -> Optional[QueueRequest]:
        """
        Return the next request without removing it from the queue.

        Returns:
            The next request to process, or None if queue is empty
        """
        pass

    @abstractmethod
    async def update_request_status(
        self, request_id: str, status: RequestStatus, error_message: Optional[str] = None
    ) -> bool:
        """
        Update the status of a request.

        Args:
            request_id: Identifier of the request to update
            status: New status for the request
            error_message: Optional error message if status is FAILED

        Returns:
            True if request was successfully updated, False otherwise
        """
        pass

    @abstractmethod
    async def get_request(self, request_id: str) -> Optional[QueueRequest]:
        """
        Retrieve a request by its ID.

        Args:
            request_id: Identifier of the request to retrieve

        Returns:
            The request if found, None otherwise
        """
        pass

    @abstractmethod
    async def size(self) -> int:
        """
        Get the number of requests in the queue.

        Returns:
            Number of requests currently in the queue
        """
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """
        Remove all requests from the queue.

        Returns:
            True if queue was successfully cleared, False otherwise
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the queue is healthy and operational.

        Returns:
            True if queue is healthy, False otherwise
        """
        pass


class ResponseStore(ABC):
    """
    Abstract base class for response storage implementations.

    This interface defines the contract for storing and retrieving request responses,
    supporting the async communication pattern where responses are stored
    for later retrieval by the API server.
    """

    @abstractmethod
    async def store_response(self, response: QueueResponse) -> bool:
        """
        Store a request response.

        Args:
            response: The response to store

        Returns:
            True if response was successfully stored, False otherwise
        """
        pass

    @abstractmethod
    async def get_response(self, request_id: str) -> Optional[QueueResponse]:
        """
        Retrieve a response by request ID.

        Args:
            request_id: Identifier of the request whose response to retrieve

        Returns:
            The response if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete_response(self, request_id: str) -> bool:
        """
        Delete a response by request ID.

        Args:
            request_id: Identifier of the request whose response to delete

        Returns:
            True if response was successfully deleted, False otherwise
        """
        pass

    @abstractmethod
    async def list_responses(self, limit: Optional[int] = None) -> List[QueueResponse]:
        """
        List stored responses.

        Args:
            limit: Maximum number of responses to return (None for all)

        Returns:
            List of stored responses
        """
        pass

    @abstractmethod
    async def cleanup_old_responses(self, max_age_hours: int = 24) -> int:
        """
        Remove responses older than the specified age.

        Args:
            max_age_hours: Maximum age of responses to keep in hours

        Returns:
            Number of responses that were cleaned up
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the response store is healthy and operational.

        Returns:
            True if store is healthy, False otherwise
        """
        pass
