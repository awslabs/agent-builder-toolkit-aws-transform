# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
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


def mcp_session_active(mcp_client: Any) -> bool:
    """Return True if an MCP client's session is already open.

    Wraps Strands' ``MCPClient._is_session_active()`` (a leading-underscore method) in
    one place so callers don't couple to that private API directly. Used to decide
    whether a client must be entered (opened) for a turn or is already open — e.g. a
    shared client the server keeps open for concurrent streaming. Fails safe to
    ``False`` (treat as not-open → enter it) if the private method is ever removed.
    """
    checker = getattr(mcp_client, "_is_session_active", None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception:
        return False


def extract_source_information(message: Any) -> tuple[Optional[str], Optional[str]]:
    """Extract ``(user_id, sender)`` from an A2A message's source-information extension.

    Single source of truth for source extraction, used by both the buffered path
    (``extract_message_info``) and the streaming ingress, so the two classify a turn
    the same way. Requires the extension to be declared in ``message.extensions`` and
    present in ``message.metadata`` (an undeclared extension is ignored).

    Returns ``(None, None)`` when no valid source information is present.
    """
    user_id = None
    sender = None
    if message.extensions and A2A_SOURCE_INFORMATION_EXT in message.extensions and message.metadata:
        source_info = message.metadata[A2A_SOURCE_INFORMATION_EXT]
        user_id = source_info.get("onBehalfOfUser")
        sender = source_info.get("senderAgentInstanceId")
    return user_id, sender


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
    context_id = request.message.contextId
    user_id, sender = extract_source_information(message)

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

    return "\n".join(text_blocks).strip()


def describe_agent_result(result: Any) -> str:
    """Summarize an agent result for logs without its content.

    Agents may return their own result objects, so every field is optional and this never raises.
    """
    try:
        message = getattr(result, "message", None) or {}
        content = message.get("content") or []
        state = getattr(result, "state", None)
        return "stop_reason=%s, content_blocks=%s, state_keys=%s" % (
            getattr(result, "stop_reason", None),
            (
                [sorted(b) if isinstance(b, dict) else type(b).__name__ for b in content]
                if isinstance(content, list)
                else type(content).__name__
            ),
            sorted(state) if isinstance(state, dict) else None,
        )
    except Exception as e:
        # Not str(e): a broken __str__ would raise, and the message could carry content.
        return f"undescribable {type(result).__name__}: {type(e).__name__}"


class TransformEndpointConfig:
    """
    Configuration utility for AWS Transform endpoints and region mappings.
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
            "us-gov-west-1": "PDT",  # GovCloud West
            "us-gov-east-1": "OSU",  # GovCloud East
        }

        airport_code = region_mapping.get(region.lower())
        if airport_code is None:
            raise ValueError(f"Unsupported AWS region: {region}")

        return airport_code

    @staticmethod
    def get_root_dns_domain(region: str) -> str:
        """
        Resolves the Elastic Gumby DNS apex for a region's partition.

        GovCloud endpoints live under a separate child zone
        (us-gov.elastic-gumby.ai.aws.dev), not the commercial apex. Building a gov
        endpoint on the commercial apex yields a hostname with no DNS record in the
        gov partition, causing SdkClientException "Unable to execute HTTP request".
        """
        if region.lower().startswith("us-gov-"):
            return "us-gov.elastic-gumby.ai.aws.dev"
        return "elastic-gumby.ai.aws.dev"

    @staticmethod
    def create_endpoint_url(stage: str, region: str, component_name: str) -> str:
        """
        Creates the endpoint URL for AWS Transform services.

        Args:
            stage: Environment stage (e.g., 'prod', 'beta', 'gamma')
            region: AWS region code
            component_name: Service component name

        Returns:
            The fully constructed endpoint URL

        Raises:
            ValueError: If the provided region is not supported
        """
        airport_code = TransformEndpointConfig.get_airport_code_for_region(region).lower()
        root_domain = TransformEndpointConfig.get_root_dns_domain(region)
        return f"https://{airport_code}.{stage.lower()}.{component_name}.{root_domain}"

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
        return TransformEndpointConfig.create_external_agenticapi_endpoint_url(
            str(os.getenv(ENV_KEY_STAGE)), str(os.getenv(ENV_KEY_AWS_REGION))
        )

    return TransformEndpointConfig.create_endpoint_url(
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
            # A client the caller keeps open (e.g. a shared client for concurrent
            # streaming) is already active — list tools on it directly. Re-entering it
            # would raise ("session currently running") and close it for others on exit.
            # A standalone client is entered/exited here to list its tools, as before.
            if mcp_session_active(mcp_client):
                mcp_tools = mcp_client.list_tools_sync()
            else:
                with mcp_client:
                    mcp_tools = mcp_client.list_tools_sync()
            for tool in mcp_tools:
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


INTERRUPTED_TURN_TEXT = "[No response: this request was interrupted before it completed.]"


def reconcile_unanswered_user_turns(messages: List[Any]) -> List[Any]:
    """Insert a placeholder assistant reply after each user message that never got one.

    A turn that is aborted (timeout, client disconnect, crash) has already persisted its user
    message but no reply. Left as is, the next turn sends two user messages in a row and the model
    answers the earlier one. History is loaded before the new prompt is appended, so a trailing
    user message is unanswered, unless another invocation for the same source is still answering
    it (a concurrent turn on a shared repository); that reader then sees the placeholder, which is
    no worse than two user messages in a row. Like reconcile_dangling_tool_uses, this never
    mutates the caller's messages and leaves a well-formed history unchanged. Unanswered
    blank-reply continuations are dropped first; an answered one directly follows the turn it
    re-asks, so it is left alone and does not count as that turn's missing reply.
    """
    from agent_builder_sdk.orchestrator_strands.hooks.blank_reply_hook_provider import (
        BLANK_REPLY_CONTINUATION_MARKER,
        drop_unanswered_continuations,
    )

    messages = drop_unanswered_continuations(messages)

    def is_continuation(message: Any) -> bool:
        custom = (message.get("metadata") or {}).get("custom") or {}
        return bool(custom.get(BLANK_REPLY_CONTINUATION_MARKER))

    result: List[Any] = []
    for idx, message in enumerate(messages):
        result.append(message)
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        following = messages[idx + 1] if idx + 1 < len(messages) else None
        if following is None or (
            isinstance(following, dict)
            and following.get("role") == "user"
            and not is_continuation(following)
        ):
            result.append({"role": "assistant", "content": [{"text": INTERRUPTED_TURN_TEXT}]})
    return result


def reconcile_dangling_tool_uses(messages: List[Any]) -> List[Any]:
    """Insert error tool results immediately after assistant tool uses left unresolved.

    Bedrock requires a toolUse to be answered in the message that IMMEDIATELY follows it, so a
    result appearing later in the list is as invalid as a missing one — hence only the next
    message is consulted. History is persisted per message, before a tool runs, so an interrupted
    turn leaves an unpaired toolUse on disk that fails every later Converse call until repaired.

    Never mutates a message: a turn whose results arrived only in part gets a copy of its result
    message with the missing ones appended. So the caller's stored objects — which the loaded
    messages alias — are left untouched, and a well-formed history round-trips unchanged.
    """
    if not messages:
        return messages
    result = list(messages)
    idx = 0
    while idx < len(result):
        message = result[idx]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            idx += 1
            continue

        tool_use_ids: List[Any] = []
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            tool_use = block.get("toolUse")
            if isinstance(tool_use, dict) and "toolUseId" in tool_use:
                tool_use_ids.append(tool_use["toolUseId"])

        following_tool_result_ids: List[Any] = []
        if idx + 1 < len(result):
            following_message = result[idx + 1]
            if isinstance(following_message, dict):
                for block in following_message.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    tool_result = block.get("toolResult")
                    if isinstance(tool_result, dict) and "toolUseId" in tool_result:
                        following_tool_result_ids.append(tool_result["toolUseId"])

        unmatched_tool_use_ids = [
            tool_use_id
            for tool_use_id in tool_use_ids
            if tool_use_id not in following_tool_result_ids
        ]
        if unmatched_tool_use_ids:
            error_blocks: List[Any] = [
                {
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [{"text": "Tool did not complete; the turn was interrupted."}],
                        "status": "error",
                    }
                }
                for tool_use_id in unmatched_tool_use_ids
            ]
            if following_tool_result_ids:
                # The next message already carries this turn's results and resolved only some of
                # the ids, so the missing ones have to join it. A separate message would displace
                # the real results out of the only position Bedrock accepts them in.
                partial_message = result[idx + 1]
                result[idx + 1] = {
                    **partial_message,
                    "content": [*(partial_message.get("content") or []), *error_blocks],
                }
            else:
                # Leaves two adjacent user turns when the next message is user text. That is the
                # shape BedrockModel._separate_tool_result_turns normalises request-locally, so do
                # NOT "fix" it by merging the results into that message — a turn carrying both
                # conversation and toolResult blocks is rejected outright.
                result.insert(idx + 1, {"role": "user", "content": error_blocks})
            idx += 2
        else:
            idx += 1
    return result


def drop_orphan_tool_results(messages: List[Any]) -> List[Any]:
    """Remove toolResult blocks whose toolUse is not in the message immediately before.

    Bedrock rejects a toolResult with no matching toolUse just as it rejects the reverse. Two turns
    interleaving their writes (or a notification merge) can leave one. Never mutates a message; a
    message left with no content keeps one text block so the turn order around it is unchanged.
    """
    result = list(messages)
    for idx, message in enumerate(result):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content") or []
        previous = result[idx - 1] if idx > 0 else None
        tool_use_ids = set()
        if isinstance(previous, dict) and previous.get("role") == "assistant":
            for block in previous.get("content") or []:
                if isinstance(block, dict) and isinstance(block.get("toolUse"), dict):
                    tool_use_ids.add(block["toolUse"].get("toolUseId"))
        kept = [
            block
            for block in content
            if not (
                isinstance(block, dict)
                and isinstance(block.get("toolResult"), dict)
                and block["toolResult"].get("toolUseId") not in tool_use_ids
            )
        ]
        if len(kept) != len(content):
            result[idx] = {**message, "content": kept or [{"text": "(stale tool result removed)"}]}
    return result
