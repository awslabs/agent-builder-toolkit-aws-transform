"""Abstract processor for JobDeletionNotification."""

import asyncio
import logging
from abc import ABC, abstractmethod

import agent_builder_types.type_defs as abt

from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.notification_types import JobDeletionDetail, Notification
from agent_builder_sdk.env_var import get_agent_context_from_env

logger = logging.getLogger(__name__)

# Keep strong references to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()


class BaseJobDeletionProcessor(ABC):
    """Abstract base processor for JobDeletionNotification.

    Provides the framework for handling job deletion notifications:
    1. Returns immediately so the Compute Service notify call does not time out
    2. Runs cleanup and AcknowledgeDeletion in a background task

    The Compute Service has a 20-second timeout on notify calls. Since partner
    cleanup may take longer (deleting S3 data, DDB entries, connector credentials,
    etc.), processing is done asynchronously. The Step Function relies on polling
    AcknowledgeDeletion status (not this HTTP response) to confirm completion.

    Partner teams MUST subclass this and implement cleanup().
    """

    @abstractmethod
    async def cleanup(self, detail: JobDeletionDetail) -> None:
        """Perform partner-specific data cleanup for the deleted job.

        This method is called when a JobDeletionNotification is received.
        Partner teams must implement this to delete their own data
        (e.g., connector credentials, customer bucket data, DDB entries).

        This method should NOT call AcknowledgeDeletion — the base class
        handles that automatically after cleanup succeeds.

        Args:
            detail: The job deletion notification detail containing
                    job_id, workspace_id, and deletion_acknowledgement_token.

        Raises:
            Exception: If cleanup fails. AcknowledgeDeletion will NOT be called.
        """
        ...

    async def process(self, notification: Notification) -> dict[str, str]:
        """Process a JobDeletionNotification.

        Returns immediately to avoid hitting the Compute Service's 20-second
        notify timeout. Cleanup and AcknowledgeDeletion run in a background task.

        Args:
            notification: The notification containing JobDeletionDetail.

        Returns:
            Dict confirming the notification was received and processing has started.
        """
        detail = notification.detail
        if not isinstance(detail, JobDeletionDetail):
            logger.warning("Invalid detail type for job deletion notification")
            return {"message": "Invalid job deletion notification detail"}

        logger.info(
            f"Received job deletion notification for job {detail.job_id} "
            f"in workspace {detail.workspace_id}, starting background cleanup"
        )

        # Run cleanup and acknowledgement in the background
        task = asyncio.create_task(self._cleanup_and_acknowledge(detail))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return {
            "message": "Job deletion notification received, cleanup in progress",
            "jobId": detail.job_id,
            "workspaceId": detail.workspace_id,
        }

    async def _cleanup_and_acknowledge(self, detail: JobDeletionDetail) -> None:
        """Background task: run partner cleanup then call AcknowledgeDeletion."""
        try:
            await self.cleanup(detail)
            logger.info(f"Cleanup completed for job {detail.job_id}")
        except Exception:
            logger.exception(
                f"Cleanup failed for job {detail.job_id} in workspace {detail.workspace_id}. "
                f"AcknowledgeDeletion will NOT be called."
            )
            return

        try:
            await self._acknowledge_deletion(detail)
            logger.info(
                f"Deletion acknowledged for job {detail.job_id} in workspace {detail.workspace_id}"
            )
        except Exception:
            logger.exception(
                f"Cleanup succeeded but AcknowledgeDeletion failed for job {detail.job_id} "
                f"in workspace {detail.workspace_id}"
            )

    async def _acknowledge_deletion(self, detail: JobDeletionDetail) -> None:
        """Call the AcknowledgeDeletion API to confirm cleanup is complete.

        Args:
            detail: The job deletion detail containing the acknowledgement token.
        """
        client = get_agentic_api_client()
        context = get_agent_context_from_env()

        request_context: abt.RequestContextTypeDef = {
            "jobMetadata": {
                "jobId": detail.job_id,
                "workspaceId": detail.workspace_id,
            },
            "agentInstanceId": context.agent_instance_id,
            "authorizationToken": context.authorization_token,
        }

        await asyncio.to_thread(
            client.acknowledge_deletion,
            deletionAcknowledgementToken=detail.deletion_acknowledgement_token,
            requestContext=request_context,
        )
