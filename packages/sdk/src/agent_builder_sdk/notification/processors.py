# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Default notification processors.

This module provides default implementations of NotificationProcessor for handling
various ATX platform notification types. Processors can be registered with the
NotificationHandler to handle specific notification events.

## Default Processors

The AgentRuntimeServer automatically registers these default processors:

- **HitlTaskProcessor**: Handles `HITL_TASK_STATUS_CHANGE` notifications for human-in-the-loop task updates
- **OrchAgentStopProcessor**: Handles `ORCH_AGENT_STOP_EVENT` notifications for graceful orchestrator shutdown
"""

import logging

from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    get_subagent_instances,
    shutdown_base_orchestrator_agent_instance,
    shutdown_subagent_instance,
)
from agent_builder_sdk.custom_types.notification_types import (
    AgentStatusChangeDetail,
    HitlTaskStatus,
    HitlTaskStatusChangeDetail,
    Notification,
    OrchAgentStopEventDetail,
)
from agent_builder_sdk.message_queue import QueueService
from agent_builder_sdk.message_queue.interface import RequestPriority

from .notifier import Notifier

logger = logging.getLogger(__name__)


class HitlTaskProcessor:
    """Default processor for HITL task status change notifications.

    Handles NotificationType.HITL_TASK_STATUS_CHANGE events. Notifies waiting agent code
    or queues SUBMITTED tasks for processing.
    """

    def __init__(self, notifier: Notifier[HitlTaskStatusChangeDetail] | None = None):
        self.notifier = notifier
        self.queue: QueueService | None = None  # Injected by NotificationHandler

    async def process(self, notification: Notification) -> dict[str, str]:
        logger.info("Processing HITL notification")

        detail = notification.detail
        if not isinstance(detail, HitlTaskStatusChangeDetail):
            logger.warning("Invalid detail type for HITL notification")
            return {"message": "Invalid HITL notification detail"}

        logger.info(
            f"HITL Task {detail.hitl_task_id}: {detail.old_status.value} -> {detail.new_status.value}"
        )

        if self.notifier and self.notifier.notify(detail):
            return {
                "message": "Notified waiter of HITL task status change",
                "hitlTaskId": detail.hitl_task_id,
            }

        if detail.new_status == HitlTaskStatus.SUBMITTED:
            if not self.queue:
                logger.warning("Queue not available for HITL task processing")
                return {"message": "Queue not available"}

            prompt = f"HITL Task {detail.hitl_task_id} is submitted"
            request_id = await self.queue.submit_request(
                message=prompt,
                sender="hitl_notification",
                context_id=detail.hitl_task_id,
                priority=RequestPriority.HIGH,
            )
            logger.info(f"Submitted HITL notification request {request_id} to queue")
            return {
                "message": "HITL notification processed",
                "hitlTaskId": detail.hitl_task_id,
                "requestId": request_id,
            }

        return {
            "message": "No processing needed",
        }


class OrchAgentStopProcessor:
    """Default processor for orchestrator agent stop event notifications.

    Handles NotificationType.ORCH_AGENT_STOP_EVENT events. Performs graceful shutdown
    of all subagents and the orchestrator agent.
    """

    def __init__(self):
        pass  # No queue needed - performs direct shutdown operations

    async def process(self, notification: Notification) -> dict[str, str]:
        logger.info("Processing agent stop event notification")

        detail = notification.detail
        if not isinstance(detail, OrchAgentStopEventDetail):
            logger.warning("Invalid detail type for agent stop notification")
            return {"message": "Invalid agent stop notification detail"}

        agent_instance_id = detail.orch_agent_instance_id
        subagents = get_subagent_instances(agent_instance_id)

        stopped_count = 0
        for subagent in subagents:
            if shutdown_subagent_instance(subagent["agentInstanceId"]):
                stopped_count += 1

        shutdown_base_orchestrator_agent_instance()

        return {
            "message": f"Stopped the orchestration agent and {stopped_count} subagent(s)",
            "agentInstanceId": agent_instance_id,
        }


class SubagentStatusChangeProcessor:
    """Example processor that queues subagent status change notifications.

    Handles NotificationType.AGENT_STATUS_CHANGE events by queuing them for agent processing
    when the status change involves a subagent.
    """

    def __init__(self, notifier: Notifier[AgentStatusChangeDetail] | None = None):
        self.notifier = notifier
        self.queue: QueueService | None = None  # Injected by NotificationHandler

    async def process(self, notification: Notification) -> dict[str, str]:
        logger.info("Processing subagent status change notification")

        detail = notification.detail
        if not isinstance(detail, AgentStatusChangeDetail):
            logger.warning("Invalid detail type for agent status notification")
            return {"message": "Invalid agent status notification detail"}

        logger.info(
            f"Agent {detail.agent_instance_id}: {detail.old_status.value} -> {detail.new_status.value}"
        )

        if self.notifier and self.notifier.notify(detail):
            return {"message": "Notified waiter of agent status change"}

        # Queue subagent status changes for processing
        if not self.queue:
            logger.warning("Queue not available for subagent status processing")
            return {"message": "Queue not available"}

        prompt = f"Subagent {detail.agent_instance_id} status changed to {detail.new_status.value}"
        request_id = await self.queue.submit_request(
            message=prompt,
            sender="subagent_status_notification",
            context_id=detail.agent_instance_id,
            priority=RequestPriority.NORMAL,
        )
        logger.info(f"Submitted subagent status notification request {request_id} to queue")

        return {
            "message": "Subagent status change queued for processing",
            "requestId": request_id,
        }
