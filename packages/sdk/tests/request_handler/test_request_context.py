# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for RequestContext."""

import unittest

from agent_builder_sdk.request_handler.context import RequestContext


class TestRequestContext(unittest.TestCase):
    """Test suite for the RequestContext class."""

    def test_message_context_initialization(self):
        """Test RequestContext initialization with various parameters."""
        # Test with no parameters
        context = RequestContext()
        self.assertIsNone(context.user_id)
        self.assertIsNone(context.agent_instance_id)
        self.assertIsNone(context.sender)
        self.assertIsNone(context.task_id)

        # Test with user_id only
        context = RequestContext(user_id="test_user")
        self.assertEqual(context.user_id, "test_user")
        self.assertIsNone(context.agent_instance_id)
        self.assertIsNone(context.sender)
        self.assertIsNone(context.task_id)

        # Test with agent_instance_id only
        context = RequestContext(agent_instance_id="agent123")
        self.assertIsNone(context.user_id)
        self.assertEqual(context.agent_instance_id, "agent123")
        self.assertIsNone(context.sender)
        self.assertIsNone(context.task_id)

        # Test with sender only
        context = RequestContext(sender="cmf")
        self.assertIsNone(context.user_id)
        self.assertIsNone(context.agent_instance_id)
        self.assertEqual(context.sender, "cmf")
        self.assertIsNone(context.task_id)

        # Test with all parameters
        context = RequestContext(
            user_id="test_user", agent_instance_id="agent123", sender="chat", task_id="task-789"
        )
        self.assertEqual(context.user_id, "test_user")
        self.assertEqual(context.agent_instance_id, "agent123")
        self.assertEqual(context.sender, "chat")
        self.assertEqual(context.task_id, "task-789")

    def test_sender_field_values(self):
        """Test that sender field accepts expected values."""
        # Test with "cmf" sender
        context = RequestContext(sender="cmf")
        self.assertEqual(context.sender, "cmf")

        # Test with "chat" sender
        context = RequestContext(sender="chat")
        self.assertEqual(context.sender, "chat")

        # Test with custom sender value
        context = RequestContext(sender="custom_sender")
        self.assertEqual(context.sender, "custom_sender")
