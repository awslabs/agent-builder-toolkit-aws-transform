"""
Agent lifecycle management using agentic framework.
"""

import asyncio
import logging
import re
import time
from functools import lru_cache
from typing import Dict, List, Optional

import botocore

from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.env_var import get_agent_context_from_env

logger = logging.getLogger(__name__)


class AgentInstanceManager(AgenticApiHelper):
    """Manages agent instance lifecycle operations."""

    def __init__(self, **kwargs):
        """Initialize AgentInstanceManager."""
        super().__init__(**kwargs)

    def list_agent_instances(self, requester_agent_instance_id: Optional[str] = None) -> dict:
        """List agent instances, optionally filtered by requester agent instance ID.

        Args:
            requester_agent_instance_id: Optional ID to filter agents by requester. The requester is the agent instance that invoked the underlying agent.

        Returns:
            dict: Response containing agentInstanceSummaries and other metadata.

        Raises:
            Exception: If there's an error listing agent instances.
        """
        try:
            request_data = {}

            if requester_agent_instance_id:
                request_data["agentFilter"] = {
                    "requesterAgentInstanceId": requester_agent_instance_id
                }

            request = self._inject_request_context(request_data)
            return self.client.list_agent_instances(**request)

        except Exception:
            logger.error("Problem listing agent instances")
            raise

    def get_status(self, agent_instance_id: str) -> dict:
        """Get the status of any agent instance by its ID.

        Args:
            agent_instance_id: The unique identifier of the agent instance.

        Returns:
            dict: The agent instance status response from the API.

        Raises:
            Exception: If there's an error retrieving the agent instance status.
        """
        try:
            request_data = {
                "agentInstanceId": agent_instance_id,
            }

            request = self._inject_request_context(request_data)
            return self.client.get_agent_instance(**request)

        except Exception:
            logger.error(
                f"Encountering error when getting status for agentInstance[{agent_instance_id}]"
            )
            raise

    def update_status(
        self,
        agent_instance_id: str,
        status: str,
        status_reason: Optional[str] = None,
        agent_output: Optional[str] = None,
    ) -> dict:
        """Update the status of any agent instance by its ID.

        Args:
            agent_instance_id: The unique identifier of the agent instance.
            status: The new status to set for the agent instance.
            status_reason: Optional reason for the status change.
            agent_output: Optional output data from the agent.

        Returns:
            dict: The update response from the API.

        Raises:
            Exception: If there's an error updating the agent instance status.
        """
        try:
            request_data = {
                "agentInstanceId": agent_instance_id,
                "agentInstanceStatus": status,
            }

            if status_reason:
                request_data["agentInstanceStatusReason"] = status_reason
            if agent_output:
                request_data["agentOutput"] = agent_output

            request = self._inject_request_context(request_data)
            return self.client.update_agent_instance(**request)

        except Exception:
            logger.error(
                f"Encountering error when updating status for agentInstance[{agent_instance_id}]"
            )
            raise

    def stop_agent(self, agent_instance_id: str) -> dict:
        """Stop the agent instance by its ID.

        Args:
            agent_instance_id: The unique identifier of the agent instance.

        Returns:
            dict: The stop response from the API.

        Raises:
            Exception: If there's an error stopping the agent instance.
        """
        try:
            request_data = {
                "agentInstanceId": agent_instance_id,
            }

            request = self._inject_request_context(request_data)
            return self.client.stop_agent(**request)

        except Exception:
            logger.error(f"Encountering error when stopping agentInstance[{agent_instance_id}]")
            raise

    def set_running(self, agent_instance_id: str) -> dict:
        """Set agent instance status to RUNNING."""
        logger.info(f"Setting agent instance {agent_instance_id} to RUNNING")
        return self.update_status(agent_instance_id, "RUNNING")

    def set_stopped(self, agent_instance_id: str, reason: Optional[str] = None) -> dict:
        """Set agent instance status to STOPPED."""
        logger.info(f"Setting agent instance {agent_instance_id} to STOPPED")
        return self.update_status(agent_instance_id, "STOPPED", status_reason=reason)

    def set_failed(self, agent_instance_id: str, reason: Optional[str] = None) -> dict:
        """Set agent instance status to FAILED."""
        logger.info(f"Setting agent instance {agent_instance_id} to FAILED")
        return self.update_status(agent_instance_id, "FAILED", status_reason=reason)

    def is_invoked(self) -> bool:
        status = self.get_status(self.agent_instance_id).get("agentInstanceStatus")
        return status == "INVOKED"


@lru_cache(maxsize=1)
def get_agent_instance_manager() -> AgentInstanceManager:
    """Get cached AgentInstanceManager from environment variables."""
    context = get_agent_context_from_env()
    client = get_agentic_api_client()

    return AgentInstanceManager(
        workspace_id=context.workspace_id,
        job_id=context.job_id,
        agent_instance_id=context.agent_instance_id,
        client=client,
    )


@lru_cache(maxsize=1)
def get_agent_instance_manager_with_context(
    workspace_id: str, job_id: str, agent_instance_id: str
) -> AgentInstanceManager:
    """Get cached AgentInstanceManager with provided context."""
    client = get_agentic_api_client()

    return AgentInstanceManager(
        workspace_id=workspace_id,
        job_id=job_id,
        agent_instance_id=agent_instance_id,
        client=client,
    )


def initialize_base_orchestrator_agent_instance(
    workspace_id: str, job_id: str, agent_instance_id: str
) -> bool:
    """
    Initialize base orchestrator instance with provided context.
    Return if agent is set to RUNNING
    """
    manager = get_agent_instance_manager_with_context(workspace_id, job_id, agent_instance_id)
    try:
        status = manager.get_status(manager.agent_instance_id).get("agentInstanceStatus")

        # If already RUNNING, return True without doing anything
        if status == "RUNNING":
            logger.info(f"Agent instance {agent_instance_id} is already RUNNING")
            return True

        # If INVOKED, set to RUNNING
        if status == "INVOKED":
            manager.set_running(manager.agent_instance_id)
            return True
        else:
            logger.warning(
                f"Agent instance {agent_instance_id} is {status}. Can't set it to RUNNING"
            )
            return False
    except Exception as e:
        logger.error(
            f"Encountered an error setting agent instance {agent_instance_id} to RUNNING: {e}"
        )
        return False


def create_agent_instance_manager() -> AgentInstanceManager:
    """Create AgentInstanceManager from environment variables."""
    return get_agent_instance_manager()


def initialize_agent_instance() -> None:
    """Initialize agent instance using environment variables."""
    manager = get_agent_instance_manager()
    manager.set_running(manager.agent_instance_id)


def shutdown_base_orchestrator_agent_instance(reason: Optional[str] = None) -> bool:
    """Shutdown base orchestrator instance using environment variables."""
    try:
        manager = get_agent_instance_manager()
        manager.set_stopped(manager.agent_instance_id, reason)
        logger.info(f"Stopped orchestrator agent instance: {manager.agent_instance_id}")
        return True
    except Exception as e:
        logger.warning(
            f"Failed to stop orchestrator agent instance {manager.agent_instance_id}: {e}"
        )
        return False


def shutdown_subagent_instance(subagent_instance_id: str) -> bool:
    """Shutdown subagent instance using environment variables.

    Returns:
        bool: True if the subagent was successfully stopped, False otherwise.
    """
    try:
        logger.info(f"Stopping subagent {subagent_instance_id}")
        manager = get_agent_instance_manager()
        manager.stop_agent(subagent_instance_id)
        logger.info(f"Stopped subagent {subagent_instance_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to stop subagent {subagent_instance_id}: {e}")
        return False


def get_subagent_instances(
    requester_agent_instance_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Get all subagent instances.

    Args:
        requester_agent_instance_id: Optional ID to filter agents by requester. The requester is the agent instance that invoked the underlying agent.

    Returns:
        List[Dict[str, str]]: List of subagent summaries with agentInstanceId, agentType, and agentInstanceStatus.
    """
    manager = get_agent_instance_manager()
    agents = manager.list_agent_instances(requester_agent_instance_id)
    return [
        agent
        for agent in agents.get("agentInstanceSummaries", [])
        if agent.get("agentType") == "SUB_AGENT"
    ]


def set_agent_running(workspace_id: str, job_id: str, agent_instance_id: str) -> None:
    """Set agent to RUNNING with retry logic"""
    manager = get_agent_instance_manager_with_context(workspace_id, job_id, agent_instance_id)
    manager.set_running(agent_instance_id)


def get_agent_status(workspace_id: str, job_id: str, agent_instance_id: str) -> str:
    try:
        manager = get_agent_instance_manager_with_context(workspace_id, job_id, agent_instance_id)
        status = manager.get_status(agent_instance_id).get("agentInstanceStatus")
        logger.info(f"Agent instance {agent_instance_id} status: {status}")
        return str(status)
    except botocore.exceptions.ClientError as error:
        # Parse Error message with multiple patterns
        if error.response["Error"]["Code"] == "TerminalResourceException":
            error_message = error.response["Error"]["Message"]

            patterns = [
                r"status (\w+) is not allowed",
                r"Agent instance status is not valid: (\w+)",
            ]

            for pattern in patterns:
                status_match = re.search(pattern, error_message, re.IGNORECASE)
                if status_match:
                    parsed_status = status_match.group(1).upper()
                    logger.info(f"Parsed agent status from error message: {parsed_status}")
                    return parsed_status

        logger.error(f"Error getting agent status: {error}")
        raise


async def wait_for_agent_non_invoking(
    workspace_id: str, job_id: str, agent_instance_id: str, timeout: int = 10
) -> str:
    """Wait for agent status to exit INVOKING state.

    Args:
        workspace_id: The workspace ID
        job_id: The job ID
        agent_instance_id: The agent instance ID
        timeout: Maximum time to wait in seconds (default: 10)

    Returns:
        Final agent status after waiting (could be RUNNING, INVOKED, etc.)
    """
    logger.info("Agent is in INVOKING state, waiting for transition to proceed with initialization")
    start_time = time.monotonic()
    attempt = 0
    status = "INVOKING"

    while (time.monotonic() - start_time) < timeout:
        attempt += 1
        try:
            status = get_agent_status(workspace_id, job_id, agent_instance_id)

            if status != "INVOKING":
                logger.info(
                    f"Agent transitioned from INVOKING to {status}, proceeding with initialization"
                )
                break

            logger.info(f"Agent is still in INVOKING state (attempt {attempt})")
        except Exception as e:
            logger.warning(f"Failed to check agent status on attempt {attempt}: {e}")

        await asyncio.sleep(0.5)  # Wait 0.5 second between attempts

    if status == "INVOKING":
        logger.warning(f"Timeout: Agent remained in INVOKING state after {timeout} seconds")

    return status
