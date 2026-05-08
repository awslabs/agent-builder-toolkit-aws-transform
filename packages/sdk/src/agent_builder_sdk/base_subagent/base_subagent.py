# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Base subagent implementation extending the base Strands Agent."""

__all__ = ("BaseSubagent", "AsyncBaseSubagent")

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, ExitStack
from typing import Any, List, Optional, Sequence, Set, Union, cast

from strands import Agent as StrandsAgent
from strands.agent import AgentResult
from strands.hooks import HookCallback, HookProvider
from strands.models.model import Model
from strands.tools.mcp import MCPClient

from agent_builder_sdk.bedrock_model_factory import BedrockModelFactory
from agent_builder_sdk.constants import DEFAULT_SUBAGENT_EXCLUDED_TOOLS
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent
from agent_builder_sdk.metrics.metrics_config import MetricsConfig
from agent_builder_sdk.utils import combine_tools

logger = logging.getLogger(__name__)


class _BaseSubagent(StrandsAgent):
    def __init__(
        self,
        system_prompt: str,
        custom_tools: Optional[List[Any]] = None,
        mcp_clients: Optional[List[MCPClient]] = None,
        hooks: Optional[Sequence[Union[HookProvider, HookCallback[Any]]]] = None,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None,
        excluded_tool_names: Optional[Set[str]] = None,
        excluded_mcp_tool_names: Optional[Set[str]] = None,
        region_name: str = "us-east-1",
        model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
        model: Union[Model, str, None] = None,
        metrics_config: Optional[MetricsConfig] = None,
        **kwargs,
    ):
        """
        Initialize the subagent.

        Args:
            system_prompt: System prompt defining the subagent's behavior
            custom_tools: List of custom tools for the subagent
            mcp_clients: List of MCP clients for tool access
            hooks: List of hook providers
            guardrail_id: Optional Bedrock guardrail ID for content filtering (ignored if model is provided)
            guardrail_version: Optional guardrail version (ignored if model is provided)
            excluded_tool_names: Set of tool names (both mcp and custom) to exclude (defaults to DEFAULT_SUBAGENT_EXCLUDED_TOOLS)
            excluded_mcp_tool_names: Optional set of mcp tool names to exclude
            region_name: AWS region for Bedrock (ignored if model is provided)
            model_id: Bedrock model identifier (ignored if model is provided)
            model: Optional Strands Model instance or model ID string (takes precedence over model_id)
            metrics_enabled: Whether to emit CloudWatch metrics (default: False)
        """

        # Store configuration
        self.excluded_tool_names = excluded_tool_names or set(DEFAULT_SUBAGENT_EXCLUDED_TOOLS)
        self.excluded_mcp_tool_names = excluded_mcp_tool_names
        self.system_prompt = system_prompt
        self.model_id = model_id
        self.region_name = region_name
        self.mcp_clients = mcp_clients
        self.custom_tools = custom_tools or []
        self.metrics_config = metrics_config or MetricsConfig(enabled=False)

        # Create Bedrock model only if no model provided
        bedrock_model = (
            None
            if model is not None
            else BedrockModelFactory.create_with_shared_capacity_role(
                model_id=model_id,
                region_name=region_name,
                guardrail_id=guardrail_id,
                guardrail_version=guardrail_version,
            )
        )

        super().__init__(
            model=model or bedrock_model,
            system_prompt=system_prompt,
            tools=self._combine_tools(),
            hooks=cast(List[Any], list(hooks)) if hooks else None,
            **kwargs,
        )

        logger.info(
            f"BaseSubagent initialized: model={model_id if model is None else type(model).__name__}"
        )

    def _combine_tools(self) -> Optional[List[Any]]:
        """Combine tools from the MCP clients with the custom tools, filtering out excluded tools."""

        return combine_tools(
            mcp_clients=self.mcp_clients,
            custom_tools=self.custom_tools,
            excluded_tool_names=self.excluded_tool_names,
            excluded_mcp_tool_names=self.excluded_mcp_tool_names,
        )

    async def _process_message(self, message: str) -> AgentResult:
        try:
            if self.mcp_clients:
                with ExitStack() as stack:
                    for client in self.mcp_clients:
                        stack.enter_context(cast(AbstractContextManager[Any], client))
                    agent_result = await self.invoke_async(message)
            else:
                agent_result = await self.invoke_async(message)

            # Emit metrics (independent of evaluation)
            self._emit_agent_metrics(agent_result)

            return agent_result
        except Exception as e:
            logger.error(f"Error invoking with source: {e}")
            raise e

    def _emit_agent_metrics(self, agent_result: AgentResult) -> None:
        """Emit CloudWatch metrics for agent execution (independent of evaluation)."""
        if not self.metrics_config.enabled:
            return

        try:
            from agent_builder_sdk.metrics.metrics_helper import MetricsHelper

            # Get metrics summary from agent result
            metrics_summary = agent_result.metrics.get_summary()

            # Emit metrics with trace correlation
            metrics_helper = MetricsHelper(
                custom_dimensions=self.metrics_config.custom_dimensions,
                namespace=self.metrics_config.namespace,
            )
            metrics_helper.emit_metrics(metrics_summary)

            logger.info("Agent metrics emitted successfully")

        except Exception as e:
            logger.warning(f"Failed to emit agent metrics: {e}")
            # Don't let metrics failures break agent execution


class BaseSubagent(_BaseSubagent, BaseAgent[Union[str, ProcessMessageRequest], AgentResult]):
    """Base subagent implementation for ATX Platform partner teams.

    A subagent class that extends StrandsAgent to provide enhanced capabilities for
    partner teams building agents on the ATX Platform. Supports MCP tool integration,
    custom tools, and configurable Bedrock models with shared capacity roles.

    If your application has a running asyncio event loop, then use AsyncBaseSubagent instead.
    This class's synchronous implementation ultimately calls the asynchronous implementation: it
    creates an event loop in a separate thread taken from a pool. This is inefficient, but this is
    also what you'd get if you synchronously and directly invoked StrandsAgent.

    Attributes:
        system_prompt: The system prompt defining agent behavior.
        model_id: Bedrock model identifier being used.
        region_name: AWS region for Bedrock operations.
        mcp_clients: List of MCP clients providing tool access.
        custom_tools: List of custom tools available to the agent.

    Example:
        Basic usage with system prompt only:

            agent = BaseSubagent(
                system_prompt="You are a helpful assistant.",
                model_id="anthropic.claude-sonnet-4-5-20250929-v1:0"
            )
            result = agent.process_message("Hello, how can you help me?")
            print(result.message)

        Advanced usage with MCP clients and custom tools:

            from strands import tool
            from strands.tools.mcp import MCPClient

            @tool
            def weather_forecast(city: str, days: int = 3) -> str:
                return f"Weather forecast for {city} for the next {days} days..."


            mcp_client = MCPClient(command="my-mcp-server")

            agent = BaseSubagent(
                system_prompt="You are a specialized assistant with access to tools.",
                custom_tools=[weather_forecast],
                mcp_clients=[mcp_client],
                region_name="us-west-2"
            )

            result = agent.process_message("What is the weather like in Seattle for the next 5 days?")
            print(result)
    """

    def process_message(self, message: Union[str, ProcessMessageRequest]) -> AgentResult:
        """Process a message and return the agent's response.

        Args:
            message: Either a string message or a ProcessMessageRequest object.
                    If a string is provided, it will be wrapped in a ProcessMessageRequest with empty context.

        Returns:
            AgentResult containing:
            - stop_reason: Why processing stopped ('end_turn', 'tool_use', 'max_tokens', etc.)
            - message: Agent's response with content (List[ContentBlock]) and role
            - metrics: Performance metrics from processing
            - state: Additional event loop state information

            See: https://strandsagents.com/latest/documentation/docs/api-reference/agent/#strands.agent.agent_result.AgentResult
        """
        # Handle both str and ProcessMessageRequest for backward compatibility
        if isinstance(message, str):
            request = ProcessMessageRequest(message=message, context=ConversationContext())
        else:
            request = message

        def execute() -> AgentResult:
            return asyncio.run(self._process_message(request.message))

        with ThreadPoolExecutor() as executor:
            future = executor.submit(execute)
            return future.result()


class AsyncBaseSubagent(
    _BaseSubagent, AsyncBaseAgent[Union[str, ProcessMessageRequest], AgentResult]
):
    """An asynchronous version of BaseSubagent.

    If your application has a running asyncio event loop, then use this class, not BaseSubagent.
    The equivalent of process_message is process_message_async.
    """

    async def process_message_async(
        self, message: Union[str, ProcessMessageRequest]
    ) -> AgentResult:
        """Asynchronously process a message and return the agent's response.

        Args:
            message: Either a string message or a ProcessMessageRequest object.
                    If a string is provided, it will be wrapped in a ProcessMessageRequest with empty context.

        Returns:
            AgentResult containing:
            - stop_reason: Why processing stopped ('end_turn', 'tool_use', 'max_tokens', etc.)
            - message: Agent's response with content (List[ContentBlock]) and role
            - metrics: Performance metrics from processing
            - state: Additional event loop state information

            See: https://strandsagents.com/latest/documentation/docs/api-reference/agent/#strands.agent.agent_result.AgentResult
        """
        # Handle both str and ProcessMessageRequest for backward compatibility
        if isinstance(message, str):
            request = ProcessMessageRequest(message=message, context=ConversationContext())
        else:
            request = message

        return await self._process_message(request.message)
