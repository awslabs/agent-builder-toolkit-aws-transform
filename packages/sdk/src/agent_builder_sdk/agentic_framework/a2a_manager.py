# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
A2A Manager for SendMessage and GetTask operations.
"""

import logging
from functools import lru_cache
from typing import Any, Dict

from botocore.exceptions import ClientError

from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.custom_types.task_types import A2ATask
from agent_builder_sdk.env_var import get_agent_context_from_env

logger = logging.getLogger(__name__)


class A2AManager(AgenticApiHelper):
    """Manager for A2A protocol operations (SendMessage, GetTask)."""

    def send_message(
        self,
        agent_instance_id: str,
        message: A2AMessage,
    ) -> Dict[str, Any]:
        """
        Send a message via A2A SendMessage API.

        Args:
            agent_instance_id: The agent instance ID to send the message to
            message: The A2AMessage object to send

        Returns:
            API response dictionary

        Raises:
            ClientError: If API call fails after retries
        """
        # Build request with message params
        request_data = {
            "agentInstanceId": agent_instance_id,
            "params": {"message": message.to_dict()},
        }

        # Inject request context (auth, job metadata)
        request_with_context = self._inject_request_context(request_data)

        try:
            logger.debug(
                f"Sending A2A message to agent {agent_instance_id} with context_id={message.contextId}"
            )
            response = self.client.send_message(**request_with_context)
            logger.info(f"A2A message sent to agent {agent_instance_id}")
            return response
        except ClientError as e:
            logger.exception(f"Failed to send A2A message to agent {agent_instance_id}: {e}")
            raise

    def send_task(
        self,
        agent_instance_id: str,
        task: A2ATask,
    ) -> Dict[str, Any]:
        """
        Send a task via A2A SendMessage API.

        Args:
            agent_instance_id: The agent instance ID to send the task to
            task: The A2ATask object to send

        Returns:
            API response dictionary

        Raises:
            ClientError: If API call fails after retries
        """
        # Build request with task params
        request_data = {
            "agentInstanceId": agent_instance_id,
            "params": {"task": task.to_dict()},
        }

        # Inject request context (auth, job metadata)
        request_with_context = self._inject_request_context(request_data)

        try:
            logger.debug(f"Sending A2A task {task.id} to agent {agent_instance_id}")
            response = self.client.send_message(**request_with_context)
            logger.info(f"A2A task {task.id} sent to agent {agent_instance_id}")
            return response
        except ClientError as e:
            logger.exception(f"Failed to send A2A task {task.id} to agent {agent_instance_id}: {e}")
            raise

    def get_task(self, task_id: str, agent_instance_id: str) -> Dict[str, Any]:
        """
        Get task information via A2A GetTask API.

        Args:
            task_id: The task ID to retrieve
            agent_instance_id: The agent instance ID to query the task from

        Returns:
            Task information dictionary

        Raises:
            ClientError: If API call fails after retries
        """
        request_data = {
            "agentInstanceId": agent_instance_id,
            "params": {"id": task_id},
        }

        # Inject request context (auth, job metadata)
        request_with_context = self._inject_request_context(request_data)

        try:
            logger.debug(f"Getting task {task_id} from agent {agent_instance_id}")
            response = self.client.get_task(**request_with_context)
            logger.info(f"Task {task_id} retrieved from agent {agent_instance_id}")
            return response
        except ClientError as e:
            logger.exception(f"Failed to get task {task_id} from agent {agent_instance_id}: {e}")
            raise


@lru_cache(maxsize=1)
def get_a2a_manager() -> A2AManager:
    """Get cached A2AManager singleton from environment variables."""
    context = get_agent_context_from_env()
    client = get_agentic_api_client()

    return A2AManager(
        workspace_id=context.workspace_id,
        job_id=context.job_id,
        agent_instance_id=context.agent_instance_id,
        client=client,
    )
