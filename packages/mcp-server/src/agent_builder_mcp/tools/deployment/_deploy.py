"""Deploy agents to Bedrock AgentCore."""

import json
import logging
import time
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _generate_runtime_name(agent_name: str) -> str:
    """
    Generate unique runtime name with seconds precision.

    Format: atx_ws_{agent_name}_{MMDDHHmmss}
    Example: atx_ws_modernization_orchestrator_02271430

    Args:
        agent_name: Agent name

    Returns:
        Runtime name conforming to AgentCore naming constraints
    """
    # Replace hyphens with underscores (AgentCore requirement)
    safe_name = agent_name.replace("-", "_").replace(".", "_")

    # Add timestamp with seconds precision
    timestamp = datetime.now().strftime("%m%d%H%M%S")

    runtime_name = f"atx_ws_{safe_name}_{timestamp}"

    # Ensure length constraint (max 48 characters)
    if len(runtime_name) > 48:
        # Truncate agent name to fit
        max_agent_len = 48 - len("atx_ws_") - len(timestamp) - 1
        safe_name = safe_name[:max_agent_len]
        runtime_name = f"atx_ws_{safe_name}_{timestamp}"

    logger.info(f"Generated runtime name: {runtime_name}")
    return runtime_name


def _poll_runtime_status(
    runtime_id: str, region: str = "us-east-1", timeout_seconds: int = 120, poll_interval: int = 10
) -> dict:
    """
    Poll AgentCore runtime status until terminal state.

    Args:
        runtime_id: AgentCore runtime ID
        region: AWS region
        timeout_seconds: Maximum wait time (default: 120s)
        poll_interval: Seconds between polls (default: 10s)

    Returns:
        Status dict with final state
    """
    client = boto3.client("bedrock-agentcore-control", region_name=region)

    elapsed = 0
    while elapsed < timeout_seconds:
        try:
            response = client.get_agent_runtime(agentRuntimeId=runtime_id)
            status = response["status"]
            logger.info(f"Runtime {runtime_id} status: {status} (elapsed: {elapsed}s)")

            # Check terminal states
            if status in ["ACTIVE", "READY"]:
                return {"success": True, "status": status, "polling_duration_seconds": elapsed}
            elif status in ["FAILED", "STOPPED", "DELETE_FAILED"]:
                return {
                    "success": False,
                    "status": status,
                    "error": f"Runtime deployment failed with status: {status}",
                    "error_type": "DeploymentError",
                    "hint": f"Check CloudWatch logs: /aws/bedrock-agentcore/agent-runtime/{runtime_id}",
                }

            # Still in progress, continue polling
            time.sleep(poll_interval)
            elapsed += poll_interval

        except ClientError as e:
            logger.error(f"Error polling runtime status: {e}")
            return {"success": False, "error": str(e), "error_type": "APIError"}

    # Timeout
    return {
        "success": False,
        "status": "TIMEOUT",
        "error": f"Runtime deployment timeout after {timeout_seconds}s",
        "error_type": "TimeoutError",
        "hint": "Runtime may still be deploying. Check status manually with AWS CLI.",
    }


def deploy_agent_to_agentcore(
    image_uri: str,
    agent_name: str,
    execution_role_arn: str,
    region: str = "us-east-1",
    stage: str = "prod",
    timeout_seconds: int = 120,
) -> str:
    """
    Deploy agent image to Bedrock AgentCore and poll until ACTIVE.

    Args:
        image_uri: ECR image URI (output from build_agent_image)
        agent_name: Agent name for runtime naming
        execution_role_arn: ARN of AgentCoreExecutionRole (e.g., arn:aws:iam::123456:role/AgentCoreExecutionRole)
        region: AWS region (default: us-east-1)
        stage: Deployment stage for BaseAgent SDK endpoint configuration (default: prod)
        timeout_seconds: Maximum wait time for deployment (default: 120s)

    Returns:
        JSON string with deployment result:
        {
            "success": true,
            "runtime_id": "abc123def456",
            "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123456:agent-runtime/abc123",
            "runtime_name": "atx_ws_agent_name_02271430",
            "status": "ACTIVE",
            "polling_duration_seconds": 45
        }

    Implementation:
    1. Generate unique runtime name with seconds precision:
       format: atx_ws_{agent_name}_{MMDDHHmmss}
    2. Call bedrock-agentcore-control create-agent-runtime
    3. Poll status every 10 seconds (timeout: 120s)
    4. Check for terminal failure states: FAILED, STOPPED, DELETE_FAILED
    5. Return when status reaches ACTIVE or READY
    """
    try:
        client = boto3.client("bedrock-agentcore-control", region_name=region)

        # Generate unique runtime name
        runtime_name = _generate_runtime_name(agent_name)

        # Create AgentCore runtime
        logger.info(f"Creating AgentCore runtime: {runtime_name}")
        logger.info(f"Image URI: {image_uri}")
        logger.info(f"Execution Role: {execution_role_arn}")

        create_response = client.create_agent_runtime(
            agentRuntimeName=runtime_name,
            agentRuntimeArtifact={"containerConfiguration": {"containerUri": image_uri}},
            roleArn=execution_role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            environmentVariables={"REGION": region, "STAGE": stage},
        )

        runtime_id = create_response["agentRuntimeId"]
        runtime_arn = create_response["agentRuntimeArn"]
        logger.info(f"Runtime created: {runtime_id}")
        logger.info(f"Runtime ARN: {runtime_arn}")

        # Poll for status
        logger.info("Polling runtime status...")
        poll_result = _poll_runtime_status(
            runtime_id, region=region, timeout_seconds=timeout_seconds
        )

        if poll_result["success"]:
            return json.dumps(
                {
                    "success": True,
                    "runtime_id": runtime_id,
                    "runtime_arn": runtime_arn,
                    "runtime_name": runtime_name,
                    "status": poll_result["status"],
                    "polling_duration_seconds": poll_result["polling_duration_seconds"],
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "success": False,
                    "runtime_id": runtime_id,
                    "runtime_arn": runtime_arn,
                    "runtime_name": runtime_name,
                    **poll_result,
                },
                indent=2,
            )

    except ClientError as e:
        logger.error(f"AgentCore deployment error: {e}")
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        return json.dumps(
            {
                "success": False,
                "error": f"{error_code}: {error_message}",
                "error_type": error_code,
                "hint": _get_error_hint(error_code),
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Unexpected error in deploy_agent_to_agentcore")
        return json.dumps(
            {"success": False, "error": str(e), "error_type": type(e).__name__}, indent=2
        )


def _get_error_hint(error_code: str) -> str:
    """Get helpful hint for common error codes."""
    hints = {
        "ValidationException": "Check that image URI and execution role ARN are valid",
        "ResourceNotFoundException": "Ensure execution role exists and ECR image is pushed",
        "AccessDeniedException": "Verify IAM permissions for bedrock-agentcore-control",
        "ConflictException": "Runtime name may already exist. Try again (unique timestamp will be generated)",
        "ServiceQuotaExceededException": "AgentCore runtime quota exceeded. Delete unused runtimes.",
    }
    return hints.get(error_code, "Check AWS CloudWatch logs for more details")
