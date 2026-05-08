# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Enhanced orchestrator with multi-source conversation support.

This module provides an enhanced orchestrator that can handle messages from different sources
(human users, subagents, notifications) and selectively include relevant conversation history
based on the message context and relationships between entities.
"""

__all__ = ("BaseOrchestrator", "AsyncBaseOrchestrator", "a2a_context_id_var", "a2a_user_id_var")

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, ExitStack
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Sequence, Set, Union, cast

from strands import Agent as StrandsAgent
from strands.agent import AgentResult
from strands.hooks import HookCallback, HookProvider
from strands.models.model import Model
from strands.tools.mcp import MCPClient
from strands.types.content import Messages

from agent_builder_sdk.bedrock_model_factory import BedrockModelFactory
from agent_builder_sdk.custom_types.orchestrator_agent_types import ProcessMessageRequest
from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent
from agent_builder_sdk.metrics.metrics_config import MetricsConfig
from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    CURRENT_SOURCE_ID_KEY,
    CURRENT_SOURCE_TYPE_KEY,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_id,
    conversation_source_type,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory import (
    EvaluateAgent,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import EvaluationCard
from agent_builder_sdk.utils import combine_tools

logger = logging.getLogger(__name__)

messages_var: ContextVar[Messages] = ContextVar("orchestator_messages")

# ContextVars for A2A context propagation to hooks.
# These are set in _invoke_with_source so that any hook (including MessageAddedEvent
# handlers, which don't receive invocation_state) can access the current request's
# context_id and user_id.
a2a_context_id_var: ContextVar[Optional[str]] = ContextVar("a2a_context_id", default=None)
a2a_user_id_var: ContextVar[Optional[str]] = ContextVar("a2a_user_id", default=None)


class _BaseOrchestrator(StrandsAgent):
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
        evaluation_card: Optional[EvaluationCard] = None,
        metrics_config: Optional[MetricsConfig] = None,
        **kwargs,
    ):
        """
        Initialize the orchestrator with explicit configuration.

        Args:
            system_prompt: System prompt that defines the agent's behavior and capabilities
            custom_tools: List of tool objects to make available to the agent
            mcp_clients: List of MCP clients for tool execution
            hooks: List of hook providers (defaults to empty list if None)
            guardrail_id: Optional Bedrock guardrail ID for content filtering (ignored if model is provided)
            guardrail_version: Optional guardrail version (ignored if model is provided)
            excluded_tool_names: Optional set of tool names (both mcp and custom) to exclude
            excluded_mcp_tool_names: Optional set of mcp tool names to exclude
            region_name: AWS region name for Bedrock (ignored if model is provided)
            model_id: Bedrock model identifier (ignored if model is provided)
            model: Optional Strands Model instance or model ID string (takes precedence over model_id)
            metrics_config: Optional metrics configuration (default: disabled with standard settings)
        """
        # Store configuration
        self.excluded_tool_names = excluded_tool_names
        self.excluded_mcp_tool_names = excluded_mcp_tool_names
        self.system_prompt = system_prompt
        self.model_id = model_id
        self.region_name = region_name
        self.mcp_clients = mcp_clients
        self.custom_tools = custom_tools or []
        self.evaluation_card = evaluation_card
        self.evaluator = EvaluateAgent(self, self.evaluation_card) if self.evaluation_card else None
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

        logger.info(f"Orchestrator initialized: model={model_id}")

    def _combine_tools(self) -> Optional[List[Any]]:
        """Combine tools from the MCP clients with the custom tools."""

        return combine_tools(
            mcp_clients=self.mcp_clients,
            custom_tools=self.custom_tools,
            excluded_tool_names=self.excluded_tool_names,
            excluded_mcp_tool_names=self.excluded_mcp_tool_names,
        )

    async def _invoke_with_source(
        self,
        message: str,
        source_id: str,
        source_type: MessageSourceType,
        **kwargs,
    ) -> AgentResult:
        # Store source information in agent state
        self._set_current_source_context(source_type, source_id)

        # Propagate A2A context_id and user_id via ContextVars so all hooks
        # (including MessageAddedEvent handlers) can access them.
        # Reset first to avoid stale values from a previous invocation in the same task.
        a2a_context_id_var.set(None)
        a2a_user_id_var.set(None)

        a2a_context = kwargs.get("a2a_context")
        if a2a_context and a2a_context.context_id:
            a2a_context_id_var.set(a2a_context.context_id)
        if source_type == MessageSourceType.USER:
            a2a_user_id_var.set(source_id)

        try:
            if self.mcp_clients:
                with ExitStack() as stack:
                    for client in self.mcp_clients:
                        stack.enter_context(cast(AbstractContextManager[Any], client))
                    return await self._process_agent_execution(message, **kwargs)
            else:
                return await self._process_agent_execution(message, **kwargs)
        except Exception as e:
            logger.error(f"Error invoking with source: {e}")
            raise e

    def _build_kwargs(self, **context_kwargs) -> Dict[str, Any]:
        """Build kwargs for invoke_async calls, filtering out None values."""
        return {k: v for k, v in context_kwargs.items() if v is not None}

    async def _process_agent_execution(self, message: str, **kwargs):
        """
        Run the agent, evaluate its trajectories, return result.

        The evaluation is run based on the Eval card that was configured as a part of
        initialization of the agent. If evaluation fails, agent execution is retried (if configured)
        and returns the new agent response with feedback incorporated.

        Args:
            message: The message text to process
            **kwargs: Additional parameters to pass through to tools

        Returns:
            The agent's response
        """
        agent_result = await self.invoke_async(message, invocation_state=kwargs)
        logger.info("Invoked Strands agent")

        # Emit metrics (independent of evaluation)
        self._emit_agent_metrics(agent_result)

        # Run Eval
        if self.evaluator:
            eval_output = self.evaluator.evaluate(agent_result)
            logger.info("Evaluation Result: ")
            logger.info(f" Status: {eval_output.eval_status}")
            logger.info(f" Score: {eval_output.eval_score}")
            logger.info(f" Task Completed: {eval_output.task_completed}")
            logger.info(f" Feedback Summary: {eval_output.agent_feedback_summary}")

            # TODO: Determine and manage re-execution of agent

        # Return result
        return agent_result

    def _set_current_source_context(self, source_type: MessageSourceType, source_id: str) -> None:
        """
        Set the source context for the agent.

        Args:
            source_type: The type of the message source
            source_id: The source ID
        """
        # The state is shared by concurrent invocations and is vulnerable to race conditions.
        # These remain set for backwards compatibility, but prefer the ContextVars below instead.
        self.state.set(CURRENT_SOURCE_TYPE_KEY, source_type)
        self.state.set(CURRENT_SOURCE_ID_KEY, source_id)
        conversation_source_type.set(source_type)
        conversation_source_id.set(source_id)

        logger.info(
            f"Set source context for agent {self.agent_id}: {source_type.value} (ID: {source_id})"
        )

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


class BaseOrchestrator(_BaseOrchestrator, BaseAgent[ProcessMessageRequest, AgentResult]):
    """Enhanced orchestrator implementation for ATX Foundation partner teams.

    A multi-source orchestrator class that extends StrandsAgent to provide advanced capabilities for
    partner teams building orchestrator agents on the ATX Foundation. Supports handling messages from
    different sources (human users, subagents, notifications), selective conversation history inclusion,
    MCP tool integration, custom tools, and configurable Bedrock models with shared capacity roles.

    If your application has a running asyncio event loop, then use AsyncBaseOrchestrator instead.
    This class's synchronous implementation ultimately calls the asynchronous implementation: it
    creates an event loop in a separate thread taken from a pool. This is inefficient, but this is
    also what you'd get if you synchronously and directly invoked StrandsAgent.

    Tool Context:
        Tools decorated with @tool(context=True) receive a ToolContext object with:
        - invocation_state: Dict containing kwargs passed to invoke_with_source/process_message
          - a2a_context: A2AContext object with context_id for A2A messaging (if provided)
          - Additional custom kwargs can be passed through invoke_kwargs

    Attributes:
        system_prompt: The system prompt defining orchestrator behavior.
        model_id: Bedrock model identifier being used.
        region_name: AWS region for Bedrock operations.
        mcp_clients: List of MCP clients providing tool access.
        custom_tools: List of custom tools available to the orchestrator.

    Example:
        Basic usage with system prompt only:

            orchestrator = BaseOrchestrator(
                system_prompt="You are an orchestrator managing multiple agents.",
                model_id="anthropic.claude-sonnet-4-5-20250929-v1:0"
            )

            request = ProcessMessageRequest(
                message="Hello, how are you?",
                context=ConversationContext(user_id="user123")
            )
            result = orchestrator.process_message(request)
            print(result.message)

        Advanced usage with MCP clients tools, and hooks:

            from strands.tools.mcp import MCPClient
            from agent_builder_sdk.orchestrator_strands.base_orchestrator import BaseOrchestrator
            from agent_builder_sdk.orchestrator_strands.conversation.file_repository import FileMultiSourceConversationRepository
            from agent_builder_sdk.custom_types.orchestrator_agent_types import (
                ConversationContext,
                ProcessMessageRequest,
            )
            from agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider import ConversationHookProvider

            from mcp import stdio_client, StdioServerParameters

            # note that this uses a locally installed MCP server
            mcp_client = MCPClient(lambda: stdio_client(
                StdioServerParameters(
                    command="uvx",
                    args=["awslabs.aws-documentation-mcp-server@latest"]
                )
            ))

            orchestrator = BaseOrchestrator(
                         system_prompt="You are an advanced orchestrator with memory and coordination tools.",
                         custom_tools=[],
                         mcp_clients=[mcp_client],
                         hooks=[ConversationHookProvider(repository=FileMultiSourceConversationRepository(storage_dir="/tmp/conversations"))],
                         region_name="us-west-2"
                )

            orchestrator.process_message(ProcessMessageRequest(
                         message="How to build agents on AWS?",
                         context=ConversationContext(user_id="user456")
                ))
    """

    def process_message(self, request: ProcessMessageRequest) -> AgentResult:
        """Process a message based on its context.

        Args:
            request: The message request containing the message and context

        Returns:
            The agent's response
        """
        # Build invoke kwargs from request context
        kwargs = self._build_kwargs(a2a_context=request.context.a2a_context)

        # Call invoke_with_source instead of _invoke_with_source to avoid breaking subclasses
        # overriding invoke_with_source with the assumption that process_message calls it.
        if request.context.agent_instance_id and request.context.agent_instance_id != "ATX_CHAT":
            return self.invoke_with_source(
                request.message,
                request.context.agent_instance_id,
                MessageSourceType.SUBAGENT,
                **kwargs,
            )
        elif request.context.user_id:
            return self.invoke_with_source(
                request.message, request.context.user_id, MessageSourceType.USER, **kwargs
            )
        else:
            return self.invoke_with_source(
                request.message, "SYSTEM", MessageSourceType.NOTIFICATION, **kwargs
            )

    def invoke_with_source(
        self,
        message: str,
        source_id: str,
        source_type: MessageSourceType,
        **kwargs,
    ) -> AgentResult:
        """Process a message from a specific source.

        This method handles messages from different sources (users, subagents, notifications)
        and ensures the appropriate conversation history is included.

        Args:
            message: The message text to process
            source_id: Identifier for the message source (user ID, subagent ID, etc.)
            source_type: Type of the message source
            **kwargs: Additional parameters to pass through to tools

        Returns:
            The agent's response
        """

        def execute() -> AgentResult:
            return asyncio.run(self._invoke_with_source(message, source_id, source_type, **kwargs))

        with ThreadPoolExecutor() as executor:
            future = executor.submit(execute)
            return future.result()


class AsyncBaseOrchestrator(_BaseOrchestrator, AsyncBaseAgent[ProcessMessageRequest, AgentResult]):
    """An asynchronous version of BaseOrchestrator.

    If your application has a running asyncio event loop, then use this class, not BaseOrchestrator.
    The equivalent of process_message is process_message_async.

    Tool Context:
        Tools decorated with @tool(context=True) receive a ToolContext object with:
        - invocation_state: Dict containing kwargs passed to invoke_with_source_async/process_message_async
          - a2a_context: A2AContext object with context_id for A2A messaging (if provided)
          - Additional custom kwargs can be passed through invoke_kwargs
    """

    @property
    def messages(self) -> Messages:
        try:
            return messages_var.get()
        except LookupError:
            messages: Messages = []
            messages_var.set(messages)
            return messages

    @messages.setter
    def messages(self, messages: Messages) -> None:
        messages_var.set(messages)

    async def process_message_async(self, request: ProcessMessageRequest) -> AgentResult:
        """Asynchronously process a message based on its context.

        Args:
            request: The message request containing the message and context

        Returns:
            The agent's response
        """
        # Build invoke kwargs from request context
        kwargs = self._build_kwargs(a2a_context=request.context.a2a_context)

        if request.context.agent_instance_id and request.context.agent_instance_id != "ATX_CHAT":
            return await self.invoke_with_source_async(
                request.message,
                request.context.agent_instance_id,
                MessageSourceType.SUBAGENT,
                **kwargs,
            )
        elif request.context.user_id:
            return await self.invoke_with_source_async(
                request.message, request.context.user_id, MessageSourceType.USER, **kwargs
            )
        else:
            return await self.invoke_with_source_async(
                request.message, "SYSTEM", MessageSourceType.NOTIFICATION, **kwargs
            )

    async def invoke_with_source_async(
        self,
        message: str,
        source_id: str,
        source_type: MessageSourceType,
        **kwargs,
    ) -> AgentResult:
        """Asynchronously process a message from a specific source.

        This method handles messages from different sources (users, subagents, notifications)
        and ensures the appropriate conversation history is included.

        Args:
            message: The message text to process
            source_id: Identifier for the message source (user ID, subagent ID, etc.)
            source_type: Type of the message source
            **kwargs: Additional parameters to pass through to tools

        Returns:
            The agent's response
        """
        logger.info("Starting agent invocation")
        return await self._invoke_with_source(message, source_id, source_type, **kwargs)
