# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for checkpoint triggers.
"""

import threading
from unittest.mock import patch

from agent_builder_sdk.checkpoint.checkpoint_triggers import (
    ConversationTurnTrigger,
    TimeBasedTrigger,
)


class TestTimeBasedTrigger:
    """Test TimeBasedTrigger functionality."""

    def test_init_default_interval(self):
        """Test default interval initialization."""
        trigger = TimeBasedTrigger()
        assert trigger.interval_second == 1800  # 30 minutes

    def test_init_custom_interval(self):
        """Test custom interval initialization."""
        trigger = TimeBasedTrigger(interval_minutes=10)
        assert trigger.interval_second == 600  # 10 minutes

    @patch("time.monotonic")
    def test_should_checkpoint_false(self, mock_time):
        """Test should_checkpoint returns False when interval not reached."""
        mock_time.return_value = 1000
        trigger = TimeBasedTrigger(interval_minutes=1)

        mock_time.return_value = 1030  # 30 seconds later
        assert not trigger.should_checkpoint()

    @patch("time.monotonic")
    def test_should_checkpoint_true(self, mock_time):
        """Test should_checkpoint returns True when interval reached."""
        mock_time.return_value = 1000
        trigger = TimeBasedTrigger(interval_minutes=1)

        mock_time.return_value = 1060  # 60 seconds later
        assert trigger.should_checkpoint()

    @patch("time.monotonic")
    def test_reset(self, mock_time):
        """Test reset updates last checkpoint time."""
        mock_time.return_value = 1000
        trigger = TimeBasedTrigger()

        mock_time.return_value = 2000
        trigger.reset()
        assert trigger.last_checkpoint_time == 2000


class TestConversationTurnTrigger:
    """Test ConversationTurnTrigger functionality."""

    def test_init_default_threshold(self):
        """Test default threshold initialization."""
        trigger = ConversationTurnTrigger()
        assert trigger.turn_threshold == 20
        assert trigger.current_turn == 0

    def test_init_custom_threshold(self):
        """Test custom threshold initialization."""
        trigger = ConversationTurnTrigger(turn_threshold=5)
        assert trigger.turn_threshold == 5
        assert trigger.current_turn == 0

    def test_should_checkpoint_false(self):
        """Test should_checkpoint returns False when threshold not reached."""
        trigger = ConversationTurnTrigger(turn_threshold=5)
        trigger.current_turn = 4
        assert not trigger.should_checkpoint()

    def test_should_checkpoint_true(self):
        """Test should_checkpoint returns True when threshold reached."""
        trigger = ConversationTurnTrigger(turn_threshold=5)
        trigger.current_turn = 5
        assert trigger.should_checkpoint()

    def test_increment_turn(self):
        """Test increment_turn increases counter."""
        trigger = ConversationTurnTrigger()
        trigger.increment_turn()
        assert trigger.current_turn == 1

        trigger.increment_turn()
        assert trigger.current_turn == 2

    def test_reset(self):
        """Test reset clears turn counter."""
        trigger = ConversationTurnTrigger()
        trigger.current_turn = 10
        trigger.reset()
        assert trigger.current_turn == 0

    def test_checkpoint_workflow(self):
        """Test complete checkpoint workflow."""
        trigger = ConversationTurnTrigger(turn_threshold=3)

        # Increment turns
        for _ in range(2):
            trigger.increment_turn()
            assert not trigger.should_checkpoint()

        # Reach threshold
        trigger.increment_turn()
        assert trigger.should_checkpoint()

        # Reset
        trigger.reset()
        assert not trigger.should_checkpoint()

    def test_thread_safety(self):
        """Test thread safety of ConversationTurnTrigger."""
        trigger = ConversationTurnTrigger(turn_threshold=1000)
        num_threads = 10
        increments_per_thread = 100

        def increment_worker():
            for _ in range(increments_per_thread):
                trigger.increment_turn()

        # Start multiple threads incrementing concurrently
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=increment_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify final count is correct (no race conditions)
        expected_count = num_threads * increments_per_thread
        assert trigger.current_turn == expected_count

    def test_has_lock_attribute(self):
        """Test that ConversationTurnTrigger has thread lock."""
        trigger = ConversationTurnTrigger()
        assert hasattr(trigger, "_lock")
        assert hasattr(trigger._lock, "acquire")
        assert hasattr(trigger._lock, "release")
