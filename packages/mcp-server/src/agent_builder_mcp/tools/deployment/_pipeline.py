"""Full deployment pipeline orchestration."""

import json
import logging

import boto3

from ._build import build_agent_image
from ._deploy import deploy_agent_to_agentcore

logger = logging.getLogger(__name__)


def _check_logging_permissions(
    iam_client, role_arn: str, account_id: str, region: str
) -> list[str]:
    """
    Validate that AgentCoreExecutionRole has required CloudWatch Logs permissions.

    Uses iam:SimulatePrincipalPolicy to check logs:DescribeLogStreams and
    logs:DescribeLogGroups against the bedrock-agentcore log group resource pattern.

    Without these two permissions, AgentCore cannot determine whether to create or
    reuse log groups/streams, resulting in *no logs* appearing in the AgentCore
    Runtime log groups.

    Args:
        iam_client: Boto3 IAM client
        role_arn: ARN of the role to check
        account_id: AWS account ID
        region: AWS region

    Returns:
        List of missing action names (empty if all present)
    """
    required_actions = [
        (
            "logs:DescribeLogStreams",
            f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*",
        ),
        ("logs:DescribeLogGroups", f"arn:aws:logs:{region}:{account_id}:log-group:*"),
    ]

    try:
        missing = []
        for action, resource_arn in required_actions:
            response = iam_client.simulate_principal_policy(
                PolicySourceArn=role_arn,
                ActionNames=[action],
                ResourceArns=[resource_arn],
            )
            for result in response.get("EvaluationResults", []):
                if result.get("EvalDecision") != "allowed":
                    missing.append(result["EvalActionName"])
        return missing

    except Exception as e:
        # iam:SimulatePrincipalPolicy may not be permitted for the caller.
        # Log and move on — this is a best-effort check.
        logger.debug(
            f"Could not simulate policy (caller may lack iam:SimulatePrincipalPolicy): {e}"
        )
        return []


def _get_default_execution_role_arn(region: str = "us-east-1") -> str | None:
    """
    Auto-detect AgentCoreExecutionRole ARN in the current account.

    Args:
        region: AWS region

    Returns:
        Role ARN or None if not found
    """
    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        role_arn = f"arn:aws:iam::{account_id}:role/AgentCoreExecutionRole"

        # Verify role exists
        iam = boto3.client("iam")
        iam.get_role(RoleName="AgentCoreExecutionRole")

        logger.info(f"Auto-detected execution role: {role_arn}")
        return role_arn
    except Exception as e:
        logger.warning(f"Could not auto-detect execution role: {e}")
        return None


def _get_default_access_role_arn(region: str = "us-east-1") -> str | None:
    """
    Auto-detect ATXAgentInvokeRole ARN in the current account.

    Args:
        region: AWS region

    Returns:
        Role ARN or None if not found
    """
    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        role_arn = f"arn:aws:iam::{account_id}:role/ATXAgentInvokeRole"

        # Verify role exists
        iam = boto3.client("iam")
        iam.get_role(RoleName="ATXAgentInvokeRole")

        logger.info(f"Auto-detected access role: {role_arn}")
        return role_arn
    except Exception as e:
        logger.warning(f"Could not auto-detect access role: {e}")
        return None


def _register_with_atx(
    agent_name: str,
    agent_version: str,
    runtime_arn: str,
    access_role_arn: str,
    registry_endpoint: str,
    region: str = "us-east-1",
    job_orchestrator: bool = False,
    chat_ui_label: str | None = None,
    chat_agent_identifier: str | None = None,
    a2a_supported: bool = True,
) -> dict:
    """
    Register agent with ATX registry.

    Args:
        agent_name: Agent name
        agent_version: Agent version
        runtime_arn: AgentCore runtime ARN
        access_role_arn: ATXAgentInvokeRole ARN
        registry_endpoint: ATX registry endpoint
        region: AWS region
        job_orchestrator: Register as job orchestrator (enables workspace binding)
        chat_ui_label: Display name for chat UI
        chat_agent_identifier: Agent identifier for chat
        a2a_supported: Enable agent-to-agent communication

    Returns:
        Registration result dict
    """
    try:
        # Import registry tool
        from ..registry._register import register_dev_agent

        # Call register_dev_agent
        logger.info(f"Registering agent '{agent_name}' with ATX registry")
        result = register_dev_agent(
            agent_name=agent_name,
            description=f"ATX agent: {agent_name}",
            agent_runtime_arn=runtime_arn,
            atx_access_role_arn=access_role_arn,
            version=agent_version,
            region=region,
            stage="prod",
            job_orchestrator=job_orchestrator,
            chat_ui_label=chat_ui_label,
            chat_agent_identifier=chat_agent_identifier,
            a2a_supported=a2a_supported,
        )

        # Parse result
        result_dict = json.loads(result)

        if result_dict.get("overall_status") == "success":
            return {
                "success": True,
                "agent_name": agent_name,
                "version": agent_version,
                "visibility": "PRIVATE",
            }
        else:
            return {
                "success": False,
                "error": result_dict.get("error", "Registration failed"),
                "error_type": "RegistrationError",
            }

    except Exception as e:
        logger.error(f"Registry registration error: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "hint": "Ensure AWS account is allowlisted by ATX team",
        }


def deploy_agent_full_pipeline(
    agent_path: str,
    agent_name: str,
    agent_version: str = "1.0.0",
    execution_role_arn: str | None = None,
    access_role_arn: str | None = None,
    use_codebuild: bool = False,
    registry_endpoint: str = "https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev",
    region: str = "us-east-1",
    stage: str = "prod",
    skip_registry: bool = False,
    job_orchestrator: bool = False,
    chat_ui_label: str | None = None,
    chat_agent_identifier: str | None = None,
    a2a_supported: bool = True,
) -> str:
    """
    Complete deployment pipeline: build → push → deploy → register.

    This orchestrates all phases:
    - Phase 1: Build image (build_agent_image)
    - Phase 2: Deploy to AgentCore (deploy_agent_to_agentcore)
    - Phase 3: Register with ATX registry (uses atx-developer-facing-mcp tools)

    Args:
        agent_path: Path to agent directory
        agent_name: Agent name
        agent_version: Version for registry (default: 1.0.0)
        execution_role_arn: AgentCoreExecutionRole ARN (if None, auto-detect from config)
        access_role_arn: ATXAgentInvokeRole ARN (if None, auto-detect from config)
        use_codebuild: Force CodeBuild build (default: False, auto-detects platform)
        registry_endpoint: ATX registry endpoint (default: prod)
        region: AWS region (default: us-east-1)
        stage: Deployment stage for BaseAgent SDK endpoint (default: prod)
        skip_registry: Skip registry registration phase (default: False)
        job_orchestrator: Register as job orchestrator (enables workspace binding)
        chat_ui_label: Display name for chat UI (defaults to agent_name)
        chat_agent_identifier: Agent identifier for chat (defaults to agent_name)
        a2a_supported: Enable agent-to-agent communication (default: True)

    Returns:
        JSON string with pipeline result:
        {
            "success": true,
            "phases": {
                "build": {"image_uri": "...", "build_method": "finch"},
                "deploy": {"runtime_arn": "...", "status": "ACTIVE"},
                "register": {"agent_name": "...", "version": "1.0.0", "visibility": "PRIVATE"}
            },
            "summary": "Agent modernization-orchestrator v1.0.0 deployed successfully"
        }
    """
    try:
        phases = {}

        # Phase 1: Build image
        logger.info("=" * 60)
        logger.info("PHASE 1: BUILD IMAGE")
        logger.info("=" * 60)

        build_result_str = build_agent_image(
            agent_path=agent_path, agent_name=agent_name, use_codebuild=use_codebuild, region=region
        )
        build_result = json.loads(build_result_str)

        if not build_result.get("success"):
            return json.dumps(
                {
                    "success": False,
                    "phase": "build",
                    "error": build_result.get("error"),
                    "error_type": build_result.get("error_type"),
                    "hint": build_result.get("hint"),
                },
                indent=2,
            )

        phases["build"] = {
            "image_uri": build_result["image_uri"],
            "build_method": build_result["build_method"],
            "ecr_repository": build_result["ecr_repository"],
        }
        logger.info(f"✓ Build phase complete: {build_result['image_uri']}")

        # Phase 2: Deploy to AgentCore
        logger.info("=" * 60)
        logger.info("PHASE 2: DEPLOY TO AGENTCORE")
        logger.info("=" * 60)

        # Auto-detect execution role if not provided
        if not execution_role_arn:
            execution_role_arn = _get_default_execution_role_arn(region)
            if not execution_role_arn:
                return json.dumps(
                    {
                        "success": False,
                        "phase": "deploy",
                        "error": "execution_role_arn not provided and could not auto-detect AgentCoreExecutionRole",
                        "error_type": "ConfigurationError",
                        "hint": "Provide execution_role_arn parameter or ensure AgentCoreExecutionRole exists in your account",
                    },
                    indent=2,
                )

        # Best-effort check: verify AgentCoreExecutionRole has the CloudWatch Logs
        # permissions that AgentCore needs internally. Without logs:DescribeLogStreams
        # and logs:DescribeLogGroups, AgentCore cannot determine whether to create or
        # reuse log groups/streams, resulting in *no logs* in the runtime log groups.
        try:
            sts = boto3.client("sts")
            account_id = sts.get_caller_identity()["Account"]
            iam = boto3.client("iam")
            missing = _check_logging_permissions(iam, execution_role_arn, account_id, region)
            if missing:
                missing_str = ", ".join(missing)
                return json.dumps(
                    {
                        "success": False,
                        "phase": "deploy",
                        "error": (
                            f"AgentCoreExecutionRole is missing required permissions: {missing_str}. "
                            f"Without these, AgentCore cannot determine whether to create or reuse "
                            f"log groups/streams, resulting in NO LOGS in the runtime log groups."
                        ),
                        "error_type": "PermissionError",
                        "hint": (
                            f"Add the following to AgentCoreExecutionRole:\n"
                            f"  - logs:DescribeLogStreams on arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*\n"
                            f"  - logs:DescribeLogGroups on arn:aws:logs:{region}:{account_id}:log-group:*"
                        ),
                    },
                    indent=2,
                )
        except Exception as e:
            logger.debug(f"Could not run permission pre-check: {e}")

        deploy_result_str = deploy_agent_to_agentcore(
            image_uri=build_result["image_uri"],
            agent_name=agent_name,
            execution_role_arn=execution_role_arn,
            region=region,
            stage=stage,
        )
        deploy_result = json.loads(deploy_result_str)

        if not deploy_result.get("success"):
            return json.dumps(
                {
                    "success": False,
                    "phase": "deploy",
                    "phases": {"build": phases["build"]},
                    "error": deploy_result.get("error"),
                    "error_type": deploy_result.get("error_type"),
                    "hint": deploy_result.get("hint"),
                },
                indent=2,
            )

        phases["deploy"] = {
            "runtime_id": deploy_result["runtime_id"],
            "runtime_arn": deploy_result["runtime_arn"],
            "runtime_name": deploy_result["runtime_name"],
            "status": deploy_result["status"],
        }
        logger.info(f"✓ Deploy phase complete: {deploy_result['runtime_arn']}")

        # Phase 3: Register with ATX (optional)
        if not skip_registry:
            logger.info("=" * 60)
            logger.info("PHASE 3: REGISTER WITH ATX")
            logger.info("=" * 60)

            # Auto-detect access role if not provided
            if not access_role_arn:
                access_role_arn = _get_default_access_role_arn(region)
                if not access_role_arn:
                    logger.warning(
                        "Could not auto-detect ATXAgentInvokeRole, skipping registry registration"
                    )
                    phases["register"] = {
                        "skipped": True,
                        "reason": "access_role_arn not provided and could not auto-detect ATXAgentInvokeRole",
                    }
                else:
                    register_result = _register_with_atx(
                        agent_name=agent_name,
                        agent_version=agent_version,
                        runtime_arn=deploy_result["runtime_arn"],
                        access_role_arn=access_role_arn,
                        registry_endpoint=registry_endpoint,
                        region=region,
                        job_orchestrator=job_orchestrator,
                        chat_ui_label=chat_ui_label,
                        chat_agent_identifier=chat_agent_identifier,
                        a2a_supported=a2a_supported,
                    )

                    if register_result.get("success"):
                        phases["register"] = register_result
                        logger.info(f"✓ Register phase complete: {agent_name} v{agent_version}")
                    else:
                        # Non-fatal: deployment succeeded even if registration failed
                        phases["register"] = {
                            "success": False,
                            "error": register_result.get("error"),
                            "warning": "Agent deployed successfully but registry registration failed",
                        }
                        logger.warning(
                            f"Registry registration failed: {register_result.get('error')}"
                        )
            else:
                register_result = _register_with_atx(
                    agent_name=agent_name,
                    agent_version=agent_version,
                    runtime_arn=deploy_result["runtime_arn"],
                    access_role_arn=access_role_arn,
                    registry_endpoint=registry_endpoint,
                    region=region,
                    job_orchestrator=job_orchestrator,
                    chat_ui_label=chat_ui_label,
                    chat_agent_identifier=chat_agent_identifier,
                    a2a_supported=a2a_supported,
                )

                if register_result.get("success"):
                    phases["register"] = register_result
                    logger.info(f"✓ Register phase complete: {agent_name} v{agent_version}")
                else:
                    # Non-fatal: deployment succeeded even if registration failed
                    phases["register"] = {
                        "success": False,
                        "error": register_result.get("error"),
                        "warning": "Agent deployed successfully but registry registration failed",
                    }
                    logger.warning(f"Registry registration failed: {register_result.get('error')}")
        else:
            phases["register"] = {"skipped": True, "reason": "skip_registry=True"}
            logger.info("Registry registration skipped")

        # Success summary
        logger.info("=" * 60)
        logger.info("DEPLOYMENT COMPLETE")
        logger.info("=" * 60)

        return json.dumps(
            {
                "success": True,
                "phases": phases,
                "summary": f"Agent {agent_name} v{agent_version} deployed successfully",
                "next_steps": [
                    "Test agent with ATX console or API",
                    "Monitor CloudWatch logs for runtime issues",
                    "Bind agent to workspace (for orchestrators)",
                ],
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Unexpected error in deploy_agent_full_pipeline")
        return json.dumps(
            {
                "success": False,
                "phase": "unknown",
                "phases": phases if phases else {},
                "error": str(e),
                "error_type": type(e).__name__,
            },
            indent=2,
        )
