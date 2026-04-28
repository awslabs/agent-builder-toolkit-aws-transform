"""
Agent factory functions for creating orchestrator instances.
"""

import logging
import os
from typing import Any, Optional, Set, TypeVar, Union

from strands.models.model import Model
from strands.tools.mcp.mcp_client import MCPClient

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent, BaseSubagent
from agent_builder_sdk.memory.episodic_memory import EpisodicMemory
from agent_builder_sdk.memory.file_memory_repository import FileSystemRepository
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.metrics.metrics_config import MetricsConfig
from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
    AsyncBaseOrchestrator,
    BaseOrchestrator,
)
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider import (
    ConversationHookProvider,
)
from agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider import (
    MemoryHookProvider,
)
from agent_builder_sdk.orchestrator_strands.tools.memory_tool import MemoryTool
from agent_builder_sdk.orchestrator_strands.tools.send_message_tools import SendMessageTools
from agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools import (
    SubagentRegistryTools,
)
from agent_builder_sdk.utils import get_base_guardrail_prompt, get_prompt_with_name

OrchestratorT = TypeVar("OrchestratorT", BaseOrchestrator, AsyncBaseOrchestrator)
SubagentT = TypeVar("SubagentT", BaseSubagent, AsyncBaseSubagent)

logger = logging.getLogger(__name__)


def _create_default_orchestrator(
    agent_class: type[OrchestratorT],
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
    system_prompt: Optional[str] = None,
    *,
    with_subagent: bool = False,
    additional_custom_tools: Optional[list[Any]] = None,
    model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
    model: Union[Model, str, None] = None,
    with_base_guardrails: bool = False,
    trace_attributes: Optional[dict[str, Any]] = None,
    excluded_mcp_tool_names: Optional[Set[str]] = None,
    metrics_config: Optional[MetricsConfig] = None,
    enable_skills: bool = False,
    skills_dir: Optional[str] = None,
    enable_code_execution: bool = False,
) -> OrchestratorT:
    logger.info("Creating default orchestrator with full feature set")

    custom_tools: list[Any] = []

    # Create memory components
    memory_storage_path = os.path.join(storage_dir, "memories")
    repository = FileSystemRepository(storage_path=memory_storage_path)
    episodic_memory = EpisodicMemory(repository=repository)
    memory_manager = MemoryManager(memories=[episodic_memory])

    # Create memory tool
    memory_tool = MemoryTool(memory_manager)
    custom_tools.append(memory_tool.memory)

    if with_subagent:
        # Create subagent discovery tool
        subagent_registry_tools = SubagentRegistryTools()
        custom_tools.append(subagent_registry_tools.discover_subagents)

        # Create send message to subagent tool
        send_message_tools = SendMessageTools()
        custom_tools.append(send_message_tools.send_message_to_subagent)

    # Build skills plugin if enabled
    skills_plugin = None
    if enable_skills:
        from strands.vended_plugins.skills import AgentSkills

        skills_source = skills_dir or os.environ.get("STRANDS_SKILLS_DIR") or "./skills"
        skills_plugin = AgentSkills(skills=[skills_source])
        logger.info("Created AgentSkills plugin for orchestrator")

    # Add experimental code execution tool if enabled
    if enable_code_execution:
        from agent_builder_sdk.experimental.code_execution import python_repl

        custom_tools.append(python_repl)
        logger.info("Added experimental python_repl tool to orchestrator")

    # Add any additional custom tools provided by caller
    if additional_custom_tools:
        custom_tools.extend(additional_custom_tools)

    # Create conversation repository
    conversation_repository = FileMultiSourceConversationRepository(storage_dir=storage_dir)

    # Create hooks
    hooks = [
        ConversationHookProvider(repository=conversation_repository),
        MemoryHookProvider(memory_manager=memory_manager),
    ]

    # Use provided system prompt or default
    if system_prompt is None:
        system_prompt = get_prompt_with_name("test_orchestrator_prompt")

    # Add guardrails if flag set True
    if with_base_guardrails:
        guardrail_prompt = get_base_guardrail_prompt()
        system_prompt += "\n" + guardrail_prompt

    # Create orchestrator with explicit hooks
    orchestrator = agent_class(
        system_prompt=system_prompt,
        hooks=hooks,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=os.getenv("AWS_REGION") or "us-east-1",
        custom_tools=custom_tools,
        model_id=model_id,
        model=model,
        trace_attributes=trace_attributes,
        excluded_mcp_tool_names=excluded_mcp_tool_names,
        metrics_config=metrics_config,
        plugins=[skills_plugin] if skills_plugin else None,
    )

    logger.info("Default orchestrator created successfully with memory and conversation support")
    return orchestrator


def create_default_orchestrator(
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
    system_prompt: Optional[str] = None,
    custom_tools: Optional[list[Any]] = None,
    model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
    model: Union[Model, str, None] = None,
    with_base_guardrails: bool = False,
    trace_attributes: Optional[dict[str, Any]] = None,
    metrics_config: Optional[MetricsConfig] = None,
) -> BaseOrchestrator:
    """
    Create a BaseOrchestrator instance with full memory and conversation support.

    This function creates a fully-featured orchestrator with:
    - Episodic memory for storing agent experiences
    - Conversation tracking across multiple sources
    - Memory tools for agent self-reflection
    - Lifecycle hooks for conversation and memory events

    If your application has a running asyncio event loop, then use create_default_async_orchestrator
    instead. See BaseOrchestrators's documentation.

    Args:
        mcp_client: Optional MCP client for tool integration
        storage_dir: Directory for agent data storage
        system_prompt: Custom system prompt, defaults to test_orchestrator_prompt
        custom_tools: Optional list of additional custom tools to add to the orchestrator
        model_id: Optional model ID for Bedrock inference
        model: Optional Strands Model instance or model ID string (takes precedence over model_id)
        metrics_config: Optional MetricsConfig for CloudWatch metrics (default: disabled)

    Returns:
        Configured BaseOrchestrator instance with memory, hooks, and tools
    """
    # Use default disabled config if none provided
    if metrics_config is None:
        metrics_config = MetricsConfig()

    return _create_default_orchestrator(
        BaseOrchestrator,
        mcp_client,
        storage_dir,
        system_prompt,
        additional_custom_tools=custom_tools,
        model_id=model_id,
        model=model,
        with_base_guardrails=with_base_guardrails,
        trace_attributes=trace_attributes,
        metrics_config=metrics_config,
    )


def create_default_async_orchestrator(
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
    system_prompt: Optional[str] = None,
    custom_tools: Optional[list[Any]] = None,
    model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
    model: Union[Model, str, None] = None,
    with_base_guardrails: bool = False,
    metrics_config: Optional[MetricsConfig] = None,
) -> AsyncBaseOrchestrator:
    """Create a AsyncBaseOrchestrator instance with full memory and conversation support.

    This function creates a fully-featured orchestrator with:
    - Episodic memory for storing agent experiences
    - Conversation tracking across multiple sources
    - Memory tools for agent self-reflection
    - Lifecycle hooks for conversation and memory events

    Args:
        mcp_client: Optional MCP client for tool integration
        storage_dir: Directory for agent data storage
        system_prompt: Custom system prompt, defaults to test_orchestrator_prompt
        custom_tools: Optional list of additional custom tools to add to the orchestrator
        model_id: Optional model ID for Bedrock inference
        model: Optional Strands Model instance or model ID string (takes precedence over model_id)
        metrics_config: Optional MetricsConfig for CloudWatch metrics (default: disabled)

    Returns:
        Configured AsyncBaseOrchestrator instance with memory, hooks, and tools
    """
    # Use default disabled config if none provided
    if metrics_config is None:
        metrics_config = MetricsConfig()

    return _create_default_orchestrator(
        AsyncBaseOrchestrator,
        mcp_client,
        storage_dir,
        system_prompt,
        additional_custom_tools=custom_tools,
        model_id=model_id,
        model=model,
        with_base_guardrails=with_base_guardrails,
        metrics_config=metrics_config,
    )


def create_default_orchestrator_with_subagent(
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
    custom_tools: Optional[list[Any]] = None,
    model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
    model: Union[Model, str, None] = None,
    with_base_guardrails: bool = False,
    metrics_config: Optional[MetricsConfig] = None,
) -> BaseOrchestrator:
    """Create a BaseOrchestrator instance with full memory and conversation support and subagent tools.

    This function creates a fully-featured orchestrator with:
    - Episodic memory for storing agent experiences
    - Conversation tracking across multiple sources
    - Memory tools for agent self-reflection
    - Lifecycle hooks for conversation and memory events
    - Subagent tools for communication and discovery (mocked)

    If your application has a running asyncio event loop, then use
    create_default_async_orchestrator_with_subagent instead. See BaseOrchestrator's documentation.

    Args:
        mcp_client: Optional MCP client for tool integration
        storage_dir: Directory for agent data storage
        system_prompt: Custom system prompt, defaults to test_orchestrator_prompt
        custom_tools: Optional list of additional custom tools to add to the orchestrator
        model_id: Optional model ID for Bedrock inference
        model: Optional Strands Model instance or model ID string (takes precedence over model_id)
        metrics_config: Optional MetricsConfig for CloudWatch metrics (default: disabled)

    Returns:
        Configured BaseOrchestrator instance with memory, hooks, and tools
    """
    # Use default disabled config if none provided
    if metrics_config is None:
        metrics_config = MetricsConfig()

    return _create_default_orchestrator(
        BaseOrchestrator,
        mcp_client,
        storage_dir,
        system_prompt,
        with_subagent=True,
        additional_custom_tools=custom_tools,
        model_id=model_id,
        model=model,
        with_base_guardrails=with_base_guardrails,
        metrics_config=metrics_config,
    )


def create_default_async_orchestrator_with_subagent(
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
    custom_tools: Optional[list[Any]] = None,
    model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
    model: Union[Model, str, None] = None,
    with_base_guardrails: bool = False,
    trace_attributes: Optional[dict[str, Any]] = None,
    excluded_mcp_tool_names: Optional[Set[str]] = None,
    metrics_config: Optional[MetricsConfig] = None,
    enable_skills: bool = False,
    skills_dir: Optional[str] = None,
    enable_code_execution: bool = False,
) -> AsyncBaseOrchestrator:
    """Create a AsyncBaseOrchestrator instance with full memory and conversation support and subagent tools.

    This function creates a fully-featured orchestrator with:
    - Episodic memory for storing agent experiences
    - Conversation tracking across multiple sources
    - Memory tools for agent self-reflection
    - Lifecycle hooks for conversation and memory events
    - Subagent tools for communication and discovery (mocked)
    - Agent skills support via Strands AgentSkills plugin (when enable_skills=True)
    - Experimental code execution support (when enable_code_execution=True)

    Args:
        system_prompt: Custom system prompt for the orchestrator
        mcp_client: Optional MCP client for tool integration
        storage_dir: Directory for agent data storage
        custom_tools: Optional list of additional custom tools to add to the orchestrator
        model_id: Optional model ID for Bedrock inference
        model: Optional Strands Model instance or model ID string (takes precedence over model_id)
        with_base_guardrails: Whether to add base guardrail prompts
        trace_attributes: Optional trace attributes for observability
        excluded_mcp_tool_names: Set of MCP tool names to exclude
        metrics_config: Optional MetricsConfig for CloudWatch metrics (default: disabled)
        enable_skills: Enable agent skills via the Strands AgentSkills plugin.
            When True, creates an AgentSkills plugin that registers a skills tool
            and auto-injects skill metadata into the system prompt.
        skills_dir: Directory containing skills. If None, uses STRANDS_SKILLS_DIR env var
            or defaults to ./skills
        enable_code_execution: Enable experimental local Python code execution tool.
            WARNING: Code executes locally without sandboxing. Use with caution.
            For sandboxed execution, AgentCore Code Interpreter integration is planned.

    Returns:
        Configured AsyncBaseOrchestrator instance with memory, hooks, and tools

    Example:
        # Enable skills and code execution
        agent = create_default_async_orchestrator_with_subagent(
            system_prompt="You are a helpful assistant.",
            enable_skills=True,
            skills_dir="./my_skills",
            enable_code_execution=True,
        )
    """
    # Use default disabled config if none provided
    if metrics_config is None:
        metrics_config = MetricsConfig()

    return _create_default_orchestrator(
        AsyncBaseOrchestrator,
        mcp_client,
        storage_dir,
        system_prompt,
        with_subagent=True,
        additional_custom_tools=custom_tools,
        model_id=model_id,
        model=model,
        with_base_guardrails=with_base_guardrails,
        trace_attributes=trace_attributes,
        excluded_mcp_tool_names=excluded_mcp_tool_names,
        metrics_config=metrics_config,
        enable_skills=enable_skills,
        skills_dir=skills_dir,
        enable_code_execution=enable_code_execution,
    )


def _create_default_subagent(
    agent_class: type[SubagentT],
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
    model: Union[Model, str, None] = None,
    additional_custom_tools: Optional[list[Any]] = None,
    metrics_config: Optional[MetricsConfig] = None,
) -> SubagentT:
    logger.info("Creating default subagent with minimal configuration")

    # Create subagent with minimal configuration
    subagent = agent_class(
        system_prompt=system_prompt,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=os.getenv("AWS_REGION") or "us-east-1",
        model=model,
        custom_tools=additional_custom_tools,
        metrics_config=metrics_config,
    )

    logger.info("Default subagent created successfully")
    return subagent


def create_default_subagent(
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
    model: Union[Model, str, None] = None,
    custom_tools: Optional[list[Any]] = None,
    metrics_config: Optional[MetricsConfig] = None,
) -> BaseSubagent:
    """Create a BaseSubagent instance with minimal configuration.

    This function creates a lightweight subagent without memory or conversation tracking.

    If your application has a running asyncio event loop, then use create_default_async_subagent
    instead. See BaseSubagent's documentation.

    Args:
        mcp_client: Optional MCP client for tool integration
        system_prompt: Custom system prompt, defaults to simple assistant prompt
        model: Optional Strands Model instance or model ID string
        custom_tools: Optional list of additional custom tools to add to the subagent
        metrics_config: Optional MetricsConfig for CloudWatch metrics (default: disabled)

    Returns:
        Configured BaseSubagent instance
    """

    return _create_default_subagent(
        BaseSubagent,
        system_prompt,
        mcp_client,
        model,
        additional_custom_tools=custom_tools,
        metrics_config=metrics_config,
    )


def create_default_async_subagent(
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
    model: Union[Model, str, None] = None,
    custom_tools: Optional[list[Any]] = None,
    metrics_config: Optional[MetricsConfig] = None,
) -> AsyncBaseSubagent:
    """Create an AsyncBaseSubagent instance with minimal configuration.

    This function creates a lightweight subagent without memory or conversation tracking.

    Args:
        mcp_client: Optional MCP client for tool integration
        system_prompt: Custom system prompt, defaults to simple assistant prompt
        model: Optional Strands Model instance or model ID string
        custom_tools: Optional list of additional custom tools to add to the subagent
        metrics_config: Optional MetricsConfig for CloudWatch metrics (default: disabled)

    Returns:
        Configured AsyncBaseSubagent instance
    """

    return _create_default_subagent(
        AsyncBaseSubagent,
        system_prompt,
        mcp_client,
        model,
        additional_custom_tools=custom_tools,
        metrics_config=metrics_config,
    )
