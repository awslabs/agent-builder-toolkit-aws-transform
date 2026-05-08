# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Enhanced orchestrator with multi-source conversation support.

This module provides an enhanced orchestrator that can handle messages from different sources
(human users, subagents, notifications) and selectively include relevant conversation history
based on the message context and relationships between entities.
"""

import asyncio
import logging
import os
import sys
from enum import Enum
from multiprocessing import Process
from typing import Any, Dict, List, Optional

from strands.hooks import HookProvider
from strands.tools.mcp import MCPClient

from agent_builder_sdk._auth_token_refresher import (
    get_auth_token_refresher,
    get_default_auth_token_file_path,
)
from agent_builder_sdk.agentic_framework.agent_lifecycle import initialize_agent_instance
from agent_builder_sdk.cli import (
    cleanup_process_safely,
    run_api_server_sync,
    run_queue_mode_async,
    setup_ab_mcp_client,
    setup_tracing,
)
from agent_builder_sdk.env_var import (
    ENV_KEY_AGENT_INSTANCE_ID,
    ENV_KEY_AWS_REGION,
    ENV_KEY_JOB_ID,
    ENV_KEY_QT_AGENTIC_API_ENDPOINT,
    ENV_KEY_WORKSPACE_ID,
    validate_required_env_vars,
)
from agent_builder_sdk.memory.episodic_memory import EpisodicMemory
from agent_builder_sdk.memory.file_memory_repository import FileSystemRepository
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.message_queue import QueueService
from agent_builder_sdk.orchestrator_strands.base_orchestrator import BaseOrchestrator
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import EvaluationCard
from agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider import (
    ConversationHookProvider,
)
from agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider import (
    MemoryHookProvider,
)
from agent_builder_sdk.orchestrator_strands.tools.memory_tool import MemoryTool
from agent_builder_sdk.request_handler import QueueRequestHandler

logger = logging.getLogger(__name__)


class PlatformFunctions(Enum):
    JOB_PLAN = "job_plan"
    WORKLOG = "worklog"
    ARTIFACT = "artifact"
    HITL = "hitl"


class AgentConfiguration(Enum):
    AWS_REGION = "aws_region"
    WORKSPACE_ID = "workspace_id"
    JOB_ID = "job_id"
    AGENT_INSTANCE_ID = "agent_instance_id"
    STORAGE_DIR = "storage_dir"
    WORKING_DIR = "working_dir"
    QUEUE_STORAGE_DIR = "queue_storage_path"
    TRACE_URL = "trace_url"
    AGENTIC_API_ENDPOINT = "agentic_api_endpoint"
    AUTH_TOKEN_REFRESH_DURATION = "auth_token_refresh_duration"
    PLATFORM_MCP_BINARY_LOCATION = "platform_mcp_binary_location"
    AUTO_ATX_AGENT_LIFECYCLE_UPDATES = "auto_atx_agent_lifecycle_updates"
    AUTO_PLATFORM_MCP_SUPPORT = "auto_platform_mcp_support"


class BaseAgentServer:
    """
    ATX Strands Agent Server with all the required bells and whistles.

    TODO: Decoupling Agent from AgentServer will come soon once
    we consolidate BaseOrchestrator and BaseSubAgent initialization.

    This class provides an easy way to instantiate a new ATX strands-based agent (see BaseOrchestrator),
    fronted by a webserver through which requests to this agent are processed asynchronously.

    Key features:
    - BaseOrchestrator features (see BaseOrchestrator class)
    - WebServer to receive incoming requests (SendMessage, Notification and Healthcheck)
    - QueueService to process incoming requests asynchronously

    Sample Initialization:
        base_agent = BaseAgentServer(
        system_prompt=SYSTEM_PROMPT,
        custom_tools=[
            # file_read,
            # file_write,
            self.discover_repositories,
            self.discover_databases,
            self.assess_database,
            self.assess_repository,
            self.generate_wave_plan,
        ],
        model_id=DEFAULT_MODEL_ID,
        agent_evaluation_card=agent_eval_card,
        agent_config_override={
            AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value: False,
            AgentConfiguration.AUTO_ATX_AGENT_LIFECYCLE_UPDATES.value: False,
        }

    """

    def __init__(
        self,
        system_prompt: str,
        custom_tools: Optional[List[Any]] = None,
        custom_mcp_clients: Optional[List[MCPClient]] = None,
        agent_lifecycle_hooks: Optional[List[HookProvider]] = None,
        model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
        agent_evaluation_card: Optional[EvaluationCard] = None,
        agent_config_override: Dict[str, Any] = {},
    ):
        """
        Initialize the orchestrator with explicit configuration.

        Args:
            system_prompt: System prompt that defines the agent's behavior and capabilities
            custom_tools: List of tool objects to make available to the agent
            custom_mcp_clients: List of mcp clients to make available to the agent
            agent_lifecycle_hooks: List of hook providers (see Strands SDK documentation)
            model_id: Bedrock model identifier to use for the agent
            agent_evaluation_card: Evaluation configuration, used to run evaluation at the end of each agent execution.
            agent_config_override: List of overrides for agent configuration (uses default values otherwise)
        """
        # Store configuration
        self.system_prompt = system_prompt
        self.custom_tools = custom_tools or []
        self.custom_mcp_clients = custom_mcp_clients or []
        self.agent_lifecycle_hooks = agent_lifecycle_hooks
        self.model_id = model_id
        self.agent_evaluation_card = agent_evaluation_card

        # Validate required environment variables
        logger.info("Validating environment variables")
        validate_required_env_vars()

        # Setup agent configuration overrides
        logger.info("Setting up agent configuration")
        self.agent_config: Dict[str, Any] = self._setup_agent_configuration(agent_config_override)

        # Setup auto token refresher
        logger.info("Setting up auto token refresher")
        self._setup_auto_token_refresher()

        try:
            # Update ATX agent lifecycle
            if self.agent_config[AgentConfiguration.AUTO_ATX_AGENT_LIFECYCLE_UPDATES.value]:
                logger.info("Updating ATX agent lifecycle")
                initialize_agent_instance()
        except Exception as e:
            logger.error(f"Failed to update ATX agent lifecycle: {e}")
            sys.exit(1)

        # Setup tracing
        logger.info("Setting up tracing")
        self._setup_tracing("local")

        # Setup Queue Service
        logger.info("Setting up Queue service for queuing up incoming agent requests")
        self.queue_service = QueueService(storage_path=AgentConfiguration.STORAGE_DIR.value)
        self.request_handler = QueueRequestHandler(
            request_queue=self.queue_service.request_queue,
            response_store=self.queue_service.response_store,
        )

        try:
            # Create the Agent
            logger.info("Setting up the base agent")
            self.agent = self._setup_base_agent()
        except Exception as e:
            logger.error(f"Failed to setup base agent: {e}")
            sys.exit(1)

        # Setup Agent Server
        try:
            logger.info("Starting Agent Server")
            self._start_api_server()
        except Exception as e:
            logger.error(f"Failed to setup API server: {e}")
            sys.exit(1)

    def start(self):
        # Start processing requests
        logger.info("Starting thread to process agent requests")
        asyncio.run(self._process_requests())

    @staticmethod
    def _setup_agent_configuration(agent_config_override):
        """
        Sets up agent configuration from env variables, overriding if necessary

        Args:
            agent_config_override: list of config to override

        Returns:
            agent_config (Dict): A dictionary of agent configuration with keys corresponding to AgentConfiguration
        """
        agent_config: Dict[str, Any] = {
            AgentConfiguration.AWS_REGION.value: os.getenv(ENV_KEY_AWS_REGION),
            AgentConfiguration.WORKSPACE_ID.value: os.getenv(ENV_KEY_WORKSPACE_ID),
            AgentConfiguration.JOB_ID.value: os.getenv(ENV_KEY_JOB_ID),
            AgentConfiguration.AGENT_INSTANCE_ID.value: os.getenv(ENV_KEY_AGENT_INSTANCE_ID),
            AgentConfiguration.STORAGE_DIR.value: ".",
            AgentConfiguration.WORKING_DIR.value: ".",
            AgentConfiguration.QUEUE_STORAGE_DIR.value: "/tmp/agent_queue",
            AgentConfiguration.TRACE_URL.value: "http://localhost:4318",
            AgentConfiguration.AGENTIC_API_ENDPOINT.value: os.getenv(
                ENV_KEY_QT_AGENTIC_API_ENDPOINT
            ),
            AgentConfiguration.AUTH_TOKEN_REFRESH_DURATION.value: 43200,
            AgentConfiguration.PLATFORM_MCP_BINARY_LOCATION.value: "/opt/amazon/eg_agentic_mcp_server",
            AgentConfiguration.AUTO_ATX_AGENT_LIFECYCLE_UPDATES.value: False,
            AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value: False,
        }
        if agent_config_override:
            for key, value in agent_config_override.items():
                agent_config[key] = value

        os.environ["TMPDIR"] = agent_config[AgentConfiguration.WORKING_DIR.value]

        logger.info(f"Configured agent_config: {agent_config}")
        return agent_config

    def _setup_auto_token_refresher(self):
        """
        Initialize auth-token refresher so auto-token would be immediately available for boto client and MCP

        Args: None

        Returns: None
        """
        refresh_duration = self.agent_config[AgentConfiguration.AUTH_TOKEN_REFRESH_DURATION.value]
        logger.info(
            f"Starting auto-token refresher with session duration: {refresh_duration} seconds"
        )
        get_auth_token_refresher(session_duration=refresh_duration)

    @staticmethod
    def _setup_tracing(tracing_type: str):
        setup_tracing(tracing_type)

    def _setup_platform_mcp(self) -> MCPClient:
        """
        Set up platform MCP client for use by the strands agent.

        Args: None

        Returns:
            Connected Strands MCP client
        """
        mcp_args: Dict[str, str] = {
            "binaryLocation": self.agent_config[
                AgentConfiguration.PLATFORM_MCP_BINARY_LOCATION.value
            ],
            "workspaceId": self.agent_config[AgentConfiguration.WORKSPACE_ID.value],
            "jobId": self.agent_config[AgentConfiguration.JOB_ID.value],
            "agentInstanceId": self.agent_config[AgentConfiguration.AGENT_INSTANCE_ID.value],
            "agenticApiEndpoint": self.agent_config[AgentConfiguration.AGENTIC_API_ENDPOINT.value],
            "authTokenFile": get_default_auth_token_file_path(),
        }
        logger.info(f"Setting up Platform MCP client with args: {mcp_args}")
        return setup_ab_mcp_client(mcp_args=mcp_args)

    def _setup_base_agent(self) -> BaseOrchestrator:
        """
        Setup the base strands agent with config. Setup MCP clients, tools, hooks
        and initialize the strands agent with them.

        Args: None

        Returns:
            Configured agent
        """
        # Setup Platform MCP
        self.mcp_client = None
        if self.agent_config[AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value]:
            self.mcp_client = self._setup_platform_mcp()

        # Create memory tools
        logger.info("Creating memory tools")
        repository = FileSystemRepository(
            storage_path=os.path.join(
                self.agent_config[AgentConfiguration.STORAGE_DIR.value], "memories"
            )
        )
        memory_manager = MemoryManager(memories=[EpisodicMemory(repository=repository)])
        memory_tool = MemoryTool(memory_manager)
        memory_tools = [memory_tool.memory]

        # Create conversation repository
        conversation_repository = FileMultiSourceConversationRepository(
            storage_dir=self.agent_config[AgentConfiguration.STORAGE_DIR.value]
        )

        # Create hooks
        logger.info("Creating agent hooks")
        hooks = [
            ConversationHookProvider(repository=conversation_repository),
            MemoryHookProvider(memory_manager=memory_manager),
        ]

        # Create base agent
        base_agent = BaseOrchestrator(
            system_prompt=self.system_prompt,
            custom_tools=memory_tools + self.custom_tools,
            mcp_clients=[self.mcp_client] if self.mcp_client is not None else None,
            hooks=hooks,
            region_name=self.agent_config[AgentConfiguration.AWS_REGION.value],
            model_id=self.model_id,
            evaluation_card=self.agent_evaluation_card,
        )

        return base_agent

    def _start_api_server(self):
        """
        Run the API server (synchronous entry point for multiprocessing).

        Args: None

        """
        self.api_process = Process(
            target=run_api_server_sync,
            args=[None, self.queue_service],
            name="APIServer",
            daemon=False,
        )
        self.api_process.start()
        logger.info(f"API server started with PID: {self.api_process.pid}")

    async def _process_requests(self):
        """
        Async method to process incoming requests (queued by api server).

        Args: None

        """
        try:
            logger.info("Starting Message Processor...")
            await run_queue_mode_async(self.agent, self.queue_service, self.request_handler)
        finally:
            await self.queue_service.stop()
            # Clean up API process if it was started
            if self.api_process:
                cleanup_process_safely(self.api_process, "APIServer")
