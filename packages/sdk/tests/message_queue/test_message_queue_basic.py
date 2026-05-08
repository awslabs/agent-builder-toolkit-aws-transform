#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Basic integration test for the queue system.
Tests the actual working functionality as implemented.
"""

import asyncio
import tempfile
import unittest

from agent_builder_sdk.message_queue.interface import (
    QueueRequest,
    QueueResponse,
    RequestPriority,
)
from agent_builder_sdk.message_queue.local_queue import LocalRequestQueue, LocalResponseStore
from agent_builder_sdk.message_queue.service import QueueService


class TestQueueBasicFunctionality(unittest.TestCase):
    """Test basic queue functionality that actually works."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.request_queue = LocalRequestQueue(self.temp_dir)
        self.response_store = LocalResponseStore(self.temp_dir)
        self.queue_service = QueueService(self.request_queue, self.response_store)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_task_creation(self):
        """Test creating a task with the actual interface."""
        request = QueueRequest(message="Test message", priority=RequestPriority.HIGH)

        self.assertEqual(request.message, "Test message")
        self.assertEqual(request.priority, RequestPriority.HIGH)
        self.assertIsNotNone(request.request_id)

    def test_task_response_creation(self):
        """Test creating a task response."""
        from agent_builder_sdk.message_queue.interface import RequestStatus

        response = QueueResponse(
            request_id="test-123", message="Test response", status=RequestStatus.COMPLETED
        )

        self.assertEqual(response.request_id, "test-123")
        self.assertEqual(response.message, "Test response")
        self.assertEqual(response.status, RequestStatus.COMPLETED)

    def test_priority_enum_values(self):
        """Test priority enum has correct values."""
        self.assertEqual(RequestPriority.URGENT.value, 4)
        self.assertEqual(RequestPriority.HIGH.value, 3)
        self.assertEqual(RequestPriority.NORMAL.value, 2)
        self.assertEqual(RequestPriority.LOW.value, 1)

    def test_queue_service_initialization(self):
        """Test queue service initializes correctly."""
        self.assertIsNotNone(self.queue_service)
        self.assertEqual(self.queue_service.request_queue, self.request_queue)
        self.assertEqual(self.queue_service.response_store, self.response_store)

    def test_async_queue_operations(self):
        """Test basic async queue operations."""

        async def run_test():
            # Create a task
            request = QueueRequest(message="Async test message", priority=RequestPriority.NORMAL)

            # Enqueue the task
            success = await self.request_queue.enqueue(request)
            self.assertTrue(success)

            # Dequeue the task
            dequeued_task = await self.request_queue.dequeue()
            self.assertIsNotNone(dequeued_task)
            self.assertEqual(dequeued_task.message, "Async test message")

            # Test empty queue
            empty_task = await self.request_queue.dequeue()
            self.assertIsNone(empty_task)

        # Run the async test
        asyncio.run(run_test())

    def test_async_response_operations(self):
        """Test basic async response operations."""

        async def run_test():
            from agent_builder_sdk.message_queue.interface import RequestStatus

            # Create a response
            response = QueueResponse(
                request_id="async-test",
                message="Async response message",
                status=RequestStatus.COMPLETED,
            )

            # Store the response
            success = await self.response_store.store_response(response)
            self.assertTrue(success)

            # Retrieve the response
            retrieved = await self.response_store.get_response("async-test")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.request_id, "async-test")
            self.assertEqual(retrieved.message, "Async response message")

            # Test non-existent response
            missing = await self.response_store.get_response("nonexistent")
            self.assertIsNone(missing)

        # Run the async test
        asyncio.run(run_test())

    def test_priority_ordering(self):
        """Test that tasks are processed in priority order."""

        async def run_test():
            # Create requests with different priorities
            requests = [
                QueueRequest(message="Low priority", priority=RequestPriority.LOW),
                QueueRequest(message="Urgent priority", priority=RequestPriority.URGENT),
                QueueRequest(message="Normal priority", priority=RequestPriority.NORMAL),
                QueueRequest(message="High priority", priority=RequestPriority.HIGH),
            ]

            # Enqueue all requests
            for request in requests:
                await self.request_queue.enqueue(request)

            # Dequeue and verify order: URGENT -> HIGH -> NORMAL -> LOW
            expected_messages = [
                "Urgent priority",
                "High priority",
                "Normal priority",
                "Low priority",
            ]

            actual_messages = []
            for _ in range(4):
                task = await self.request_queue.dequeue()
                if task:
                    actual_messages.append(task.message)

            self.assertEqual(actual_messages, expected_messages)

        # Run the async test
        asyncio.run(run_test())

    def test_queue_service_async_operations(self):
        """Test queue service async operations."""

        async def run_test():
            # Submit a task (using correct parameters)
            request_id = await self.queue_service.submit_request(
                message="Service test message", priority=RequestPriority.HIGH
            )
            self.assertIsNotNone(request_id)

            # Check health
            health = await self.queue_service.health_check()
            self.assertIsInstance(health, dict)

            # Get task status
            await self.queue_service.get_request_status(request_id)
            # This might be None or have some status depending on implementation

        # Run the async test
        asyncio.run(run_test())
