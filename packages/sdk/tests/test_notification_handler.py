# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for the notification handler.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent_builder_sdk.custom_types.notification_types import NotificationType
from agent_builder_sdk.message_queue.interface import RequestPriority
from agent_builder_sdk.notification.notification_handler import NotificationHandler
from agent_builder_sdk.notification.processors import HitlTaskProcessor, OrchAgentStopProcessor


@pytest.fixture
def mock_queue():
    return AsyncMock()


@pytest.fixture
def handler(mock_queue):
    handler = NotificationHandler(mock_queue)
    # Register default processors for testing
    handler.register_processor(NotificationType.HITL_TASK_STATUS_CHANGE, HitlTaskProcessor())
    handler.register_processor(NotificationType.ORCH_AGENT_STOP_EVENT, OrchAgentStopProcessor())
    return handler


@pytest.mark.asyncio
async def test_handle_hitl_notification_submitted(handler, mock_queue):
    """Test handling HITL notification with SUBMITTED status."""
    request = {
        "notificationType": "HitlTaskStatusChangeNotification",
        "notificationDetail": json.dumps(
            {"hitlTaskId": "task-123", "oldStatus": "IN_PROGRESS", "newStatus": "SUBMITTED"}
        ),
    }

    mock_queue.submit_request.return_value = "request-456"

    result = await handler.handle_notification(request)

    mock_queue.submit_request.assert_called_once_with(
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


@pytest.mark.asyncio
async def test_handle_hitl_notification_non_submitted(handler, mock_queue):
    """Test handling HITL notification with non-SUBMITTED status."""
    request = {
        "notificationType": "HitlTaskStatusChangeNotification",
        "notificationDetail": json.dumps(
            {"hitlTaskId": "task-123", "oldStatus": "IN_PROGRESS", "newStatus": "AWAITING_APPROVAL"}
        ),
    }

    result = await handler.handle_notification(request)

    mock_queue.submit_request.assert_not_called()
    assert result == {
        "message": "No processing needed",
    }


@pytest.mark.asyncio
async def test_handle_generic_notification(handler):
    """Test handling generic notification types."""
    request = {
        "notificationType": "JobStatusChangeNotification",
        "notificationDetail": json.dumps(
            {"jobId": "job-123", "oldStatus": "RUNNING", "newStatus": "COMPLETED"}
        ),
    }

    result = await handler.handle_notification(request)

    assert result == {
        "message": "Notification received: JobStatusChangeNotification",
        "notificationType": "JobStatusChangeNotification",
    }


@pytest.mark.asyncio
async def test_handle_agent_status_notification_stopped(handler):
    """Test handling OrchAgentStopEvent notification."""
    request = {
        "notificationType": "OrchAgentStopEvent",
        "notificationDetail": json.dumps(
            {
                "workspaceId": "ws-123",
                "jobId": "job-456",
                "orchAgentInstanceId": "agent-123",
                "newStatus": "STOPPED",
            }
        ),
    }

    with patch(
        "agent_builder_sdk.notification.processors.get_subagent_instances"
    ) as mock_get_subagents, patch(
        "agent_builder_sdk.notification.processors.shutdown_subagent_instance"
    ) as mock_shutdown_subagent, patch(
        "agent_builder_sdk.notification.processors.shutdown_base_orchestrator_agent_instance"
    ) as mock_shutdown_orch:
        mock_get_subagents.return_value = [
            {"agentInstanceId": "sub-1"},
            {"agentInstanceId": "sub-2"},
        ]
        mock_shutdown_subagent.return_value = True

        result = await handler.handle_notification(request)

        mock_get_subagents.assert_called_once_with("agent-123")
        assert mock_shutdown_subagent.call_count == 2
        mock_shutdown_subagent.assert_any_call("sub-1")
        mock_shutdown_subagent.assert_any_call("sub-2")
        mock_shutdown_orch.assert_called_once()
        assert result == {
            "message": "Stopped the orchestration agent and 2 subagent(s)",
            "agentInstanceId": "agent-123",
        }


@pytest.mark.asyncio
async def test_handle_agent_status_notification_non_stopped(handler):
    """Test handling unsupported notification type."""
    request = {
        "notificationType": "JobStatusChangeNotification",
        "notificationDetail": json.dumps({"oldStatus": "RUNNING", "newStatus": "FAILED"}),
    }

    result = await handler.handle_notification(request)

    assert result == {
        "message": "Notification received: JobStatusChangeNotification",
        "notificationType": "JobStatusChangeNotification",
    }


@pytest.mark.asyncio
async def test_handle_orch_agent_stop_event(handler):
    """Test handling OrchAgentStopEvent notification."""
    request = {
        "notificationType": "OrchAgentStopEvent",
        "notificationDetail": json.dumps(
            {
                "workspaceId": "ws-123",
                "jobId": "job-456",
                "orchAgentInstanceId": "orch-789",
                "newStatus": "STOPPED",
            }
        ),
    }

    with patch(
        "agent_builder_sdk.notification.processors.get_subagent_instances"
    ) as mock_get_subagents, patch(
        "agent_builder_sdk.notification.processors.shutdown_subagent_instance"
    ) as mock_shutdown_subagent, patch(
        "agent_builder_sdk.notification.processors.shutdown_base_orchestrator_agent_instance"
    ) as mock_shutdown_orch:
        mock_get_subagents.return_value = [{"agentInstanceId": "sub-1"}]
        mock_shutdown_subagent.return_value = True

        result = await handler.handle_notification(request)

        mock_get_subagents.assert_called_once_with("orch-789")
        mock_shutdown_subagent.assert_called_once_with("sub-1")
        mock_shutdown_orch.assert_called_once()
        assert result == {
            "message": "Stopped the orchestration agent and 1 subagent(s)",
            "agentInstanceId": "orch-789",
        }


@pytest.mark.asyncio
async def test_handle_notification_error(handler):
    """Test error handling in notification processing."""
    request = {
        "notificationType": "HitlTaskStatusChangeNotification",
        "notificationDetail": "invalid json",
    }

    result = await handler.handle_notification(request)

    assert result["message"] == "Error processing notification"
    assert result["notificationType"] == "HitlTaskStatusChangeNotification"
    assert "error" in result


@pytest.mark.asyncio
async def test_register_processor():
    """Test processor registration."""
    mock_queue = AsyncMock()
    handler = NotificationHandler(mock_queue)

    processor = HitlTaskProcessor()
    handler.register_processor(NotificationType.HITL_TASK_STATUS_CHANGE, processor)

    # Verify queue was injected
    assert processor.queue == mock_queue

    # Verify processor was registered
    assert handler._processors[NotificationType.HITL_TASK_STATUS_CHANGE] == processor


@pytest.mark.asyncio
async def test_no_processor_registered():
    """Test handling notification with no processor registered."""
    mock_queue = AsyncMock()
    handler = NotificationHandler(mock_queue)

    request = {
        "notificationType": "JobStatusChangeNotification",
        "notificationDetail": json.dumps({"oldStatus": "RUNNING", "newStatus": "COMPLETED"}),
    }

    result = await handler.handle_notification(request)

    assert result == {
        "message": "Notification received: JobStatusChangeNotification",
        "notificationType": "JobStatusChangeNotification",
    }
