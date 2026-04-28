import logging
from typing import Any

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import MessageAddedEvent

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


class MemoryHookProvider(HookProvider):
    """Hook provider for automatic memory management"""

    def __init__(self, memory_manager: MemoryManager):
        """
        Initialize the memory hook provider.

        Args:
            memory_manager: The memory manager to use for retrieving and storing memories
        """
        self.memory_manager = memory_manager

    def retrieve_memories(self, event: MessageAddedEvent) -> None:
        """
        Retrieve relevant memories before processing user message.

        This method is called when a new message is added to the agent's conversation.
        It retrieves relevant memories based on the message content and injects them
        into the user message as context.

        Args:
            event: The MessageAddedEvent containing the message and agent
        """
        messages = event.agent.messages

        # Only process user messages that aren't tool results
        if not messages:
            return

        if messages[-1]["role"] == "user" and "toolResult" not in messages[-1]["content"][0]:
            user_message = messages[-1]["content"][0].get("text", "")
            if not user_message:
                return

            try:
                # Create memory context from agent state
                conversation_context = ConversationContext()
                memory_context = MemoryContext(conversation_context=conversation_context)

                # Retrieve relevant memories
                memory_content = self.memory_manager.get_context_for_message(
                    message=user_message, memory_context=memory_context, limit=5
                )

                # Inject memories into user message if any were retrieved
                if memory_content:
                    original_text = messages[-1]["content"][0]["text"]
                    messages[-1]["content"][0][
                        "text"
                    ] = f"{original_text}\n\nRelevant context from memory: {memory_content}"
                    logger.info("Retrieved and injected memory context")

            except Exception as e:
                logger.error(f"Failed to retrieve memories: {e}")

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """
        Register memory hooks.

        Args:
            registry: The hook registry to register callbacks with
            **kwargs: Additional arguments
        """
        registry.add_callback(MessageAddedEvent, self.retrieve_memories)
        logger.info("Memory retrieval hook registered")
