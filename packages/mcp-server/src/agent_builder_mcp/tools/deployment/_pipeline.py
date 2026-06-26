# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Full deployment pipeline orchestration."""

import json
import logging
import uuid

import boto3

from ..registry._client import registry_client
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


def _get_default_role_arn(role_name: str, label: str) -> str | None:
    """
    Auto-detect an IAM role ARN in the current account.

    Constructs the ARN from the caller's account ID and the given role name.

    Args:
        role_name: IAM role name (e.g. "AgentCoreExecutionRole")
        label: Human-readable label for log messages (e.g. "execution role")

    Returns:
        Role ARN or None if not found
    """
    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        logger.info(f"Using {label}: {role_arn} (constructed from account ID, not verified)")
        return role_arn
    except Exception as e:
        logger.warning(f"Could not auto-detect {label}: {e}")
        return None


def _get_default_execution_role_arn() -> str | None:
    """Auto-detect AgentCoreExecutionRole ARN in the current account."""
    return _get_default_role_arn("AgentCoreExecutionRole", "execution role")


def _get_default_access_role_arn() -> str | None:
    """Auto-detect ATXAgentInvokeRole ARN in the current account."""
    return _get_default_role_arn("ATXAgentInvokeRole", "access role")


def _build_provider_contact(owner_contact_info: str) -> list[dict]:
    """
    Build the Agent Provider contactInfo list from the owner contact.

    The registry requires a non-empty ``contactInfo`` list on the Agent Provider
    extension. The contact ``type`` is inferred as ``email`` when the value looks
    like an email address, otherwise ``other`` — both are valid contact types
    accepted by the registry.

    Args:
        owner_contact_info: Owner contact (email or other identifier)

    Returns:
        contactInfo list with a single contact entry
    """
    contact_type = "email" if "@" in owner_contact_info else "other"
    return [{"type": contact_type, "value": owner_contact_info}]


def _register_with_atx(
    agent_name: str,
    agent_version: str,
    runtime_arn: str,
    access_role_arn: str,
    registry_endpoint: str,
    owner_contact_info: str,
    region: str = "us-east-1",
    job_orchestrator: bool = False,
    chat_ui_label: str | None = None,
    chat_agent_identifier: str | None = None,
    a2a_supported: bool = True,
) -> dict:
    """
    Register agent with ATX registry.

    Performs three steps: RegisterAgent, PublishAgentVersion,
    UpdatePublisherAccessControl. Uses the same registry client as the
    standalone MCP tools.

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
        owner_contact_info: Required owner contact (email or CTI) for agent
            notifications. Used for both the agent metadata ownerContactInfo and
            the Agent Provider extension contactInfo. Must be non-blank.

    Returns:
        Registration result dict
    """
    try:
        if not owner_contact_info or not owner_contact_info.strip():
            return {
                "success": False,
                "error": "owner_contact_info is required and must be a non-blank string",
                "error_type": "ValidationError",
            }

        client = registry_client(region=region, endpoint_url=registry_endpoint)
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]

        # Step 1: RegisterAgent
        metadata: dict = {
            "type": "ORCHESTRATOR_AGENT" if job_orchestrator else "SUB_AGENT",
            "description": f"ATX agent: {agent_name}",
            "ownerName": agent_name,
            "ownerContactInfo": owner_contact_info,
            "ownerType": "DIRECT_AGENT",
            "customerConfigurationRequired": False,
            "jobOrchestrator": job_orchestrator,
        }
        if job_orchestrator:
            metadata["jobOrchestratorMetadata"] = {
                "chatUILabel": chat_ui_label or agent_name,
                "chatAgentIdentifier": chat_agent_identifier or agent_name,
                "a2aSupported": a2a_supported,
            }

        logger.info(f"Step 1/3: Registering agent '{agent_name}'")
        try:
            client.register_agent(
                name=agent_name,
                metadata=metadata,
                idempotencyToken=str(uuid.uuid4()),
            )
            logger.info(f"Agent '{agent_name}' registered")
        except client.exceptions.ConflictException:
            logger.info(f"Agent '{agent_name}' already registered, continuing to publish")

        # Step 2: PublishAgentVersion
        configuration: dict = {
            "shortDescription": f"ATX agent: {agent_name}",
            "agentResiliencyConfiguration": {
                "partnerControllerRetryWindowMinutes": 6,
                "agentRecoveryConfiguration": {"recoveryWaitTimeSeconds": 60},
            },
            "computeConfiguration": {
                "provisionedComputeConfiguration": {
                    "agentCoreConfiguration": {
                        "runtimeArn": runtime_arn,
                        "atxAccessRoleArn": access_role_arn,
                    }
                }
            },
            "inputPayloadSchema": {},
            "outputPayloadSchema": {},
            "objectiveNegotiationPrompt": "",
            "monitoringType": "HEALTHCHECK",
            "notificationsEnabled": "ENABLED",
            "agentCard": {
                "id": agent_name,
                "name": agent_name,
                "description": f"ATX agent: {agent_name}",
                "version": agent_version,
                "capabilities": {
                    "restartable": True,
                    "a2aSupported": a2a_supported,
                    "legacyDashboard": False,
                    "legacyTaskLink": False,
                    "webAppV2": True,
                    "legacyRestartable": False,
                    "extensions": [
                        {
                            "name": "Agent Provider",
                            "description": "Agent publisher details",
                            "params": {
                                "name": agent_name,
                                "accountId": account_id,
                                "ownerType": "DIRECT_AGENT",
                                "contactInfo": _build_provider_contact(owner_contact_info),
                            },
                        },
                        {
                            "name": "Agent Dependencies",
                            "description": "Runtime dependencies",
                            "params": {"agentDependencies": []},
                        },
                        {
                            "name": "Agent Connectors",
                            "description": "Agent connector configurations",
                            "params": {"connectors": []},
                        },
                    ],
                },
                "skills": [],
            },
        }

        logger.info(f"Step 2/3: Publishing version '{agent_version}'")
        try:
            client.publish_agent_version(
                name=agent_name,
                version=agent_version,
                configuration=configuration,
                idempotencyToken=str(uuid.uuid4()),
            )
            logger.info(f"Version '{agent_version}' published")
        except client.exceptions.ConflictException:
            logger.info(f"Version '{agent_version}' already published, continuing to access control")

        # Step 3: UpdatePublisherAccessControl (grant own account)
        # Only ConflictException is non-fatal (access already enabled).
        # ValidationException (e.g. allowlist at capacity) and AccessDeniedException
        # indicate the agent is registered but unusable — let them propagate.
        try:
            logger.info(f"Step 3/3: Enabling access for account {account_id}")
            client.update_publisher_access_control(
                agentName=agent_name,
                customerAccountId=account_id,
                accessControl="ENABLED",
                idempotencyToken=str(uuid.uuid4()),
            )
            logger.info(f"Access enabled for account {account_id}")
        except client.exceptions.ConflictException:
            logger.info(f"Access already enabled for account {account_id}")

        return {
            "success": True,
            "agent_name": agent_name,
            "version": agent_version,
            "visibility": "RESTRICTED",
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
    owner_contact_info: str,
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
        owner_contact_info: Required owner contact (email or CTI) for agent
            notifications. Populates agent metadata ownerContactInfo and the
            Agent Provider extension contactInfo. Must be non-blank (only
            enforced when registry registration runs, i.e. skip_registry=False).

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

        if not skip_registry and (not owner_contact_info or not owner_contact_info.strip()):
            return json.dumps(
                {
                    "success": False,
                    "phase": "validate",
                    "error": "owner_contact_info is required and must be a non-blank string",
                    "error_type": "ValidationError",
                    "hint": "Pass owner_contact_info (email or CTI) so partners can be contacted.",
                },
                indent=2,
            )

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
            execution_role_arn = _get_default_execution_role_arn()
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
        # permissions that AgentCore needs internally. SimulatePrincipalPolicy can
        # return false negatives for AWS managed policies, so this is a warning only.
        try:
            sts = boto3.client("sts")
            account_id = sts.get_caller_identity()["Account"]
            iam = boto3.client("iam")
            missing = _check_logging_permissions(iam, execution_role_arn, account_id, region)
            if missing:
                missing_str = ", ".join(missing)
                logger.warning(
                    f"IAM permission pre-check reports potentially missing permissions: {missing_str}. "
                    f"This may be a false positive (e.g. AWS managed policies). Proceeding with deployment. "
                    f"If you see no logs after deployment, add: "
                    f"logs:DescribeLogStreams and logs:DescribeLogGroups to AgentCoreExecutionRole."
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
                access_role_arn = _get_default_access_role_arn()
                if not access_role_arn:
                    logger.warning(
                        "Could not auto-detect ATXAgentInvokeRole, skipping registry registration"
                    )
                    phases["register"] = {
                        "skipped": True,
                        "reason": "access_role_arn not provided and could not auto-detect ATXAgentInvokeRole",
                    }

            if access_role_arn:
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
                    owner_contact_info=owner_contact_info,
                )

                if register_result.get("success"):
                    phases["register"] = register_result
                    logger.info(f"✓ Register phase complete: {agent_name} v{agent_version}")
                else:
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
