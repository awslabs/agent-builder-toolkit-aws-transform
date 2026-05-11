# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.server._inject_qt_request_context import _inject_qt_request_context
from agent_builder_agentic_mcp.server._server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/qt-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


# Job Management Tools


@mcp.tool(name="get_job", description="Gets information about a job.")
async def get_job() -> Dict[str, Any]:
    """
    Gets information about a job.

    Args:
    Returns:
        The job information
    """
    logger.info("Getting job information")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"includeObjective": True}

        # Make the API call
        response = client.get_job(**_inject_qt_request_context(kwargs))

        return {"job": response["job"]}
    except Exception as e:
        logger.error(f"Error getting job information: {str(e)}")
        raise


@mcp.tool(name="update_job_status", description="Updates the status of a job.")
async def update_job_status(
    status: str,
    status_info: Optional[Dict[str, Any]] = None,
    notification_artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Updates the status of a job.

    Args:
        status: The new status of the job
        status_info: Optional status information
        notification_artifact_id: Optional UUID of an artifact to use for notification

    Returns:
        Empty response
    """
    logger.info(f"Updating job status to: {status}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"status": status}

        if status_info:
            kwargs["statusInfo"] = status_info

        if notification_artifact_id:
            kwargs["notificationArtifactId"] = notification_artifact_id

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        client.update_job_status(**_inject_qt_request_context(kwargs))

        # Return empty response
        return {}
    except Exception as e:
        logger.error(f"Error updating job status: {str(e)}")
        raise


@mcp.tool(
    name="create_worklog",
    description="Creates a worklog entry for a job. The only required input is plan_step_id. Use list_job_plan_steps tool to get the plan_step_id value if not provided",
)
async def create_worklog(
    plan_step_id: str,
    description: Optional[str] = None,
    timestamp: Optional[str] = None,
    action: Optional[str] = None,
    start_time: Optional[str] = None,
    artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a worklog entry for a job.

    Args:
        plan_step_id (str): **REQUIRED** - The ID of the plan step associated with this worklog
        description (str, optional): Description of the worklog
        timestamp (str, optional): Timestamp (in epoch milliseconds) of when the event occurred
        action (str, optional): Action associated with this worklog
        start_time (str, optional): Timestamp (in epoch milliseconds) when the overall action/step started, used for elapsed time calculation in the UX
        artifact_id (str, optional): ID of an artifact associated with this worklog

    Returns:
        Empty response
    """
    logger.info("Creating worklog entry")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        worklog: Dict[str, Any] = {}

        if timestamp:
            worklog["timestamp"] = timestamp
        else:
            worklog["timestamp"] = datetime.now().timestamp()

        if description:
            worklog["description"] = description

        attribute_map: Dict[str, Any] = {"STEP_ID": plan_step_id}

        if action:
            attribute_map["ACTION"] = action

        if start_time:
            attribute_map["START_TIME"] = start_time

        if artifact_id:
            attribute_map["ARTIFACT_ID"] = artifact_id

        worklog["attributeMap"] = attribute_map

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"worklog": worklog}

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        client.create_worklog(**_inject_qt_request_context(kwargs))

        # Return empty response
        return {}
    except Exception as e:
        logger.error(f"Error creating worklog entry: {str(e)}")
        raise


@mcp.tool(
    name="list_worklogs",
    description="Lists worklog entries for a job. Can filter by plan_step_id and/or time range. ",
)
async def list_worklogs(
    plan_step_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lists worklog entries for a job.

    Args:
        plan_step_id: Optional plan step ID to filter worklogs by (same as plan_step_id in create_worklog)
        start_time: Optional start time filter (epoch milliseconds)
        end_time: Optional end time filter (epoch milliseconds)
        next_token: Optional token for pagination

    Returns:
        List of worklogs and optional next token
    """
    logger.info(
        f"Listing worklogs with filters - plan_step_id: {plan_step_id}, "
        f"start_time: {start_time}, end_time: {end_time}, next_token: {next_token}"
    )

    try:
        client = atx_agenticapi_client()

        kwargs: Dict[str, Any] = {}

        worklog_filter: Dict[str, Any] = {}

        if plan_step_id:
            step_filter: Dict[str, Any] = {"stepId": plan_step_id}
            if start_time or end_time:
                time_filter: Dict[str, Any] = {}
                if start_time:
                    time_filter["startTime"] = start_time
                if end_time:
                    time_filter["endTime"] = end_time
                step_filter["timeFilter"] = time_filter
            worklog_filter["stepIdFilter"] = step_filter
        elif start_time or end_time:
            time_filter = {}
            if start_time:
                time_filter["startTime"] = start_time
            if end_time:
                time_filter["endTime"] = end_time
            worklog_filter["timeFilter"] = time_filter

        if worklog_filter:
            kwargs["worklogFilter"] = worklog_filter

        if next_token:
            kwargs["nextToken"] = next_token

        response = client.list_worklogs(**_inject_qt_request_context(kwargs))

        result = {"worklogs": response["worklogs"]}

        if "nextToken" in response:
            result["nextToken"] = response["nextToken"]

        return result
    except Exception as e:
        logger.error(f"Error listing worklogs: {str(e)}")
        raise


# Job Plan Management Tools


@mcp.tool(
    name="put_job_plan",
    description='Creates or updates a job plan. The mode should be either "override": {} or "append": {"parentStepId": "<existing_step_id>", "afterStepId": "<optional_existing_step_id>"}. For append mode, parentStepId must be an existing StepId string obtained from the job. If no parentStepId is provided, it will default to use the last existing StepId of the job. The plan should have a key "nodes" where the value is a list of type JobPlanStepNode, which has a required field of stepLabel (string), a required stepName field (string), a required description field (string), and an optional subSteps field which is a list of type JobPlanStepNode.',
)
async def put_job_plan(plan: Dict[str, Any], mode: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates or updates a job plan.

    Args:
        plan: The job plan to create or update
        mode: The mode for updating the job plan (override or append)

    Returns:
        The job plan version and mappings
    """
    logger.info(f"Creating or updating job plan with mode: {mode}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"plan": plan, "mode": mode}

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        response = client.put_job_plan(**_inject_qt_request_context(kwargs))

        result = {
            "status": response.get("status"),
        }

        if "mappings" in response:
            result["mappings"] = response["mappings"]

        return result
    except Exception as e:
        logger.error(f"Error creating or updating job plan: {str(e)}")
        raise


@mcp.tool(name="list_job_plan_steps", description="Lists steps in a job plan.")
async def list_job_plan_steps(
    parent_step_id: Optional[str] = None,
    max_results: Optional[int] = None,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lists steps in a job plan.

    Args:
        parent_step_id: Optional parent step ID to filter by
        max_results: Optional maximum number of results to return
        next_token: Optional token for pagination

    Returns:
        List of job plan steps
    """
    logger.info("Listing job plan steps")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {}

        if parent_step_id:
            kwargs["parentStepId"] = parent_step_id

        if max_results:
            kwargs["maxResults"] = max_results

        if next_token:
            kwargs["nextToken"] = next_token

        # Make the API call
        response = client.list_job_plan_steps(**_inject_qt_request_context(kwargs))

        result = {"steps": response["steps"]}

        if "nextToken" in response:
            result["nextToken"] = response["nextToken"]

        return result
    except Exception as e:
        logger.error(f"Error listing job plan steps: {str(e)}")
        raise


@mcp.tool(
    name="update_job_plan_step",
    description="Updates a step in a job plan. The plan_step contains: 1) required stepId field, 2) optional startTime field (unix epoch time), 3) optional endTime field (unix epoch time), and 4) status field which should be one of: NOT_STARTED, IN_PROGRESS, SUCCEEDED, PENDING_HUMAN_INPUT, FAILED. If stepId is not provided, use list_job_plan_steps tool to get the stepId. Do not misuse stepName for stepId.",
)
async def update_job_plan_step(plan_step: Dict[str, Any]) -> Dict[str, Any]:
    """
    Updates a step in a job plan.

    Args:
        plan_step: The plan step to update

    Returns:
        Empty response
    """
    logger.info(f"Updating job plan step with ID: {plan_step.get('stepId', 'unknown')}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"planStep": plan_step}

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        client.update_job_plan_step(**_inject_qt_request_context(kwargs))

        # Return empty response
        return {}
    except Exception as e:
        logger.error(f"Error updating job plan step: {str(e)}")
        raise


@mcp.tool(name="delete_job_plan_step", description="Deletes a step from a job plan.")
async def delete_job_plan_step(step_id: str) -> Dict[str, Any]:
    """
    Deletes a step from a job plan.

    Args:
        step_id: The ID of the step to delete

    Returns:
        Empty response
    """
    logger.info(f"Deleting job plan step {step_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"stepId": step_id}

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        client.delete_job_plan_step(**_inject_qt_request_context(kwargs))

        # Return empty response
        return {}
    except Exception as e:
        logger.error(f"Error deleting job plan step: {str(e)}")
        raise
