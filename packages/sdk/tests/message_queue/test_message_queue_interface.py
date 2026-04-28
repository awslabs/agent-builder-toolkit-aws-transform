"""
Unit tests for queue interface module.
Tests the abstract base classes and data models.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from agent_builder_sdk.message_queue.interface import (
    QueueRequest,
    QueueResponse,
    RequestPriority,
    RequestQueue,
    RequestStatus,
    ResponseStore,
)


class TestRequest(unittest.TestCase):
    """Test QueueRequest data model."""

    def test_request_creation(self):
        """Test creating a request with all fields."""
        request = QueueRequest(
            request_id="test-123",
            message="Test message",
            priority=RequestPriority.HIGH,
            retry_count=0,
            max_retries=3,
            status=RequestStatus.PENDING,
        )

        self.assertEqual(request.request_id, "test-123")
        self.assertEqual(request.message, "Test message")
        self.assertEqual(request.priority, RequestPriority.HIGH)
        self.assertEqual(request.retry_count, 0)
        self.assertEqual(request.max_retries, 3)
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertIsInstance(request.created_at, datetime)

    def test_request_defaults(self):
        """Test request creation with default values."""
        request = QueueRequest(message="Another test")

        self.assertEqual(request.retry_count, 0)
        self.assertEqual(request.max_retries, 3)
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.priority, RequestPriority.NORMAL)
        self.assertIsNotNone(request.request_id)  # Auto-generated UUID

    def test_request_to_dict(self):
        """Test converting request to dictionary."""
        request = QueueRequest(message="Dict test", priority=RequestPriority.URGENT)

        request_dict = request.to_dict()

        self.assertEqual(request_dict["request_id"], request.request_id)
        self.assertEqual(request_dict["message"], "Dict test")
        self.assertEqual(request_dict["priority"], RequestPriority.URGENT.value)
        self.assertIn("created_at", request_dict)

    def test_request_from_dict(self):
        """Test creating request from dictionary."""
        request_data = {
            "request_id": "test-dict",
            "message": "From dict",
            "context": {"user_id": "test-user"},
            "priority": RequestPriority.LOW.value,
            "status": RequestStatus.PROCESSING.value,
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:00:00",
            "retry_count": 2,
            "max_retries": 5,
        }

        request = QueueRequest.from_dict(request_data)

        self.assertEqual(request.request_id, "test-dict")
        self.assertEqual(request.message, "From dict")
        self.assertEqual(request.context, {"user_id": "test-user"})
        self.assertEqual(request.priority, RequestPriority.LOW)
        self.assertEqual(request.retry_count, 2)
        self.assertEqual(request.max_retries, 5)
        self.assertEqual(request.status, RequestStatus.PROCESSING)

    def test_request_serialization_edge_cases(self):
        """Test request serialization with edge cases."""
        # request with all optional fields
        request = QueueRequest(
            request_id="edge-case-request",
            message="Edge case test",
            context={"nested": {"data": "value"}},
            priority=RequestPriority.URGENT,
            status=RequestStatus.PROCESSING,
            error_message="Test error",
            retry_count=2,
            max_retries=5,
        )

        # Set optional datetime fields
        request.started_at = datetime.now(timezone.utc)
        request.completed_at = datetime.now(timezone.utc)

        # Test to_dict
        request_dict = request.to_dict()
        self.assertIn("started_at", request_dict)
        self.assertIn("completed_at", request_dict)
        self.assertEqual(request_dict["error_message"], "Test error")
        self.assertEqual(request_dict["retry_count"], 2)
        self.assertEqual(request_dict["max_retries"], 5)

        # Test from_dict with all fields
        reconstructed = request.from_dict(request_dict)
        self.assertEqual(reconstructed.request_id, request.request_id)
        self.assertEqual(reconstructed.error_message, request.error_message)
        self.assertEqual(reconstructed.retry_count, request.retry_count)
        self.assertEqual(reconstructed.max_retries, request.max_retries)

    def test_request_from_dict_with_optional_fields(self):
        """Test request.from_dict with optional datetime fields."""
        request_data = {
            "request_id": "optional-fields-test",
            "message": "Test with optional fields",
            "context": {},
            "priority": RequestPriority.NORMAL.value,
            "status": RequestStatus.COMPLETED.value,
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:30:00",
            "started_at": "2024-01-01T12:05:00",
            "completed_at": "2024-01-01T12:25:00",
            "error_message": "Optional error",
            "retry_count": 1,
            "max_retries": 3,
        }

        request = QueueRequest.from_dict(request_data)
        self.assertIsNotNone(request.started_at)
        self.assertIsNotNone(request.completed_at)
        self.assertEqual(request.error_message, "Optional error")

    def test_request_default_values(self):
        """Test request creation with various default values."""
        # Minimal request
        request = QueueRequest(message="Minimal request")

        # Check defaults
        self.assertIsNotNone(request.request_id)  # Auto-generated
        self.assertEqual(request.priority, RequestPriority.NORMAL)
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.retry_count, 0)
        self.assertEqual(request.max_retries, 3)
        self.assertEqual(request.context, {})
        self.assertIsNone(request.started_at)
        self.assertIsNone(request.completed_at)
        self.assertIsNone(request.error_message)
        self.assertIsInstance(request.created_at, datetime)
        self.assertIsInstance(request.updated_at, datetime)


class TestResponse(unittest.TestCase):
    """Test QueueResponse data model."""

    def test_response_creation(self):
        """Test creating a request response."""
        response = QueueResponse(
            request_id="request-123",
            message="QueueResponse message",
            status=RequestStatus.COMPLETED,
        )

        self.assertEqual(response.request_id, "request-123")
        self.assertEqual(response.message, "QueueResponse message")
        self.assertEqual(response.status, RequestStatus.COMPLETED)
        self.assertIsInstance(response.created_at, datetime)

    def test_response_defaults(self):
        """Test response creation with defaults."""
        response = QueueResponse(request_id="request-456", message="Default test")

        self.assertEqual(response.status, RequestStatus.COMPLETED)
        self.assertEqual(response.metadata, {})
        self.assertIsNone(response.error_message)

    def test_response_to_dict(self):
        """Test converting response to dictionary."""
        response = QueueResponse(
            request_id="request-789", message="Dict response", status=RequestStatus.FAILED
        )

        response_dict = response.to_dict()

        self.assertEqual(response_dict["request_id"], "request-789")
        self.assertEqual(response_dict["message"], "Dict response")
        self.assertEqual(response_dict["status"], RequestStatus.FAILED.value)
        self.assertIn("created_at", response_dict)

    def test_response_from_dict(self):
        """Test creating response from dictionary."""
        response_data = {
            "request_id": "request-dict",
            "context_id": "1",
            "task_id": "task-456",
            "message": "From dict response",
            "status": RequestStatus.FAILED.value,
            "created_at": "2024-01-01T12:00:00",
            "metadata": {"key": "value"},
            "error_message": "Test error",
        }

        response = QueueResponse.from_dict(response_data)

        self.assertEqual(response.request_id, "request-dict")
        self.assertEqual(response.context_id, "1")
        self.assertEqual(response.task_id, "task-456")
        self.assertEqual(response.message, "From dict response")
        self.assertEqual(response.status, RequestStatus.FAILED)
        self.assertEqual(response.metadata, {"key": "value"})
        self.assertEqual(response.error_message, "Test error")

    def test_request_response_serialization_edge_cases(self):
        """Test QueueResponse serialization with edge cases."""
        response = QueueResponse(
            request_id="response-edge-case",
            message="Edge case response",
            status=RequestStatus.FAILED,
            metadata={"complex": {"nested": {"data": [1, 2, 3]}}},
            error_message="Complex error message",
        )

        # Test to_dict
        response_dict = response.to_dict()
        self.assertEqual(response_dict["status"], RequestStatus.FAILED.value)
        self.assertEqual(response_dict["error_message"], "Complex error message")
        self.assertIn("complex", response_dict["metadata"])

        # Test from_dict
        reconstructed = QueueResponse.from_dict(response_dict)
        self.assertEqual(reconstructed.request_id, response.request_id)
        self.assertEqual(reconstructed.status, RequestStatus.FAILED)
        self.assertEqual(reconstructed.error_message, "Complex error message")
        self.assertEqual(reconstructed.metadata["complex"]["nested"]["data"], [1, 2, 3])

    def test_request_response_from_dict_minimal(self):
        """Test QueueResponse.from_dict with minimal required fields."""
        response_data = {
            "request_id": "minimal-response",
            "message": "Minimal response",
            "status": RequestStatus.COMPLETED.value,
            "created_at": "2024-01-01T12:00:00",
        }

        response = QueueResponse.from_dict(response_data)
        self.assertEqual(response.request_id, "minimal-response")
        self.assertEqual(response.message, "Minimal response")
        self.assertEqual(response.status, RequestStatus.COMPLETED)
        self.assertEqual(response.metadata, {})  # Default empty dict
        self.assertIsNone(response.error_message)  # Default None

    def test_request_response_default_values(self):
        """Test request response creation with default values."""
        response = QueueResponse(request_id="default-test", message="Default response")

        # Check defaults
        self.assertEqual(response.status, RequestStatus.COMPLETED)
        self.assertEqual(response.metadata, {})
        self.assertIsNone(response.error_message)
        self.assertIsInstance(response.created_at, datetime)


class TestRequestPriority(unittest.TestCase):
    """Test RequestPriority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        self.assertEqual(RequestPriority.URGENT.value, 4)
        self.assertEqual(RequestPriority.HIGH.value, 3)
        self.assertEqual(RequestPriority.NORMAL.value, 2)
        self.assertEqual(RequestPriority.LOW.value, 1)

    def test_priority_ordering(self):
        """Test priority ordering for queue processing."""
        priorities = [
            RequestPriority.LOW,
            RequestPriority.URGENT,
            RequestPriority.NORMAL,
            RequestPriority.HIGH,
        ]
        sorted_priorities = sorted(priorities, key=lambda p: p.value, reverse=True)

        expected = [
            RequestPriority.URGENT,
            RequestPriority.HIGH,
            RequestPriority.NORMAL,
            RequestPriority.LOW,
        ]
        self.assertEqual(sorted_priorities, expected)

    def test_priority_comparison(self):
        """Test priority enum comparison and ordering."""
        priorities = [
            RequestPriority.LOW,
            RequestPriority.URGENT,
            RequestPriority.NORMAL,
            RequestPriority.HIGH,
        ]

        # Sort by value (descending for priority)
        sorted_priorities = sorted(priorities, key=lambda p: p.value, reverse=True)

        expected_order = [
            RequestPriority.URGENT,
            RequestPriority.HIGH,
            RequestPriority.NORMAL,
            RequestPriority.LOW,
        ]
        self.assertEqual(sorted_priorities, expected_order)

        # Test individual comparisons
        self.assertGreater(RequestPriority.URGENT.value, RequestPriority.HIGH.value)
        self.assertGreater(RequestPriority.HIGH.value, RequestPriority.NORMAL.value)
        self.assertGreater(RequestPriority.NORMAL.value, RequestPriority.LOW.value)


class TestRequestStatus(unittest.TestCase):
    """Test RequestStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        self.assertEqual(RequestStatus.PENDING.value, "pending")
        self.assertEqual(RequestStatus.PROCESSING.value, "processing")
        self.assertEqual(RequestStatus.COMPLETED.value, "completed")
        self.assertEqual(RequestStatus.FAILED.value, "failed")
        self.assertEqual(RequestStatus.TIMEOUT.value, "timeout")

    def test_status_enum_values(self):
        """Test all status enum values."""
        all_statuses = [
            RequestStatus.PENDING,
            RequestStatus.PROCESSING,
            RequestStatus.COMPLETED,
            RequestStatus.FAILED,
            RequestStatus.TIMEOUT,
        ]

        # All should have string values
        for status in all_statuses:
            self.assertIsInstance(status.value, str)
            self.assertGreater(len(status.value), 0)

        # Test specific values
        self.assertEqual(RequestStatus.PENDING.value, "pending")
        self.assertEqual(RequestStatus.PROCESSING.value, "processing")
        self.assertEqual(RequestStatus.COMPLETED.value, "completed")
        self.assertEqual(RequestStatus.FAILED.value, "failed")
        self.assertEqual(RequestStatus.TIMEOUT.value, "timeout")


class TestRequestQueue(unittest.TestCase):
    """Test RequestQueue abstract base class."""

    def test_abstract_methods(self):
        """Test that RequestQueue cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            RequestQueue()


class TestResponseStore(unittest.TestCase):
    """Test ResponseStore abstract base class."""

    def test_abstract_methods(self):
        """Test that ResponseStore cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            ResponseStore()


class TestAbstractClasses(unittest.TestCase):
    """Test abstract class behavior."""

    def test_abstract_class_instantiation_errors(self):
        """Test that abstract classes cannot be instantiated."""
        # RequestQueue is abstract
        with self.assertRaises(TypeError):
            RequestQueue()

        # ResponseStore is abstract
        with self.assertRaises(TypeError):
            ResponseStore()


if __name__ == "__main__":
    unittest.main()


class TestInterfaceCoverage(unittest.TestCase):
    """Tests to improve coverage of interface classes."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_queue_interface_method_coverage(self):
        """Test queue interface methods to improve coverage."""
        import asyncio

        async def run_test():
            from agent_builder_sdk.message_queue.local_queue import LocalRequestQueue

            queue = LocalRequestQueue(self.temp_dir)

            # Test that interface methods work
            request = QueueRequest(message="test", priority=RequestPriority.NORMAL)

            # Test enqueue
            result = await queue.enqueue(request)
            self.assertTrue(result)

            # Test peek (should not remove request)
            peeked = await queue.peek()
            self.assertIsNotNone(peeked)
            self.assertEqual(peeked.message, "test")

            # Test dequeue (should remove request)
            dequeued = await queue.dequeue()
            self.assertIsNotNone(dequeued)
            self.assertEqual(dequeued.message, "test")

            # Test dequeue with timeout on empty queue
            empty_result = await queue.dequeue(timeout=0.1)
            self.assertIsNone(empty_result)

        asyncio.run(run_test())

    def test_response_store_interface_coverage(self):
        """Test response store interface methods."""
        import asyncio

        async def run_test():
            from agent_builder_sdk.message_queue.local_queue import LocalResponseStore

            store = LocalResponseStore(self.temp_dir)

            response = QueueResponse(
                request_id="test-id", message="test response", status=RequestStatus.COMPLETED
            )

            # Test store response
            result = await store.store_response(response)
            self.assertTrue(result)

            # Test get response
            retrieved = await store.get_response("test-id")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.message, "test response")

            # Test delete response
            result = await store.delete_response("test-id")
            self.assertTrue(result)

            # Test get non-existent response
            none_result = await store.get_response("non-existent")
            self.assertIsNone(none_result)

        asyncio.run(run_test())
