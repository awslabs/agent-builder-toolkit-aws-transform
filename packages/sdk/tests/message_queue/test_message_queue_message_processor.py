"""
Unit tests for queue request handler.
Tests integration between queue system and request processing.
"""

import asyncio
import tempfile
import unittest
from unittest.mock import patch

from agent_builder_sdk.message_queue.interface import (
    QueueRequest,
    RequestPriority,
    RequestStatus,
)
from agent_builder_sdk.message_queue.local_queue import LocalRequestQueue, LocalResponseStore
from agent_builder_sdk.request_handler import QueueRequestHandler


class TestQueueRequestHandler(unittest.TestCase):
    """Test QueueRequestHandler implementation."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.request_queue = LocalRequestQueue(self.temp_dir)
        self.response_store = LocalResponseStore(self.temp_dir)

        self.handler = QueueRequestHandler(
            request_queue=self.request_queue, response_store=self.response_store
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test handler initialization."""
        self.assertEqual(self.handler.request_queue, self.request_queue)
        self.assertEqual(self.handler.response_store, self.response_store)
        self.assertIsNone(self.handler._current_request)

    def test_receive_message_success(self):
        """Test receiving a message successfully."""

        async def run_test():
            # Add a request to the queue
            request = QueueRequest(message="Test message", priority=RequestPriority.HIGH)
            await self.request_queue.enqueue(request)

            # Receive the message
            message_data = await self.handler.receive_request()

            self.assertIsNotNone(message_data)
            self.assertEqual(message_data["message"], "Test message")
            self.assertEqual(message_data["priority"], RequestPriority.HIGH.value)
            self.assertIsNotNone(self.handler._current_request)

        asyncio.run(run_test())

    def test_receive_message_empty_queue(self):
        """Test receiving message when queue is empty."""

        async def run_test():
            # Try to receive from empty queue
            message_data = await self.handler.receive_request()

            self.assertIsNone(message_data)
            self.assertIsNone(self.handler._current_request)

        asyncio.run(run_test())

    def test_send_message_success(self):
        """Test sending a message (storing response) successfully."""

        async def run_test():
            # Set up a current request
            request = QueueRequest(message="Response test", priority=RequestPriority.NORMAL)
            self.handler._current_request = request

            # Send response
            success = await self.handler.store_response("Test response content")

            self.assertTrue(success)

            # Verify response was stored
            response = await self.response_store.get_response(request.request_id)
            self.assertIsNotNone(response)
            self.assertEqual(response.message, "Test response content")
            self.assertEqual(response.status, RequestStatus.COMPLETED)

        asyncio.run(run_test())

    def test_send_message_no_current_request(self):
        """Test sending message when no current request."""

        async def run_test():
            # Try to send without current request
            success = await self.handler.store_response("No request response")

            self.assertFalse(success)

        asyncio.run(run_test())

    def test_handle_request_error(self):
        """Test handling request error."""

        async def run_test():
            # Set up a current request
            request = QueueRequest(message="Error test", priority=RequestPriority.NORMAL)
            self.handler._current_request = request

            # Handle error
            test_error = Exception("Test error message")
            success = await self.handler.handle_request_error(test_error)

            self.assertTrue(success)

            # Verify error response was stored
            response = await self.response_store.get_response(request.request_id)
            self.assertIsNotNone(response)
            self.assertEqual(response.status, RequestStatus.FAILED)
            self.assertIn("Test error message", response.error_message)

        asyncio.run(run_test())

    def test_handle_request_timeout(self):
        """Test handling request timeout."""

        async def run_test():
            # Set up a current request
            request = QueueRequest(message="Timeout test", priority=RequestPriority.NORMAL)
            self.handler._current_request = request

            # Handle timeout
            success = await self.handler.handle_request_timeout()

            self.assertTrue(success)

            # Verify timeout response was stored
            response = await self.response_store.get_response(request.request_id)
            self.assertIsNotNone(response)
            self.assertEqual(response.status, RequestStatus.TIMEOUT)

        asyncio.run(run_test())

    def test_process_multiple_requests(self):
        """Test processing multiple requests in sequence."""

        async def run_test():
            # Add multiple requests
            requests = []
            for i in range(3):
                request = QueueRequest(message=f"Multi test {i}", priority=RequestPriority.NORMAL)
                requests.append(request)
                await self.request_queue.enqueue(request)

            # Process each request
            for i in range(3):
                # Receive message
                message_data = await self.handler.receive_request()
                self.assertIsNotNone(message_data)
                self.assertEqual(message_data["message"], f"Multi test {i}")

                # Send response
                success = await self.handler.store_response(f"Response {i}")
                self.assertTrue(success)

            # Verify all responses were stored
            for i, request in enumerate(requests):
                response = await self.response_store.get_response(request.request_id)
                self.assertIsNotNone(response)
                self.assertEqual(response.message, f"Response {i}")

        asyncio.run(run_test())

    def test_request_status_updates(self):
        """Test that request status is updated during processing."""

        async def run_test():
            # Add a request
            request = QueueRequest(message="Status update test", priority=RequestPriority.NORMAL)
            await self.request_queue.enqueue(request)

            # Receive the request
            message_data = await self.handler.receive_request()
            self.assertIsNotNone(message_data)

            # Task should be marked as processing
            current_request = self.handler._current_request
            self.assertIsNotNone(current_request)

            # Send response (completes the request)
            success = await self.handler.store_response("Status test response")
            self.assertTrue(success)

            # Verify final response status
            response = await self.response_store.get_response(request.request_id)
            self.assertEqual(response.status, RequestStatus.COMPLETED)

        asyncio.run(run_test())

    def test_error_handling_preserves_queue_state(self):
        """Test that errors don't corrupt the queue state."""

        async def run_test():
            # Add multiple requests
            for i in range(3):
                request = QueueRequest(
                    message=f"Error preserve test {i}", priority=RequestPriority.NORMAL
                )
                await self.request_queue.enqueue(request)

            # Process first request successfully
            message_data = await self.handler.receive_request()
            self.assertIsNotNone(message_data)
            await self.handler.store_response("Success response")

            # Process second request with error
            message_data = await self.handler.receive_request()
            self.assertIsNotNone(message_data)
            await self.handler.handle_request_error(Exception("Test error"))

            # Process third request successfully
            message_data = await self.handler.receive_request()
            self.assertIsNotNone(message_data)
            await self.handler.store_response("Another success")

            # Verify queue is empty
            message_data = await self.handler.receive_request()
            self.assertIsNone(message_data)

        asyncio.run(run_test())

    def test_receive_message_with_exception(self):
        """Test receive_message when queue raises exception."""

        async def run_test():
            # Mock queue to raise exception
            with patch.object(self.request_queue, "dequeue", side_effect=Exception("Queue error")):
                message_data = await self.handler.receive_request()
                self.assertIsNone(message_data)

        asyncio.run(run_test())

    def test_send_message_with_store_failure(self):
        """Test send_message when response store fails."""

        async def run_test():
            # Set up current request
            request = QueueRequest(message="Store failure test", priority=RequestPriority.NORMAL)
            self.handler._current_request = request

            # Mock store to fail
            with patch.object(
                self.response_store, "store_response", side_effect=Exception("Store error")
            ):
                success = await self.handler.store_response("Test response")
                self.assertFalse(success)

        asyncio.run(run_test())

    def test_handle_request_error_without_current_request(self):
        """Test handle_request_error when no current request."""

        async def run_test():
            # No current request set
            self.handler._current_request = None

            success = await self.handler.handle_request_error(Exception("Test error"))
            self.assertFalse(success)

        asyncio.run(run_test())

    def test_handle_request_timeout_without_current_request(self):
        """Test handle_request_timeout when no current request."""

        async def run_test():
            # No current request set
            self.handler._current_request = None

            success = await self.handler.handle_request_timeout()
            self.assertFalse(success)

        asyncio.run(run_test())

    def test_handle_request_error_with_store_failure(self):
        """Test handle_request_error when response store fails."""

        async def run_test():
            # Set up current request
            request = QueueRequest(message="Error handling test", priority=RequestPriority.NORMAL)
            self.handler._current_request = request

            # Mock store to fail
            with patch.object(
                self.response_store, "store_response", side_effect=Exception("Store error")
            ):
                success = await self.handler.handle_request_error(Exception("Original error"))
                self.assertFalse(success)

        asyncio.run(run_test())

    def test_handle_request_timeout_with_store_failure(self):
        """Test handle_request_timeout when response store fails."""

        async def run_test():
            # Set up current request
            request = QueueRequest(message="Timeout handling test", priority=RequestPriority.NORMAL)
            self.handler._current_request = request

            # Mock store to fail
            with patch.object(
                self.response_store, "store_response", side_effect=Exception("Store error")
            ):
                success = await self.handler.handle_request_timeout()
                self.assertFalse(success)

        asyncio.run(run_test())


class TestQueueRequestHandlerCoverage(unittest.TestCase):
    """Additional coverage tests for QueueRequestHandler."""

    def setUp(self):
        """Set up test environment."""
        import tempfile
        from unittest.mock import Mock

        self.temp_dir = tempfile.mkdtemp()
        self.mock_request_queue = Mock()
        self.mock_response_store = Mock()
        self.handler = QueueRequestHandler(
            request_queue=self.mock_request_queue, response_store=self.mock_response_store
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_send_message_with_recipient(self):
        """Test send_message with recipient_id parameter when no current request."""
        import asyncio

        async def run_test():
            # Test that send_message returns False when no current request is set
            result = await self.handler.store_response(
                message="Message to recipient", recipient_id="recipient_123"
            )

            # Should return False because there's no current request
            self.assertFalse(result)

        asyncio.run(run_test())

    def test_send_message_with_current_request(self):
        """Test send_message when there is a current request."""
        import asyncio
        from unittest.mock import AsyncMock

        from agent_builder_sdk.message_queue.interface import QueueRequest, RequestPriority

        async def run_test():
            # Create a mock request
            mock_request = QueueRequest(
                message="Test request",
                priority=RequestPriority.NORMAL,
                request_id="test-request-123",
            )

            # Mock request queue to return the request
            self.mock_request_queue.dequeue = AsyncMock(return_value=mock_request)

            # Mock response store
            self.mock_response_store.store_response = AsyncMock(return_value=True)

            # Mock request queue update_request_status
            self.mock_request_queue.update_request_status = AsyncMock(return_value=True)

            # First receive a message to set current request
            received = await self.handler.receive_request()
            self.assertIsNotNone(received)

            # Now send_message should work
            result = await self.handler.store_response(
                message="Response message", recipient_id="recipient_123"
            )

            self.assertTrue(result)
            self.mock_response_store.store_response.assert_called_once()

        asyncio.run(run_test())

    def test_send_message_failure(self):
        """Test send_message when response storage fails."""
        import asyncio
        from unittest.mock import AsyncMock

        from agent_builder_sdk.message_queue.interface import QueueRequest, RequestPriority

        async def run_test():
            # Create a mock request
            mock_request = QueueRequest(
                message="Test request",
                priority=RequestPriority.NORMAL,
                request_id="test-request-456",
            )

            # Mock request queue to return the request
            self.mock_request_queue.dequeue = AsyncMock(return_value=mock_request)

            # Mock response store to fail
            self.mock_response_store.store_response = AsyncMock(return_value=False)

            # Mock request queue update_request_status
            self.mock_request_queue.update_request_status = AsyncMock(return_value=True)

            # First receive a message to set current request
            received = await self.handler.receive_request()
            self.assertIsNotNone(received)

            # Now send_message should fail due to storage failure
            result = await self.handler.store_response("Failed message")

            self.assertFalse(result)
            self.mock_response_store.store_response.assert_called_once()

        asyncio.run(run_test())
