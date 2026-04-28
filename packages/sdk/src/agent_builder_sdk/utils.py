import logging
import os
import tempfile
from importlib.resources import read_text
from multiprocessing import Process
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from pydantic import BaseModel
from strands.agent import AgentResult

from agent_builder_sdk.custom_types.common_types import (
    A2AError,
    A2AErrorCode,
    A2AMessage,
    InvocationRequest,
)
from agent_builder_sdk.custom_types.extension_types import ExtensionResponse
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.env_var import (
    ENV_KEY_AWS_REGION,
    ENV_KEY_STAGE,
    is_external_agentic_api_enabled,
)
from agent_builder_sdk.extensions.base_extension_handler import BaseExtensionHandler
from agent_builder_sdk.message_queue import QueueResponse
from agent_builder_sdk.util.suggestions_manager import get_and_consume_suggestions

# A2A Extension constants
A2A_SOURCE_INFORMATION_EXT = "https://aws.com/transform/ext/source_information/v1"
A2A_CHAT_SUGGESTIONS_EXT = "https://aws.com/transform/ext/chat_suggestions/v1"
A2A_MESSAGE_TYPE_EXT = "https://aws.com/transform/ext/message_type/v1"

logger = logging.getLogger(__name__)


def get_prompt() -> str:
    return get_prompt_with_name("system_prompt")


def get_base_guardrail_prompt() -> str:
    return get_prompt_with_name("base_guardrails")


def get_prompt_with_name(file_name: str) -> str:
    return read_text("agent_builder_sdk.prompts", f"{file_name}.md").strip()


def convert_queue_response_to_send_message_output(
    response: Optional[QueueResponse], request_message: A2AMessage, sender: str | None = None
) -> SendMessageOutput:
    error: Optional[A2AError] = None
    result: Optional[A2AMessage] = None
    if response and response.error_message:
        error = A2AError(code=A2AErrorCode.INTERNAL_ERROR, message=response.error_message)

    else:
        parts = []
        if response and response.message:
            parts = [{"text": response.message, "kind": "text"}]

        extensions = response.extensions if response and response.extensions else []
        metadata = response.metadata if response and response.metadata else {}

        if sender and A2A_SOURCE_INFORMATION_EXT not in metadata:
            metadata[A2A_SOURCE_INFORMATION_EXT] = {"senderAgentInstanceId": sender}

        if A2A_SOURCE_INFORMATION_EXT in metadata and A2A_SOURCE_INFORMATION_EXT not in extensions:
            extensions.append(A2A_SOURCE_INFORMATION_EXT)

        pending_suggestions = get_and_consume_suggestions()
        if pending_suggestions:
            metadata[A2A_CHAT_SUGGESTIONS_EXT] = pending_suggestions
            if A2A_CHAT_SUGGESTIONS_EXT not in extensions:
                extensions.append(A2A_CHAT_SUGGESTIONS_EXT)

        result = A2AMessage(
            role="agent",
            parts=parts,
            messageId=request_message.messageId,
            kind="message",
            contextId=response.context_id if response else None,
            metadata=metadata,
            extensions=extensions,
        )

    return SendMessageOutput(error=error, result=result)


def convert_subagent_response_to_send_message_output(
    context_id: str | None,
    request_message: A2AMessage,
    response: Optional[str] = None,
    error_message: Optional[str] = None,
    sender: str | None = None,
) -> SendMessageOutput:
    if error_message:
        error = A2AError(code=A2AErrorCode.INTERNAL_ERROR, message=error_message)
        return SendMessageOutput(error=error, result=None)

    parts = [{"text": response, "kind": "text"}] if response else []

    metadata: dict[str, Any] = {}
    extensions: list[str] = []
    if sender:
        metadata[A2A_SOURCE_INFORMATION_EXT] = {"senderAgentInstanceId": sender}
        extensions.append(A2A_SOURCE_INFORMATION_EXT)

    result = A2AMessage(
        role="agent",
        parts=parts,
        messageId=request_message.messageId,
        kind="message",
        contextId=context_id,
        metadata=metadata,
        extensions=extensions,
    )
    return SendMessageOutput(error=None, result=result)


class MessageInfo(BaseModel):
    user_id: str | None
    sender: str | None
    task_id: str | None
    context_id: str | None
    parts: list[dict[str, Any]]


def extract_message_info(request: InvocationRequest) -> MessageInfo:
    """
    Extract user information and process message parts from the request.

    This function extracts relevant information from an A2A invocation request.
    It also normalizes the first message part by converting the "kind" field to "type".

    Args:
        request: The InvocationRequest containing the A2A message to process.

    Returns:
        MessageInfo: Extracted and processed message information.
    """
    message = request.message
    task_id = message.taskId
    parts = message.parts
    user_id = None
    sender = None
    context_id = request.message.contextId
    if message.extensions and A2A_SOURCE_INFORMATION_EXT in message.extensions and message.metadata:
        source_info = message.metadata[A2A_SOURCE_INFORMATION_EXT]
        if "onBehalfOfUser" in source_info:
            user_id = source_info["onBehalfOfUser"]
        if "senderAgentInstanceId" in source_info:
            sender = source_info["senderAgentInstanceId"]

    parts[0]["type"] = parts[0]["kind"]

    del parts[0]["kind"]

    return MessageInfo(
        user_id=user_id,
        sender=sender,
        task_id=task_id,
        context_id=context_id,
        parts=parts,
    )


def process_extension_handlers(
    request: InvocationRequest,
    request_id: str,
    context_id: str | None,
    sender: str | None,
    user_id: str | None,
    extension_handlers: Optional[Sequence[BaseExtensionHandler]],
) -> Optional[ExtensionResponse]:
    """
    Process extension handlers for A2A message extensions.

    Args:
        request: The invocation request
        request_id: The request ID
        context_id: The context ID
        sender: The sender agent instance ID
        user_id: The user ID
        extension_handlers: List of extension handlers

    Returns:
        Extension handler response if processed, None otherwise
    """
    message_extensions = getattr(request.message, "extensions", []) or []
    handler_by_uri = {handler.uri: handler for handler in (extension_handlers or [])}

    handler_response = None
    for ext_uri in message_extensions:
        handler = handler_by_uri.get(ext_uri)
        if handler and handler.should_process(
            request=request, sender=sender, user_id=user_id, context_id=context_id
        ):
            logger.info(f"Processing supported extension: {ext_uri}")
            handler_response = handler.process_request(
                request=request,
                request_id=request_id,
                context_id=context_id,
                sender=sender,
                user_id=user_id,
            )
        else:
            logger.info(f"Ignoring unsupported extension: {ext_uri}")

    return handler_response


def extract_text_from_strands_agent_response(response: AgentResult) -> str:
    """
    Extracts the text from the response of the Strands agent.

    Args:
        response: The response from the Strands agent.

    Returns:
        The text extracted from the response.
    """
    text_blocks = []
    for block in response.message["content"]:
        if text := block.get("text", "").strip():
            text_blocks.append(text)
        else:
            logger.warning("Encountered non-text content block in agent result: %s", block)

    return "\n".join(text_blocks).strip()


class ElasticGumbyEndpointConfig:
    """
    Configuration utility for Elastic Gumby endpoints and region mappings.
    """

    @staticmethod
    def get_airport_code_for_region(region: str) -> str:
        """
        Maps AWS regions to their corresponding airport codes.

        Args:
            region: AWS region code (e.g., 'us-east-1')

        Returns:
            The airport code corresponding to the region

        Raises:
            ValueError: If the provided region is not supported
        """
        region_mapping: Dict[str, str] = {
            "us-east-1": "IAD",  # N. Virginia
            "us-east-2": "CMH",  # Ohio
            "us-west-1": "SFO",  # N. California
            "us-west-2": "PDX",  # Oregon
            "af-south-1": "CPT",  # Cape Town
            "ap-east-1": "HKG",  # Hong Kong
            "ap-south-1": "BOM",  # Mumbai
            "ap-northeast-1": "NRT",  # Tokyo
            "ap-northeast-2": "ICN",  # Seoul
            "ap-northeast-3": "KIX",  # Osaka
            "ap-southeast-1": "SIN",  # Singapore
            "ap-southeast-2": "SYD",  # Sydney
            "ap-southeast-3": "JKT",  # Jakarta
            "ca-central-1": "YUL",  # Montreal
            "eu-central-1": "FRA",  # Frankfurt
            "eu-west-1": "DUB",  # Ireland - Dublin
            "eu-west-2": "LHR",  # London
            "eu-west-3": "CDG",  # Paris
            "eu-north-1": "ARN",  # Stockholm
            "eu-south-1": "MXP",  # Milan
            "me-south-1": "BAH",  # Bahrain
            "sa-east-1": "GRU",  # São Paulo
        }

        airport_code = region_mapping.get(region.lower())
        if airport_code is None:
            raise ValueError(f"Unsupported AWS region: {region}")

        return airport_code

    @staticmethod
    def create_endpoint_url(stage: str, region: str, component_name: str) -> str:
        """
        Creates the endpoint URL for Elastic Gumby services.

        Args:
            stage: Environment stage (e.g., 'prod', 'beta', 'gamma')
            region: AWS region code
            component_name: Service component name

        Returns:
            The fully constructed endpoint URL

        Raises:
            ValueError: If the provided region is not supported
        """
        airport_code = ElasticGumbyEndpointConfig.get_airport_code_for_region(region).lower()
        return f"https://{airport_code}.{stage.lower()}.{component_name}.elastic-gumby.ai.aws.dev"

    @staticmethod
    def create_external_agenticapi_endpoint_url(stage: str, region: str):
        if "prod" == stage.lower():
            return f"https://transform-agents.{region}.api.aws"
        return f"https://transform-agents-{stage.lower()}.{region}.api.aws"


def build_agentic_api_endpoint_from_env():
    """
    Build the Agentic API endpoint URL from environment variables.

    Returns:
        str: The fully constructed Agentic API endpoint URL

    Raises:
        ValueError: If STAGE or AWS_REGION environment variables are not set or empty
    """
    if not os.getenv(ENV_KEY_STAGE) or not os.getenv(ENV_KEY_AWS_REGION):
        raise ValueError(
            "STAGE and AWS_REGION env variables must be non-empty when building AgenticApi endpoint"
        )

    if is_external_agentic_api_enabled():
        return ElasticGumbyEndpointConfig.create_external_agenticapi_endpoint_url(
            str(os.getenv(ENV_KEY_STAGE)), str(os.getenv(ENV_KEY_AWS_REGION))
        )

    return ElasticGumbyEndpointConfig.create_endpoint_url(
        str(os.getenv(ENV_KEY_STAGE)), str(os.getenv(ENV_KEY_AWS_REGION)), "agenticapi"
    )


def get_default_auth_token_file_path() -> str:
    """
    Get the default file path for AWS authentication token storage.

    Determines the appropriate location for storing AWS authentication tokens based on
    the runtime environment. In containerized environments, uses the standard AWS
    location under the amazon user's home directory. In local development environments,
    uses the current user's home directory.

    Returns:
        str: The absolute path to the authentication token file

    Environment Detection:
        - Container (CONTAINER_ENV set): /home/amazon/.aws/transform-credentials
        - Local development: ~/.aws/transform-credentials
    """
    if os.environ.get("CONTAINER_ENV"):
        # Container: Use amazon user's home directory (standard AWS location)
        return "/home/amazon/.aws/transform-credentials"
    else:
        # Local: Use current user's home directory
        return str(Path.home() / ".aws" / "transform-credentials")


def build_mcp_args_from_parsed_args(args) -> Dict[str, str]:
    """
    Build required MCP arguments dictionary from parsed command line arguments.

    Args:
        args: Parsed command line arguments containing MCP-related parameters

    Returns:
        Dictionary containing required MCP arguments

    Raises:
        AttributeError: If required arguments are missing from args
    """

    required_attrs = ["binary_location", "workspace_id", "job_id", "agent_instance_id"]
    missing_attrs = [attr for attr in required_attrs if not hasattr(args, attr)]

    if missing_attrs:
        raise AttributeError(f"Missing required arguments: {', '.join(missing_attrs)}")

    agentic_api_endpoint = (
        args.agentic_api_endpoint
        if hasattr(args, "agentic_api_endpoint") and args.agentic_api_endpoint is not None
        else build_agentic_api_endpoint_from_env()
    )

    return {
        "binaryLocation": args.binary_location,
        "workspaceId": args.workspace_id,
        "jobId": args.job_id,
        "agentInstanceId": args.agent_instance_id,
        "agenticApiEndpoint": agentic_api_endpoint,
        "authTokenFile": get_default_auth_token_file_path(),
    }


def combine_tools(
    mcp_clients: Optional[List[Any]] = None,
    custom_tools: Optional[List[Any]] = None,
    excluded_tool_names: Optional[Set[str]] = None,
    excluded_mcp_tool_names: Optional[Set[str]] = None,
) -> Optional[List[Any]]:
    """
    Combine tools from MCP clients with custom tools, with optional filtering.

    Args:
        mcp_clients: List of MCP clients to get tools from
        custom_tools: List of custom tools to include
        excluded_tool_names: Set of tool names to exclude

    Returns:
        Combined list of tools with duplicates checked and exclusions applied

    Raises:
        ValueError: If duplicate tool names are found
    """
    all_tools: List[Any] = []
    tool_names = set()
    excluded_tool_names = excluded_tool_names or set()
    excluded_mcp_tool_names = excluded_mcp_tool_names or set()

    def add_tool(tool):
        if tool.tool_name in excluded_tool_names:
            logger.info(f"Excluding tool: {tool.tool_name}")
            return
        if tool.tool_name in tool_names:
            raise ValueError(f"Duplicate tool name found: '{tool.tool_name}'")
        tool_names.add(tool.tool_name)
        all_tools.append(tool)

    # Add MCP tools
    if mcp_clients:
        for mcp_client in mcp_clients:
            with mcp_client:
                for tool in mcp_client.list_tools_sync():
                    if tool.tool_name in excluded_mcp_tool_names:
                        logger.info(f"Excluding mcp tool: {tool.tool_name}")
                        continue
                    add_tool(tool)

    # Add custom tools
    if custom_tools:
        for tool in custom_tools:
            add_tool(tool)

    return all_tools


def cleanup_process_safely(process: Process, process_name: str, timeout: int = 5):
    """
    Safely cleanup a multiprocessing. Process to avoid deadlocks.

    Args:
        process: The process to cleanup
        process_name: Name of the process for logging
        timeout: Timeout in seconds for graceful termination
    """
    if not process or not process.is_alive():
        return

    logger.info(f"Terminating {process_name} process...")

    try:
        # First, try graceful termination
        process.terminate()
        process.join(timeout=timeout)

        if process.is_alive():
            logger.warning(
                f"{process_name} process did not terminate gracefully within {timeout}s, force killing..."
            )
            process.kill()
            process.join(timeout=2)  # Short timeout for kill

            if process.is_alive():
                logger.error(f"Failed to kill {process_name} process")
            else:
                logger.info(f"{process_name} process killed successfully")
        else:
            logger.info(f"{process_name} process terminated gracefully")

    except Exception as e:
        logger.error(f"Error cleaning up {process_name} process: {e}")
        try:
            # Last resort - force kill
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
        except Exception as kill_error:
            logger.error(f"Failed to force kill {process_name} process: {kill_error}")


def write_content_to_file(content: str, file_path: str) -> None:
    """Atomically write content to file to prevent race conditions with concurrent readers."""
    dir_path = os.path.dirname(file_path) or "."
    temp_path = None
    try:
        os.makedirs(dir_path, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False) as tf:
            tf.write(content)
            temp_path = tf.name
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(temp_path, file_path)
        logger.info(f"Successfully wrote content to {file_path}")
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        logger.error(f"Failed to write to {file_path}: {e}")
        raise
