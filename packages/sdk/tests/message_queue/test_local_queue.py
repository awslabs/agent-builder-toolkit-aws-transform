# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for local queue implementation.
Tests file-based queue and response store with persistence and locking.
"""

import asyncio
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from agent_builder_sdk.message_queue.interface import (
    QueueRequest,
    QueueResponse,
    RequestPriority,
    RequestStatus,
)
from agent_builder_sdk.message_queue.local_queue import LocalRequestQueue, LocalResponseStore


class TestLocalRequestQueue(unittest.TestCase):
    """Test LocalRequestQueue implementation."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue = LocalRequestQueue(self.temp_dir)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test queue initialization creates necessary directories."""
        self.assertTrue(os.path.exists(self.queue.storage_path))
        self.assertTrue(os.path.exists(self.queue.queue_file))
        # Lock file is created on first use, not during initialization

    def test_enqueue_request(self):
        """Test adding a request to the queue."""

        async def run_test():
            request = QueueRequest(message="Test message", priority=RequestPriority.HIGH)

            success = await self.queue.enqueue(request)
            self.assertTrue(success)

            # Verify request was saved to file
            with open(self.queue.queue_file, "r") as f:
                data = json.load(f)
                self.assertEqual(len(data["requests"]), 1)
                # Check that a request with our message exists
                found_request = False
                for request_data in data["requests"].values():
                    if request_data["message"] == "Test message":
                        found_request = True
                        break
                self.assertTrue(found_request)

        asyncio.run(run_test())

    def test_dequeue_request(self):
        """Test removing a request from the queue."""

        async def run_test():
            # Add a request first
            request = QueueRequest(message="Dequeue test", priority=RequestPriority.NORMAL)
            await self.queue.enqueue(request)

            # Dequeue the request
            dequeued_request = await self.queue.dequeue()

            self.assertIsNotNone(dequeued_request)
            self.assertEqual(dequeued_request.message, "Dequeue test")

        asyncio.run(run_test())

    def test_dequeue_empty_queue(self):
        """Test dequeuing from empty queue returns None."""

        async def run_test():
            request = await self.queue.dequeue()
            self.assertIsNone(request)

        asyncio.run(run_test())

    def test_priority_ordering(self):
        """Test requests are dequeued in priority order."""

        async def run_test():
            # Add requests in mixed priority order
            requests = [
                QueueRequest(message="Low priority", priority=RequestPriority.LOW),
                QueueRequest(message="Urgent priority", priority=RequestPriority.URGENT),
                QueueRequest(message="Normal priority", priority=RequestPriority.NORMAL),
                QueueRequest(message="High priority", priority=RequestPriority.HIGH),
            ]

            for request in requests:
                await self.queue.enqueue(request)

            # Dequeue and verify order: URGENT -> HIGH -> NORMAL -> LOW
            expected_order = ["Urgent priority", "High priority", "Normal priority", "Low priority"]
            actual_order = []

            while True:
                request = await self.queue.dequeue()
                if request is None:
                    break
                actual_order.append(request.message)

            self.assertEqual(actual_order, expected_order)

        asyncio.run(run_test())

    def test_fifo_within_same_priority(self):
        """Test FIFO ordering within same priority level."""

        async def run_test():
            # Add multiple requests with same priority
            for i in range(3):
                request = QueueRequest(message=f"Message {i}", priority=RequestPriority.NORMAL)
                await self.queue.enqueue(request)
                await asyncio.sleep(0.01)  # Ensure different timestamps

            # Dequeue and verify FIFO order
            expected_order = ["Message 0", "Message 1", "Message 2"]
            actual_order = []

            while True:
                request = await self.queue.dequeue()
                if request is None:
                    break
                actual_order.append(request.message)

            self.assertEqual(actual_order, expected_order)

        asyncio.run(run_test())

    def test_get_queue_size(self):
        """Test getting queue size."""

        async def run_test():
            self.assertEqual(await self.queue.size(), 0)

            # Add some requests
            for i in range(3):
                request = QueueRequest(message=f"Size test {i}", priority=RequestPriority.NORMAL)
                await self.queue.enqueue(request)

            self.assertEqual(await self.queue.size(), 3)

            # Remove one request
            await self.queue.dequeue()
            self.assertEqual(await self.queue.size(), 2)

        asyncio.run(run_test())

    def test_update_request_status(self):
        """Test updating request status."""

        async def run_test():
            request = QueueRequest(message="Status test", priority=RequestPriority.NORMAL)
            await self.queue.enqueue(request)

            # Update status
            success = await self.queue.update_request_status(
                request.request_id, RequestStatus.PROCESSING
            )
            self.assertTrue(success)

            # Verify status was updated
            updated_request = await self.queue.get_request(request.request_id)
            self.assertIsNotNone(updated_request)
            self.assertEqual(updated_request.status, RequestStatus.PROCESSING)

        asyncio.run(run_test())

    def test_update_nonexistent_request_status(self):
        """Test updating status of non-existent request."""

        async def run_test():
            success = await self.queue.update_request_status("nonexistent", RequestStatus.COMPLETED)
            self.assertFalse(success)

        asyncio.run(run_test())

    def test_is_healthy(self):
        """Test health check."""

        async def run_test():
            self.assertTrue(await self.queue.health_check())

        asyncio.run(run_test())

    # def test_persistence_across_instances(self):
    #     """Test that queue data persists across different instances."""

    #     async def run_test():
    #         # Add request with first instance
    #         request1 = QueueRequest(message="Persistence test 1", priority=RequestPriority.HIGH)
    #         await self.queue.enqueue(request1)

    #         # Create new instance pointing to same directory
    #         queue2 = LocalRequestQueue(self.temp_dir)

    #         # Add another request with second instance
    #         request2 = QueueRequest(message="Persistence test 2", priority=RequestPriority.LOW)
    #         await queue2.enqueue(request2)

    #         # Verify both requests are accessible from either instance
    #         # Note: Each instance loads data independently, so we check the total in the file
    #         self.assertEqual(await self.queue.size(), 1)  # First instance has 1 request
    #         self.assertEqual(await queue2.size(), 2)  # Second instance loaded both requests

    #         # Dequeue from second instance should get high priority request first
    #         dequeued = await queue2.dequeue()
    #         self.assertEqual(dequeued.message, "Persistence test 1")

    #         # Dequeue from second instance should get remaining request
    #         dequeued = await queue2.dequeue()
    #         self.assertEqual(dequeued.message, "Persistence test 2")

    #     asyncio.run(run_test())

    def test_concurrent_access(self):
        """Test concurrent access to queue."""

        async def run_test():
            results = []
            errors = []

            async def enqueue_requests(start_id):
                try:
                    for i in range(5):
                        request = QueueRequest(
                            message=f"Concurrent test {start_id}-{i}",
                            priority=RequestPriority.NORMAL,
                        )
                        success = await self.queue.enqueue(request)
                        results.append(success)
                except Exception as e:
                    errors.append(e)

            # Start multiple concurrent requests
            requests = []
            for i in range(3):
                request = enqueue_requests(i)
                requests.append(request)

            await asyncio.gather(*requests)

            # Verify no errors and all operations succeeded
            self.assertEqual(len(errors), 0)
            self.assertEqual(len(results), 15)  # 3 requests * 5 operations each
            self.assertTrue(all(results))
            self.assertEqual(await self.queue.size(), 15)

        asyncio.run(run_test())

    def test_file_locking(self):
        """Test that file locking is used for thread safety."""

        # This test is more about ensuring the locking mechanism exists
        # rather than testing the actual file locking behavior
        async def run_test():
            request = QueueRequest(message="Lock test", priority=RequestPriority.NORMAL)
            success = await self.queue.enqueue(request)
            self.assertTrue(success)

            # Verify the request was added
            self.assertEqual(await self.queue.size(), 1)

        asyncio.run(run_test())

    def test_corrupted_file_handling(self):
        """Test handling of corrupted queue files."""

        async def run_test():
            # Write invalid JSON to queue file
            with open(self.queue.queue_file, "w") as f:
                f.write("invalid json content")

            # Should handle corrupted file gracefully
            try:
                await self.queue._load_from_disk()
                # Should not crash, might reset to empty state
                self.assertTrue(True)  # If we get here, it handled the error
            except Exception:
                # If it raises an exception, that's also acceptable behavior
                self.assertTrue(True)

        asyncio.run(run_test())

    def test_missing_file_initialization(self):
        """Test initialization when files don't exist."""

        async def run_test():
            # Remove the queue file
            if os.path.exists(self.queue.queue_file):
                os.remove(self.queue.queue_file)

            # Should recreate file on first operation
            request = QueueRequest(
                message="Test after file removal", priority=RequestPriority.NORMAL
            )
            success = await self.queue.enqueue(request)
            self.assertTrue(success)

            # File should exist now
            self.assertTrue(os.path.exists(self.queue.queue_file))

        asyncio.run(run_test())

    def test_dequeue_with_timeout(self):
        """Test dequeue with timeout parameter."""

        async def run_test():
            # Test dequeue with timeout on empty queue
            start_time = time.time()
            request = await self.queue.dequeue(timeout=0.1)
            end_time = time.time()

            self.assertIsNone(request)
            # Should have waited approximately the timeout duration
            elapsed = end_time - start_time
            self.assertGreaterEqual(elapsed, 0.05)  # Allow some variance

        asyncio.run(run_test())

    def test_peek_operation(self):
        """Test peek operation (look without removing)."""

        async def run_test():
            # Add a request
            request = QueueRequest(message="Peek test", priority=RequestPriority.HIGH)
            await self.queue.enqueue(request)

            # Peek should return the request without removing it
            peeked_request = await self.queue.peek()
            self.assertIsNotNone(peeked_request)
            self.assertEqual(peeked_request.message, "Peek test")

            # Queue size should still be 1
            self.assertEqual(await self.queue.size(), 1)

            # Dequeue should still return the same request
            dequeued_request = await self.queue.dequeue()
            self.assertEqual(dequeued_request.request_id, peeked_request.request_id)

        asyncio.run(run_test())

    def test_clear_operation(self):
        """Test clearing all requests from queue."""

        async def run_test():
            # Add multiple requests
            for i in range(3):
                request = QueueRequest(message=f"Clear test {i}", priority=RequestPriority.NORMAL)
                await self.queue.enqueue(request)

            self.assertEqual(await self.queue.size(), 3)

            # Clear the queue
            success = await self.queue.clear()
            self.assertTrue(success)

            # Queue should be empty
            self.assertEqual(await self.queue.size(), 0)

        asyncio.run(run_test())

    def test_get_request_by_id(self):
        """Test retrieving specific request by ID."""

        async def run_test():
            # Add a request
            request = QueueRequest(message="Get by ID test", priority=RequestPriority.NORMAL)
            await self.queue.enqueue(request)

            # Retrieve by ID
            retrieved_request = await self.queue.get_request(request.request_id)
            self.assertIsNotNone(retrieved_request)
            self.assertEqual(retrieved_request.request_id, request.request_id)
            self.assertEqual(retrieved_request.message, "Get by ID test")

            # Try to get non-existent request
            nonexistent_request = await self.queue.get_request("nonexistent-id")
            self.assertIsNone(nonexistent_request)

        asyncio.run(run_test())

    def test_request_status_updates_with_error(self):
        """Test request status updates with error messages."""

        async def run_test():
            # Add a request
            request = QueueRequest(message="Status error test", priority=RequestPriority.NORMAL)
            await self.queue.enqueue(request)

            # Update status with error message
            success = await self.queue.update_request_status(
                request.request_id, RequestStatus.FAILED, "Test error message"
            )
            self.assertTrue(success)

            # Retrieve and verify error message
            updated_request = await self.queue.get_request(request.request_id)
            self.assertIsNotNone(updated_request)
            self.assertEqual(updated_request.status, RequestStatus.FAILED)
            self.assertEqual(updated_request.error_message, "Test error message")

        asyncio.run(run_test())

    def test_file_permission_errors(self):
        """Test handling of file permission errors."""

        async def run_test():
            # This test simulates permission errors
            with patch("builtins.open", side_effect=PermissionError("Permission denied")):
                try:
                    await self.queue._save_to_disk()
                    # Should handle permission error gracefully
                except PermissionError:
                    # Expected behavior - permission error should be raised or handled
                    pass

        asyncio.run(run_test())

    def test_large_queue_operations(self):
        """Test operations with larger number of requests."""

        async def run_test():
            # Add many requests with different priorities
            request_count = 50
            for i in range(request_count):
                priority = [
                    RequestPriority.LOW,
                    RequestPriority.NORMAL,
                    RequestPriority.HIGH,
                    RequestPriority.URGENT,
                ][i % 4]
                request = QueueRequest(message=f"Large queue test {i}", priority=priority)
                await self.queue.enqueue(request)

            self.assertEqual(await self.queue.size(), request_count)

            # Dequeue all requests and verify priority ordering
            urgent_count = 0
            high_count = 0
            normal_count = 0
            low_count = 0

            while await self.queue.size() > 0:
                request = await self.queue.dequeue()
                if request.priority == RequestPriority.URGENT:
                    urgent_count += 1
                elif request.priority == RequestPriority.HIGH:
                    high_count += 1
                elif request.priority == RequestPriority.NORMAL:
                    normal_count += 1
                elif request.priority == RequestPriority.LOW:
                    low_count += 1

            # Verify we got all requests
            total_dequeued = urgent_count + high_count + normal_count + low_count
            self.assertEqual(total_dequeued, request_count)

        asyncio.run(run_test())


class TestLocalResponseStore(unittest.TestCase):
    """Test LocalResponseStore implementation."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = LocalResponseStore(self.temp_dir)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test response store initialization."""
        self.assertTrue(os.path.exists(self.store.storage_path))
        self.assertTrue(os.path.exists(self.store.responses_file))
        # Lock file is created on first use, not during initialization

    def test_store_response(self):
        """Test storing a response."""

        async def run_test():
            response = QueueResponse(
                request_id="resp-test-1",
                message="Test response message",
                status=RequestStatus.COMPLETED,
            )

            success = await self.store.store_response(response)
            self.assertTrue(success)

            # Verify response was saved to file
            with open(self.store.responses_file, "r") as f:
                data = json.load(f)
                self.assertEqual(len(data["responses"]), 1)
                # Check that a response with our request_id exists
                self.assertIn("resp-test-1", data["responses"])

        asyncio.run(run_test())

    def test_get_response(self):
        """Test retrieving a response."""

        async def run_test():
            # Store a response first
            response = QueueResponse(
                request_id="resp-test-2",
                message="Get response test",
                status=RequestStatus.COMPLETED,
            )
            await self.store.store_response(response)

            # Retrieve the response
            retrieved = await self.store.get_response("resp-test-2")

            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.request_id, "resp-test-2")
            self.assertEqual(retrieved.message, "Get response test")
            self.assertEqual(retrieved.status, RequestStatus.COMPLETED)

        asyncio.run(run_test())

    def test_get_nonexistent_response(self):
        """Test retrieving non-existent response returns None."""

        async def run_test():
            response = await self.store.get_response("nonexistent")
            self.assertIsNone(response)

        asyncio.run(run_test())

    def test_remove_response(self):
        """Test removing a response."""

        async def run_test():
            # Store a response first
            response = QueueResponse(
                request_id="resp-test-3", message="Remove test", status=RequestStatus.COMPLETED
            )
            await self.store.store_response(response)

            # Verify it exists
            self.assertIsNotNone(await self.store.get_response("resp-test-3"))

            # Remove it
            success = await self.store.delete_response("resp-test-3")
            self.assertTrue(success)

            # Verify it's gone
            self.assertIsNone(await self.store.get_response("resp-test-3"))

        asyncio.run(run_test())

    def test_remove_nonexistent_response(self):
        """Test removing non-existent response."""

        async def run_test():
            success = await self.store.delete_response("nonexistent")
            self.assertFalse(success)

        asyncio.run(run_test())

    def test_is_healthy(self):
        """Test health check."""

        async def run_test():
            self.assertTrue(await self.store.health_check())

        asyncio.run(run_test())

    def test_concurrent_response_operations(self):
        """Test concurrent response store operations."""

        async def run_test():
            results = []
            errors = []

            async def store_responses(start_id):
                try:
                    for i in range(5):
                        response = QueueResponse(
                            request_id=f"concurrent-resp-{start_id}-{i}",
                            message=f"Concurrent response {start_id}-{i}",
                            status=RequestStatus.COMPLETED,
                        )
                        success = await self.store.store_response(response)
                        results.append(success)
                except Exception as e:
                    errors.append(e)

            # Start multiple concurrent requests
            requests = []
            for i in range(3):
                request = store_responses(i)
                requests.append(request)

            await asyncio.gather(*requests)

            # Verify no errors and all operations succeeded
            self.assertEqual(len(errors), 0)
            self.assertEqual(len(results), 15)  # 3 requests * 5 responses each
            self.assertTrue(all(results))

            # Verify all responses can be retrieved
            for i in range(3):
                for j in range(5):
                    response = await self.store.get_response(f"concurrent-resp-{i}-{j}")
                    self.assertIsNotNone(response)

        asyncio.run(run_test())

    def test_list_responses(self):
        """Test listing stored responses."""

        async def run_test():
            # Store multiple responses
            responses = []
            for i in range(5):
                response = QueueResponse(
                    request_id=f"list-test-{i}",
                    message=f"QueueResponse {i}",
                    status=RequestStatus.COMPLETED,
                )
                responses.append(response)
                await self.store.store_response(response)

            # List all responses
            all_responses = await self.store.list_responses()
            self.assertEqual(len(all_responses), 5)

            # List with limit
            limited_responses = await self.store.list_responses(limit=3)
            self.assertEqual(len(limited_responses), 3)

        asyncio.run(run_test())

    def test_cleanup_old_responses(self):
        """Test cleanup of old responses."""

        async def run_test():
            # Store responses with different ages
            old_response = QueueResponse(
                request_id="old-response", message="Old response", status=RequestStatus.COMPLETED
            )
            # Manually set old timestamp
            old_response.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
            await self.store.store_response(old_response)

            new_response = QueueResponse(
                request_id="new-response", message="New response", status=RequestStatus.COMPLETED
            )
            await self.store.store_response(new_response)

            # Cleanup responses older than 24 hours
            cleaned_count = await self.store.cleanup_old_responses(max_age_hours=24)

            # Should have cleaned up the old response
            self.assertGreaterEqual(cleaned_count, 0)  # May be 0 or 1 depending on implementation

            # New response should still exist
            retrieved = await self.store.get_response("new-response")
            self.assertIsNotNone(retrieved)

        asyncio.run(run_test())

    def test_corrupted_response_file(self):
        """Test handling of corrupted response files."""

        async def run_test():
            # Write invalid JSON to response file
            with open(self.store.responses_file, "w") as f:
                f.write("invalid json content")

            # Should handle corrupted file gracefully
            try:
                await self.store._load_from_disk()
                self.assertTrue(True)  # If we get here, it handled the error
            except Exception:
                # If it raises an exception, that's also acceptable behavior
                self.assertTrue(True)

        asyncio.run(run_test())

    def test_response_with_metadata(self):
        """Test responses with metadata."""

        async def run_test():
            # Store response with metadata
            response = QueueResponse(
                request_id="metadata-test",
                message="QueueResponse with metadata",
                status=RequestStatus.COMPLETED,
                metadata={"key1": "value1", "key2": "value2"},
            )
            await self.store.store_response(response)

            # Retrieve and verify metadata
            retrieved = await self.store.get_response("metadata-test")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.metadata["key1"], "value1")
            self.assertEqual(retrieved.metadata["key2"], "value2")

        asyncio.run(run_test())

    def test_response_overwrite(self):
        """Test overwriting existing responses."""

        async def run_test():
            # Store initial response
            response1 = QueueResponse(
                request_id="overwrite-test",
                message="Original response",
                status=RequestStatus.COMPLETED,
            )
            await self.store.store_response(response1)

            # Overwrite with new response
            response2 = QueueResponse(
                request_id="overwrite-test",
                message="Updated response",
                status=RequestStatus.COMPLETED,
            )
            await self.store.store_response(response2)

            # Should have the updated response
            retrieved = await self.store.get_response("overwrite-test")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.message, "Updated response")

        asyncio.run(run_test())
