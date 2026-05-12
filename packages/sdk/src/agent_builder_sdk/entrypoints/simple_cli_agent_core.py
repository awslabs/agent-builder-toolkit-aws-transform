# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Sample entrypoint file that creates an async orchestrator configured as a deep research agent.

This demonstrates how to set up an AgentRuntimeServer with custom tools and configuration.
"""

import argparse
import logging

from agent_builder_sdk.agent_factory import (
    MetricsConfig,
    create_default_async_orchestrator_with_subagent,
)
from agent_builder_sdk.checkpoint.checkpoint_triggers import CheckpointStrategy
from agent_builder_sdk.custom_types.notification_types import NotificationType
from agent_builder_sdk.extensions.acknowledgments.acknowledgment_handler import (
    AcknowledgmentHandler,
)
from agent_builder_sdk.logging_config import configure_logging
from agent_builder_sdk.notification import SubagentStatusChangeProcessor
from agent_builder_sdk.notification.notification_handler import NotificationProcessor
from agent_builder_sdk.observability.trace_helper import get_trace_attributes
from agent_builder_sdk.orchestrator_strands.tools.example_tools import research_topic
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.task.example_task_manager import ExampleAlwaysCreateTaskManager
from agent_builder_sdk.task.in_memory_task_store import InMemoryTaskStore
from agent_builder_sdk.utils import get_prompt_with_name

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description="Run Agent Runtime Server")

    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")

    parser.add_argument("--port", type=int, default=8080, help="Port to bind server to")

    parser.add_argument(
        "--storage-dir", default="/tmp/orchestrator_agent", help="Storage directory for agent data"
    )

    parser.add_argument(
        "--queue-storage-path",
        default="/tmp/agent_queue",
        help="Path to store request queue and response data",
    )

    parser.add_argument(
        "--binary-location",
        default="/home/amazon/AgentBuilderAgenticMCP/bin/agent-builder-agentic-mcp",
        help="Path to the agentic MCP server binary",
    )

    parser.add_argument(
        "--checkpoint-strategy",
        choices=["time", "conversation"],
        default="conversation",
        help="Checkpointing strategy. If not specified, checkpointing is disabled.",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=10,
        help="Checkpoint interval: minutes for time strategy, turns for conversation strategy (default: 10)",
    )

    parser.add_argument(
        "--tracing",
        choices=["local", "cloudwatch"],
        default=None,
        help="Enable tracing. Use 'local' for Jaeger or 'cloudwatch' for AWS X-Ray (both use http://localhost:4318)",
    )

    parser.add_argument(
        "--base-guardrail",
        action="store_true",
        help="Enable built-in system prompt guardrails, guarding against behaviors such as job/artifacts deletion, prompt inejection etc.",
    )

    return parser


def main():
    """Main entry point."""
    configure_logging()

    parser = create_parser()
    args = parser.parse_args()

    # Create agent factory with default configuration
    def agent_factory(mcp_client, storage_dir):
        # Get trace attributes for this session
        trace_attributes = get_trace_attributes()
        metric_config = MetricsConfig(enabled=True, namespace="DynamicShowcaseAgent")

        # excluded_mcp_tool_names = {"retrieve_from_knowledge_base"}

        # PREFERRED: Use async orchestrator for better performance with AgentRuntimeServer
        # For sync version (not recommended), use create_default_orchestrator_with_subagent
        return create_default_async_orchestrator_with_subagent(
            mcp_client=mcp_client,
            storage_dir=storage_dir,
            # Pass in your system prompt here
            system_prompt=get_prompt_with_name("test_orchestrator_prompt"),
            custom_tools=[research_topic],
            model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            trace_attributes=trace_attributes,  # Enable tracing,
            with_base_guardrails=args.base_guardrail,
            metrics_config=metric_config,
            # excluded_mcp_tool_names=excluded_mcp_tool_names,
        )

    logger.info("Starting Agent Runtime Server...")

    # Convert string strategy to enum
    checkpoint_strategy = None
    if args.checkpoint_strategy:
        checkpoint_strategy = CheckpointStrategy(args.checkpoint_strategy)

    extension_handlers = [AcknowledgmentHandler()]

    # EXAMPLE: TaskManager factory usage (uncomment to test task creation)
    # This shows how to create a TaskManager with access to queue
    def task_manager_factory(**kwargs):
        """Create TaskManager with access to queue.

        Args:
            context: Contains queue for background processing

        Returns:
            Configured TaskManager instance
        """
        return ExampleAlwaysCreateTaskManager(
            task_store=InMemoryTaskStore(),
            queue=kwargs["queue"],  # Queue created by AgentRuntimeServer
        )

    # EXAMPLE: Custom notification processor that queues subagent status changes
    # This shows how to add custom processors while keeping defaults
    custom_notification_processors: dict[NotificationType, NotificationProcessor] = {
        NotificationType.AGENT_STATUS_CHANGE: SubagentStatusChangeProcessor()
    }

    server = AgentRuntimeServer(
        agent_factory=agent_factory,
        host=args.host,
        port=args.port,
        storage_dir=args.storage_dir,
        binary_location=args.binary_location,
        checkpoint_strategy=checkpoint_strategy,
        checkpoint_interval=args.checkpoint_interval,
        extension_handlers=extension_handlers,
        # task_manager_factory=task_manager_factory,  # Uncomment to enable task creation
        notification_processors=custom_notification_processors,
        tracing=args.tracing,
    )

    # This will set up everything and run the server
    server.start()


if __name__ == "__main__":
    main()
