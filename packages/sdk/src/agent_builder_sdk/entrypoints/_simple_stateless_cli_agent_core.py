# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Simplified CLI for Agent Runtime Server.
"""

import argparse
import logging

from agent_builder_sdk.agent_factory import create_default_subagent
from agent_builder_sdk.logging_config import configure_logging
from agent_builder_sdk.server.stateless_agent_runtime_server import StatelessAgentRuntimeServer
from agent_builder_sdk.utils import get_prompt_with_name

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description="Run Stateless Agent Runtime Server")

    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")

    parser.add_argument("--port", type=int, default=8080, help="Port to bind server to")

    parser.add_argument(
        "--binary-location",
        default="/home/amazon/ElasticGumbyAgenticMCP/bin/eg_agentic_mcp_server",
        help="Path to the agentic MCP server binary",
    )

    parser.add_argument(
        "--tracing",
        choices=["local", "cloudwatch"],
        default=None,
        help="Enable tracing. Use 'local' for Jaeger or 'cloudwatch' for AWS X-Ray (both use http://localhost:4318)",
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
            system_prompt=get_prompt_with_name("test_orchestrator_prompt"),
        )

    logger.info("Starting Stateless Agent Runtime Server...")
    server = StatelessAgentRuntimeServer(
        agent_factory=agent_factory,
        host=args.host,
        port=args.port,
        binary_location=args.binary_location,
        tracing=args.tracing,
    )

    # This will set up everything and run the server
    server.start()


if __name__ == "__main__":
    main()
