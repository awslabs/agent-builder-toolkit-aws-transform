# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for notification processors."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_builder_sdk.custom_types.notification_types import (
    AgentInstanceStatus,
    AgentStatusChangeDetail,
    HitlTaskStatus,
    HitlTaskStatusChangeDetail,
    Notification,
    NotificationType,
    OrchAgentStopEventDetail,
)
from agent_builder_sdk.message_queue.interface import RequestPriority
from agent_builder_sdk.notification.processors import (
    HitlTaskProcessor,
    OrchAgentStopProcessor,
    SubagentStatusChangeProcessor,
)


class TestHitlTaskProcessor:
    """Test cases for HitlTaskProcessor."""

    @pytest.fixture
    def processor(self):
        """Create HitlTaskProcessor instance."""
        processor = HitlTaskProcessor()
        processor.queue = AsyncMock()
        return processor

    @pytest.fixture
    def hitl_notification(self):
        """Create HITL notification fixture."""
        detail = HitlTaskStatusChangeDetail(
            hitl_task_id="task-123",
            old_status=HitlTaskStatus.IN_PROGRESS,
            new_status=HitlTaskStatus.SUBMITTED,
        )
        return Notification(
            notification_type=NotificationType.HITL_TASK_STATUS_CHANGE, detail=detail
        )

    async def test_process_submitted_status(self, processor, hitl_notification):
        """Test processing HITL notification with SUBMITTED status."""
        processor.queue.submit_request.return_value = "request-456"

        result = await processor.process(hitl_notification)

        processor.queue.submit_request.assert_called_once_with(
            message="HITL Task task-123 is submitted",
            sender="hitl_notification",
            context_id="task-123",
            priority=RequestPriority.HIGH,
        )
        assert result == {
            "message": "HITL notification processed",
            "hitlTaskId": "task-123",
            "requestId": "request-456",
        }

    async def test_process_non_submitted_status(self, processor):
        """Test processing HITL notification with non-SUBMITTED status."""
        detail = HitlTaskStatusChangeDetail(
            hitl_task_id="task-123",
            old_status=HitlTaskStatus.CREATED,
            new_status=HitlTaskStatus.AWAITING_HUMAN_INPUT,
        )
        notification = Notification(
            notification_type=NotificationType.HITL_TASK_STATUS_CHANGE, detail=detail
        )

        result = await processor.process(notification)

        processor.queue.submit_request.assert_not_called()
        assert result == {"message": "No processing needed"}

    async def test_process_with_notifier(self, hitl_notification):
        """Test processing with notifier that successfully notifies."""
        mock_notifier = MagicMock()
        mock_notifier.notify.return_value = True
        processor = HitlTaskProcessor(notifier=mock_notifier)
        processor.queue = AsyncMock()

        result = await processor.process(hitl_notification)

        mock_notifier.notify.assert_called_once_with(hitl_notification.detail)
        processor.queue.submit_request.assert_not_called()
        assert result == {
            "message": "Notified waiter of HITL task status change",
            "hitlTaskId": "task-123",
        }

    async def test_process_submitted_status_no_queue(self, hitl_notification):
        """Test processing HITL notification with SUBMITTED status but no queue."""
        processor = HitlTaskProcessor()
        # Don't inject queue

        result = await processor.process(hitl_notification)

        assert result == {"message": "Queue not available"}

    async def test_process_invalid_detail_type(self, processor):
        """Test processing with invalid detail type."""
        invalid_detail = AgentStatusChangeDetail(
            agent_instance_id="agent-123",
            old_status=AgentInstanceStatus.RUNNING,
            new_status=AgentInstanceStatus.COMPLETED,
        )
        notification = Notification(
            notification_type=NotificationType.HITL_TASK_STATUS_CHANGE, detail=invalid_detail
        )

        result = await processor.process(notification)

        assert result == {"message": "Invalid HITL notification detail"}


class TestOrchAgentStopProcessor:
    """Test cases for OrchAgentStopProcessor."""

    @pytest.fixture
    def processor(self):
        """Create OrchAgentStopProcessor instance."""
        processor = OrchAgentStopProcessor()
        processor.queue = AsyncMock()
        return processor

    @pytest.fixture
    def stop_notification(self):
        """Create orchestrator stop notification fixture."""
        detail = OrchAgentStopEventDetail(
            workspace_id="workspace-789",
            job_id="job-101",
            orch_agent_instance_id="orch-agent-202",
            new_status=AgentInstanceStatus.STOPPED,
        )
        return Notification(notification_type=NotificationType.ORCH_AGENT_STOP_EVENT, detail=detail)

    @patch("agent_builder_sdk.notification.processors.get_subagent_instances")
    @patch("agent_builder_sdk.notification.processors.shutdown_subagent_instance")
    @patch(
        "agent_builder_sdk.notification.processors.shutdown_base_orchestrator_agent_instance"
    )
    async def test_process_stop_event(
        self,
        mock_shutdown_orch,
        mock_shutdown_subagent,
        mock_get_subagents,
        processor,
        stop_notification,
    ):
        """Test processing orchestrator stop event."""
        mock_get_subagents.return_value = [
            {"agentInstanceId": "subagent-1"},
            {"agentInstanceId": "subagent-2"},
        ]
        mock_shutdown_subagent.side_effect = [True, True]

        result = await processor.process(stop_notification)

        mock_get_subagents.assert_called_once_with("orch-agent-202")
        assert mock_shutdown_subagent.call_count == 2
        mock_shutdown_orch.assert_called_once()
        assert result == {
            "message": "Stopped the orchestration agent and 2 subagent(s)",
            "agentInstanceId": "orch-agent-202",
        }

    @patch("agent_builder_sdk.notification.processors.get_subagent_instances")
    @patch("agent_builder_sdk.notification.processors.shutdown_subagent_instance")
    @patch(
        "agent_builder_sdk.notification.processors.shutdown_base_orchestrator_agent_instance"
    )
    async def test_process_stop_event_partial_shutdown(
        self,
        mock_shutdown_orch,
        mock_shutdown_subagent,
        mock_get_subagents,
        processor,
        stop_notification,
    ):
        """Test processing stop event with partial subagent shutdown."""
        mock_get_subagents.return_value = [
            {"agentInstanceId": "subagent-1"},
            {"agentInstanceId": "subagent-2"},
        ]
        mock_shutdown_subagent.side_effect = [True, False]

        result = await processor.process(stop_notification)

        assert result == {
            "message": "Stopped the orchestration agent and 1 subagent(s)",
            "agentInstanceId": "orch-agent-202",
        }

    async def test_process_invalid_detail_type(self, processor):
        """Test processing with invalid detail type."""
        invalid_detail = HitlTaskStatusChangeDetail(
            hitl_task_id="task-123",
            old_status=HitlTaskStatus.CREATED,
            new_status=HitlTaskStatus.SUBMITTED,
        )
        notification = Notification(
            notification_type=NotificationType.ORCH_AGENT_STOP_EVENT, detail=invalid_detail
        )

        result = await processor.process(notification)

        assert result == {"message": "Invalid agent stop notification detail"}


class TestSubagentStatusChangeProcessor:
    """Test cases for SubagentStatusChangeProcessor."""

    @pytest.fixture
    def processor(self):
        """Create SubagentStatusChangeProcessor instance."""
        processor = SubagentStatusChangeProcessor()
        processor.queue = AsyncMock()
        return processor

    @pytest.fixture
    def agent_status_notification(self):
        """Create agent status change notification fixture."""
        detail = AgentStatusChangeDetail(
            agent_instance_id="subagent-456",
            old_status=AgentInstanceStatus.INVOKING,
            new_status=AgentInstanceStatus.RUNNING,
        )
        return Notification(notification_type=NotificationType.AGENT_STATUS_CHANGE, detail=detail)

    async def test_process_status_change(self, processor, agent_status_notification):
        """Test processing subagent status change."""
        processor.queue.submit_request.return_value = "request-789"

        result = await processor.process(agent_status_notification)

        processor.queue.submit_request.assert_called_once_with(
            message="Subagent subagent-456 status changed to RUNNING",
            sender="subagent_status_notification",
            context_id="subagent-456",
            priority=RequestPriority.NORMAL,
        )
        assert result == {
            "message": "Subagent status change queued for processing",
            "requestId": "request-789",
        }

    async def test_process_with_notifier(self, agent_status_notification):
        """Test processing with notifier that successfully notifies."""
        mock_notifier = MagicMock()
        mock_notifier.notify.return_value = True
        processor = SubagentStatusChangeProcessor(notifier=mock_notifier)
        processor.queue = AsyncMock()

        result = await processor.process(agent_status_notification)

        mock_notifier.notify.assert_called_once_with(agent_status_notification.detail)
        processor.queue.submit_request.assert_not_called()
        assert result == {"message": "Notified waiter of agent status change"}

    async def test_process_status_change_no_queue(self, agent_status_notification):
        """Test processing subagent status change with no queue."""
        processor = SubagentStatusChangeProcessor()
        # Don't inject queue

        result = await processor.process(agent_status_notification)

        assert result == {"message": "Queue not available"}

    async def test_process_invalid_detail_type(self, processor):
        """Test processing with invalid detail type."""
        invalid_detail = HitlTaskStatusChangeDetail(
            hitl_task_id="task-123",
            old_status=HitlTaskStatus.CREATED,
            new_status=HitlTaskStatus.SUBMITTED,
        )
        notification = Notification(
            notification_type=NotificationType.AGENT_STATUS_CHANGE, detail=invalid_detail
        )

        result = await processor.process(notification)

        assert result == {"message": "Invalid agent status notification detail"}


class TestProcessorInitialization:
    """Test processor initialization and queue injection."""

    def test_hitl_processor_initialization(self):
        """Test HitlTaskProcessor initialization."""
        processor = HitlTaskProcessor()
        assert processor.notifier is None
        assert processor.queue is None  # Starts as None, gets injected later

        mock_notifier = MagicMock()
        processor_with_notifier = HitlTaskProcessor(notifier=mock_notifier)
        assert processor_with_notifier.notifier == mock_notifier
        assert processor_with_notifier.queue is None

    def test_orch_stop_processor_initialization(self):
        """Test OrchAgentStopProcessor initialization."""
        processor = OrchAgentStopProcessor()
        # No queue attribute at all - cleaner!
        assert not hasattr(processor, "queue")

    def test_subagent_processor_initialization(self):
        """Test SubagentStatusChangeProcessor initialization."""
        processor = SubagentStatusChangeProcessor()
        assert processor.notifier is None
        assert processor.queue is None  # Starts as None, gets injected later

        mock_notifier = MagicMock()
        processor_with_notifier = SubagentStatusChangeProcessor(notifier=mock_notifier)
        assert processor_with_notifier.notifier == mock_notifier
        assert processor_with_notifier.queue is None
