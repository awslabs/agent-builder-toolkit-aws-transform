# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Memory tool for Strands agents.

This module provides a simplified memory tool that can store and retrieve
episodic memory for the current job execution.
"""

import logging
from typing import Optional

from strands.tools import tool

from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.memory.memory_types import MemoryTypeEnum

logger = logging.getLogger(__name__)


class MemoryTool:
    """Simplified memory tool for episodic memory operations."""

    def __init__(self, memory_manager: MemoryManager):
        """
        Initialize the memory tool.

        Args:
            memory_manager: Memory manager instance to use for operations
        """
        self.memory_manager = memory_manager
        logger.info("Initialized MemoryTool")

    @tool
    async def memory(
        self,
        operation: str,
        content: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """Store and retrieve episodic memories from job orchestration activities.

        This tool maintains episodic memory - a record of specific events, activities,
        and experiences that occurred during job execution. Use it to remember what
        happened, when it happened, and the context around specific orchestration events.

        Episodic memories capture:
        - Specific activities performed during orchestration phases
        - Events that occurred during job execution
        - Experiences and interactions during the orchestration process

        Args:
            operation: Memory operation - either 'store' or 'retrieve'
            content: Description of the episodic event/activity (required for 'store' operation)
            limit: Maximum number of memories to retrieve for 'retrieve' operation (default: 10)

        Returns:
            String result of the operation
        """
        try:
            # Use empty context since we're job-centric
            context = ConversationContext()

            if operation == "store":
                if not content or not content.strip():
                    return "Error: Content is required for store operation"

                # Store memory using the injected memory manager
                memory_id = self.memory_manager.store_memory(
                    memory_type=MemoryTypeEnum.EPISODIC,
                    context=context,
                    content=content,
                )

                if memory_id:
                    preview = content[:50] + ("..." if len(content) > 50 else "")
                    return f"Successfully stored memory: {preview}"
                else:
                    return "Error: Failed to store memory"

            elif operation == "retrieve":
                # Retrieve memories using the injected memory manager
                memories = self.memory_manager.retrieve_memories(
                    memory_type=MemoryTypeEnum.EPISODIC,
                    context=context,
                    limit=limit,
                )

                if not memories:
                    return "No memories found"

                # Format memories for easier consumption by the agent
                result_lines = [f"Retrieved {len(memories)} memories:"]
                for i, memory in enumerate(memories, 1):
                    content_text = memory.get("content", "")
                    timestamp = memory.get("timestamp", "")
                    result_lines.append(f"{i}. [{timestamp}] {content_text}")

                return "\n".join(result_lines)

            else:
                return f"Error: Unknown operation '{operation}'. Use 'store' or 'retrieve'"

        except Exception as e:
            logger.error(f"Memory operation error: {e}")
            return f"Error: Memory operation failed: {str(e)}"
