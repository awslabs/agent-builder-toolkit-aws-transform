# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from typing import Any, Dict, Optional

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.server import mcp
from agent_builder_agentic_mcp.server._inject_qt_request_context import (
    _get_request_context,
    _inject_qt_request_context,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/atx-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


# Define tools using FastMCP's decorator pattern


@mcp.tool(
    name="invoke_agent",
    description='Invokes an agent with the specified ID and optional input payload. The agentId is a required String of length between 1 and 64 characters. CRITICAL: For agent_input, construct a dictionary with a key "serializedPayload" and agent input payload content string as the value. Then provide EXACTLY ONE set of QUOTES around the JSON object. Example: agent_input=\'{"serializedPayload":"input-payload-content"}\' - ensure there is exactly one pair of quotes surrounding the dictionary. Optional field agent_version should be a string of min length of 5 and follow this pattern: "^\\\\d+\\\\.\\\\d+\\\\.\\\\d+(?:-dev-[a-zA-Z0-9]+)?$".',
)
async def invoke_agent(
    agent_id: str,
    agent_input: Optional[Dict[str, str]] = None,
    agent_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Invokes an agent with the specified ID and optional input payload.

    Args:
        agent_id: The ID of the agent to invoke
        input_payload: Optional input payload for the agent as a serialized string
        agent_version: Optional agent version

    Returns:
        The agent instance ID
    """
    logger.info(f"Invoking agent: {agent_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {
            "agentId": agent_id,
        }

        if agent_input:
            kwargs["inputPayload"] = agent_input

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        if agent_version:
            kwargs["agentVersion"] = agent_version

        # Make the API call
        response = client.invoke_agent(**_inject_qt_request_context(kwargs))

        # Return the agent instance ID
        return {"agentInstanceId": response["agentInstanceId"]}
    except Exception as e:
        logger.error(f"Error invoking agent: {str(e)}")
        raise


@mcp.tool(
    name="get_agent_instance",
    description="Gets information about an agent instance. The agent_instance_id is a required field of type UUID.",
)
async def get_agent_instance(agent_instance_id: str) -> Dict[str, Any]:
    """
    Gets information about an agent instance.

    Args:
        agent_instance_id: The ID of the agent instance

    Returns:
        Information about the agent instance
    """
    logger.info(f"Getting agent instance: {agent_instance_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Make the API call
        response = client.get_agent_instance(
            requestContext=_get_request_context().to_dict(), agentInstanceId=agent_instance_id
        )

        # Return the agent instance information
        return {
            "agentInstanceId": response["agentInstanceId"],
            "agentType": response["agentType"],
            "agentInstanceStatus": response["agentInstanceStatus"],
            "agentInput": response.get("agentInput"),
            "agentOutput": response.get("agentOutput"),
        }
    except Exception as e:
        logger.error(f"Error getting agent instance: {str(e)}")
        raise


@mcp.tool(
    name="update_agent_instance",
    description='Updates the status of an agent instance. The agent_instance_id is a required string. agent_instance_status is a required field of type enum UpdateAgentInstanceStatus {RUNNING, FAILED, COMPLETED, STOPPED}. agent_instance_status_reason is an optional String. CRITICAL: For agent_output, construct a dictionary with a key "serializedPayload" and agent output payload content string as the value. Then provide EXACTLY ONE set of QUOTES around the JSON object. Example: agent_output=\'{"serializedPayload":"output-payload-content"}\' - ensure there is exactly one pair of quotes surrounding the dictionary.',
)
async def update_agent_instance(
    agent_instance_id: str,
    agent_instance_status: str,
    agent_instance_status_reason: Optional[str] = None,
    agent_output: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Updates the status of an agent instance.

    Args:
        agent_instance_id: The ID of the agent instance
        agent_instance_status: The new status of the agent instance
        agent_instance_status_reason: Optional reason for the status change
        agent_output: Optional output from the agent as a serialized string

    Returns:
        Empty response
    """
    logger.info(f"Updating agent instance: {agent_instance_id} to status: {agent_instance_status}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {
            "agentInstanceId": agent_instance_id,
            "agentInstanceStatus": agent_instance_status,
        }

        if agent_instance_status_reason:
            kwargs["agentInstanceStatusReason"] = agent_instance_status_reason

        if agent_output:
            kwargs["agentOutput"] = agent_output

        # Make the API call
        client.update_agent_instance(**_inject_qt_request_context(kwargs))

        # Return empty response
        return {}
    except Exception as e:
        logger.error(f"Error updating agent instance: {str(e)}")
        raise


@mcp.tool(
    name="stop_agent",
    description="Stops an agent instance. The agent_instance_id is a required field of type UUID.",
)
async def stop_agent(agent_instance_id: str) -> Dict[str, Any]:
    """
    Stops an agent instance.

    Args:
        agent_instance_id: The ID of the agent instance

    Returns:
        Empty response
    """
    logger.info(f"Stopping agent instance: {agent_instance_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Generate a UUID for idempotency
        idempotency_token = str(uuid.uuid4())

        # Make the API call
        client.stop_agent(
            requestContext=_get_request_context().to_dict(),
            agentInstanceId=agent_instance_id,
            idempotencyToken=idempotency_token,
        )

        # Return empty response
        return {}
    except Exception as e:
        logger.error(f"Error stopping agent instance: {str(e)}")
        raise


@mcp.tool(
    name="list_agent_instances",
    description="Lists agent instances for a job. The next_token field is an optional token for pagination. The max_results field is an optional number ranging from 1 to 100.",
)
async def list_agent_instances(
    max_results: Optional[int] = None, next_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Lists agent instances for a job.

    Args:
        max_results: Optional maximum number of results to return
        next_token: Optional token for pagination

    Returns:
        List of agent instances
    """
    logger.info("Listing agent instances")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {}

        if max_results:
            kwargs["maxResults"] = max_results

        if next_token:
            kwargs["nextToken"] = next_token

        # Make the API call
        response = client.list_agent_instances(**_inject_qt_request_context(kwargs))

        # Return the list of agent instances
        result = {"agentInstanceSummaries": response.get("agentInstanceSummaries", [])}

        if "nextToken" in response:
            result["nextToken"] = response["nextToken"]

        return result
    except Exception as e:
        logger.error(f"Error listing agent instances: {str(e)}")
        raise
