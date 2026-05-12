#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Simple command-line interface for the BaseOrchestrator Agent.

⚠️  DEPRECATED: This CLI is deprecated and will be removed in a future version.
    Please use AgentRuntimeServer instead for new implementations.
    Example: src/agent_builder_sdk/entrypoints/simple_cli_agent_core.py
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from multiprocessing import Process
from typing import Any, Dict, Optional, Tuple

from mcp import StdioServerParameters, stdio_client
from strands.telemetry import StrandsTelemetry
from strands.tools.mcp import MCPClient
from typing_extensions import deprecated

from agent_builder_sdk._auth_token_refresher import get_auth_token_refresher
from agent_builder_sdk.agentic_framework.agent_lifecycle import initialize_agent_instance
from agent_builder_sdk.checkpoint.checkpoint_manager import (
    BackgroundCheckpointer,
    CheckpointManager,
)
from agent_builder_sdk.checkpoint.checkpoint_repository import create_checkpoint_repository
from agent_builder_sdk.checkpoint.checkpoint_triggers import (
    ConversationTurnTrigger,
    TimeBasedTrigger,
)
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.env_var import (
    ENV_KEY_DISABLE_MCP_USAGE_FLAG,
    ENV_KEY_DISABLE_PROD_BEDROCK_CAPACITY_FLAG,
)
from agent_builder_sdk.fastapi_server import start_api_server
from agent_builder_sdk.memory.episodic_memory import EpisodicMemory
from agent_builder_sdk.memory.file_memory_repository import FileSystemRepository
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.message_queue import QueueService
from agent_builder_sdk.orchestrator_strands.base_orchestrator import BaseOrchestrator
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
from agent_builder_sdk.request_handler import QueueRequestHandler
from agent_builder_sdk.utils import (
    build_agentic_api_endpoint_from_env,
    cleanup_process_safely,
    extract_text_from_strands_agent_response,
    get_default_auth_token_file_path,
    get_prompt_with_name,
)

logger = logging.getLogger(__name__)


@deprecated(
    "Use AgentRuntimeServer instead for new implementations. See /entrypoints/simple_cli_agent_core.py for an example"
)
def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description="Run BaseOrchestrator Agent in console mode")

    parser.add_argument(
        "--binaryLocation",
        help="Filepath to the location of the agentic MCP server binary",
        default="/home/amazon/AgentBuilderAgenticMCP/bin/agent-builder-agentic-mcp",
    )

    parser.add_argument(
        "--model_id",
        default="anthropic.claude-sonnet-4-5-20250929-v1:0",
        help="Bedrock model ID to use",
    )

    parser.add_argument(
        "--region", default=os.getenv("AWS_REGION", "us-west-2"), help="AWS region for Bedrock"
    )
    parser.add_argument(
        "--storage-dir", default="/ramdisk/orchestrator_agent", help="Storage directory"
    )

    parser.add_argument(
        "--localTesting",
        action="store_true",
        help="Run in local testing mode (console input instead of queue event_loop)",
    )

    parser.add_argument(
        "--new_aws_data_path",
        help="Path to add to AWS_DATA_PATH environment variable",
        default="/home/amazon/.aws/models",
    )

    parser.add_argument(
        "--queueStoragePath",
        help="Path to store request queue and response data",
        default="/tmp/agent_queue",
    )

    parser.add_argument(
        "--args",
        help="Command arguments as a space-separated string",
    )
    parser.add_argument(
        "--agenticApiEndpoint",
        help="Endpoint for the Agentic API",
        default=os.getenv("QT_AGENTIC_API_ENDPOINT"),
    )
    parser.add_argument(
        "--workspaceId", help="Id of the workspace", default=os.getenv("WORKSPACE_ID")
    )
    parser.add_argument("--jobId", help="Id of the job", default=os.getenv("JOB_ID"))
    parser.add_argument(
        "--agentInstanceId", help="Agent Instance Id", default=os.getenv("AGENT_INSTANCE_ID")
    )
    parser.add_argument("--workingDir", help="Working directory", default=os.getenv("/ramdisk"))

    parser.add_argument(
        "--authTokenRefreshSessionDuration",
        type=int,
        default=43200,
        help="Duration in seconds for the auth token session (300-43200 seconds, default: 43200)",
    )

    parser.add_argument(
        "--disableAgentLifecycle",
        action="store_true",
        help="Disable agent lifecycle management (skip initialization and shutdown communication to AgenticApi)",
    )

    parser.add_argument(
        "--disableProdBedrockUsage",
        action="store_true",
        help="Disable prod Bedrock capacity usage",
    )

    parser.add_argument(
        "--disableMcpUsage",
        action="store_true",
        help="Disable MCP usage",
    )

    parser.add_argument(
        "--tracing",
        default=None,
        help="Enable tracing. Use 'local' for Jaeger or 'cloudwatch' for AWS X-Ray (both use http://localhost:4318)",
    )

    parser.add_argument(
        "--guardrail_id",
        help="Bedrock guardrail ID for content filtering and automated reasoning",
        default=os.getenv("BEDROCK_GUARDRAIL_ID"),
    )

    parser.add_argument(
        "--guardrail_version",
        default=os.getenv("BEDROCK_GUARDRAIL_VERSION", "1"),
        help="Bedrock guardrail version (default: 1)",
    )

    # Checkpointing configuration
    checkpoint_group = parser.add_argument_group(
        "checkpointing", "Background checkpointing options"
    )
    checkpoint_group.add_argument(
        "--checkpoint-strategy",
        choices=["time", "conversation"],
        help="Checkpointing strategy. If not specified, checkpointing is disabled.",
    )
    checkpoint_group.add_argument(
        "--checkpoint-interval",
        type=int,
        default=30,
        help="Checkpoint interval: minutes for time strategy, turns for conversation strategy (default: 30)",
    )
    checkpoint_group.add_argument(
        "--checkpoint-dir",
        default="/ramdisk/orchestrator_agent",
        help="Directory for checkpoint storage (default: /ramdisk/orchestrator_agent)",
    )

    return parser


def setup_tracing(tracing_type: str):
    """Setup tracing based on tracing type configuration."""
    tracing_endpoint = "http://localhost:4318"

    if tracing_type == "cloudwatch":
        logger.info(f"Setting up CloudWatch X-Ray tracing via AWS collector at: {tracing_endpoint}")
    else:
        logger.info(f"Setting up local Jaeger tracing at: {tracing_endpoint}")

    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = tracing_endpoint

    strands_telemetry = StrandsTelemetry()
    strands_telemetry.setup_otlp_exporter()
    strands_telemetry.setup_console_exporter()
    logger.info(f"{tracing_type} tracing configured for endpoint")


def setup_ab_mcp_client(mcp_args: Dict[str, str]) -> MCPClient:
    """
    Set up and connect the MCP client using Strands framework.

    Args:
        mcp_args: Parsed command line arguments

    Returns:
        Connected Strands MCP client
    """
    try:
        command_args = [
            item
            for key, value in mcp_args.items()
            for item in [f"--{key}", str(value)]
            if key != "binaryLocation"
        ]

        logger.info("Creating Strands MCP client")
        binary_location = mcp_args["binaryLocation"]
        logger.info(f"MCP command: {binary_location}, args: {command_args}")

        mcp_client = MCPClient(
            lambda: stdio_client(
                StdioServerParameters(
                    command=mcp_args["binaryLocation"], args=command_args, env=os.environ.copy()
                )
            )
        )

        return mcp_client
    except Exception as e:
        logger.exception("Failed to create MCP client due to")
        raise e


def create_orchestrator(args, mcp_client: Optional[MCPClient]) -> BaseOrchestrator:
    """
    Create and configure the orchestrator agent.

    Args:
        args: Parsed command line arguments
        mcp_client: Connected MCP client, or None if MCP is disabled

    Returns:
        Configured orchestrator agent
    """

    custom_tools: list[Any] = []

    # Create memory components
    memory_storage_path = os.path.join(args.storage_dir, "memories")
    repository = FileSystemRepository(storage_path=memory_storage_path)
    episodic_memory = EpisodicMemory(repository=repository)
    memory_manager = MemoryManager(memories=[episodic_memory])

    # Create memory tool
    memory_tool = MemoryTool(memory_manager)
    custom_tools.append(memory_tool.memory)

    # Create subagent discovery tool
    subagent_registry_tools = SubagentRegistryTools()
    custom_tools.append(subagent_registry_tools.discover_subagents)

    # Create send message to subagent tool
    send_message_tools = SendMessageTools()
    custom_tools.append(send_message_tools.send_message_to_subagent)

    # Create conversation repository
    conversation_repository = FileMultiSourceConversationRepository(storage_dir=args.storage_dir)

    # Create hooks
    hooks = [
        ConversationHookProvider(repository=conversation_repository),
        MemoryHookProvider(memory_manager=memory_manager),
    ]

    # Create orchestrator with explicit hooks
    orchestrator = BaseOrchestrator(
        system_prompt=get_prompt_with_name("test_orchestrator_prompt"),
        hooks=hooks,
        model_id=args.model_id,
        guardrail_id=args.guardrail_id,
        guardrail_version=args.guardrail_version,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=args.region,
        custom_tools=custom_tools,
    )

    return orchestrator


def setup_agent(
    args, mcp_args: Dict[str, str]
) -> Tuple[BaseOrchestrator, QueueService, QueueRequestHandler]:
    """
    Set up and configure the orchestrator agent.

    Args:
        args: Parsed command line arguments
        mcp_args: Parsed command line arguments for the mcp client

    Returns:
        Tuple of (agent, queue_service, request_handler)
    """
    logger.info("Setting up Orchestrator Agent...")

    if os.getenv(ENV_KEY_DISABLE_MCP_USAGE_FLAG):
        logging.info("Skipping setting mcp client")
        mcp_client = None
    else:
        mcp_client = setup_ab_mcp_client(mcp_args)

    logger.info("Initializing queue service...")
    queue_service = QueueService(storage_path=args.queueStoragePath)

    request_handler = QueueRequestHandler(
        request_queue=queue_service.request_queue, response_store=queue_service.response_store
    )

    agent = create_orchestrator(args, mcp_client)

    logger.info("Agent setup completed successfully")
    return agent, queue_service, request_handler


async def run_console(orchestrator: BaseOrchestrator):
    """
    Run the agent in interactive console mode.

    Args:
        orchestrator: Configured orchestrator agent
    """
    print("BaseOrchestrator Agent - Console Mode")
    print("\nCommands:")
    print("  exit     - Quit the application")
    print(f"{'=' * 60}\n")

    while True:
        try:
            user_input = input("You: ")

            if user_input.lower() == "exit":
                break
            elif not user_input:
                continue
            response = orchestrator.process_message(
                ProcessMessageRequest(
                    message=user_input,
                    context=ConversationContext(user_id="tester"),
                )
            )
            print(f"\nAgent Response: {response.message}")
        except KeyboardInterrupt:
            print("\nExiting...")
        except Exception as e:
            logger.error(f"Error event_loop message: {e}")
            print(f"\nError: {str(e)}")


async def run_queue_mode(
    orchestrator: BaseOrchestrator,
    queue_service: QueueService,
    request_handler: QueueRequestHandler,
    background_checkpointer=None,
):
    """
    Run the orchestrator in queue processing mode.

    Args:
        orchestrator: Configured orchestrator agent
        queue_service: Queue service for request management
        request_handler: Queue message processor
        background_checkpointer: Background checkpointer
    """
    logger.info("Running in queue processing mode")

    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start queue service
    await queue_service.start()
    logger.info("Queue service started...")

    try:
        # Main processing loop
        while not shutdown_event.is_set():
            try:
                # Receive message from queue (with timeout to allow checking shutdown)
                message_data = await request_handler.receive_request()
                if message_data is None:
                    # No message available, continue loop
                    continue

                logger.info(f"Processing request {message_data['request_id']}")

                request = ProcessMessageRequest(message_data["message"], message_data["context"])

                # Process the message
                try:
                    result = orchestrator.process_message(request)

                    # Extract text from the response structure
                    extracted_text = extract_text_from_strands_agent_response(result)

                    # Store response
                    await request_handler.store_response(extracted_text)

                    # Increment conversation turn for checkpointing
                    if background_checkpointer:
                        background_checkpointer.increment_conversation_turn()

                except asyncio.TimeoutError:
                    logger.warning("Request processing timed out")
                    await request_handler.handle_request_timeout()

                except Exception as e:
                    logger.error(f"Error processing request {message_data['request_id']}: {e}")
                    await request_handler.handle_request_error(e)

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(1)  # Brief pause before continuing

    finally:
        # Cleanup
        logger.info("Shutting down queue processing...")
        await queue_service.stop()


async def run_queue_mode_async(
    orchestrator: BaseOrchestrator,
    queue_service: QueueService,
    request_handler: QueueRequestHandler,
    background_checkpointer=None,
):
    """
    Run the orchestrator in queue processing mode (async version that reuses existing objects).

    Args:
        orchestrator: Already configured orchestrator agent
        queue_service: Already initialized queue service
        request_handler: Already initialized message processor
        background_checkpointer: Background checkpointer
    """
    logger.info("Starting queue mode with existing agent and services...")

    try:
        # Run queue mode with the existing objects
        await run_queue_mode(orchestrator, queue_service, request_handler, background_checkpointer)
    except KeyboardInterrupt:
        logger.info("Queue mode interrupted")
    except Exception as e:
        logger.error(f"Queue mode failed: {e}")
        raise


def run_api_server_sync(args, queue_service: QueueService):
    """
    Run the API server (synchronous entry point for multiprocessing).

    Args:
        args: Parsed command line arguments
    """
    logger.info("Starting API server process...")

    try:
        start_api_server(queue_service)
    except KeyboardInterrupt:
        logger.info("API server process interrupted")
    except Exception as e:
        logger.error(f"API server process failed: {e}")
        raise


def create_checkpoint_trigger(strategy: str, interval: int):
    """Create checkpoint trigger based on strategy."""
    if strategy == "time":
        return TimeBasedTrigger(interval_minutes=interval)
    elif strategy == "conversation":
        return ConversationTurnTrigger(turn_threshold=interval)
    else:
        raise ValueError(f"Unknown checkpoint strategy: {strategy}")


def initialize_background_checkpointer(args) -> Optional[BackgroundCheckpointer]:
    """Initialize background checkpointer from CLI arguments."""
    if not args.checkpoint_strategy:
        logger.info("Background checkpointing disabled (no strategy specified)")
        return None

    try:
        checkpoint_repository = create_checkpoint_repository(args.checkpoint_dir)

        # Restore the last checkpoint if available
        checkpoint_repository.restore_if_available()

        trigger = create_checkpoint_trigger(args.checkpoint_strategy, args.checkpoint_interval)
        manager = CheckpointManager(checkpoint_repository, trigger)
        background_checkpointer = BackgroundCheckpointer(manager)
        background_checkpointer.enable()
        logger.info(
            f"Background checkpointing enabled with {args.checkpoint_strategy} strategy (interval: {args.checkpoint_interval}, location: {args.checkpoint_dir})"
        )
        return background_checkpointer
    except Exception as e:
        logger.warning(
            f"Failed to initialize checkpointing: {e}. Agent will proceed without checkpointing."
        )
        return None


@deprecated(
    "Use AgentRuntimeServer instead for new implementations. See /entrypoints/simple_cli_agent_core.py for an example"
)
async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Initialize auth-token refresher so auto-token would be immediately available for boto client and MCP
    logging.info(
        f"Starting auto-token refresher with session duration: {args.authTokenRefreshSessionDuration} seconds"
    )
    get_auth_token_refresher(session_duration=args.authTokenRefreshSessionDuration)

    # Initialize the orchestrator agent instance
    if args.disableAgentLifecycle:
        logger.info("Agent lifecycle management disabled")
    else:
        try:
            initialize_agent_instance()
            logger.info("Base orchestrator instance initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize base orchestrator instance: {e}")
            sys.exit(1)

    # Initialize checkpointing
    background_checkpointer = initialize_background_checkpointer(args)

    current_aws_data_path = os.environ.get("AWS_DATA_PATH", "")
    if current_aws_data_path:
        os.environ["AWS_DATA_PATH"] = f"{current_aws_data_path}{os.pathsep}{args.new_aws_data_path}"
    else:
        os.environ["AWS_DATA_PATH"] = args.new_aws_data_path

    if args.disableProdBedrockUsage:
        logging.info("Disable prod bedrock usage is set to true ")
        os.environ[ENV_KEY_DISABLE_PROD_BEDROCK_CAPACITY_FLAG] = "true"

    if args.disableMcpUsage:
        logging.info("Disable MCP usage is set to true")
        os.environ[ENV_KEY_DISABLE_MCP_USAGE_FLAG] = "true"

    agentic_api_endpoint = (
        args.agenticApiEndpoint
        if args.agenticApiEndpoint is not None
        else build_agentic_api_endpoint_from_env()
    )

    required_mcp_args: Dict[str, str] = {
        "binaryLocation": args.binaryLocation,
        "workspaceId": args.workspaceId,
        "jobId": args.jobId,
        "agentInstanceId": args.agentInstanceId,
        "agenticApiEndpoint": agentic_api_endpoint,
        "authTokenFile": get_default_auth_token_file_path(),
    }

    try:
        # Setup tracing
        if args.tracing is not None:
            setup_tracing(args.tracing)

        # Set up the agent and all components
        orchestrator, queue_service, request_handler = setup_agent(args, required_mcp_args)
        if args.localTesting:
            await run_console(orchestrator)
        else:
            api_process = Process(
                target=run_api_server_sync,
                args=[args, queue_service],
                name="APIServer",
                daemon=False,
            )
            api_process.start()
            logger.info(f"API server started with PID: {api_process.pid}")

            try:
                logger.info("Starting Message Processor in Queue Mode...")
                # Run queue mode in the main process with existing objects
                await run_queue_mode_async(
                    orchestrator, queue_service, request_handler, background_checkpointer
                )
            finally:
                # Graceful shutdown of background checkpointer
                if background_checkpointer:
                    logger.info("Shutting down background checkpointer...")
                    await background_checkpointer.shutdown()

                await queue_service.stop()
                # Clean up API process if it was started
                if api_process:
                    cleanup_process_safely(api_process, "APIServer")
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)


@deprecated(
    "Use AgentRuntimeServer instead for new implementations. See /entrypoints/simple_cli_agent_core.py for an example"
)
def run_main():
    """Entry point wrapper that handles the event loop and process orchestration."""
    logger.debug("Beginning application startup")

    try:
        # Run the main application (which now handles both setup and queue processing)
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application failed with error: {e}")
        raise


if __name__ == "__main__":
    run_main()
