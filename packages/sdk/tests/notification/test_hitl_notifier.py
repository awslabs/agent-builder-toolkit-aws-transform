import asyncio

import pytest

from agent_builder_sdk.custom_types.notification_types import (
    HitlTaskStatus,
    HitlTaskStatusChangeDetail,
)
from agent_builder_sdk.notification.hitl_notifier import HitlNotifier


@pytest.fixture
def notifier():
    return HitlNotifier()


@pytest.fixture
def sample_notification():
    return HitlTaskStatusChangeDetail(
        hitl_task_id="task-123",
        old_status=HitlTaskStatus.IN_PROGRESS,
        new_status=HitlTaskStatus.SUBMITTED,
    )


class TestHitlNotifier:
    def test_init(self):
        notifier = HitlNotifier()
        assert notifier._futures == {}

    @pytest.mark.asyncio
    async def test_wait_and_notify_success(self, notifier, sample_notification):
        # Start waiting in background
        wait_task = asyncio.create_task(notifier.wait("task-123", HitlTaskStatus.SUBMITTED))
        await asyncio.sleep(0.01)  # Let wait() set up the future

        # Notify
        result = notifier.notify(sample_notification)

        # Verify
        assert result is True
        notification_result = await wait_task
        assert notification_result == sample_notification

    @pytest.mark.asyncio
    async def test_wait_duplicate_waiter(self, notifier):
        # Start first waiter
        wait_task1 = asyncio.create_task(notifier.wait("task-123", HitlTaskStatus.SUBMITTED))
        await asyncio.sleep(0.01)

        # Try to start second waiter for same task/status - fix regex pattern
        with pytest.raises(
            ValueError, match="A waiter for HitlTaskStatus.SUBMITTED HITL task-123 already exists"
        ):
            await notifier.wait("task-123", HitlTaskStatus.SUBMITTED)

        # Clean up
        wait_task1.cancel()
        try:
            await wait_task1
        except asyncio.CancelledError:
            pass

    def test_notify_no_waiter(self, notifier, sample_notification):
        result = notifier.notify(sample_notification)
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_wrong_status(self, notifier, sample_notification):
        # Set up waiter for different status
        wait_task = asyncio.create_task(notifier.wait("task-123", HitlTaskStatus.CANCELLED))
        await asyncio.sleep(0.01)  # Let wait() set up the future

        # Notify with different status
        result = notifier.notify(sample_notification)  # SUBMITTED status
        assert result is False

        # Clean up
        wait_task.cancel()
        try:
            await wait_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_future_cleanup_on_completion(self, notifier, sample_notification):
        wait_task = asyncio.create_task(notifier.wait("task-123", HitlTaskStatus.SUBMITTED))
        await asyncio.sleep(0.01)

        # Verify future exists
        assert "task-123" in notifier._futures[HitlTaskStatus.SUBMITTED]

        # Complete the future
        notifier.notify(sample_notification)
        await wait_task

        # Verify future is cleaned up
        assert "task-123" not in notifier._futures[HitlTaskStatus.SUBMITTED]

    @pytest.mark.asyncio
    async def test_multiple_tasks_different_status(self, notifier):
        # Create notifications for different statuses
        notification1 = HitlTaskStatusChangeDetail(
            "task-1", HitlTaskStatus.IN_PROGRESS, HitlTaskStatus.SUBMITTED
        )
        notification2 = HitlTaskStatusChangeDetail(
            "task-2", HitlTaskStatus.CREATED, HitlTaskStatus.CANCELLED
        )

        # Start waiters
        wait_task1 = asyncio.create_task(notifier.wait("task-1", HitlTaskStatus.SUBMITTED))
        wait_task2 = asyncio.create_task(notifier.wait("task-2", HitlTaskStatus.CANCELLED))
        await asyncio.sleep(0.01)

        # Notify both
        assert notifier.notify(notification1) is True
        assert notifier.notify(notification2) is True

        # Verify both complete
        result1 = await wait_task1
        result2 = await wait_task2
        assert result1 == notification1
        assert result2 == notification2
