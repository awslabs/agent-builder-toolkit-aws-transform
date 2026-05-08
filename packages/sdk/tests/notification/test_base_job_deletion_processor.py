# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for BaseJobDeletionProcessor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_builder_sdk.custom_types.notification_types import (
    HitlTaskStatus,
    HitlTaskStatusChangeDetail,
    JobDeletionDetail,
    Notification,
    NotificationType,
)
from agent_builder_sdk.notification.base_job_deletion_processor import BaseJobDeletionProcessor


class ConcreteJobDeletionProcessor(BaseJobDeletionProcessor):
    """Concrete implementation for testing."""

    def __init__(self):
        self.cleanup_called = False
        self.cleanup_detail = None
        self.cleanup_error = None

    async def cleanup(self, detail: JobDeletionDetail) -> None:
        self.cleanup_called = True
        self.cleanup_detail = detail
        if self.cleanup_error:
            raise self.cleanup_error


def _make_notification(job_id="job-123", workspace_id="ws-456", token="token-789") -> Notification:
    """Helper to create a JobDeletion notification."""
    return Notification(
        notification_type=NotificationType.JOB_DELETION,
        detail=JobDeletionDetail(
            job_id=job_id,
            workspace_id=workspace_id,
            deletion_acknowledgement_token=token,
        ),
    )


class TestBaseJobDeletionProcessorCannotInstantiate:
    """Test that BaseJobDeletionProcessor cannot be instantiated directly."""

    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            BaseJobDeletionProcessor()


class TestProcessReturnsImmediately:
    """Test that process() returns immediately without waiting for cleanup."""

    async def test_returns_cleanup_in_progress(self):
        processor = ConcreteJobDeletionProcessor()
        notification = _make_notification()

        with patch.object(processor, "_acknowledge_deletion", new_callable=AsyncMock):
            result = await processor.process(notification)

        assert result == {
            "message": "Job deletion notification received, cleanup in progress",
            "jobId": "job-123",
            "workspaceId": "ws-456",
        }

    async def test_returns_before_cleanup_completes(self):
        """Verify process() does not block on cleanup."""
        cleanup_started = asyncio.Event()
        cleanup_gate = asyncio.Event()

        class SlowProcessor(BaseJobDeletionProcessor):
            async def cleanup(self, detail):
                cleanup_started.set()
                await cleanup_gate.wait()  # Block until test releases

        processor = SlowProcessor()
        notification = _make_notification()

        with patch.object(processor, "_acknowledge_deletion", new_callable=AsyncMock):
            result = await processor.process(notification)

        # process() returned before cleanup finished
        assert result["message"] == "Job deletion notification received, cleanup in progress"

        # Let cleanup finish to avoid dangling tasks
        cleanup_gate.set()
        await asyncio.sleep(0.05)


class TestBackgroundCleanupAndAcknowledge:
    """Test the background _cleanup_and_acknowledge flow."""

    async def test_cleanup_then_acknowledge(self):
        processor = ConcreteJobDeletionProcessor()
        notification = _make_notification()

        with patch.object(processor, "_acknowledge_deletion", new_callable=AsyncMock) as mock_ack:
            await processor.process(notification)
            await asyncio.sleep(0.1)  # Wait for background task

        assert processor.cleanup_called
        assert processor.cleanup_detail.job_id == "job-123"
        assert processor.cleanup_detail.workspace_id == "ws-456"
        assert processor.cleanup_detail.deletion_acknowledgement_token == "token-789"
        mock_ack.assert_called_once_with(notification.detail)

    async def test_cleanup_failure_skips_acknowledge(self):
        processor = ConcreteJobDeletionProcessor()
        processor.cleanup_error = RuntimeError("S3 delete failed")
        notification = _make_notification()

        with patch.object(processor, "_acknowledge_deletion", new_callable=AsyncMock) as mock_ack:
            await processor.process(notification)
            await asyncio.sleep(0.1)

        assert processor.cleanup_called
        mock_ack.assert_not_called()

    async def test_acknowledge_failure_does_not_raise(self):
        """AcknowledgeDeletion failure should be logged but not crash."""
        processor = ConcreteJobDeletionProcessor()
        notification = _make_notification()

        with patch.object(
            processor,
            "_acknowledge_deletion",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            await processor.process(notification)
            await asyncio.sleep(0.1)

        # Should not raise — error is logged in background task
        assert processor.cleanup_called


class TestInvalidNotification:
    """Test handling of invalid notification detail types."""

    async def test_invalid_detail_type(self):
        processor = ConcreteJobDeletionProcessor()
        invalid_detail = HitlTaskStatusChangeDetail(
            hitl_task_id="task-123",
            old_status=HitlTaskStatus.CREATED,
            new_status=HitlTaskStatus.SUBMITTED,
        )
        notification = Notification(
            notification_type=NotificationType.JOB_DELETION,
            detail=invalid_detail,
        )

        result = await processor.process(notification)

        assert result == {"message": "Invalid job deletion notification detail"}
        assert not processor.cleanup_called


class TestAcknowledgeDeletion:
    """Test the _acknowledge_deletion API call."""

    @patch(
        "agent_builder_sdk.notification.base_job_deletion_processor.get_agent_context_from_env"
    )
    @patch("agent_builder_sdk.notification.base_job_deletion_processor.get_agentic_api_client")
    async def test_acknowledge_deletion_call(self, mock_get_client, mock_get_context):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_context = MagicMock()
        mock_context.agent_instance_id = "agent-001"
        mock_context.authorization_token = "auth-token"
        mock_get_context.return_value = mock_context

        processor = ConcreteJobDeletionProcessor()
        detail = JobDeletionDetail(
            job_id="job-123",
            workspace_id="ws-456",
            deletion_acknowledgement_token="token-789",
        )

        await processor._acknowledge_deletion(detail)

        mock_client.acknowledge_deletion.assert_called_once_with(
            deletionAcknowledgementToken="token-789",
            requestContext={
                "jobMetadata": {"jobId": "job-123", "workspaceId": "ws-456"},
                "agentInstanceId": "agent-001",
                "authorizationToken": "auth-token",
            },
        )
