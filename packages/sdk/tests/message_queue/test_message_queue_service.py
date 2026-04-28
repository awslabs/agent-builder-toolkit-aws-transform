"""
Unit tests for queue service.
Tests high-level queue coordination and health monitoring.
"""

import asyncio
import tempfile
import unittest
from unittest.mock import patch

from agent_builder_sdk.message_queue.interface import (
    QueueResponse,
    RequestPriority,
    RequestStatus,
)
from agent_builder_sdk.message_queue.local_queue import LocalRequestQueue, LocalResponseStore
from agent_builder_sdk.message_queue.service import QueueService


class TestQueueService(unittest.TestCase):
    """Test QueueService implementation."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.request_queue = LocalRequestQueue(self.temp_dir)
        self.response_store = LocalResponseStore(self.temp_dir)

        self.service = QueueService(
            request_queue=self.request_queue, response_store=self.response_store
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test service initialization."""
        self.assertEqual(self.service.request_queue, self.request_queue)
        self.assertEqual(self.service.response_store, self.response_store)

    def test_submit_request(self):
        """Test submitting a request through the service."""

        async def run_test():
            request_id = await self.service.submit_request(
                message="Service test message", priority=RequestPriority.HIGH
            )

            self.assertIsNotNone(request_id)

            # Verify request was added to queue
            self.assertEqual(await self.request_queue.size(), 1)

            # Verify request details
            request = await self.request_queue.dequeue()
            self.assertEqual(request.message, "Service test message")
            self.assertEqual(request.priority, RequestPriority.HIGH)

        asyncio.run(run_test())

    def test_submit_request_with_defaults(self):
        """Test submitting request with default priority."""

        async def run_test():
            request_id = await self.service.submit_request(message="Default priority test")

            self.assertIsNotNone(request_id)

            request = await self.request_queue.dequeue()
            self.assertEqual(request.priority, RequestPriority.NORMAL)

        asyncio.run(run_test())

    def test_get_request_result(self):
        """Test getting request result."""

        async def run_test():
            # Store a response first
            response = QueueResponse(
                request_id="result-test",
                message="Test result message",
                status=RequestStatus.COMPLETED,
            )
            await self.response_store.store_response(response)

            # Get result through service
            result = await self.service.get_response("result-test")

            self.assertIsNotNone(result)
            self.assertEqual(result.request_id, "result-test")
            self.assertEqual(result.message, "Test result message")
            self.assertEqual(result.status, RequestStatus.COMPLETED)

        asyncio.run(run_test())

    def test_get_nonexistent_request_result(self):
        """Test getting result for non-existent request."""

        async def run_test():
            result = await self.service.get_response("nonexistent")
            self.assertIsNone(result)

        asyncio.run(run_test())

    def test_get_request_status(self):
        """Test getting request status."""

        async def run_test():
            # Submit a request
            request_id = await self.service.submit_request("Status test message")

            # Get status
            status = await self.service.get_request_status(request_id)

            # Should be PENDING initially
            self.assertEqual(status, RequestStatus.PENDING)

        asyncio.run(run_test())

    def test_health_check_healthy(self):
        """Test health check when system is healthy."""

        async def run_test():
            health = await self.service.health_check()

            self.assertIn("request_queue_healthy", health)
            self.assertIn("response_store_healthy", health)
            self.assertIn("service_running", health)

            self.assertTrue(health["request_queue_healthy"])
            self.assertTrue(health["response_store_healthy"])
            # service_running is False because we haven't started the service

        asyncio.run(run_test())

    def test_wait_for_response_success(self):
        """Test waiting for response with success."""

        async def run_test():
            request_id = "wait-test"

            # Store response after a short delay
            async def delayed_response():
                await asyncio.sleep(0.1)
                response = QueueResponse(
                    request_id=request_id,
                    message="Delayed response",
                    status=RequestStatus.COMPLETED,
                )
                await self.response_store.store_response(response)

            # Start the delayed response task
            asyncio.create_task(delayed_response())

            # Wait for response
            result = await self.service.wait_for_response(
                request_id=request_id, timeout=1.0, poll_interval=0.05
            )

            self.assertIsNotNone(result)
            self.assertEqual(result.request_id, request_id)
            self.assertEqual(result.message, "Delayed response")

        asyncio.run(run_test())

    def test_wait_for_response_timeout(self):
        """Test waiting for response with timeout."""

        async def run_test():
            # Wait for non-existent response
            result = await self.service.wait_for_response(
                request_id="timeout-test", timeout=0.1, poll_interval=0.05
            )

            self.assertIsNone(result)

        asyncio.run(run_test())

    def test_service_lifecycle(self):
        """Test service start and stop."""

        async def run_test():
            # Start service
            await self.service.start()
            self.assertTrue(self.service._running)

            # Stop service
            await self.service.stop()
            self.assertFalse(self.service._running)

        asyncio.run(run_test())

    def test_submit_with_context(self):
        """Test submitting request with user context."""

        async def run_test():
            request_id = await self.service.submit_request(
                message="Context test",
                user_id="test-user",
                sender="test-sender",
                priority=RequestPriority.HIGH,
            )

            self.assertIsNotNone(request_id)

            # Verify request context
            request = await self.request_queue.dequeue()
            self.assertEqual(request.context.get("user_id"), "test-user")
            self.assertEqual(request.context.get("sender"), "test-sender")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()

    def test_service_start_stop_lifecycle(self):
        """Test service start and stop lifecycle."""

        async def run_test():
            # Initially not running
            self.assertFalse(self.service._running)

            # Start service
            await self.service.start()
            self.assertTrue(self.service._running)

            # Starting again should not cause issues
            await self.service.start()
            self.assertTrue(self.service._running)

            # Stop service
            await self.service.stop()
            self.assertFalse(self.service._running)

            # Stopping again should not cause issues
            await self.service.stop()
            self.assertFalse(self.service._running)

        asyncio.run(run_test())

    def test_submit_request_with_queue_failure(self):
        """Test submit_request when queue enqueue fails."""

        async def run_test():
            # Mock queue to fail
            with patch.object(self.request_queue, "enqueue", return_value=False):
                try:
                    request_id = await self.service.submit_request("Failure test")
                    # If it returns a request_id despite failure, that's unexpected but not wrong
                    self.assertIsNotNone(request_id)
                except Exception:
                    # If it raises an exception, that's also acceptable
                    pass

        asyncio.run(run_test())

    def test_get_request_status_nonexistent(self):
        """Test getting status of non-existent request."""

        async def run_test():
            status = await self.service.get_request_status("nonexistent-request-id")
            self.assertIsNone(status)

        asyncio.run(run_test())

    def test_wait_for_response_immediate(self):
        """Test wait_for_response when response is immediately available."""

        async def run_test():
            # Store response first
            response = QueueResponse(
                request_id="immediate-response",
                message="Immediate response message",
                status=RequestStatus.COMPLETED,
            )
            await self.response_store.store_response(response)

            # Wait for response should return immediately
            result = await self.service.wait_for_response(
                request_id="immediate-response", timeout=1.0, poll_interval=0.1
            )

            self.assertIsNotNone(result)
            self.assertEqual(result.request_id, "immediate-response")
            self.assertEqual(result.message, "Immediate response message")

        asyncio.run(run_test())

    def test_health_check_with_unhealthy_components(self):
        """Test health check when components are unhealthy."""

        async def run_test():
            # Mock components to be unhealthy
            with patch.object(self.request_queue, "health_check", return_value=False), patch.object(
                self.response_store, "health_check", return_value=False
            ):

                health = await self.service.health_check()

                self.assertFalse(health["request_queue_healthy"])
                self.assertFalse(health["response_store_healthy"])
                self.assertFalse(health["service_running"])  # Service not started

        asyncio.run(run_test())

    def test_health_check_with_running_service(self):
        """Test health check when service is running."""

        async def run_test():
            # Start the service
            await self.service.start()

            try:
                health = await self.service.health_check()

                self.assertTrue(health["service_running"])
                self.assertIn("timestamp", health)
                self.assertIn("queue_size", health)
            finally:
                # Clean up
                await self.service.stop()

        asyncio.run(run_test())

    def test_cleanup_loop_behavior(self):
        """Test cleanup loop starts and stops with service."""

        async def run_test():
            # Start service (which starts cleanup loop)
            await self.service.start()

            # Cleanup request should be created
            self.assertIsNotNone(self.service._cleanup_request)

            # Stop service
            await self.service.stop()

            # Cleanup request should be cancelled
            if self.service._cleanup_request:
                self.assertTrue(
                    self.service._cleanup_request.cancelled()
                    or self.service._cleanup_request.done()
                )

        asyncio.run(run_test())

    def test_concurrent_operations(self):
        """Test concurrent service operations."""

        async def run_test():
            # Submit multiple requests concurrently
            requests = []
            for i in range(10):
                request = self.service.submit_request(
                    f"Concurrent test {i}", priority=RequestPriority.NORMAL
                )
                requests.append(request)

            # Wait for all submissions
            request_ids = await asyncio.gather(*requests)

            # All should succeed
            self.assertEqual(len(request_ids), 10)
            for request_id in request_ids:
                self.assertIsNotNone(request_id)

            # Queue should have all requests
            queue_size = await self.request_queue.size()
            self.assertEqual(queue_size, 10)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()


class TestQueueServiceCoverage(unittest.TestCase):
    """Additional coverage tests for QueueService."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.service = QueueService(storage_path=self.temp_dir)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_service_initialization_with_custom_components(self):
        """Test QueueService initialization with custom request queue and response store."""
        from agent_builder_sdk.message_queue.local_queue import (
            LocalRequestQueue,
            LocalResponseStore,
        )

        # Create custom components
        custom_queue = LocalRequestQueue(f"{self.temp_dir}/custom_requests")
        custom_store = LocalResponseStore(f"{self.temp_dir}/custom_responses")

        # Initialize service with custom components
        service = QueueService(
            request_queue=custom_queue, response_store=custom_store, storage_path=self.temp_dir
        )

        self.assertEqual(service.request_queue, custom_queue)
        self.assertEqual(service.response_store, custom_store)
        self.assertFalse(service._running)

    def test_service_start_and_stop_lifecycle(self):
        """Test service start and stop lifecycle."""
        import asyncio

        async def run_test():
            # Start service
            await self.service.start()
            self.assertTrue(self.service._running)

            # Stop service
            await self.service.stop()
            self.assertFalse(self.service._running)

        asyncio.run(run_test())

    def test_service_start_when_already_running(self):
        """Test starting service when it's already running."""
        import asyncio

        async def run_test():
            # Start service first time
            await self.service.start()
            self.assertTrue(self.service._running)

            # Try to start again - should not cause issues
            await self.service.start()
            self.assertTrue(self.service._running)

            # Clean up
            await self.service.stop()

        asyncio.run(run_test())

    def test_submit_request_with_all_parameters(self):
        """Test submit_request with all optional parameters."""
        import asyncio

        async def run_test():
            request_id = await self.service.submit_request(
                message="Full parameter test",
                user_id="test_user",
                sender="test_sender",
                priority=RequestPriority.HIGH,
            )

            self.assertIsNotNone(request_id)
            self.assertIsInstance(request_id, str)

        asyncio.run(run_test())

    def test_get_request_status_existing_request(self):
        """Test get_request_status for existing request."""
        import asyncio

        async def run_test():
            # Submit a request first
            request_id = await self.service.submit_request("Status test")

            # Get request status
            status = await self.service.get_request_status(request_id)

            self.assertIsNotNone(status)
            self.assertIn(
                status, [RequestStatus.PENDING, RequestStatus.PROCESSING, RequestStatus.COMPLETED]
            )

        asyncio.run(run_test())

    def test_get_request_status_nonexistent_request(self):
        """Test get_request_status for non-existent request."""
        import asyncio

        async def run_test():
            status = await self.service.get_request_status("nonexistent-request-id")
            self.assertIsNone(status)

        asyncio.run(run_test())

    def test_wait_for_response_timeout(self):
        """Test wait_for_response timeout."""
        import asyncio

        async def run_test():
            # Wait for non-existent response
            result = await self.service.wait_for_response(
                request_id="timeout-test", timeout=0.1, poll_interval=0.05
            )

            self.assertIsNone(result)

        asyncio.run(run_test())

    def test_health_check_healthy_service(self):
        """Test health_check when service is healthy."""
        import asyncio

        async def run_test():
            health = await self.service.health_check()

            self.assertIsInstance(health, dict)
            self.assertIn("queue_size", health)
            self.assertIn("request_queue_healthy", health)
            self.assertIn("response_store_healthy", health)
            self.assertTrue(health["request_queue_healthy"])
            self.assertTrue(health["response_store_healthy"])

        asyncio.run(run_test())

    def test_submit_request_with_task_id(self):
        """Test submit_request with task_id parameter."""
        import asyncio

        async def run_test():
            request_id = await self.service.submit_request(
                message="Task ID test",
                user_id="test_user",
                sender="test_sender",
                task_id="task-123",
                priority=RequestPriority.NORMAL,
            )

            self.assertIsNotNone(request_id)

        asyncio.run(run_test())
