#!/usr/bin/env python3
"""
Simple command-line interface for running a subagent with AgentRuntimeServer.
"""

import argparse
import logging
import os

from agent_builder_sdk.agent_factory import create_default_subagent
from agent_builder_sdk.logging_config import configure_logging
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.utils import get_prompt_with_name

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description="Run Base Subagent with AgentRuntimeServer")

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
        "--host",
        default="0.0.0.0",
        help="Host to bind the server to",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to run the server on",
    )

    parser.add_argument(
        "--storage-dir", default="/tmp/sub_agent", help="Storage directory for agent data"
    )

    return parser


def main():
    """Main entry point."""
    configure_logging()
    parser = create_parser()
    args = parser.parse_args()

    # Create agent factory with default configuration
    def agent_factory(mcp_client, storage_dir):
        # If you're writing your own entry point based off this code,
        # use create_default_async_subagent instead.
        return create_default_subagent(
            mcp_client=mcp_client,
            system_prompt=get_prompt_with_name("test_subagent_prompt"),
        )

    # Create and start server
    server = AgentRuntimeServer(
        agent_factory=agent_factory,
        host=args.host,
        port=args.port,
        binary_location=args.binary_location,
        storage_dir=args.storage_dir,
    )

    # This will set up everything and run the server
    server.start()


if __name__ == "__main__":
    main()
