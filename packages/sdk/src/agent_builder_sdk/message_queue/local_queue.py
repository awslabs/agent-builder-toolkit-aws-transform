"""
Local file-based implementations of request queue and response store.

This module provides persistent, file-based implementations that survive
container restarts by storing data on disk using JSON files and file locking
for thread safety.
"""

import asyncio
import fcntl
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from structlog.contextvars import bound_contextvars

from .interface import QueueRequest, QueueResponse, RequestQueue, RequestStatus, ResponseStore

logger = logging.getLogger(__name__)


class LocalRequestQueue(RequestQueue):
    """
    File-based request queue implementation that persists to disk.

    This implementation uses JSON files to store requests and provides
    persistence across container restarts. It uses file locking
    to ensure thread safety in concurrent environments.
    """

    def __init__(self, storage_path: str = "/tmp/agent_queue"):
        """
        Initialize the local request queue.

        Args:
            storage_path: Directory path where queue data will be stored
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # File paths
        self.queue_file = self.storage_path / "requests.json"
        self.lock_file = self.storage_path / "queue.lock"

        # In-memory cache for performance
        self._requests: Dict[str, QueueRequest] = {}
        self._queue_order: List[str] = []  # Request IDs in priority order
        self._last_loaded: float = 0.0

        # Initialize files if they don't exist
        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize storage files if they don't exist."""
        if not self.queue_file.exists():
            with open(self.queue_file, "w") as f:
                json.dump({"requests": {}, "queue_order": []}, f)

    @asynccontextmanager
    async def _file_lock(self):
        """Async context manager for file locking."""
        lock_fd = None
        try:
            # Open lock file
            lock_fd = os.open(str(self.lock_file), os.O_CREAT | os.O_WRONLY)

            # Acquire exclusive lock (blocking) - will not work on Windows
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    async def _load_from_disk(self):
        """Load requests from disk if file has been modified."""
        try:
            stat = self.queue_file.stat()
            if stat.st_mtime > self._last_loaded:
                with open(self.queue_file, "r") as f:
                    data = json.load(f)

                # Load requests
                self._requests = {}
                for request_id, task_data in data.get("requests", {}).items():
                    self._requests[request_id] = QueueRequest.from_dict(task_data)

                # Load queue order
                self._queue_order = data.get("queue_order", [])

                # Filter out completed/failed requests from queue order
                self._queue_order = [
                    request_id
                    for request_id in self._queue_order
                    if request_id in self._requests
                    and self._requests[request_id].status
                    in [RequestStatus.PENDING, RequestStatus.PROCESSING]
                ]

                self._last_loaded = stat.st_mtime
                logger.debug(f"Loaded {len(self._requests)} requests from disk")
        except Exception as e:
            logger.exception(f"Error loading from disk: {e}")

    async def _save_to_disk(self):
        """Save current requests to disk."""
        try:
            data = {
                "requests": {
                    request_id: task.to_dict() for request_id, task in self._requests.items()
                },
                "queue_order": self._queue_order,
            }

            # Write to temporary file first, then rename for atomicity
            temp_file = self.queue_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            temp_file.rename(self.queue_file)
            self._last_loaded = time.time()
            logger.debug(f"Saved {len(self._requests)} requests to disk")
        except Exception as e:
            logger.error(f"Error saving requests to disk: {e}")
            raise

    def _sort_queue_by_priority(self):
        """Sort the queue order by priority and creation time."""

        def priority_key(request_id: str) -> tuple:
            task = self._requests.get(request_id)
            if not task:
                return (0, datetime.max)  # Invalid requests go to end

            # Higher priority value = higher priority (processed first)
            # Earlier creation time = higher priority (FIFO within same priority)
            return (-task.priority.value, task.created_at)

        self._queue_order.sort(key=priority_key)

    async def enqueue(self, task: QueueRequest) -> bool:
        """Add a task to the queue."""
        with bound_contextvars(**{"queue.request.id": task.request_id}):
            logger.info("Attempting to enqueue")
            # Obtain exclusive lock
            async with self._file_lock():
                try:
                    logger.info("Attempting to load requests from disk")
                    await self._load_from_disk()  # Load existing requests
                    logger.info("Loaded existing requests from disk")
                    # Add task to memory
                    self._requests[task.request_id] = task
                    logger.info("Added task to memory")
                    # Add to queue order if it's a pending task
                    if task.status == RequestStatus.PENDING:
                        self._queue_order.append(task.request_id)
                        self._sort_queue_by_priority()

                    logger.info("Attempting to save to disk")
                    # Save to disk
                    await self._save_to_disk()

                    logger.info(
                        f"Enqueued request {task.request_id} with priority {task.priority.name}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Error enqueuing task {task.request_id}: {e}")
                    return False

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueRequest]:
        """Remove and return the next task from the queue."""
        start_time = time.time()

        # logging.info("trying to dequeu")

        while True:
            async with self._file_lock():
                try:
                    await self._load_from_disk()

                    # Find next pending task
                    for request_id in self._queue_order[:]:
                        with bound_contextvars(**{"queue.request.id": request_id}):
                            task = self._requests.get(request_id)
                            if task and task.status == RequestStatus.PENDING:
                                # Mark as processing
                                task.status = RequestStatus.PROCESSING
                                task.started_at = datetime.now(timezone.utc)
                                task.updated_at = datetime.now(timezone.utc)
                                # Remove from queue order
                                self._queue_order.remove(request_id)
                                # Save changes
                                await self._save_to_disk()

                                logger.info(f"Dequeued request {request_id}")
                                return task
                    # No requests available
                    if timeout is None or timeout <= 0:
                        return None

                    # Check timeout
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        return None

                except Exception as e:
                    logger.error(f"Error dequeuing task: {e}")
                    return None

            # Wait a bit before checking again
            await asyncio.sleep(0.1)

    async def peek(self) -> Optional[QueueRequest]:
        """Return the next task without removing it from the queue."""
        async with self._file_lock():
            try:
                await self._load_from_disk()

                # Find next pending task
                for request_id in self._queue_order:
                    task = self._requests.get(request_id)
                    if task and task.status == RequestStatus.PENDING:
                        return task

                return None
            except Exception as e:
                logger.error(f"Error peeking at queue: {e}")
                return None

    async def update_request_status(
        self, request_id: str, status: RequestStatus, error_message: Optional[str] = None
    ) -> bool:
        """Update the status of a task."""
        with bound_contextvars(**{"queue.request.id": request_id}):
            async with self._file_lock():
                try:
                    await self._load_from_disk()

                    task = self._requests.get(request_id)
                    if not task:
                        logger.warning(f"Request {request_id} not found for status update")
                        return False

                    # Update task
                    task.status = status
                    task.updated_at = datetime.now(timezone.utc)

                    if status in [
                        RequestStatus.COMPLETED,
                        RequestStatus.FAILED,
                        RequestStatus.TIMEOUT,
                    ]:
                        task.completed_at = datetime.now(timezone.utc)

                    if error_message:
                        task.error_message = error_message

                    # TODO: Implement full retry logic
                    # When a task fails, check if retry_count < max_retries
                    # If yes, increment retry_count and reset status to PENDING
                    # Add exponential backoff between retries
                    # Implement dead letter queue for permanently failed requests
                    # For now, requests do not retry and respond with error immediately

                    # Remove from queue order if completed/failed
                    if status in [
                        RequestStatus.COMPLETED,
                        RequestStatus.FAILED,
                        RequestStatus.TIMEOUT,
                    ]:
                        if request_id in self._queue_order:
                            self._queue_order.remove(request_id)

                    # Save changes
                    await self._save_to_disk()

                    logger.info(f"Updated task {request_id} status to {status.value}")
                    return True
                except Exception as e:
                    logger.error(f"Error updating task {request_id} status: {e}")
                    return False

    async def get_request(self, request_id: str) -> Optional[QueueRequest]:
        """Retrieve a task by its ID."""
        with bound_contextvars(**{"queue.request.id": request_id}):
            async with self._file_lock():
                try:
                    await self._load_from_disk()
                    return self._requests.get(request_id)
                except Exception as e:
                    logger.error(f"Error getting task {request_id}: {e}")
                    return None

    async def size(self) -> int:
        """Get the number of pending requests in the queue."""
        async with self._file_lock():
            try:
                await self._load_from_disk()
                return len(
                    [
                        request_id
                        for request_id in self._queue_order
                        if self._requests.get(request_id)
                        and self._requests[request_id].status == RequestStatus.PENDING
                    ]
                )
            except Exception as e:
                logger.error(f"Error getting queue size: {e}")
                return 0

    async def clear(self) -> bool:
        """Remove all requests from the queue."""
        async with self._file_lock():
            try:
                self._requests.clear()
                self._queue_order.clear()
                await self._save_to_disk()
                logger.info("Cleared all requests from queue")
                return True
            except Exception as e:
                logger.error(f"Error clearing queue: {e}")
                return False

    async def health_check(self) -> bool:
        """Check if the queue is healthy and operational."""
        try:
            # Check if storage directory is accessible
            if not self.storage_path.exists():
                return False

            # Try to load from disk
            async with self._file_lock():
                await self._load_from_disk()

            return True
        except Exception as e:
            logger.error(f"Queue health check failed: {e}")
            return False


class LocalResponseStore(ResponseStore):
    """
    File-based response store implementation that persists to disk.

    This implementation uses JSON files to store responses and provides
    persistence across container restarts.
    """

    def __init__(self, storage_path: str = "/tmp/agent_responses"):
        """
        Initialize the local response store.

        Args:
            storage_path: Directory path where response data will be stored
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # File paths
        self.responses_file = self.storage_path / "responses.json"
        self.lock_file = self.storage_path / "responses.lock"

        # In-memory cache
        self._responses: Dict[str, QueueResponse] = {}
        self._last_loaded: float = 0.0

        # Initialize files if they don't exist
        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize storage files if they don't exist."""
        if not self.responses_file.exists():
            with open(self.responses_file, "w") as f:
                json.dump({"responses": {}}, f)

    @asynccontextmanager
    async def _file_lock(self):
        """Async context manager for file locking."""
        lock_fd = None
        try:
            lock_fd = os.open(str(self.lock_file), os.O_CREAT | os.O_WRONLY)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    async def _load_from_disk(self):
        """Load responses from disk if file has been modified."""
        try:
            stat = self.responses_file.stat()
            if stat.st_mtime > self._last_loaded:
                with open(self.responses_file, "r") as f:
                    data = json.load(f)

                self._responses = {}
                for request_id, response_data in data.get("responses", {}).items():
                    self._responses[request_id] = QueueResponse.from_dict(response_data)

                self._last_loaded = stat.st_mtime
                logger.debug(f"Loaded {len(self._responses)} responses from disk")
        except Exception as e:
            logger.error(f"Error loading responses from disk: {e}")

    async def _save_to_disk(self):
        """Save current responses to disk."""
        try:
            data = {
                "responses": {
                    request_id: response.to_dict()
                    for request_id, response in self._responses.items()
                }
            }

            temp_file = self.responses_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            temp_file.rename(self.responses_file)
            self._last_loaded = time.time()
            logger.debug(f"Saved {len(self._responses)} responses to disk")
        except Exception as e:
            logger.error(f"Error saving responses to disk: {e}")
            raise

    async def store_response(self, response: QueueResponse) -> bool:
        """Store a task response."""
        async with self._file_lock():
            try:
                await self._load_from_disk()
                self._responses[response.request_id] = response
                await self._save_to_disk()
                logger.info(f"Stored response for task {response.request_id}")
                return True
            except Exception as e:
                logger.error(f"Error storing response for task {response.request_id}: {e}")
                return False

    async def get_response(self, request_id: str) -> Optional[QueueResponse]:
        """Retrieve a response by task ID."""
        async with self._file_lock():
            try:
                await self._load_from_disk()
                return self._responses.get(request_id)
            except Exception as e:
                logger.error(f"Error getting response for task {request_id}: {e}")
                return None

    async def delete_response(self, request_id: str) -> bool:
        """Delete a response by task ID."""
        async with self._file_lock():
            try:
                await self._load_from_disk()
                if request_id in self._responses:
                    del self._responses[request_id]
                    await self._save_to_disk()
                    logger.info(f"Deleted response for task {request_id}")
                    return True
                return False
            except Exception as e:
                logger.error(f"Error deleting response for task {request_id}: {e}")
                return False

    async def list_responses(self, limit: Optional[int] = None) -> List[QueueResponse]:
        """List stored responses."""
        async with self._file_lock():
            try:
                await self._load_from_disk()
                responses = list(self._responses.values())

                # Sort by creation time (newest first)
                responses.sort(key=lambda r: r.created_at, reverse=True)

                if limit:
                    responses = responses[:limit]

                return responses
            except Exception as e:
                logger.error(f"Error listing responses: {e}")
                return []

    async def cleanup_old_responses(self, max_age_hours: int = 24) -> int:
        """Remove responses older than the specified age."""
        async with self._file_lock():
            try:
                await self._load_from_disk()

                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
                old_request_ids = [
                    request_id
                    for request_id, response in self._responses.items()
                    if response.created_at < cutoff_time
                ]

                for request_id in old_request_ids:
                    del self._responses[request_id]

                if old_request_ids:
                    await self._save_to_disk()
                    logger.info(f"Cleaned up {len(old_request_ids)} old responses")

                return len(old_request_ids)
            except Exception as e:
                logger.error(f"Error cleaning up old responses: {e}")
                return 0

    async def health_check(self) -> bool:
        """Check if the response store is healthy and operational."""
        try:
            if not self.storage_path.exists():
                return False

            async with self._file_lock():
                await self._load_from_disk()

            return True
        except Exception as e:
            logger.error(f"Response store health check failed: {e}")
            return False
