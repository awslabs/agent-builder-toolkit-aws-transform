"""
Agent Runtime Server implementation compatible with multiple agent execution environments.
"""

import asyncio
import inspect
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, Optional, Protocol, Sequence, cast

import uvicorn
from fastapi import FastAPI
from strands.tools.mcp import MCPClient
from tenacity import before_sleep_log, retry, retry_if_result, stop_after_attempt, wait_exponential

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
from agent_builder_sdk.custom_types.notification_types import NotificationType
from agent_builder_sdk.env_var import has_mde_environment, set_runtime_env_vars
from agent_builder_sdk.extensions.acknowledgments.acknowledgment_handler import (
    AcknowledgmentHandler,
)
from agent_builder_sdk.extensions.base_extension_handler import BaseExtensionHandler
from agent_builder_sdk.interfaces import AnyBaseAgent
from agent_builder_sdk.mcp_client_factory import MCPClientFactory
from agent_builder_sdk.message_queue import QueueService
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.notification import (
    HitlNotifier,
    HitlTaskProcessor,
    NotificationProcessor,
    OrchAgentStopProcessor,
)
from agent_builder_sdk.notification.notification_handler import NotificationHandler
from agent_builder_sdk.request_handler import QueueRequestHandler
from agent_builder_sdk.server.base_server import BaseServer
from agent_builder_sdk.server.request_context import RequestContextMiddleware
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_sdk.task.task_manager import TaskManager
from agent_builder_sdk.task_handler import TaskHandler
from agent_builder_sdk.utils import build_agentic_api_endpoint_from_env

if TYPE_CHECKING:
    from multiprocessing.synchronize import Event as EventType

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
        binary_location: str = "/home/amazon/ElasticGumbyAgenticMCP/bin/eg_agentic_mcp_server",
        mcp_client: Optional[MCPClient] = None,
        queue_storage_path: Optional[str] = None,  # Deprecated: use storage_dir instead
        timeout: int = 28,
        delayed_timeout: int = 300,
        token_refresh_buffer: int = 40,
        token_refreshed_event: Optional["EventType"] = None,
        checkpoint_strategy: Optional[CheckpointStrategy] = None,
        checkpoint_interval: int = 30,
        auto_transition_job_to_executing: bool = True,
        extension_handlers: Optional[Sequence[BaseExtensionHandler]] = None,
        task_manager_factory: Optional[Callable[..., TaskManager]] = None,
        notification_processors: Optional[Dict[NotificationType, NotificationProcessor]] = None,
        tracing: Optional[str] = None,
    ):
        """
        Initialize the Agent Runtime Server.

        Args:
            agent_factory: Factory function for creating custom agents (required)
            host: Server host address (default: "0.0.0.0")
            port: Server port (default: 8080)
            storage_dir: Base directory for all agent runtime data (default: "/tmp/agent_runtime")
            binary_location: Path to the MCP binary for tool integration (used if mcp_client not provided)
            mcp_client: Pre-configured MCPClient instance (optional). If provided, takes precedence over binary_location.
            queue_storage_path: DEPRECATED - use storage_dir instead (backward compatibility only)
            storage_dir: Directory for agent data storage
            timeout: Timeout in seconds for waiting for synchronous responses
            delayed_timeout: Timeout in seconds for waiting for asynchronous responses after
                           send_message API timeout (_timeout, default 28s) expires (default: 300)
            token_refresh_buffer: Buffer in seconds before token expiration to refresh (default: 40)
            token_refreshed_event: Callback event that is signaled after each successful token refresh.
                The refresh process calls ``.set()`` once the new token has been written.
                The consumer should call ``.wait()`` to block until the signal arrives,
                then call ``.clear()`` to reset the event.
            checkpoint_strategy: Checkpoint strategy enum (optional)
            checkpoint_interval: Checkpoint interval - turns or minutes (default: 30)
            auto_transition_job_to_executing: Automatically transition job from ASSESSING to EXECUTING on agent initialization (default: True)
            extension_handlers: List of extension handlers that will be used by the MessageHandler for processing A2A extensions (e.g., acknowledgment)
            task_manager_factory: Factory function for creating TaskManager. Can accept **kwargs for maximum flexibility.
                                 Available kwargs: queue (QueueService), get_agent_func (Callable) (optional, experimental)
            notification_processors: Dict mapping NotificationType to NotificationProcessor instances for custom notification handling (optional).
            tracing: Type of tracing to use (cloudwatch or local) (optional)
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

            # 3. check agent status
            try:
                agent_status = get_agent_status(
                    self.context.workspace_id, self.context.job_id, self.context.agent_instance_id
                )
                if agent_status == "INVOKING":
                    self._initialization_task = asyncio.create_task(
                        self._background_finalize(self._wait_for_non_invoking_and_initialize())
                    )
                    return
                elif agent_status == "RUNNING":
                    # Container rotation case: agent already RUNNING on the platform side,
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
                    await self._finalize_agent_setup(agent_status)
                    return
            except Exception as e:
                logger.warning(f"Cannot initialize agent with exception: {e}")

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
            mcp_client = MCPClientFactory.setup_eg_mcp_client(required_mcp_args)

        # Status-dependent platform integration
        if agent_status in ["INVOKED", "RUNNING"]:
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

        # Always create agent (core functionality)
        self.agent = await self._create_agent(mcp_client, **self._get_agent_params())

        # Set agent to running
        if agent_status == "INVOKED":
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

    def _get_agent_params(self) -> dict[str, Any]:
        """Return parameters to be used for agent initialization"""
        assert self.context

        return {
            "workspace_id": self.context.workspace_id,
            "job_id": self.context.job_id,
            "agent_instance_id": self.context.agent_instance_id,
            "hitl_notifier": self._hitl_notifier,
            "task_manager": self.task_manager,
        }

    async def _create_agent(self, mcp_client: MCPClient, **agent_params) -> AnyBaseAgent:
        def accepts_kwargs(func):
            sig = inspect.signature(func)
            return any(
                param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
            )

        if inspect.iscoroutinefunction(self.agent_factory):
            async_factory = cast(AsyncAgentFactory, self.agent_factory)
            return await async_factory(mcp_client, self.storage_dir, **agent_params)
        else:
            if accepts_kwargs(self.agent_factory):
                sync_factory = cast(SyncAgentFactory, self.agent_factory)
                return sync_factory(mcp_client, self.storage_dir, **agent_params)
            else:
                sync_factory_no_kwargs = cast(SyncAgentFactoryNoKwargs, self.agent_factory)
                return sync_factory_no_kwargs(mcp_client, self.storage_dir)

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
        """Cleanup all components during shutdown."""
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

            logger.info("Graceful shutdown completed")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def handle_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle stop agent request for orchestrator agents.

        Attempts to stop all subagents first, then stops the orchestrator agent.
        The orchestrator shutdown proceeds regardless of subagent shutdown failures.
        Each shutdown operation is retried up to 3 times with exponential backoff.

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

        # Start HTTP server
        uvicorn.run(self.app, host=self.host, port=self.port)


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
