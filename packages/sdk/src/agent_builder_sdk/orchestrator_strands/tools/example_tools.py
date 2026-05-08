# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Example tools for demonstrating various agent capabilities.

This module contains sample tools that showcase different patterns and features
for building custom agent tools. These tools are for demonstration and learning
purposes only and should not be used in production environments.

Available Tools:
- research_topic: Demonstrates background task execution with A2A progress updates.
                  REQUIRES AsyncBaseOrchestrator - will not work correctly with sync BaseOrchestrator.
"""

import asyncio
import logging
from typing import Optional

from strands import ToolContext
from strands.tools import tool

from agent_builder_sdk.custom_types.orchestrator_agent_types import A2AContext
from agent_builder_sdk.messages.a2a_message_helper import send_message

logger = logging.getLogger(__name__)

# Keep strong references to background tasks to prevent garbage collection
_background_tasks = set()


async def _do_research_background(topic: str, a2a_context: A2AContext):
    """Background research task that sends progress updates."""
    try:
        # Validate context_id exists (should always be true when this function is called)
        if not a2a_context.context_id:
            logger.error(f"Cannot start background research for '{topic}' - no context_id")
            return

        context_id = a2a_context.context_id
        logger.info(f"Starting background research on '{topic}' with context: {context_id}")

        # Simulate 1-minute research with updates every 10 seconds
        research_stages = [
            "Gathering initial sources...",
            "Analyzing key findings...",
            "Cross-referencing data...",
            "Synthesizing insights...",
            "Validating results...",
            "Finalizing report...",
        ]

        for i, stage in enumerate(research_stages, 1):
            # Send progress update with topic prefix
            progress_msg = f"[{topic}] Research progress ({i}/{len(research_stages)}): {stage}"
            try:
                await send_message(
                    message=progress_msg,
                    context_id=context_id,
                    target_agent_instance_id="ATX_CHAT",
                )
            except Exception as e:
                logger.error(f"Failed to send stage {i} message: {e}")

            # Simulate work (10 seconds)
            await asyncio.sleep(10)

        # Final result
        final_result = f"""Research Summary for '{topic}':

Key Findings:
- Comprehensive analysis completed
- Multiple sources reviewed
- Data validated and cross-referenced

Conclusion:
Research on {topic} has been successfully completed with thorough investigation."""

        logger.info(f"Research completed for '{topic}'")
        try:
            await send_message(
                message=final_result,
                context_id=context_id,
                target_agent_instance_id="ATX_CHAT",
            )
        except Exception as e:
            logger.error(f"Failed to send final summary: {e}")

    except asyncio.CancelledError:
        logger.warning(f"Task was cancelled for topic '{topic}'")
        # Don't re-raise, just exit gracefully
    except Exception as e:
        logger.error(f"Unexpected error in background research: {e}", exc_info=True)
        # Don't re-raise, just exit gracefully


@tool(context=True)
async def research_topic(topic: str, tool_context: ToolContext) -> str:
    """
    Conduct research on a topic.

    Performs comprehensive research on the specified topic, including gathering sources,
    analyzing findings, cross-referencing data, and synthesizing insights. Progress updates
    are sent during the research process.

    Args:
        topic: The research topic to investigate

    Returns:
        Confirmation that research has started
    """
    # NOTE: This tool requires AsyncBaseOrchestrator. It will not work correctly with
    # the synchronous BaseOrchestrator due to event loop lifecycle management.

    # Access invocation_state from ToolContext
    a2a_context: Optional[A2AContext] = tool_context.invocation_state.get("a2a_context")

    if not a2a_context or not a2a_context.context_id:
        logger.warning("No a2a_context provided, cannot start background research")
        return f"Unable to start research on '{topic}' - no context provided"

    # Create task and keep strong reference to prevent garbage collection
    task = asyncio.create_task(_do_research_background(topic, a2a_context))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Return immediately
    return f"Started researching '{topic}' in the background."
