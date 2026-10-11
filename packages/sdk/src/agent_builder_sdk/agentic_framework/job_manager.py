# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
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


# Terminal states a job can no longer transition out of. Attempting to update
# the status of a job already in one of these states is rejected by the service
# with a 400 ValidationException.
TERMINAL_STATES = frozenset(
    {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.STOPPED.value}
)


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
            dict: Response from the API, or an empty dict if the update was
                skipped because the job is already in a terminal state.

        Raises:
            Exception: If there's an error updating the job status
        """
        try:
            # Guard against updating a job that has already reached a terminal
            # state. The service rejects such calls with a 400 ValidationException.
            # Skip the call instead.
            current_job_status = self.get_job_status()
            if current_job_status in TERMINAL_STATES:
                logger.warning(
                    f"Skipping UpdateJobStatus to {status.value}: job is already in "
                    f"terminal state {current_job_status}"
                )
                return {}

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
