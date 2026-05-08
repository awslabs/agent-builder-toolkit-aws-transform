"""
Stateless Agent Runtime Server implementation
"""

import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, Optional

import uvicorn
from fastapi import FastAPI
from strands.agent import AgentResult

from agent_builder_sdk._auth_token_refresher import (
    get_default_auth_token_file_path,
    setup_initial_auth_token,
)
from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    get_agent_status,
    set_agent_running,
    wait_for_agent_non_invoking,
)
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.agentic_framework.job_manager import JobManager
from agent_builder_sdk.env_var import has_mde_environment, set_runtime_env_vars
from agent_builder_sdk.interfaces import AnyBaseAgent
from agent_builder_sdk.mcp_client_factory import MCPClientFactory
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.server.base_server import BaseServer
from agent_builder_sdk.server.request_context import RequestContextMiddleware
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_sdk.task_handler import TaskHandler
from agent_builder_sdk.utils import build_agentic_api_endpoint_from_env

logger = logging.getLogger(__name__)


class StatelessAgentRuntimeServer(BaseServer):
    """
    Stateless Agent Runtime Server compatible with multiple agent execution environments.

    Provides JSON-RPC endpoints for agent communication, message processing, and health monitoring.
    Supports both Bedrock AgentCore runtime protocols and ATX internal messaging formats.
    """

    def __init__(
        self,
        agent_factory: Callable[..., AnyBaseAgent[str, AgentResult]],
        host: str = "0.0.0.0",
        port: int = 8080,
        binary_location: str = "/home/amazon/ElasticGumbyAgenticMCP/bin/eg_agentic_mcp_server",
        storage_dir: str = "/tmp/orchestrator_agent",
        auto_transition_job_to_executing: bool = True,
        tracing: Optional[str] = None,
    ):
        """
        Initialize the Stateless Agent Runtime Server.

        Args:
            agent_factory: Factory function for creating custom agents (required)
            host: Server host address (default: "0.0.0.0")
            port: Server port (default: 8080)
            binary_location: Path to the MCP binary for tool integration
            storage_dir: Directory for agent data storage
            auto_transition_job_to_executing: Automatically transition job from ASSESSING to EXECUTING on agent initialization (default: True)
            tracing: Type of tracing to use (optional)
        """
        self.stop_requested = False
        self.agent_factory = agent_factory
        self.host = host
        self.port = port
        self.binary_location = binary_location
        self.storage_dir = storage_dir
        self.auto_transition_job_to_executing = auto_transition_job_to_executing

        # Agent state
        self.agent: Optional[AnyBaseAgent[str, AgentResult]] = None
        self.initialized = False
        self._initialization_lock = asyncio.Lock()
        self.context: Optional[AgentRuntimeContext] = None

        # Set timeouts
        self._timeout = 28
        self._delayed_timeout = 60 * 5

        # Initialize components
        self.notification_handler = None  # TODO: add non-queue notification handler
        self.task_handler = TaskHandler()
        self.message_handler: Optional[MessageHandler] = None

        # Create FastAPI app with lifespan
        self.app = FastAPI(
            title="ATX AgentCore Compatible Stateless Agent Server", lifespan=self._lifespan
        )
        self.app.add_middleware(RequestContextMiddleware)
        self.setup_common_routes()

        # Setup tracing
        if tracing:
            self.setup_tracing(tracing)

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

        async with self._initialization_lock:
            if self.initialized:
                logger.info("Agent finished initialization during waiting the lock")
                return

            # 3. check agent status
            try:
                agent_status = get_agent_status(
                    self.context.workspace_id, self.context.job_id, self.context.agent_instance_id
                )
                if agent_status == "INVOKING":
                    asyncio.create_task(self._wait_for_non_invoking_and_initialize())
                    return
                else:
                    logger.info(f"Agent status is {agent_status}, finalizing agent setup")
                    await self._finalize_agent_setup(agent_status)
                    return
            except Exception as e:
                logger.warning(f"Cannot initializate agent with exception: {e}")

    async def _wait_for_non_invoking_and_initialize(self) -> None:
        """Wait for agent status to exit INVOKING state, then complete initialization."""

        assert self.context

        final_status = await wait_for_agent_non_invoking(
            self.context.workspace_id, self.context.job_id, self.context.agent_instance_id
        )
        if final_status != "INVOKING":
            await self._finalize_agent_setup(final_status)

    async def _finalize_agent_setup(self, agent_status: str = "RUNNING") -> None:
        assert self.context

        agentic_api_endpoint = build_agentic_api_endpoint_from_env()

        required_mcp_args: Dict[str, str] = {
            "binaryLocation": self.binary_location,
            "workspaceId": self.context.workspace_id,
            "jobId": self.context.job_id,
            "agentInstanceId": self.context.agent_instance_id,
            "agenticApiEndpoint": agentic_api_endpoint,
            "authTokenFile": get_default_auth_token_file_path(),
        }

        try:
            # Set up MCP client
            mcp_client = MCPClientFactory.setup_ab_mcp_client(required_mcp_args)
            if not mcp_client:
                logger.error("Failed to create MCP client")
                raise ValueError("MCP client initialization failed")

            # Use agent factory to create agent
            # Check if agent_factory can accept kwargs for backward compatibility
            def accepts_kwargs(func):
                sig = inspect.signature(func)
                return any(
                    param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
                )

            # Create a dictionary of all potential parameters
            agent_params = {
                "workspace_id": self.context.workspace_id,
                "job_id": self.context.job_id,
                "agent_instance_id": self.context.agent_instance_id,
            }

            if accepts_kwargs(self.agent_factory):
                # If agent_factory has **kwargs, pass all parameters
                self.agent = self.agent_factory(mcp_client, self.storage_dir, **agent_params)
            else:
                # Fall back to original signature for backward compatibility
                self.agent = self.agent_factory(mcp_client, self.storage_dir)

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

            # Set up message handler
            logger.info("Initializing message handler...")
            self.message_handler = MessageHandler(
                agent=self.agent, timeout=self._timeout, delayed_timeout=self._delayed_timeout
            )

            # Set agent to running
            if agent_status == "INVOKED":
                set_agent_running(
                    self.context.workspace_id, self.context.job_id, self.context.agent_instance_id
                )
            self.initialized = True
            logger.info("Agent initialization completed successfully")

        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            raise

    async def handle_mde_notification(self, request: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Received notification request - implementing as no-op")
        return {"status": "acknowledged"}

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """FastAPI lifespan for graceful startup (no cleanup needed for stateless)."""
        await self._startup()
        yield

    async def _startup(self) -> None:
        """Unified startup logic."""
        logger.info("Starting up Agent Runtime Server...")

        # Initialize agent if environment is available (MDE mode)
        if has_mde_environment():
            logger.info("MDE mode: Initializing agent from environment...")
            await self._initialize_mde_mode()
        else:
            logger.info("AgentCore mode: Agent will be initialized on first request")

    def start(self) -> None:
        """
        Start the Stateless Agent Runtime Server with FastAPI

        Initializes the message handler and starts the FastAPI server with uvicorn. Supports only sync
        request processing modes.
        """
        logger.info(f"Starting Stateless AgentCore server on {self.host}:{self.port}")

        # Start HTTP server
        uvicorn.run(self.app, host=self.host, port=self.port)
