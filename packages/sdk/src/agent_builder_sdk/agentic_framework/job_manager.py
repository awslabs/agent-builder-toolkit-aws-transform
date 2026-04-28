"""
Job management using agentic framework.
"""

import logging
from enum import Enum
from typing import Any, Dict, Optional

from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status values."""

    CREATED = "CREATED"
    STARTING = "STARTING"
    ASSESSING = "ASSESSING"
    PLANNING = "PLANNING"
    PLANNED = "PLANNED"
    EXECUTING = "EXECUTING"
    AWAITING_HUMAN_INPUT = "AWAITING_HUMAN_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class JobManager(AgenticApiHelper):
    """Manages job lifecycle operations."""

    def __init__(self, **kwargs):
        """Initialize JobManager."""
        super().__init__(**kwargs)

    def update_job_status(
        self, status: JobStatus, status_info: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Update job status.

        Args:
            status: The new job status
            status_info: Optional status information

        Returns:
            dict: Response from the API

        Raises:
            Exception: If there's an error updating the job status
        """
        try:
            input_data: Dict[str, Any] = {"status": status.value}

            if status_info:
                input_data["statusInfo"] = status_info

            request = self._inject_request_context(input_data)
            response = self.client.update_job_status(**request)
            logger.debug(f"UpdateJobStatus response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error updating job status to {status}: {e}")
            raise

    def get_job_status(self) -> str:
        """Get current job status.

        Returns:
            str: Current job status

        Raises:
            Exception: If there's an error retrieving the job status
        """
        try:
            input_data: Dict[str, Any] = {"includeObjective": False}
            request = self._inject_request_context(input_data)
            response = self.client.get_job(**request)
            job_info = response.get("job", {})
            status_details = job_info.get("statusDetails", {})
            return status_details.get("status", "UNKNOWN")
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            raise

    def transition_to_executing_if_assessing(self) -> None:
        """Transition job from ASSESSING to EXECUTING if currently in ASSESSING status."""
        current_job_status = self.get_job_status()
        logger.info(f"Current job status: {current_job_status}")

        if current_job_status == JobStatus.ASSESSING.value:
            logger.info("Auto-transitioning job from ASSESSING to EXECUTING")
            self.update_job_status(JobStatus.EXECUTING)
            logger.info("Job successfully transitioned to EXECUTING")
