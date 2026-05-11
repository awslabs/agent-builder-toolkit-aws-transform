# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from typing import Any, Dict, Optional, TypedDict

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.server._inject_qt_request_context import _inject_qt_request_context
from agent_builder_agentic_mcp.server._server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/atx-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


# Type definitions to help with type checking
class CreateHitlTaskKwargs(TypedDict, total=False):
    ux_component_id: str
    description: str
    title: str
    severity: Optional[str]
    hitl_task_type: Optional[str]
    step_id: Optional[str]
    blocking_type: Optional[str]
    hitl_request_artifact: Optional[Dict[str, Any]]
    expired_at: Optional[str]
    tag: Optional[str]
    idempotency_token: str


class StartHitlTaskKwargs(TypedDict, total=False):
    hitl_task_id: str
    first_in_chain: Optional[bool]
    idempotency_token: str


class CloseHitlTaskKwargs(TypedDict, total=False):
    hitl_task_id: str
    closure_type: str
    idempotency_token: str


class ListHitlTasksKwargs(TypedDict, total=False):
    task_type: str
    task_filter: Optional[Dict[str, Any]]
    max_results: Optional[int]
    next_token: Optional[str]


# HITL Task Tools


@mcp.tool(
    name="create_hitl_task",
    description="Creates a Human-In-The-Loop (HITL) task. Fields ux_component_id, description, and title are required. IMPORTANT: For step_id, either use the value directly provided by the user, or if not provided, use list_job_plan_steps tool and use the step_id of the first plan of the job. Fields severity (enum: STANDARD, CRITICAL), hitl_task_type (enum: NORMAL, DASHBOARD), blocking_type (enum: BLOCKING, NON_BLOCKING), hitl_request_artifact, expired_at, and tag are optional. If provided, hitl_request_artifact should have a key 'artifactId' with a valid UUID value.",
)
async def create_hitl_task(
    ux_component_id: str,
    description: str,
    title: str,
    severity: Optional[str] = "STANDARD",
    hitl_task_type: Optional[str] = "NORMAL",
    step_id: Optional[str] = None,
    blocking_type: Optional[str] = "BLOCKING",
    hitl_request_artifact: Optional[Dict[str, Any]] = None,
    expired_at: Optional[str] = None,
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a Human-In-The-Loop (HITL) task.

    Args:
        ux_component_id: The ID of the UX component. The value should be a known component registry ID.
        description: The description of the task.
        title: The title of the task
        severity: Optional severity of the task
        hitl_task_type: Optional type of the task
        step_id: Optional step ID
        blocking_type: Optional blocking type
        hitl_request_artifact: Optional request artifact
        expired_at: Optional expiration time
        tag: Optional tag

    Returns:
        The HITL task ID
    """
    logger.info(f"Creating HITL task with UX component ID: {ux_component_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters with proper typing
        kwargs: Dict[str, Any] = {
            "uxComponentId": ux_component_id,
            "description": description,
            "title": title,
        }

        if severity:
            kwargs["severity"] = severity

        if hitl_task_type:
            kwargs["hitlTaskType"] = hitl_task_type

        if step_id:
            kwargs["stepId"] = step_id

        if blocking_type:
            kwargs["blockingType"] = blocking_type

        if hitl_request_artifact:
            kwargs["hitlRequestArtifact"] = hitl_request_artifact

        if expired_at:
            kwargs["expiredAt"] = expired_at

        if tag:
            kwargs["tag"] = tag

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        response = client.create_hitl_task(**_inject_qt_request_context(kwargs))

        return {"hitl_task_id": response["hitlTaskId"]}
    except Exception as e:
        logger.error(f"Error creating HITL task: {str(e)}")
        raise


@mcp.tool(name="get_hitl_task", description="Gets information about a HITL task.")
async def get_hitl_task(hitl_task_id: str) -> Dict[str, Any]:
    """
    Gets information about a HITL task.

    Args:
        hitl_task_id: The ID of the HITL task

    Returns:
        The HITL task information
    """
    logger.info(f"Getting HITL task with ID: {hitl_task_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters with proper typing
        kwargs: Dict[str, Any] = {"hitlTaskId": hitl_task_id}

        # Make the API call
        response = client.get_hitl_task(**_inject_qt_request_context(kwargs))

        return {"hitl_task": response["hitlTask"]}
    except Exception as e:
        logger.error(f"Error getting HITL task: {str(e)}")
        raise


@mcp.tool(name="start_hitl_task", description="Starts a HITL task.")
async def start_hitl_task(
    hitl_task_id: str,
    first_in_chain: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Starts a HITL task.

    Args:
        hitl_task_id: The ID of the HITL task
        first_in_chain: Optional flag indicating if this is the first task in a chain

    Returns:
        The HITL task status
    """
    logger.info(f"Starting HITL task with ID: {hitl_task_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters with proper typing
        kwargs: Dict[str, Any] = {"hitlTaskId": hitl_task_id}

        if first_in_chain is not None:
            kwargs["firstInChain"] = first_in_chain

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        response = client.start_hitl_task(**_inject_qt_request_context(kwargs))

        return {"hitl_task_status": response["hitlTaskStatus"]}
    except Exception as e:
        logger.error(f"Error starting HITL task: {str(e)}")
        raise


@mcp.tool(
    name="close_hitl_task",
    description="Closes a HITL task. The required field hitlTaskId should be a UUID. Optional field closure_type (enum: CANCELLED, CLOSED, CLOSED_PENDING_NEXT_TASK)",
)
async def close_hitl_task(hitl_task_id: str, closure_type: str = "CANCELLED") -> Dict[str, Any]:
    """
    Closes a HITL task.

    Args:
        hitl_task_id: The ID of the HITL task
        closure_type: The type of closure

    Returns:
        The HITL task status
    """
    logger.info(f"Closing HITL task with ID: {hitl_task_id} with closure type: {closure_type}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters with proper typing
        kwargs: Dict[str, Any] = {"hitlTaskId": hitl_task_id, "closureType": closure_type}

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        response = client.close_hitl_task(**_inject_qt_request_context(kwargs))

        return {"hitl_task_status": response["hitlTaskStatus"]}
    except Exception as e:
        logger.error(f"Error closing HITL task: {str(e)}")
        raise


@mcp.tool(
    name="list_hitl_tasks",
    description="Lists HITL tasks for a job. Required field task_type (enum: NORMAL, DASHBOARD). Optional max_results has a max value of 100. Optional task_filter is a union with one of these fields: HitlTaskStatus (enum: CREATED, AWAITING_HUMAN_INPUT, IN_PROGRESS, SUBMITTED, CLOSED, CANCELLED, CLOSED_PENDING_NEXT_TASK, DELIVERED, AWAITING_APPROVAL), agentInstanceId (UUID), stepId (StepId), tag (string), or blockingType (enum: BLOCKING, NON_BLOCKING).",
)
async def list_hitl_tasks(
    task_type: str,
    task_filter: Optional[Dict[str, Any]] = None,
    max_results: Optional[int] = None,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lists HITL tasks for a job.

    Args:
        task_type: The type of tasks to list
        task_filter: Optional filter for tasks
        max_results: Optional maximum number of results to return
        next_token: Optional token for pagination

    Returns:
        List of HITL tasks
    """
    logger.info("Listing HITL tasks")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters with proper typing
        kwargs: Dict[str, Any] = {"taskType": task_type}

        if task_filter:
            kwargs["taskFilter"] = task_filter

        if max_results:
            kwargs["maxResults"] = max_results

        if next_token:
            kwargs["nextToken"] = next_token

        # Make the API call
        response = client.list_hitl_tasks(**_inject_qt_request_context(kwargs))

        result = {"hitl_tasks": response.get("hitlTasks", [])}

        if "nextToken" in response:
            result["next_token"] = response["nextToken"]

        return result
    except Exception as e:
        logger.error(f"Error listing HITL tasks: {str(e)}")
        raise
