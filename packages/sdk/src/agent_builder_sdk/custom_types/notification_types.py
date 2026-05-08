"""
Notification types for the ATX Base Agent
"""

import json
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Union


class NotificationType(Enum):
    """Types of notifications supported by the platform."""

    AGENT_STATUS_CHANGE = "AgentStatusChangeNotification"
    HITL_TASK_STATUS_CHANGE = "HitlTaskStatusChangeNotification"
    JOB_STATUS_CHANGE = "JobStatusChangeNotification"
    JOB_DELETION = "JobDeletionNotification"
    ORCH_AGENT_STOP_EVENT = "OrchAgentStopEvent"


class HitlTaskStatus(Enum):
    """Status values for HITL tasks."""

    CREATED = "CREATED"
    AWAITING_HUMAN_INPUT = "AWAITING_HUMAN_INPUT"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    CLOSED_PENDING_NEXT_TASK = "CLOSED_PENDING_NEXT_TASK"
    DELIVERED = "DELIVERED"


class AgentInstanceStatus(Enum):
    """Status values for agent instances."""

    INVOKING = "INVOKING"
    INVOKED = "INVOKED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    UNRESPONSIVE = "UNRESPONSIVE"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"


@dataclass
class NotificationDetail(ABC):
    """Base class for all notification details."""

    pass


@dataclass
class HitlTaskStatusChangeDetail(NotificationDetail):
    """Detail for HitlTaskStatusChangeNotification type."""

    hitl_task_id: str
    old_status: HitlTaskStatus
    new_status: HitlTaskStatus


@dataclass
class JobStatusChangeDetail(NotificationDetail):
    """Detail for JobStatusChangeNotification type."""

    old_status: str
    new_status: str


@dataclass
class AgentStatusChangeDetail(NotificationDetail):
    """Detail for AgentStatusChangeNotification type."""

    agent_instance_id: str
    old_status: AgentInstanceStatus
    new_status: AgentInstanceStatus


@dataclass
class OrchAgentStopEventDetail(NotificationDetail):
    """Detail for OrchAgentStopEvent type."""

    workspace_id: str
    job_id: str
    orch_agent_instance_id: str
    new_status: AgentInstanceStatus


@dataclass
class JobDeletionDetail(NotificationDetail):
    """Detail for JobDeletionNotification type."""

    job_id: str
    workspace_id: str
    deletion_acknowledgement_token: str


@dataclass
class Notification:
    """Base notification structure."""

    notification_type: NotificationType
    detail: NotificationDetail

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Notification":
        """Factory method that creates Notification from dictionary."""
        # Handle 'type' and fall back to 'notificationType' (legacy)
        notification_type_value = data.get("type", data.get("notificationType"))

        notification_type = NotificationType(notification_type_value)

        # Handle 'detail' and fall back to 'notificationDetail' (legacy)
        detail_json = data.get("detail", data.get("notificationDetail"))
        detail_data = json.loads(detail_json) if detail_json else {}

        detail: Union[
            HitlTaskStatusChangeDetail,
            JobStatusChangeDetail,
            AgentStatusChangeDetail,
            OrchAgentStopEventDetail,
            JobDeletionDetail,
        ]
        if notification_type == NotificationType.HITL_TASK_STATUS_CHANGE:
            detail = HitlTaskStatusChangeDetail(
                hitl_task_id=detail_data["hitlTaskId"],
                old_status=HitlTaskStatus(detail_data["oldStatus"]),
                new_status=HitlTaskStatus(detail_data["newStatus"]),
            )
        elif notification_type == NotificationType.JOB_STATUS_CHANGE:
            detail = JobStatusChangeDetail(
                old_status=detail_data["oldStatus"],
                new_status=detail_data["newStatus"],
            )
        elif notification_type == NotificationType.AGENT_STATUS_CHANGE:
            detail = AgentStatusChangeDetail(
                agent_instance_id=detail_data["agentInstanceId"],
                old_status=AgentInstanceStatus(detail_data["oldStatus"]),
                new_status=AgentInstanceStatus(detail_data["newStatus"]),
            )
        elif notification_type == NotificationType.ORCH_AGENT_STOP_EVENT:
            detail = OrchAgentStopEventDetail(
                workspace_id=detail_data["workspaceId"],
                job_id=detail_data["jobId"],
                orch_agent_instance_id=detail_data["orchAgentInstanceId"],
                new_status=AgentInstanceStatus(detail_data["newStatus"]),
            )
        elif notification_type == NotificationType.JOB_DELETION:
            detail = JobDeletionDetail(
                job_id=detail_data["jobId"],
                workspace_id=detail_data["workspaceId"],
                deletion_acknowledgement_token=detail_data["deletionAcknowledgementToken"],
            )
        else:
            raise ValueError(f"Unsupported notification type: {notification_type}")

        return cls(notification_type=notification_type, detail=detail)
