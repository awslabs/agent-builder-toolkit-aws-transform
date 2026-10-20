# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Agent Runtime Server implementation compatible with multiple agent execution environments.
"""

import asyncio
import inspect
import logging
import os
from contextlib import asynccontextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    Optional,
    Protocol,
    Sequence,
    cast,
)

import uvicorn
from botocore.exceptions import ClientError
from fastapi import FastAPI
from strands.tools.mcp import MCPClient
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from agent_builder_sdk._auth_token_refresher import (
    AuthTokenRefresher,
    get_auth_token_refresher,
    get_default_auth_token_file_path,
    setup_initial_auth_token,
)
from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    get_agent_status,
    get_subagent_instances,
    set_agent_running,
    shutdown_base_orchestrator_agent_instance,
    shutdown_subagent_instance,
    wait_for_agent_non_invoking,
)
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.agentic_framework.job_manager import JobManager
from agent_builder_sdk.checkpoint.checkpoint_service import CheckpointService
from agent_builder_sdk.checkpoint.checkpoint_triggers import CheckpointStrategy
from agent_builder_sdk.constants import (
    DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS,
    DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS,
)
from agent_builder_sdk.custom_types.notification_types import NotificationType
from agent_builder_sdk.env_var import has_mde_environment, set_runtime_env_vars
from agent_builder_sdk.extensions.acknowledgments.acknowledgment_handler import (
    AcknowledgmentHandler,
)
from agent_builder_sdk.extensions.base_extension_handler import BaseExtensionHandler
from agent_builder_sdk.interfaces import AnyBaseAgent, StreamingCapable
from agent_builder_sdk.mcp_client_factory import MCPClientFactory
from agent_builder_sdk.memory.episodic_memory import EpisodicMemory
from agent_builder_sdk.memory.file_memory_repository import FileSystemRepository
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.message_queue import QueueService
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.notification import (
    HitlNotifier,
    HitlTaskProcessor,
    NotificationProcessor,
    OrchAgentStopProcessor,
)
from agent_builder_sdk.notification.notification_handler import NotificationHandler
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.request_handler import QueueRequestHandler
from agent_builder_sdk.server.base_server import BaseServer
from agent_builder_sdk.server.request_context import RequestContextMiddleware
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_sdk.server.streaming_agent_pool import StreamingAgentPool

# Lightweight dataclass (no ag_ui/a2a deps) — safe to import eagerly on the default path.
from agent_builder_sdk.streaming.config import StreamingConfig
from agent_builder_sdk.task.task_manager import TaskManager
from agent_builder_sdk.task_handler import TaskHandler
from agent_builder_sdk.utils import build_agentic_api_endpoint_from_env, mcp_session_active

if TYPE_CHECKING:
    from multiprocessing.synchronize import Event as EventType

# ClientError codes that indicate a permanent failure — do not retry.
_NON_RETRYABLE_ERROR_CODES = frozenset(
    {"ValidationException", "AccessDeniedException", "ResourceNotFoundException"}
)

logger = logging.getLogger(__name__)


class AgentRuntimeServer(BaseServer):
    """
    Agent Runtime Server compatible with multiple agent execution environments.

    Provides JSON-RPC endpoints for agent communication, message processing, and health monitoring.
    Supports both Bedrock AgentCore runtime protocols and ATX internal messaging formats.
    Includes support for extension handlers to process A2A extensions like acknowledgments.
    """

    def __init__(
        self,
        agent_factory: "AgentFactory",
        host: str = "0.0.0.0",
        port: int = 8080,
        storage_dir: str = "/tmp/agent_runtime",
        binary_location: str = "/home/amazon/AgentBuilderAgenticMCP/bin/agent-builder-agentic-mcp",
        mcp_client: Optional[MCPClient] = None,
        queue_storage_path: Optional[str] = None,  # Deprecated: use storage_dir instead
        timeout: int = DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS,
        delayed_timeout: int = DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS,
        token_refresh_buffer: int = 40,
        token_refreshed_event: Optional["EventType"] = None,
        checkpoint_strategy: Optional[CheckpointStrategy] = None,
        checkpoint_interval: int = 30,
        auto_transition_job_to_executing: bool = True,
        extension_handlers: Optional[Sequence[BaseExtensionHandler]] = None,
        task_manager_factory: Optional[Callable[..., TaskManager]] = None,
        notification_processors: Optional[Dict[NotificationType, NotificationProcessor]] = None,
        tracing: Optional[str] = None,
        streaming_config: Optional["StreamingConfig"] = None,
    ):
        """
        Initialize the Agent Runtime Server.

        Args:
            agent_factory: Factory function for creating custom agents (required)
            host: Server host address
            port: Server port
            storage_dir: Base directory for all agent runtime data
            binary_location: Path to the MCP binary for tool integration (used if mcp_client not provided)
            mcp_client: Pre-configured MCPClient instance (optional). If provided, takes precedence over binary_location.
            queue_storage_path: DEPRECATED - use storage_dir instead (backward compatibility only)
            timeout: Timeout in seconds for waiting for synchronous message/send responses. Defaults to
                DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS (28s). A value above MAX_SEND_MESSAGE_TIMEOUT_SECONDS
                (28s) logs a warning: the platform limits each SendMessage attempt to 29s, so the
                acknowledgment can be cut off.
            delayed_timeout: Timeout in seconds for waiting for asynchronous responses, applied
                           after the synchronous ``timeout`` window expires
            token_refresh_buffer: Buffer in seconds before token expiration to refresh
            token_refreshed_event: Callback event that is signaled after each successful token refresh.
                The refresh process calls ``.set()`` once the new token has been written.
                The consumer should call ``.wait()`` to block until the signal arrives,
                then call ``.clear()`` to reset the event.
            checkpoint_strategy: Checkpoint strategy enum (optional)
            checkpoint_interval: Checkpoint interval in turns or minutes
            auto_transition_job_to_executing: Automatically transition job from ASSESSING to EXECUTING on agent initialization
            extension_handlers: List of extension handlers that will be used by the MessageHandler for processing A2A extensions (e.g., acknowledgment)
            task_manager_factory: Factory function for creating TaskManager. Can accept **kwargs for maximum flexibility.
                                 Available kwargs: queue (QueueService), get_agent_func (Callable) (optional, experimental)
            notification_processors: Dict mapping NotificationType to NotificationProcessor instances for custom notification handling (optional).
            tracing: Type of tracing to use (cloudwatch or local) (optional)
            streaming_config: Opt-in to streaming (message/stream). None (default) means the
                server does not serve message/stream and behaves exactly as before. Passing a
                ``StreamingConfig`` turns streaming on: streaming turns are served by per-user
                agents (one Strands invocation per user at a time) over a dedicated shared MCP
                client, so multiple users of one job can stream at once, with the config's
                idle-TTL and emit toggles applied. The message/send path is unaffected either way.

                ⚠️ CONCURRENCY CONTRACT (partner-facing): when streaming is on, N users' turns
                run CONCURRENTLY on one event loop in a single process. Any tool or hook you
                provide MUST NOT keep per-request state in module-level or class-level mutable
                globals — one user's turn will clobber another's, or leak state across users. Use
                a ``contextvars.ContextVar`` (per-turn/per-task isolation) or the per-request
                ToolContext/invocation_state instead. (The SDK's own SuggestionsManager uses a
                ContextVar for exactly this reason.) This constraint does NOT apply with streaming
                off (turns are serialized).
        """
        self.stop_requested = False
        self.agent_factory = agent_factory
        self.host = host
        self.port = port
        self.auth_token_refresher: Optional[AuthTokenRefresher] = None
        self.task_manager: Optional[TaskManager] = None
        self.task_manager_factory = task_manager_factory
        self.notification_processors = notification_processors
        self.auto_transition_job_to_executing = auto_transition_job_to_executing

        handlers = list(extension_handlers) if extension_handlers else []
        if not any(isinstance(h, AcknowledgmentHandler) for h in handlers):
            handlers.insert(0, AcknowledgmentHandler())
        self.extension_handlers = handlers
        # Handle deprecated queue_storage_path parameter
        if queue_storage_path is not None:
            import warnings

            warnings.warn(
                "queue_storage_path parameter is deprecated. queue_storage_path will be removed in a future version.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Use the deprecated path for backward compatibility
            self.base_storage_dir = storage_dir
            self.storage_dir = os.path.join(self.base_storage_dir, "agent")
            self.queue_storage_path = queue_storage_path
        else:
            # Unified storage path - derive all paths from base directory
            self.base_storage_dir = storage_dir
            self.storage_dir = os.path.join(self.base_storage_dir, "agent")
            self.queue_storage_path = os.path.join(self.base_storage_dir, "queue")

        self.binary_location = binary_location
        self.mcp_client = mcp_client

        # Streaming (opt-in). None => off; a StreamingConfig => on, with per-source streaming
        # agents served from this pool over a dedicated, persistently-open MCP client, shaped by
        # the config's idle-TTL and emit toggles.
        self.streaming_config = streaming_config
        self._streaming_agent_pool: Optional[StreamingAgentPool] = None
        # MCP client shared across the per-source streaming agents (opened once, kept open).
        self._shared_mcp_client: Optional[MCPClient] = None
        # True when self._shared_mcp_client above is the caller-provided mcp_client (the optional
        # mcp_client constructor arg), rather than one we built from binary_location. The caller
        # owns that client's lifecycle, so _cleanup must not stop it — parity with
        # _setup_concurrent_streaming, which also won't start/reset a caller-owned client. Set in
        # _setup_concurrent_streaming.
        self._shared_mcp_client_caller_owned: bool = False
        # Conversation repository shared by the shared singleton agent and all per-user
        # streaming agents (so one user's sync and streaming turns read/write the same history).
        self._shared_conversation_repository: Optional[FileMultiSourceConversationRepository] = None
        # Memory manager shared by the shared singleton agent and all per-user streaming agents,
        # so the job's sync and streaming turns use the SAME (job-scoped) memory store rather than
        # diverging per per-source storage_dir. Memory is job-scoped — same behavior as the
        # existing shared singleton agent.
        self._shared_memory_manager: Optional[MemoryManager] = None

        # Agent state
        self.agent: Optional[AnyBaseAgent] = None
        self.initialized = False
        self._initialization_lock = asyncio.Lock()
        self._initialization_task: Optional[asyncio.Task] = None
        self.agent_ready_event = asyncio.Event()
        self.context: Optional[AgentRuntimeContext] = None
        self.message_processor_task: Optional[asyncio.Task] = None
        self._stop_lock = asyncio.Lock()
        self._stop_result: Optional[dict] = None

        # Set timeouts
        # MessageHandler validates the timeout, so it is not validated (and warned about) twice.
        self.timeout = timeout
        self.delayed_timeout = delayed_timeout

        # Set AuthTokenRefresher parameters
        self.token_refresh_buffer = token_refresh_buffer
        self.token_refreshed_event = token_refreshed_event

        # Initialize components
        self.queue = QueueService(storage_path=self.queue_storage_path)
        self.request_handler = QueueRequestHandler(
            request_queue=self.queue.request_queue, response_store=self.queue.response_store
        )
        self.task_handler = TaskHandler(task_manager=self.task_manager)
        self.message_handler = MessageHandler(
            self.queue,
            timeout=self.timeout,
            delayed_timeout=self.delayed_timeout,
            extension_handlers=self.extension_handlers,
            task_manager=self.task_manager,
        )

        # Checkpointing service (always create for restoration, but only enable active checkpointing if properly configured)
        self.checkpoint_service = CheckpointService(
            storage_dir=self.base_storage_dir,
            strategy=checkpoint_strategy,
            interval=checkpoint_interval,
        )

        self._hitl_notifier = HitlNotifier()

        # Create notification handler with queue access
        self.notification_handler = NotificationHandler(queue=self.queue)

        # Register default processors
        self.notification_handler.register_processor(
            NotificationType.HITL_TASK_STATUS_CHANGE,
            HitlTaskProcessor(notifier=self._hitl_notifier),
        )
        self.notification_handler.register_processor(
            NotificationType.ORCH_AGENT_STOP_EVENT, OrchAgentStopProcessor()
        )

        # Register custom processors (replaces defaults)
        if self.notification_processors:
            for notification_type, processor in self.notification_processors.items():
                self.notification_handler.register_processor(notification_type, processor)

        # Create FastAPI app with lifespan
        self.app = FastAPI(title="ATX AgentCore Compatible Agent Server", lifespan=self._lifespan)
        self.app.add_middleware(RequestContextMiddleware)
        self.setup_common_routes()

        # Setup tracing
        if tracing:
            self.setup_tracing(tracing)

    def _create_checkpoint_callback(self):
        """Create checkpoint callback for conversation-based checkpointing."""
        return self.checkpoint_service.create_callback() if self.checkpoint_service else None

    async def initialize_agent(self, auth_token: Optional[str] = None) -> None:
        """
        Initialize the agent with stored context and authentication token.

        Args:
            auth_token: Initial authentication token (optional)
        """
        if not self.context:
            raise ValueError("Agent context not set. Initialize context first.")

        logger.info(
            f"Initializing agent for workspace: {self.context.workspace_id}, job: {self.context.job_id}"
        )

        # 1. Set runtime environment variables (for AgentCore)
        set_runtime_env_vars(
            job_id=self.context.job_id,
            workspace_id=self.context.workspace_id,
            agent_instance_id=self.context.agent_instance_id,
        )
        # 2. Set up initial token if it is provided
        if auth_token:
            setup_initial_auth_token(auth_token)

        if self.initialized:
            logger.info("Agent already initialized, skipping")
            return

        async with self._initialization_lock:
            if self.initialized:
                logger.info("Agent finished initialization during waiting the lock")
                return

            # Skip if a background initialization task is already running
            if self._initialization_task and not self._initialization_task.done():
                logger.info("Initialization already in progress, skipping")
                return

            # 3. check agent status (with retry for transient network errors)
            agent_status = await self._get_agent_status_with_retry()
            if agent_status is None:
                logger.error("Failed to get agent status after retries, agent will not initialize")
                return

            if agent_status == "INVOKING":
                # Platform is still processing the InvokeAgent call (setting up
                # resources, writing metadata). Wait in the background until the
                # status transitions to INVOKED, then complete initialization.
                self._initialization_task = asyncio.create_task(
                    self._background_finalize(self._wait_for_non_invoking_and_initialize())
                )
                return
            elif agent_status in ["RUNNING", "IDLE"]:
                # Container rotation case: agent already RUNNING/IDLE on the platform side,
                # but this container is a fresh process and needs to rebuild local state
                # (checkpoint restore, MCP client, agent factory). Run in the background
                # so health checks return fast; real requests wait on agent_ready_event
                # via _get_ready_agent() in the message processor.
                logger.info(f"Agent status is {agent_status}, starting background finalize")
                self._initialization_task = asyncio.create_task(
                    self._background_finalize(self._finalize_agent_setup(agent_status))
                )
                return
            else:
                logger.info(f"Agent status is {agent_status}, finalizing agent setup")
                try:
                    await self._finalize_agent_setup(agent_status)
                except Exception as e:
                    logger.warning(f"Cannot finalize agent setup with exception: {e}")
                return

    async def _background_finalize(self, coro: Coroutine) -> None:
        """Run an initialization coroutine in the background with error handling.

        If the coroutine raises, log it and clear _initialization_task so a
        subsequent initialize_agent() call can retry. agent_ready_event is
        never set on failure, so _get_ready_agent() callers stay blocked —
        intentional, since the agent can't serve requests without a
        successful setup.
        """
        try:
            await coro
        except Exception:
            logger.exception("Background initialization failed")
            self._initialization_task = None

    async def _get_agent_status_with_retry(self) -> Optional[str]:
        """Get agent status, retrying transient network errors.

        Retries connection timeouts and endpoint connectivity failures with exponential
        backoff (attempt count and timing set by the @retry decorator below); permanent
        client errors in _NON_RETRYABLE_ERROR_CODES are not retried.

        Runs in a thread executor so the backoff sleeps do not block the asyncio event
        loop (health checks must keep responding).

        Returns:
            Agent status string, or None if all retries are exhausted.
        """
        assert self.context
        context = self.context

        def _is_retryable(exception: BaseException) -> bool:
            """Retry all exceptions except permanent client errors."""
            if isinstance(exception, ClientError):
                error_code = exception.response.get("Error", {}).get("Code", "")
                if error_code in _NON_RETRYABLE_ERROR_CODES:
                    return False
            return True

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=8),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _get_status():
            return get_agent_status(context.workspace_id, context.job_id, context.agent_instance_id)

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _get_status)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in _NON_RETRYABLE_ERROR_CODES:
                logger.error(f"Non-retryable error during agent initialization: {error_code} - {e}")
            else:
                logger.error(f"Failed to get agent status after retries: {error_code} - {e}")
            return None
        except Exception:
            logger.error(
                "Failed to get agent status after retries during agent initialization",
                exc_info=True,
            )
            return None

    async def _wait_for_non_invoking_and_initialize(self) -> None:
        """Wait for agent status to exit INVOKING state, then complete initialization."""
        assert self.context

        final_status = await wait_for_agent_non_invoking(
            self.context.workspace_id, self.context.job_id, self.context.agent_instance_id
        )
        if final_status != "INVOKING":
            await self._finalize_agent_setup(final_status)

    async def _finalize_agent_setup(self, agent_status: str = "RUNNING") -> None:
        """Finalize agent setup with MCP client, auth refresher, and checkpointing."""
        assert self.context

        # Use provided MCP client if available, otherwise create from binary_location
        if self.mcp_client:
            logger.info("Using provided MCP client")
            mcp_client = self.mcp_client
        else:
            logger.info("Creating MCP client from binary_location")
            agentic_api_endpoint = build_agentic_api_endpoint_from_env()
            required_mcp_args = {
                "binaryLocation": self.binary_location,
                "workspaceId": self.context.workspace_id,
                "jobId": self.context.job_id,
                "agentInstanceId": self.context.agent_instance_id,
                "agenticApiEndpoint": agentic_api_endpoint,
                "authTokenFile": get_default_auth_token_file_path(),
            }
            mcp_client = MCPClientFactory.setup_ab_mcp_client(required_mcp_args)

        # Status-dependent platform integration
        if agent_status in ["INVOKED", "RUNNING", "IDLE"]:
            logger.info(
                "Setting up full platform integration (setting agent to RUNNING + auth refresher + checkpointing)"
            )

            # Set up auth token refresher
            self.auth_token_refresher = get_auth_token_refresher(
                workspace_id=self.context.workspace_id,
                job_id=self.context.job_id,
                agent_instance_id=self.context.agent_instance_id,
                first_token=self.context.initial_auth_token,
                token_refresh_buffer=self.token_refresh_buffer,
                token_refreshed_event=self.token_refreshed_event,
            )

            # Initialize checkpoint service
            if self.checkpoint_service:
                self.checkpoint_service.initialize(self.context)
                await self.checkpoint_service.start_background_checkpointing()
        else:
            logger.info(f"Agent is {agent_status} - skipping auth refresher and checkpointing")

        # Create TaskManager if factory provided
        if self.task_manager_factory:
            logger.info("Creating TaskManager from factory")
            self.task_manager = self.task_manager_factory(
                queue=self.queue, get_agent_func=self._get_ready_agent
            )

            # Update handlers with new task_manager
            if self.task_handler:
                self.task_handler.task_manager = self.task_manager
            if self.message_handler:
                self.message_handler.task_manager = self.task_manager
            logger.info("TaskManager created and injected into handlers")

        # For concurrent streaming, build the shared conversation repository BEFORE the
        # shared singleton agent so both it and the per-user streaming agents use the same
        # history store (one user's sync + streaming turns stay coherent). A single instance
        # is required: separate instances on one storage_dir overwrite each other's saves.
        # Not built otherwise, so default behavior is unchanged.
        #
        # Build EXACTLY ONCE (guard on is None). _finalize_agent_setup re-runs on a retried
        # initialization; the streaming agent pool captures these instances in a closure and is
        # itself idempotent, so rebuilding the stores here on a retry would leave the pool using
        # the FIRST instances while the singleton agent gets the SECOND — two repositories on one
        # storage_dir overwriting each other's saves (the exact divergence this shared instance
        # exists to prevent).
        self._build_shared_streaming_stores()

        # Always create agent (core functionality)
        self.agent = await self._create_agent(mcp_client, **self._get_agent_params())

        # Opt-in streaming: validate the agent can stream and stand up the per-source pool +
        # shared MCP client. No-op when off. Done BEFORE the job is transitioned to EXECUTING
        # below, so the streaming path is fully ready before the WebApp can send chat (no
        # post-EXECUTING warm-up gap). The buffered path above is untouched.
        self._setup_streaming()

        # Set agent to running
        if agent_status in ["INVOKED", "IDLE"]:
            set_agent_running(
                self.context.workspace_id, self.context.job_id, self.context.agent_instance_id
            )

        # Auto-transition job from ASSESSING to EXECUTING if enabled
        if self.auto_transition_job_to_executing:
            client = get_agentic_api_client()
            job_manager = JobManager(
                workspace_id=self.context.workspace_id,
                job_id=self.context.job_id,
                agent_instance_id=self.context.agent_instance_id,
                client=client,
            )
            job_manager.transition_to_executing_if_assessing()

        self.initialized = True
        self.agent_ready_event.set()
        logger.info("Agent initialization completed successfully.")

    def _build_shared_streaming_stores(self) -> None:
        """Build the shared conversation repository + memory manager for concurrent streaming,
        EXACTLY ONCE.

        For concurrent streaming both the shared singleton agent and every per-user streaming
        agent must use the SAME history + memory store (one user's message/send and
        message/stream turns stay coherent). A single instance is required: separate instances
        on one storage_dir overwrite each other's saves.

        Guarded on ``is None`` because ``_finalize_agent_setup`` re-runs on a retried
        initialization. The streaming agent pool captures these instances in a closure and is
        itself idempotent, so rebuilding here on a retry would leave the pool on the FIRST
        instances while the singleton agent gets the SECOND — two repositories on one
        storage_dir clobbering each other (the exact divergence the shared instance prevents).

        No-op when streaming is off, so default behavior is unchanged.
        """
        if self.streaming_config is None or self._shared_conversation_repository is not None:
            return
        self._shared_conversation_repository = FileMultiSourceConversationRepository(
            storage_dir=self.storage_dir
        )
        # Memory is job-scoped (same behavior as the existing shared singleton agent). Without a
        # shared instance each agent derives <its storage_dir>/memories, so the per-user
        # streaming dir (<base>/agent/sources/<id>/memories) would diverge from the singleton's
        # dir (<base>/agent/memories).
        memory_repository = FileSystemRepository(
            storage_path=os.path.join(self.storage_dir, "memories")
        )
        self._shared_memory_manager = MemoryManager(
            memories=[EpisodicMemory(repository=memory_repository)]
        )

    def _build_streaming_runtime(self) -> None:
        """Validate the agent can stream, then build the per-source pool + shared MCP client."""
        self._validate_streaming_capability()
        self._setup_concurrent_streaming()

    def _validate_streaming_capability(self) -> None:
        """Fail fast (at init, before EXECUTING) if streaming can't work.

        No-op when streaming is off. When on, two misconfigurations must surface now rather
        than as a mid-stream AttributeError (after 200/SSE headers are flushed) or as silent
        data divergence users hit later:
        1. The agent isn't StreamingCapable. Streaming is async-only, so it's declared by
           AsyncBaseOrchestrator / AsyncBaseSubagent, not the sync agents.
        2. A legacy factory can't receive injected kwargs. When streaming is on the server injects
           shared resources via **kwargs (_get_agent_params). A `def f(mcp_client, storage_dir)`
           factory silently DROPS them, so a per-source agent that shares history/memory would
           diverge from the shared singleton for the same user.
        """
        if self.streaming_config is None:
            return

        if not isinstance(self.agent, StreamingCapable):
            raise RuntimeError(
                "streaming requires a StreamingCapable agent (AsyncBaseOrchestrator or "
                "AsyncBaseSubagent, or a subclass). The provided agent factory built "
                f"{type(self.agent).__name__}, which does not support streaming."
            )

        # StreamingCapable's process_message_stream takes cfg; guard against a hand-rolled
        # subclass with a mismatched signature
        stream_params = inspect.signature(self.agent.process_message_stream).parameters
        accepts_cfg = "cfg" in stream_params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in stream_params.values()
        )
        if not accepts_cfg:
            raise RuntimeError(
                "streaming requires process_message_stream to accept a `cfg` argument "
                "(the StreamingConfig the server forwards per turn), e.g. "
                "`process_message_stream(self, request, conversation_id, cfg=DEFAULT_STREAMING_CONFIG)`. "
                f"The provided agent's {type(self.agent).__name__}.process_message_stream does not "
                "accept `cfg`."
            )

        if not self._is_async_factory(self.agent_factory) and not self._factory_accepts_kwargs(
            self.agent_factory
        ):
            raise RuntimeError(
                "streaming requires an agent_factory that accepts **kwargs so the server can "
                "inject the shared resources it forwards to the factory. The provided factory "
                "uses the legacy (mcp_client, storage_dir) signature; update it to "
                "`def agent_factory(mcp_client, storage_dir, **kwargs)` and forward kwargs to the "
                "agent factory."
            )

    def _setup_concurrent_streaming(self) -> None:
        """Build the streaming MCP client (opened once, shared) and per-source agent pool.

        Only called when streaming is enabled (streaming_config is not None). Uses a dedicated
        MCP client so the buffered path's per-turn open/close is untouched. Each per-source agent is
        built by the same partner factory, given the shared client and its own storage dir.

        Idempotent: if initialization failed after this ran and is being retried, the
        already-started shared client and pool are reused rather than started again
        (starting a second time would orphan the first client's background thread, or
        raise "session already running" for a caller-provided client).

        Concurrency assumptions (verified against mcp-1.27.0 + strands 1.45.0):
        - Safe concurrent tool calls across per-source agents rely on ONE shared MCPClient
          with a single background event loop; the MCP session dispatches by request id
          (no serialization). This holds for the default direct-call path; re-verify if
          per-request progress callbacks or task-augmented execution (tasks_config) are
          enabled later.
        - Conversation persistence: the shared conversation repository saves the full
          store to disk synchronously per message. On the concurrent path this is a known
          latency ceiling (grows with total conversation size); offloading/coalescing the
          write is deferred to P1. The default (streaming off) path is unchanged — it already
          saved per message.
        """
        assert self.context
        # Only reached via the `streaming_config is not None` gate in initialize_agent.
        assert self.streaming_config is not None

        # Idempotency keys on the POOL (the terminal artifact set only after everything below
        # succeeds), NOT on _shared_mcp_client. If we keyed on the client and start() later
        # failed, the client ref would be set, this guard would early-return on every retry,
        # and the pool would never be built — streaming permanently dead. Keying on the pool
        # lets a failed init be retried cleanly.
        if self._streaming_agent_pool is not None:
            logger.info("Concurrent streaming already set up; reusing shared client + pool")
            return

        # MCP client shared across per-source agents, opened once and kept open for the
        # server's life (the MCP protocol multiplexes concurrent tool calls over one
        # connection). Dedicated so the message/send path's per-turn open/close is untouched.
        caller_provided_client = self.mcp_client is not None
        # Remember caller-ownership so _cleanup won't stop a client the caller owns.
        self._shared_mcp_client_caller_owned = caller_provided_client
        if self.mcp_client is not None:
            logger.info("Concurrent streaming: reusing provided MCP client")
            shared_mcp_client = self.mcp_client
        else:
            agentic_api_endpoint = build_agentic_api_endpoint_from_env()
            shared_mcp_client = MCPClientFactory.setup_ab_mcp_client(
                {
                    "binaryLocation": self.binary_location,
                    "workspaceId": self.context.workspace_id,
                    "jobId": self.context.job_id,
                    "agentInstanceId": self.context.agent_instance_id,
                    "agenticApiEndpoint": agentic_api_endpoint,
                    "authTokenFile": get_default_auth_token_file_path(),
                }
            )
        self._shared_mcp_client = shared_mcp_client
        # Only start a client that isn't already active — a caller may hand us a client they
        # own and already started; starting it again raises "session currently running". If
        # start() fails on a client WE built, drop the ref so a retried init builds a fresh one
        # rather than reusing a half-open client (a caller-owned client's lifecycle isn't ours
        # to reset).
        if not mcp_session_active(shared_mcp_client):
            try:
                shared_mcp_client.start()  # persistent open; closed in _cleanup
            except Exception:
                if not caller_provided_client:
                    self._shared_mcp_client = None
                raise

        agent_params = self._get_agent_params()
        # Bind to a local so the narrowed (non-None) type is visible inside the closure below;
        # mypy does not carry the method-level assert's narrowing across the nested-def boundary.
        streaming_config = self.streaming_config

        async def create_streaming_agent(user_storage_dir: str) -> AnyBaseAgent:
            agent = await self._create_agent_with_storage(
                shared_mcp_client, user_storage_dir, **agent_params
            )
            # Attach the streaming hooks the agent declares (e.g. an orchestrator persists each
            # turn back to Chat, since a stream has no return value to persist; a sub-agent
            # declares none). The shared singleton agent that serves message/send never goes
            # through here, so the buffered path is unaffected.
            from strands import Agent as StrandsAgent

            if isinstance(agent, StreamingCapable):
                for hook in agent.get_streaming_hook_providers(streaming_config):
                    cast(StrandsAgent, agent).hooks.add_hook(hook)
            return agent

        self._streaming_agent_pool = StreamingAgentPool(
            create_agent=create_streaming_agent,
            base_storage_dir=self.storage_dir,
            idle_ttl_seconds=streaming_config.agent_idle_ttl_seconds,
        )
        logger.info("Concurrent streaming enabled: streaming agent pool ready")

    async def _create_agent_with_storage(
        self, mcp_client: MCPClient, storage_dir: str, **agent_params
    ) -> AnyBaseAgent:
        """Like _create_agent but with an explicit per-user storage_dir."""
        if self._is_async_factory(self.agent_factory):
            async_factory = cast(AsyncAgentFactory, self.agent_factory)
            return await async_factory(mcp_client, storage_dir, **agent_params)
        else:
            if self._factory_accepts_kwargs(self.agent_factory):
                sync_factory = cast(SyncAgentFactory, self.agent_factory)
                return sync_factory(mcp_client, storage_dir, **agent_params)
            else:
                sync_factory_no_kwargs = cast(SyncAgentFactoryNoKwargs, self.agent_factory)
                return sync_factory_no_kwargs(mcp_client, storage_dir)

    def _get_agent_params(self) -> dict[str, Any]:
        """Return parameters to be used for agent initialization"""
        assert self.context

        params: dict[str, Any] = {
            "workspace_id": self.context.workspace_id,
            "job_id": self.context.job_id,
            "agent_instance_id": self.context.agent_instance_id,
            "hitl_notifier": self._hitl_notifier,
            "task_manager": self.task_manager,
        }
        # Only present when concurrent streaming is enabled; the factory forwards it to the
        # ConversationHookProvider so the shared singleton agent and per-user streaming agents
        # share history.
        if self._shared_conversation_repository is not None:
            params["conversation_repository"] = self._shared_conversation_repository
        # Same as conversation: inject the shared memory manager only when concurrent streaming
        # built one, so the shared singleton agent and per-user streaming agents share memory.
        if self._shared_memory_manager is not None:
            params["memory_manager"] = self._shared_memory_manager
        return params

    @staticmethod
    def _factory_accepts_kwargs(func) -> bool:
        sig = inspect.signature(func)
        return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values())

    @staticmethod
    def _is_async_factory(func) -> bool:
        """True if the factory is async — covers both a plain ``async def`` function AND a
        callable OBJECT whose ``__call__`` is ``async def`` (the shape AsyncAgentFactory
        advertises as a Protocol). Plain ``iscoroutinefunction(func)`` is False for the latter,
        which would otherwise leave an un-awaited coroutine as ``self.agent``."""
        return inspect.iscoroutinefunction(func) or inspect.iscoroutinefunction(
            getattr(func, "__call__", None)
        )

    async def _create_agent(self, mcp_client: MCPClient, **agent_params) -> AnyBaseAgent:
        return await self._create_agent_with_storage(mcp_client, self.storage_dir, **agent_params)

    async def _get_agent_for_streaming(self, source_id: str, source_type: MessageSourceType):
        """Serve a streaming turn. Rejects unless streaming was opted into."""
        if self.streaming_config is None:
            raise NotImplementedError(
                "This agent does not support streaming. "
                "Enable it by passing a StreamingConfig to AgentRuntimeServer."
            )
        # Wait for initialization to finish (it runs as a background task, so the
        # pool and shared MCP client are built only once the agent is ready).
        await self.agent_ready_event.wait()
        if self._streaming_agent_pool is None:
            raise RuntimeError("Streaming agent pool unavailable after initialization")
        return await self._streaming_agent_pool.get_agent(source_id, source_type)

    @asynccontextmanager
    async def _streaming_turn_lease(self, source_id: str) -> AsyncIterator[None]:
        """Mark the source in-flight in the pool for the whole turn so its per-user agent is
        never idle-evicted mid-stream. Falls back to a no-op if the pool isn't built."""
        if self._streaming_agent_pool is None:
            yield
            return
        async with self._streaming_agent_pool.lease(source_id):
            yield

    async def handle_mde_notification(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self.notification_handler is None:
            raise ValueError("Notification handler not initialized")
        return await self.notification_handler.handle_notification(request)

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """FastAPI lifespan for graceful startup/shutdown."""
        await self._startup()
        yield
        await self._cleanup()

    async def _startup(self) -> None:
        """Unified startup logic."""
        logger.info("Starting up Agent Runtime Server...")

        await self.queue.start()
        self.message_processor_task = asyncio.create_task(
            self.request_handler.start_processing(
                self._get_ready_agent, self._create_checkpoint_callback
            )
        )

        # Initialize agent if environment is available (MDE mode)
        if has_mde_environment():
            logger.info("MDE mode: Initializing agent from environment...")
            await self._initialize_mde_mode()
        else:
            logger.info("AgentCore mode: Agent will be initialized on first request")

    async def _get_ready_agent(self):
        """Get agent when ready (used by QueueService)."""
        logger.info("Getting ready agent...")
        await self.agent_ready_event.wait()
        logger.info("Agent is ready")
        return self.agent

    async def _cleanup(self) -> None:
        """Cleanup all components during shutdown.

        This runs up to twice per shutdown (once from the STOP handler, once from FastAPI's
        lifespan shutdown). That is fine: every step below already no-ops if its resource is
        gone (task already done, service already None, etc.), so running twice is harmless — same
        as before concurrent streaming was added.

        Only ONE step needs care: MCPClient.stop() throws if the client is already stopped. So
        after stopping it we set self._shared_mcp_client = None, and the "is not None" check skips
        it on the second pass. (This client only exists when concurrent streaming is on; on the
        default path it's None and the step is skipped entirely.)
        """
        logger.info("Starting graceful shutdown...")

        try:
            # 1. Cancel message processor task
            if self.message_processor_task and not self.message_processor_task.done():
                logger.info("Stopping message processor...")
                self.message_processor_task.cancel()
                try:
                    await self.message_processor_task
                except asyncio.CancelledError:
                    logger.info("Message processor stopped")

            # 2. Cancel background initialization task if still running
            if self._initialization_task and not self._initialization_task.done():
                logger.info("Stopping background initialization...")
                self._initialization_task.cancel()
                try:
                    await self._initialization_task
                except asyncio.CancelledError:
                    logger.info("Background initialization stopped")

            # 3. Stop queue service
            if self.queue:
                logger.info("Stopping queue service...")
                await self.queue.stop()

            # 4. Shutdown checkpoint service
            if self.checkpoint_service:
                await self.checkpoint_service.shutdown()

            # 5. Stop auth token refresher process
            if self.auth_token_refresher:
                logger.info("Shutting down the auth_token_refresher")
                self.auth_token_refresher.shutdown()

            # 7. Close the shared MCP client (opened once for concurrent streaming), UNLESS the
            # caller provided it — a caller-owned client's lifecycle is the caller's, so we must
            # not stop it here (parity with _setup_concurrent_streaming, which won't start/reset
            # a caller-owned client either).
            if self._shared_mcp_client is not None and not self._shared_mcp_client_caller_owned:
                logger.info("Closing shared MCP client...")
                try:
                    self._shared_mcp_client.stop(None, None, None)
                except Exception as e:
                    logger.warning(f"Error closing shared MCP client: {e}")
                finally:
                    # Null it so a later pass (or the idempotency guard above being bypassed)
                    # never re-stops an already-closed client.
                    self._shared_mcp_client = None

            logger.info("Graceful shutdown completed")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def handle_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle stop agent request for orchestrator agents.

        Attempts to stop all subagents first, then stops the orchestrator agent.
        The orchestrator shutdown proceeds regardless of subagent shutdown failures.
        Each shutdown operation is retried with exponential backoff (see shutdown_with_retry).

        Args:
            params: Request parameters containing agentInstanceId

        Returns:
            Dict containing:
                - message: Summary of shutdown results
                - agentInstanceId: The orchestrator agent instance ID
                - failedSubagents: List of subagent IDs that failed to stop

        Raises:
            ValueError: If agentInstanceId is missing from params
        """

        logger.info("Processing stop agent request for orchestrator")

        agent_instance_id = params.get("agentInstanceId")
        if not agent_instance_id:
            logger.error("Missing agentInstanceId in stop request")
            raise ValueError("Missing agentInstanceId in stop request")

        async with self._stop_lock:
            if self._stop_result is not None:
                logger.info(
                    f"Stop already completed for agent {agent_instance_id}, "
                    f"returning cached result for idempotent stop request: {self._stop_result}"
                )
                return self._stop_result

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_result(lambda x: not x),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                retry_error_callback=lambda _: False,
            )
            def shutdown_with_retry(agent_type: str, subagent_id: Optional[str]) -> bool:
                """Shutdown agent with retry logic."""
                if agent_type == "subagent":
                    if not subagent_id:
                        logger.error("Subagent ID is required for subagent shutdown")
                        return False
                    return shutdown_subagent_instance(subagent_id)
                else:
                    return shutdown_base_orchestrator_agent_instance()

            subagents = get_subagent_instances(agent_instance_id)
            stopped_count = 0
            failed_subagents = []

            for subagent in subagents:
                subagent_id = subagent["agentInstanceId"]
                logger.info(f"Attemping subagent {subagent_id} shutdown...")
                if shutdown_with_retry("subagent", subagent_id):
                    stopped_count += 1
                else:
                    failed_subagents.append(subagent_id)
                    logger.error(f"Failed to stop subagent {subagent_id} after retries")

            logger.info("Attempting orchestrator agent shutdown...")
            orchestrator_stopped = shutdown_with_retry("orchestrator", agent_instance_id)

            if not orchestrator_stopped:
                logger.error("Failed to stop orchestrator after retries")

            message = f"{'Stopped' if orchestrator_stopped else 'Failed to stop'} the orchestration agent. Stopped {stopped_count} subagent(s)"
            if failed_subagents:
                message += f", {len(failed_subagents)} subagent(s) failed to stop"

            result = {
                "message": message,
                "agentInstanceId": agent_instance_id,
                "failedSubagents": failed_subagents,
            }

            if orchestrator_stopped:
                self._stop_result = result

            return result

    def start(self) -> None:
        """Start the Agent Runtime Server."""
        logger.info(f"Starting Agent Runtime Server on {self.host}:{self.port}")

        # On streaming, send `Connection: close` on every response so the AgentCore in-guest proxy
        # never reuses a pooled HTTP/1.1 socket this server has since closed (it does not liveness-check
        # the pooled connection, so a reused-then-dead socket black-holes the next invoke).
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            headers=[("Connection", "close")] if self.streaming_config is not None else None,
        )


class SyncAgentFactory(Protocol):
    def __call__(self, mcp_client: MCPClient, storage_dir: str, **kwargs):
        pass


class SyncAgentFactoryNoKwargs(Protocol):
    def __call__(self, mcp_client: MCPClient, storage_dir: str):
        pass


class AsyncAgentFactory(Protocol):
    async def __call__(self, mcp_client: MCPClient, storage_dir: str, **kwargs):
        pass


AgentFactory = SyncAgentFactory | SyncAgentFactoryNoKwargs | AsyncAgentFactory
