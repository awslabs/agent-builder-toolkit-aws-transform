# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Base subagent implementation extending the base Strands Agent."""

__all__ = ("BaseSubagent", "AsyncBaseSubagent")

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, ExitStack
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Union,
    cast,
)

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
from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent, StreamingCapable
from agent_builder_sdk.metrics.metrics_config import MetricsConfig
from agent_builder_sdk.streaming.config import DEFAULT_STREAMING_CONFIG, StreamingConfig
from agent_builder_sdk.utils import combine_tools, mcp_session_active

if TYPE_CHECKING:
    # Type-only; the runtime import stays lazy inside the streaming methods so non-streaming
    # partners don't pay for the streaming subsystem's deps.
    from agent_builder_sdk.streaming.raw_a2a_emitter import RawStreamState

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
    _BaseSubagent,
    AsyncBaseAgent[Union[str, ProcessMessageRequest], AgentResult],
    StreamingCapable,
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

    # ------ streaming ------
    async def process_message_stream(
        self,
        request: ProcessMessageRequest,
        conversation_id: str,
        cfg: StreamingConfig = DEFAULT_STREAMING_CONFIG,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a turn as raw A2A frames (agent-to-agent, no AG-UI).

        The streaming counterpart of ``process_message_async`` for a sub-agent. Drives Strands
        ``stream_async`` and yields raw A2A frames (Strands event carried verbatim in each frame's
        DataPart — see ``raw_a2a_emitter``): a ``task`` opener, a ``working`` status-update per
        event, then a terminal ``completed`` (or ``failed`` on error). Unlike the orchestrator's
        ``_stream_message_async``, this is deliberately trimmed — no suggestion scope, no
        persist-to-chat, no AG-UI translation, no a2a ContextVars — because the consumer is another
        agent, not the WebApp.

        ``conversation_id`` is accepted for signature parity with the orchestrator's streaming
        entry (the server's ``_handle_streaming`` passes it); the sub-agent is stateless and does
        not thread it into history. A concurrent invocation on the same agent instance raises
        Strands ``ConcurrencyException``; it is surfaced as a terminal failed frame rather than
        escaping. ``cfg`` bounds the turn (``turn_timeout_seconds``).

        This method owns only the terminal-failure framing; the turn itself runs in
        ``_run_streaming_turn``. The connection has already returned 200 + SSE headers, so every
        failure is surfaced as a terminal ``failed`` frame instead of a truncated stream (detail
        stays in the log). The turn-timeout case is handled inside ``_run_streaming_turn`` because
        it needs the timeout scope to confirm expiry.
        """
        from strands.types.exceptions import ConcurrencyException

        from agent_builder_sdk.streaming.raw_a2a_emitter import RawStreamState, error_frames

        a2a_context = request.context.a2a_context
        context_id = a2a_context.context_id if a2a_context else None
        state = RawStreamState(context_id=context_id)

        try:
            async for frame in self._run_streaming_turn(request, state, cfg, conversation_id):
                yield frame
        except ConcurrencyException:
            logger.warning(
                "Concurrent stream invocation rejected for conversation %s", conversation_id
            )
            for frame in error_frames(
                state, "Agent is already processing another request for this session."
            ):
                yield frame
        except Exception:
            logger.exception("Sub-agent streaming turn failed for conversation %s", conversation_id)
            for frame in error_frames(
                state, "An internal error occurred while processing the streaming turn."
            ):
                yield frame

    async def _run_streaming_turn(
        self,
        request: ProcessMessageRequest,
        state: "RawStreamState",
        cfg: StreamingConfig,
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Drive ``stream_async`` under the turn timeout, emitting raw A2A frames.

        Opens the MCP clients, emits one ``working`` frame per Strands event, captures the final
        ``AgentResult``, then closes with a terminal ``completed`` frame. If the turn exceeds
        ``cfg.turn_timeout_seconds`` it ends with a ``failed`` frame instead. Any other exception
        (e.g. ``ConcurrencyException``) propagates to ``process_message_stream``, which frames it.
        """
        from agent_builder_sdk.streaming.raw_a2a_emitter import (
            error_frames,
            event_frames,
            finish_frames,
        )

        with ExitStack() as stack:
            for client in self.mcp_clients or []:
                if not mcp_session_active(client):
                    stack.enter_context(cast(AbstractContextManager[Any], client))
            result = None
            try:
                async with asyncio.timeout(cfg.turn_timeout_seconds) as turn_cm:
                    async for event in self.stream_async(request.message):
                        for frame in event_frames(event, state):
                            yield frame
                        if isinstance(event, dict) and "result" in event:
                            result = event["result"]
                    for frame in finish_frames(state, result):
                        yield frame
            except TimeoutError:
                if not turn_cm.expired():
                    raise
                logger.warning(
                    "Sub-agent streaming turn exceeded %.0fs budget for conversation %s",
                    cfg.turn_timeout_seconds,
                    conversation_id,
                )
                for frame in error_frames(
                    state, "The request took too long to process and was stopped."
                ):
                    yield frame

    def get_streaming_hook_providers(self, cfg: StreamingConfig) -> List[HookProvider]:
        """No hooks: a sub-agent's reply goes to another agent, not persisted to Chat."""
        return []

    def requires_context_id(self) -> bool:
        """No Chat routing, so contextId is optional."""
        return False
