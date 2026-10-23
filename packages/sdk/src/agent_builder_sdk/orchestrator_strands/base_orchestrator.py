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

from botocore.config import Config as BotocoreConfig
from strands import Agent as StrandsAgent
from strands.agent import AgentResult
from strands.hooks import HookCallback, HookProvider
from strands.models import CacheConfig
from strands.models.model import Model
from strands.tools.mcp import MCPClient
from strands.types.content import Messages

from agent_builder_sdk.bedrock_model_factory import BedrockModelFactory
from agent_builder_sdk.custom_types.orchestrator_agent_types import ProcessMessageRequest
from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent, StreamingCapable
from agent_builder_sdk.locale_utils import get_locale_instruction
from agent_builder_sdk.metrics.metrics_config import MetricsConfig
from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    CURRENT_SOURCE_ID_KEY,
    CURRENT_SOURCE_TYPE_KEY,
    MessageSourceType,
    classify_source,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_id,
    conversation_source_type,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory import (
    EvaluateAgent,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import EvaluationCard

# Only the lightweight config (a plain dataclass, no heavy deps) is imported at module
# load — it's needed for method-signature defaults. The adapter symbols (adapt / to_a2a_frames
# / StreamState) live in a2a_agui_adapter, which pulls ag_ui.core + a2a.types; those are
# lazy-imported inside the streaming methods so a partner who never enables concurrent
# streaming doesn't pay for (or need) those runtime deps. StreamState is referenced only as a
# string annotation below to keep it out of module-load.
from agent_builder_sdk.streaming.config import DEFAULT_STREAMING_CONFIG, StreamingConfig

if TYPE_CHECKING:
    from agent_builder_sdk.streaming import StreamState
from agent_builder_sdk.util.suggestions_manager import (
    begin_turn_scope as begin_suggestions_turn_scope,
)
from agent_builder_sdk.utils import combine_tools, mcp_session_active

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
        guardrail_stream_processing_mode: Optional[str] = None,
        excluded_tool_names: Optional[Set[str]] = None,
        excluded_mcp_tool_names: Optional[Set[str]] = None,
        region_name: str = "us-east-1",
        model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
        model: Union[Model, str, None] = None,
        boto_client_config: Optional[BotocoreConfig] = None,
        evaluation_card: Optional[EvaluationCard] = None,
        metrics_config: Optional[MetricsConfig] = None,
        locale: Optional[str] = None,
        enable_prompt_caching: bool = False,
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
            guardrail_stream_processing_mode: Optional Bedrock guardrail streaming mode, "sync" or
                "async" (ignored if model is provided). Only affects the streaming (message/stream)
                path — the buffered path is not a token stream. "sync" (Bedrock's default when
                omitted) buffers and scans chunks before releasing them, so blocked content never
                reaches the client at the cost of some latency; "async" releases chunks immediately
                and scans in the background, preserving the streaming latency win but allowing
                inappropriate content to reach the client until the scan catches up. Left to the
                job-agent owner to choose per their latency/safety needs; None => Bedrock default.
            excluded_tool_names: Optional set of tool names (both mcp and custom) to exclude
            excluded_mcp_tool_names: Optional set of mcp tool names to exclude
            region_name: AWS region name for Bedrock (ignored if model is provided)
            model_id: Bedrock model identifier (ignored if model is provided)
            model: Optional Strands Model instance or model ID string (takes precedence over model_id)
            boto_client_config: Optional botocore Config for the Bedrock-Runtime client, forwarded
                to Strands' BedrockModel (ignored if ``model`` is provided). Defaults to None.
                When None, Strands applies its OWN default client config internally
                (``read_timeout=120s`` and ``user_agent_extra="strands-agents"``), so passing None
                is equivalent to not passing it and existing callers are unchanged. When set,
                Strands merges its ``user_agent_extra`` onto the supplied config, so e.g.
                ``Config(read_timeout=300)`` raises the read timeout while keeping the
                ``strands-agents`` user agent. This is the Strands BedrockModel path only; the
                deprecated ``agent.py`` uses a separate ``DEFAULT_BOTO_CONFIG`` and is unaffected.
            metrics_config: Optional metrics configuration (default: disabled with standard settings)
            locale: Optional user locale (e.g. "ja", "pt-BR"). When set, a localization
                instruction is appended to the system prompt so the agent responds in the
                user's language. Sourced from AgentRuntimeContext.locale, which is populated
                identically for AgentCore (invoke/restore payload) and MDE (env var).
            enable_prompt_caching: Turn on Bedrock prompt caching for the model built here
                (ignored if model is provided). With ``CacheConfig(strategy="auto")`` Strands
                places the cache points itself, for Claude model ids only, and Bedrock decides
                which prompt tokens it reads from or writes to the cache
                (https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html).
                Cache reads cost a fraction of the uncached input price and cache writes cost a
                premium over it, entries keep Bedrock's default lifetime, and Bedrock's
                ``inputTokens`` counts only the uncached tokens.
        """
        # Append locale instruction to the system prompt when a locale is present.
        # get_locale_instruction returns "" for English/None/unknown, so non-localized
        # sessions are unchanged.
        if locale:
            locale_instruction = get_locale_instruction(locale)
            if locale_instruction:
                system_prompt = f"{system_prompt}\n{locale_instruction}"

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
        self._metrics_baseline: Optional[Dict[str, float]] = None

        # Create Bedrock model only if no model provided. The stream-processing mode is passed only
        # when set, so an unset value leaves BedrockModel on its own default (Bedrock treats an
        # omitted streamProcessingMode as synchronous) rather than sending an explicit None.
        guardrail_extra: Dict[str, Any] = (
            {"guardrail_stream_processing_mode": guardrail_stream_processing_mode}
            if guardrail_stream_processing_mode
            else {}
        )
        # No tools_ttl: every cached prefix starts with the tools, so they are cached anyway.
        cache_extra: Dict[str, Any] = (
            {"cache_config": CacheConfig(strategy="auto")} if enable_prompt_caching else {}
        )
        bedrock_model = (
            None
            if model is not None
            else BedrockModelFactory.create_with_shared_capacity_role(
                model_id=model_id,
                region_name=region_name,
                guardrail_id=guardrail_id,
                guardrail_version=guardrail_version,
                boto_client_config=boto_client_config,
                **guardrail_extra,
                **cache_extra,
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
            # Only enter clients that aren't already active. When the server keeps a
            # shared MCP client open for concurrent streaming, that same client may also
            # be this agent's client; entering it per turn would raise ("session already
            # running"). A standalone (inactive) client is entered/exited here as before.
            with ExitStack() as stack:
                for client in self.mcp_clients or []:
                    if not mcp_session_active(client):
                        stack.enter_context(cast(AbstractContextManager[Any], client))
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
            self._metrics_baseline = metrics_helper.emit_metrics(
                metrics_summary, self._metrics_baseline
            )

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


class AsyncBaseOrchestrator(
    _BaseOrchestrator, AsyncBaseAgent[ProcessMessageRequest, AgentResult], StreamingCapable
):
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
        source_id, source_type = classify_source(request.context)
        return await self.invoke_with_source_async(
            request.message, source_id, source_type, **kwargs
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

    # ------ streaming ------

    async def process_message_stream(
        self,
        request: ProcessMessageRequest,
        conversation_id: str,
        cfg: StreamingConfig = DEFAULT_STREAMING_CONFIG,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a turn as A2A frames. The streaming counterpart of process_message_async:
        same source classification, but delegates to _stream_message_async instead of
        invoke_with_source_async."""
        kwargs = self._build_kwargs(a2a_context=request.context.a2a_context)
        source_id, source_type = classify_source(request.context)

        async for frame in self._stream_message_async(
            request.message, source_id, source_type, conversation_id, cfg, **kwargs
        ):
            yield frame

    async def _stream_message_async(
        self,
        message: str,
        source_id: str,
        source_type: MessageSourceType,
        conversation_id: str,
        cfg: StreamingConfig = DEFAULT_STREAMING_CONFIG,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a turn as A2A frames (the live counterpart of _invoke_with_source).

        Runs the agent through Strands ``stream_async`` and yields A2A frames (dicts):
        Strands event -> AG-UI events (``adapt``, gated by ``cfg``) -> A2A frames
        (``to_a2a_frames``). This does NOT go through the request queue — it runs
        inline on the caller's coroutine and holds the connection for the turn.

        ``conversation_id`` is the stable id for the whole conversation; it becomes the wire
        threadId. The task/run id is minted here (the agent, as the A2A server, owns Task
        ids). A concurrent invocation on the same agent instance raises
        ``ConcurrencyException`` (Strands allows one at a time); we surface that as a
        terminal RUN_ERROR frame rather than letting it escape.
        """
        from strands.types.exceptions import ConcurrencyException

        self._set_current_source_context(source_type, source_id)
        a2a_context_id_var.set(None)
        a2a_user_id_var.set(None)
        # Isolate suggestions to THIS streaming turn. Concurrent streaming turns run inline on
        # one event loop (no queue serialization), so a partner tool calling add_suggestions()
        # mid-stream must not clobber the shared holder that a concurrent message/send turn
        # would consume. Each streaming turn is its own asyncio task, so this per-turn scope is
        # naturally isolated. The message/send path never opens a scope → behavior unchanged.
        # The response-persist hook consumes this turn's suggestions on the final boundary.
        begin_suggestions_turn_scope()
        a2a_context = kwargs.get("a2a_context")
        if a2a_context and a2a_context.context_id:
            a2a_context_id_var.set(a2a_context.context_id)
        if source_type == MessageSourceType.USER:
            a2a_user_id_var.set(source_id)

        # Lazy import: keeps ag_ui.core + a2a.types off the module-load path for partners who
        # never stream (this method only runs on the opt-in streaming path).
        from agent_builder_sdk.streaming import StreamState, to_a2a_error_frames
        from agent_builder_sdk.streaming.response_persist_hook import (
            persist_stream_error as _persist_stream_error,
        )

        # contextId is required: it is the A2A routing id we echo on every frame envelope so
        # the reply routes to the right conversation. The ingress rejects a contextId-less
        # streaming turn; assert here too so any other caller fails fast rather than emitting
        # unroutable frames.
        context_id = a2a_context.context_id if a2a_context else None
        if not context_id:
            raise ValueError("contextId is required for a streaming turn")

        # threadId = the conversation id (AG-UI, rides in the DataPart). context_id = the
        # caller-minted A2A contextId echoed on the frame envelope. run_id (the A2A taskId)
        # is minted by StreamState — the agent owns Task ids.
        state = StreamState(thread_id=conversation_id, context_id=context_id)

        try:
            # Only enter MCP clients that aren't already active. When the server keeps
            # a shared client open for concurrent streaming, entering it per turn would
            # (a) raise on the second concurrent stream and (b) close it for everyone on
            # the first stream's exit. A standalone (inactive) client is entered/exited
            # here as before.
            with ExitStack() as stack:
                for client in self.mcp_clients or []:
                    if not mcp_session_active(client):
                        stack.enter_context(cast(AbstractContextManager[Any], client))
                # Bound the turn: if it produces no terminal within the budget (e.g. a hung MCP
                # tool or a stalled model call), abort so the client gets a clean terminal instead
                # of the stream hanging.
                #
                # Only a TimeoutError from THIS scope expiring is a turn timeout. On 3.11+
                # TimeoutError is asyncio.TimeoutError, so an inner TimeoutError (an MCP tool, a boto3
                # read timeout, a nested asyncio.timeout) also raises TimeoutError here — guard on
                # turn_cm.expired() and re-raise anything else so it falls through to the generic
                # handler with its real error class logged, not mislabeled as a turn timeout.
                try:
                    async with asyncio.timeout(cfg.turn_timeout_seconds) as turn_cm:
                        async for frame in self._stream_frames(message, state, cfg, **kwargs):
                            yield frame
                except TimeoutError:
                    if not turn_cm.expired():
                        raise
                    logger.warning(
                        "Streaming turn exceeded %.0fs budget for conversation %s; ending "
                        "with a terminal",
                        cfg.turn_timeout_seconds,
                        conversation_id,
                    )
                    timeout_msg = "The request took too long to process and was stopped."
                    await _persist_stream_error(context_id, timeout_msg, state.run_id)
                    for frame in to_a2a_error_frames(timeout_msg, state):
                        yield frame
        except ConcurrencyException:
            logger.warning(
                "Concurrent stream invocation rejected for conversation %s", conversation_id
            )
            # to_a2a_error_frames opens the run + closes any open block before the terminal
            # RUN_ERROR, so the client never gets a failed/final frame with no Task opener or
            # an unbalanced Start-without-End block. Persist the same message so a reload shows the
            # error instead of a blank turn (parity with the buffered path); keyed on run_id, the id
            # the RUN_ERROR frame carries, so live and stored copies reconcile. Best-effort.
            busy_msg = "Agent is already processing another request for this session."
            await _persist_stream_error(context_id, busy_msg, state.run_id)
            for frame in to_a2a_error_frames(busy_msg, state):
                yield frame
        except Exception:
            # Any other failure (model/MCP/adapter error) surfaces as a terminal error
            # frame so the client sees a clean end instead of a truncated SSE stream.
            # The connection has already returned 200 + headers, so the ingress can no
            # longer turn this into an HTTP error.
            # Client gets a generic message; the exception detail (which can carry
            # ARNs, account ids, endpoints, or file paths from Bedrock/MCP errors)
            # stays in the server log only. Persist the same generic message so a reload matches
            # the live error (parity with the buffered path); best-effort, keyed on run_id.
            logger.exception("Streaming turn failed for conversation %s", conversation_id)
            error_msg = "An internal error occurred while processing the streaming turn."
            await _persist_stream_error(context_id, error_msg, state.run_id)
            for frame in to_a2a_error_frames(error_msg, state):
                yield frame

    async def _stream_frames(
        self,
        message: str,
        state: "StreamState",
        cfg: StreamingConfig,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Drive Strands stream_async, mapping each event to A2A frames."""
        from ag_ui.core import RunFinishedEvent

        from agent_builder_sdk.streaming import adapt, to_a2a_frames

        # Expose the per-turn StreamState to hooks via invocation_state so the
        # response-persist hook (registered only on streaming agents) can write the
        # final message under the same id the stream showed. Additive key; the
        # message/send path never sets it, so its hooks are unaffected.
        kwargs["stream_state"] = state
        async for event in self.stream_async(message, invocation_state=kwargs):
            # Ahead of adapt(): a client may stop reading at the terminal frame it yields.
            if isinstance(event, dict) and "result" in event:
                self._emit_agent_metrics(event["result"])
            for agui_event in adapt(event, state, cfg):
                # Events produced off the model stream (suggestion interactions the response hook
                # built as the final message was assembled) must ride BEFORE the terminal — drain
                # state.side_events just ahead of RUN_FINISHED so the chips arrive with the response,
                # not after the run closed. The hook fills side_events on the final model call, which
                # precedes this terminal event, so they are ready here. Each side event is already a
                # wire-ready model that to_a2a_frames maps like any content event.
                if isinstance(agui_event, RunFinishedEvent) and state.side_events:
                    for side_event in state.side_events:
                        for frame in to_a2a_frames(side_event, state):
                            yield frame
                    state.side_events.clear()
                for frame in to_a2a_frames(agui_event, state):
                    yield frame

    def get_streaming_hook_providers(self, cfg: StreamingConfig) -> List[HookProvider]:
        """Persist each streamed turn back to Chat (the buffered path persists via its return
        value; a stream has none, so the agent persists its own reply)."""
        from agent_builder_sdk.streaming.response_persist_hook import (
            StreamingResponsePersistHook,
        )

        return [StreamingResponsePersistHook(cfg)]

    def requires_context_id(self) -> bool:
        """contextId is the key Chat routes the persisted reply by."""
        return True
