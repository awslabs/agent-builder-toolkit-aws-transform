import logging
import os
from pathlib import Path
from typing import Optional

from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext
from agent_builder_sdk.server.server_models import AgentRuntimeContext

logger = logging.getLogger(__name__)

ENV_KEY_AWS_REGION = "AWS_REGION"
ENV_KEY_STAGE = "STAGE"
ENV_KEY_WORKSPACE_ID = "WORKSPACE_ID"
ENV_KEY_JOB_ID = "JOB_ID"
ENV_KEY_AGENT_INSTANCE_ID = "AGENT_INSTANCE_ID"
ENV_KEY_AGENT_ID = "AGENT_ID"
ENV_KEY_AGENT_VERSION = "AGENT_VERSION"
ENV_KEY_TENANT_ACCOUNT_ID = "TENANT_ACCOUNT_ID"
ENV_KEY_AUTHORIZATION_TOKEN = "AUTHORIZATION_TOKEN"
ENV_KEY_AUTH_TOKEN_FILE = "AUTH_TOKEN_FILE"
ENV_KEY_QT_AGENTIC_API_ENDPOINT = "QT_AGENTIC_API_ENDPOINT"
ENV_KEY_BEDROCK_SHARED_CAPACITY_ROLE_ARN = "BEDROCK_SHARED_CAPACITY_ROLE_ARN"
ENV_KEY_USE_EXTERNAL_AGENTIC_API = "USE_EXTERNAL_AGENTIC_API"

# Disable Flag, mainly for local test
ENV_KEY_DISABLE_PROD_BEDROCK_CAPACITY_FLAG = "DISABLE_PROD_BEDROCK_CAPACITY"
ENV_KEY_DISABLE_MCP_USAGE_FLAG = "DISABLE_MCP_USAGE"

# Constants for token file format
ATX_AUTH_TOKEN_KEY = "ATX_AUTHZ_TOKEN"


def should_use_prod_bedrock_capacity() -> bool:
    """
    Determine if prod Bedrock capacity should be used.

    Returns:
        bool: True if prod Bedrock capacity should be used, False otherwise
    """
    disable_flag = os.getenv(ENV_KEY_DISABLE_PROD_BEDROCK_CAPACITY_FLAG, "").lower()
    if disable_flag in ("true", "1", "yes"):
        logger.info("Prod Bedrock capacity disabled via environment variable")
        return False
    logger.info("Using prod Bedrock capacity by default")
    return True


def get_bedrock_shared_capacity_role_arn(region: str) -> Optional[str]:
    """
    Get the appropriate BedrockSharedCapacityRole ARN based on region.

    Args:
        region: AWS region name

    Returns:
        Role ARN if available, None otherwise
    """
    role_arn = os.getenv("BEDROCK_SHARED_CAPACITY_ROLE_ARN")
    if role_arn:
        logger.info(f"Using BedrockSharedCapacityRole ARN from environment: {role_arn}")
        return role_arn

    account_mappings = {
        "us-east-1": "982081074531",  # Prod IAD account
        "us-west-2": "982081074531",  # Use IAD account for PDX as per CDK logic
    }

    account_id = account_mappings.get(region)
    if account_id:
        role_arn = f"arn:aws:iam::{account_id}:role/BedrockSharedCapacityRole"
        logger.info(f"Using BedrockSharedCapacityRole ARN for region {region}: {role_arn}")
        return role_arn

    logger.warning(f"No BedrockSharedCapacityRole ARN available for region: {region}")
    return None


def retrieve_auth_token() -> str:
    auth_token_file_path = os.getenv(ENV_KEY_AUTH_TOKEN_FILE)
    if auth_token_file_path is None or not Path(auth_token_file_path).exists():
        raise ValueError(
            f"{ENV_KEY_AUTH_TOKEN_FILE} env-var is not set or auth-token file is not found"
        )

    # Read auth token from file if env-var is set and file exists
    auth_token = None
    try:
        with open(auth_token_file_path, "r") as file:
            for line in file:
                line = line.strip()
                if line.startswith(ATX_AUTH_TOKEN_KEY):
                    auth_token = line.split("=", 1)[1]
                    break
    except IOError as e:
        raise ValueError(f"Failed to read auth token from file {auth_token_file_path}: {e}")

    if not auth_token:
        raise ValueError(f"ATX_AUTHZ_TOKEN not found in credentials file {auth_token_file_path}")

    logger.info(f"Successfully read auth token from file: {auth_token_file_path}")
    return auth_token


def get_agent_context_from_env() -> AgenticApiRequestContext:
    """
    Get agent context from environment variables.

    Returns:
        AgenticApiRequestContext: The request context created from environment variables

    Raises:
        ValueError: If required environment variables are missing
    """
    # Get required environment variables
    job_id = os.getenv(ENV_KEY_JOB_ID)
    workspace_id = os.getenv(ENV_KEY_WORKSPACE_ID)
    agent_instance_id = os.getenv(ENV_KEY_AGENT_INSTANCE_ID)
    authorization_token = retrieve_auth_token()

    # Validate all required env vars are present
    if not all([job_id, workspace_id, agent_instance_id, authorization_token]):
        missing_vars = [
            var
            for var, val in [
                ("JOB_ID", job_id),
                ("WORKSPACE_ID", workspace_id),
                ("AGENT_INSTANCE_ID", agent_instance_id),
                ("AUTHORIZATION_TOKEN", authorization_token),
            ]
            if not val
        ]
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Create and return context
    return AgenticApiRequestContext(
        job_id=str(job_id),
        workspace_id=str(workspace_id),
        agent_instance_id=str(agent_instance_id),
        authorization_token=str(authorization_token),
    )


def _validate_mde_env_vars(raise_on_missing: bool = True) -> bool:
    """Validate MDE environment variables.

    Args:
        raise_on_missing: If True, raises ValueError on missing vars. If False, returns bool.

    Returns:
        bool: True if all required vars present, False otherwise (only when raise_on_missing=False)

    Raises:
        ValueError: When required vars missing and raise_on_missing=True
    """
    required_vars = [
        ENV_KEY_WORKSPACE_ID,
        ENV_KEY_JOB_ID,
        ENV_KEY_AGENT_INSTANCE_ID,
        ENV_KEY_AUTHORIZATION_TOKEN,
    ]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        if raise_on_missing:
            raise ValueError(f"Missing required environment variables for MDE mode: {missing_vars}")
        return False
    return True


def has_mde_environment() -> bool:
    """Check if MDE environment variables are available."""
    return _validate_mde_env_vars(raise_on_missing=False)


def get_agentic_api_request_context_with_current_token(
    base_context: AgentRuntimeContext,
) -> AgenticApiRequestContext:
    """Get agentic API request context with current auth token, using base context for IDs.

    Args:
        base_context: Existing context with workspace_id, job_id, agent_instance_id

    Returns:
        AgenticApiRequestContext with same IDs but current auth token
    """
    current_token = retrieve_auth_token()
    return AgenticApiRequestContext(
        workspace_id=base_context.workspace_id,
        job_id=base_context.job_id,
        agent_instance_id=base_context.agent_instance_id,
        authorization_token=current_token,
    )


def get_initial_agent_runtime_context_from_env() -> AgentRuntimeContext:
    """Get initial agent context from environment variables (including initial auth token)."""
    # Validate required vars (raises on missing)
    _validate_mde_env_vars(raise_on_missing=True)

    # Get values (we know they exist after validation)
    workspace_id = os.getenv(ENV_KEY_WORKSPACE_ID)
    job_id = os.getenv(ENV_KEY_JOB_ID)
    agent_instance_id = os.getenv(ENV_KEY_AGENT_INSTANCE_ID)
    initial_auth_token = os.getenv(ENV_KEY_AUTHORIZATION_TOKEN)

    return AgentRuntimeContext(
        workspace_id=str(workspace_id),
        job_id=str(job_id),
        agent_instance_id=str(agent_instance_id),
        initial_auth_token=initial_auth_token,
    )


def validate_required_env_vars():
    missing_vars = []
    for env_var, env_key in [
        ("AWS_REGION", ENV_KEY_AWS_REGION),
        ("STAGE", ENV_KEY_STAGE),
        ("WORKSPACE_ID", ENV_KEY_WORKSPACE_ID),
        ("JOB_ID", ENV_KEY_JOB_ID),
        ("AGENT_INSTANCE_ID", ENV_KEY_AGENT_INSTANCE_ID),
    ]:
        if not os.getenv(env_key):
            missing_vars.append(env_var)

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")


def set_runtime_env_vars(job_id: str, workspace_id: str, agent_instance_id: str) -> None:
    """Set runtime environment variables for agent execution.

    Args:
        job_id: Job ID to set
        workspace_id: Workspace ID to set
        agent_instance_id: Agent instance ID to set
    """
    for key, value in [
        (ENV_KEY_JOB_ID, job_id),
        (ENV_KEY_WORKSPACE_ID, workspace_id),
        (ENV_KEY_AGENT_INSTANCE_ID, agent_instance_id),
    ]:
        existing = os.getenv(key)
        if existing and existing != value:
            logger.warning(f"Overwriting {key} from {existing} to {value}")
        os.environ[key] = value


def is_external_agentic_api_enabled() -> bool:
    if (os.environ.get(ENV_KEY_USE_EXTERNAL_AGENTIC_API, "")).lower() == "true":
        logger.info("Using external agentic api")
        return True
    return False
