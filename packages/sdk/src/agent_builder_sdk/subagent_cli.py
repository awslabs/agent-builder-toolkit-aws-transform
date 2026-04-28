#!/usr/bin/env python3
"""
Simple command-line interface for the Base Subagent.

⚠️  DEPRECATED: This CLI is deprecated and will be removed in a future version.
    Please use simple_subagent_cli.py instead for new implementations.
    See: src/agent_builder_sdk/entrypoints/simple_subagent_cli.py
"""
import argparse
import asyncio
import logging
import os
import sys
from multiprocessing import Process
from typing import Dict

from typing_extensions import deprecated

from agent_builder_sdk._auth_token_refresher import get_auth_token_refresher
from agent_builder_sdk.agentic_framework.agent_lifecycle import initialize_agent_instance
from agent_builder_sdk.base_subagent.base_subagent import BaseSubagent
from agent_builder_sdk.cli import setup_eg_mcp_client
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.env_var import ENV_KEY_DISABLE_MCP_USAGE_FLAG
from agent_builder_sdk.subagent_server import start_subagent_api_server
from agent_builder_sdk.utils import build_mcp_args_from_parsed_args, cleanup_process_safely

logger = logging.getLogger(__name__)


@deprecated(
    "Use simple_subagent_cli.py or simple_stateless_agent_core.py instead for new implementations"
)
def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description="Run Base Subagent in console mode")

    parser.add_argument(
        "--binary-location",
        help="Filepath to the location of the agentic MCP server binary",
        default="/home/amazon/ElasticGumbyAgenticMCP/bin/eg_agentic_mcp_server",
    )

    parser.add_argument(
        "--model-id",
        default="anthropic.claude-sonnet-4-5-20250929-v1:0",
        help="Bedrock model ID to use",
    )

    parser.add_argument(
        "--region", default=os.getenv("AWS_REGION", "us-west-2"), help="AWS region for Bedrock"
    )

    parser.add_argument(
        "--new-aws-data-path",
        help="Path to add to AWS_DATA_PATH environment variable",
        default="/home/amazon/.aws/models",
    )

    parser.add_argument(
        "--agentic-api-endpoint",
        help="Endpoint for the Agentic API",
        default=os.getenv("QT_AGENTIC_API_ENDPOINT"),
    )
    parser.add_argument(
        "--workspace-id", help="Id of the workspace", default=os.getenv("WORKSPACE_ID")
    )
    parser.add_argument("--job-id", help="Id of the job", default=os.getenv("JOB_ID"))
    parser.add_argument(
        "--agent-instance-id", help="Agent Instance Id", default=os.getenv("AGENT_INSTANCE_ID")
    )

    parser.add_argument(
        "--local-testing",
        action="store_true",
        help="Run in local testing mode (console input instead of queue event_loop)",
    )

    parser.add_argument(
        "--guardrail-id",
        help="Bedrock guardrail ID for content filtering",
        default=os.getenv("BEDROCK_GUARDRAIL_ID"),
    )

    parser.add_argument(
        "--guardrail-version",
        default=os.getenv("BEDROCK_GUARDRAIL_VERSION", "1"),
        help="Bedrock guardrail version (default: 1)",
    )

    parser.add_argument(
        "--auth-token-refresh-session-duration",
        type=int,
        default=43200,
        help="Duration in seconds for the auth token session (300-43200 seconds, default: 43200)",
    )
    return parser


def setup_agent(args, mcp_args: Dict[str, str]):
    """
    Set up and configure the subagent.

    Args:
        args: Parsed command line arguments

    Returns:
        Configured subagent
    """
    logger.info("Setting up subagent...")

    if os.getenv(ENV_KEY_DISABLE_MCP_USAGE_FLAG):
        logging.info("Skipping setting mcp client for subagent")
        mcp_client = None
    else:
        mcp_client = setup_eg_mcp_client(mcp_args)

    # Create subagent with explicit hooks
    subagent = BaseSubagent(
        system_prompt="You are a helpful assistant",
        model_id=args.model_id,
        guardrail_id=args.guardrail_id,
        guardrail_version=args.guardrail_version,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=args.region,
    )

    logger.info("Subagent is set up successfully")
    return subagent


@deprecated("This file is deprecated. Use `simple_subagent_cli.py` instead")
async def run_console(subagent: BaseSubagent):
    """
    Run the subagent in interactive console mode.

    Args:
        subagent: Configured subagent
    """
    print("Base Subagent - Console Mode")
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

            request = ProcessMessageRequest(message=user_input, context=ConversationContext())
            response = subagent.process_message(request)
            print(f"\nAgent Response: {response.message}")
        except KeyboardInterrupt:
            print("\nExiting...")
        except Exception as e:
            logger.error(f"Error event_loop message: {e}")
            print(f"\nError: {str(e)}")


def run_api_server_sync(args, subagent: BaseSubagent):
    """
    Run the API server (synchronous entry point for multiprocessing).

    Args:
        args: Parsed command line arguments
    """
    logger.info("Starting API server process...")

    try:
        start_subagent_api_server(subagent)
    except KeyboardInterrupt:
        logger.info("API server process interrupted")
    except Exception as e:
        logger.error(f"API server process failed: {e}")
        raise


@deprecated(
    "Use simple_subagent_cli.py or simple_stateless_agent_core.py instead for new implementations"
)
async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Initialize auth-token refresher so auto-token would be immediately available for boto client and MCP
    logging.info(
        f"Starting auto-token refresher with session duration: {args.auth_token_refresh_session_duration} seconds"
    )
    get_auth_token_refresher(session_duration=args.auth_token_refresh_session_duration)

    # Initialize the subagent instance
    try:
        initialize_agent_instance()
        logger.info("Subagent instance initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize subagent instance: {e}")
        sys.exit(1)

    current_aws_data_path = os.environ.get("AWS_DATA_PATH", "")
    if current_aws_data_path:
        os.environ["AWS_DATA_PATH"] = f"{current_aws_data_path}{os.pathsep}{args.new_aws_data_path}"
    else:
        os.environ["AWS_DATA_PATH"] = args.new_aws_data_path

    try:
        required_mcp_args = build_mcp_args_from_parsed_args(args)
        subagent = setup_agent(args, required_mcp_args)
        if args.local_testing:
            await run_console(subagent)
        else:
            api_process = Process(
                target=run_api_server_sync,
                args=[args, subagent],
                name="SubagentAPIServer",
                daemon=False,
            )
            api_process.start()
            logger.info(f"API server started with PID: {api_process.pid}")

            try:
                # Keep main process alive
                while api_process.is_alive():
                    await asyncio.sleep(1)
            finally:
                cleanup_process_safely(api_process, "SubagentAPIServer")

    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)


@deprecated(
    "Use simple_subagent_cli.py or simple_stateless_agent_core.py instead for new implementations"
)
def run_main():
    """Entry point wrapper that handles the event loop and process orchestration."""
    logger.debug("Beginning application startup")

    try:
        # Run the main application
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application failed with error: {e}")
        raise


if __name__ == "__main__":
    run_main()
