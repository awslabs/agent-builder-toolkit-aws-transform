"""
Queue service mamager for coordinating request processing.

This module provides a service layer that manages the request queue,
response store, and processing loop coordination.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from structlog.contextvars import bound_contextvars

from ..server.request_context import transaction_id
from .interface import (
    QueueRequest,
    QueueResponse,
    RequestPriority,
    RequestQueue,
    RequestStatus,
    ResponseStore,
)
from .local_queue import LocalRequestQueue, LocalResponseStore

logger = logging.getLogger(__name__)


class QueueService:
    """
    Service manager for request queue operations.

    This class coordinates between the request queue, response store,
    and provides high-level operations for request management.
    """

    def __init__(
        self,
        request_queue: Optional[RequestQueue] = None,
        response_store: Optional[ResponseStore] = None,
        storage_path: str = "/tmp/agent_queue",
    ):
        """
        Initialize the queue service.

        Args:
            request_queue: Request queue implementation (defaults to LocalRequestQueue)
            response_store: Response store implementation (defaults to LocalResponseStore)
            storage_path: Base storage path for default implementations
        """
        self.request_queue = request_queue or LocalRequestQueue(f"{storage_path}/requests")
        self.response_store = response_store or LocalResponseStore(f"{storage_path}/responses")

        # Service state
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the queue service and background tasks."""
        if self._running:
            logger.warning("Queue service is already running.")
            return
        self._running = True
        logger.info("Starting queue service.")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop the queue service and background tasks."""
        if not self._running:
            logger.warning("Queue service is not running.")
            return
        logger.info("Stopping queue service.")
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def submit_request(
        self,
        message: str,
        user_id: Optional[str] = None,
        sender: Optional[str] = None,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        priority: RequestPriority = RequestPriority.NORMAL,
        agent_instance_id: str | None = None,
    ) -> str:
        """
        Submit a new request to the queue.

        Args:
            message: The message/request content
            user_id: User identifier
            sender: Sender identifier
            priority: Request priority

        Returns:
            Request ID of the submitted request
        """
        request = QueueRequest(
            message=message,
            context={
                "user_id": user_id,
                "sender": sender,
                "context_id": context_id,
                "agent_instance_id": agent_instance_id,
                "task_id": task_id,
                "transaction_id": transaction_id.get(),
            },
            priority=priority,
        )

        with bound_contextvars(**{"queue.request.id": request.request_id}):
            logger.info("Submitting request")
            logger.debug(f"Request: {request}")
            success = await self.request_queue.enqueue(request)
            if not success:
                raise RuntimeError(f"Failed to enqueue request {request.request_id}")

            logger.info(f"Submitted request {request.request_id}")
            return request.request_id

    async def get_request_status(self, request_id: str) -> Optional[RequestStatus]:
        """
        Get the status of a request.

        Args:
            request_id: ID of the request

        Returns:
            Status of the request if found, None otherwise
        """
        with bound_contextvars(**{"queue.request.id": request_id}):
            request = await self.request_queue.get_request(request_id)
            return request.status if request else None

    async def get_response(self, request_id: str) -> Optional[QueueResponse]:
        """
        Get the response for a completed request.

        Args:
            request_id: ID of the request

        Returns:
            Response if found, None otherwise
        """
        with bound_contextvars(**{"queue.request.id": request_id}):
            return await self.response_store.get_response(request_id)

    async def wait_for_response(
        self, request_id: str, timeout: float = 30.0, poll_interval: float = 0.5
    ) -> Optional[QueueResponse]:
        """
        Wait for a request response with timeout.

        Args:
            request_id: Request identifier
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check for response in seconds

        Returns:
            Request response if available within timeout, None otherwise
        """
        with bound_contextvars(**{"queue.request.id": request_id}):
            start_time = asyncio.get_running_loop().time()
            logger.info(f"Waiting for response with timeout: {timeout} seconds")
            while True:
                # Check for response
                response = await self.get_response(request_id)
                if response:
                    return response

                # Check timeout
                elapsed = asyncio.get_running_loop().time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Timeout waiting for response to request {request_id}")
                    return None

                # Wait before next check
                await asyncio.sleep(poll_interval)

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on queue service components.

        Returns:
            Health status information
        """
        queue_healthy = await self.request_queue.health_check()
        store_healthy = await self.response_store.health_check()
        queue_size = await self.request_queue.size()

        # TODO: Implement recovery strategies for unhealthy queue system
        # - Add attempt_recovery() method to automatically fix common issues
        # - Implement storage path recreation when directories are missing
        # - Add corrupted file repair (backup and recreate JSON files)
        # - Handle stale lock file removal
        # - Add circuit breaker pattern to prevent cascading failures
        # - Implement graceful degradation when recovery fails
        # - Add periodic health monitoring with automatic recovery attempts
        # - Integrate recovery with API layer for seamless error handling
        # For now, health check only detects issues but doesn't recover from them

        return {
            "service_running": self._running,
            "request_queue_healthy": queue_healthy,
            "response_store_healthy": store_healthy,
            "queue_size": queue_size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _cleanup_loop(self):
        """Background task for periodic cleanup operations."""
        while self._running:
            try:
                # Clean up old responses (older than 24 hours)
                cleaned = await self.response_store.cleanup_old_responses(max_age_hours=24)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} old responses")

                # Sleep for 1 hour before next cleanup
                await asyncio.sleep(3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
