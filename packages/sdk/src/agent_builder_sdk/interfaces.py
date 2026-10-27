# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Core interfaces for the Agent Builder SDK package.

This module defines the fundamental protocols and interfaces that all agents
must implement to work with the platform infrastructure.
"""

__all__ = ("BaseAgent", "AsyncBaseAgent", "AnyBaseAgent", "StreamingCapable")


from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Protocol, TypeVar

if TYPE_CHECKING:
    from strands.hooks import HookProvider

    from agent_builder_sdk.custom_types.orchestrator_agent_types import ProcessMessageRequest
    from agent_builder_sdk.streaming.config import StreamingConfig

T = TypeVar("T", contravariant=True)
R = TypeVar("R", covariant=True)


class BaseAgent(Protocol[T, R]):
    """Base protocol for all synchronous agent implementations.

    This protocol defines the minimal interface that any agent must implement
    to be compatible with the platform's runtime infrastructure, including
    AgentRuntimeServer, QueueRequestHandler, and other core components.

    All agent implementations (BaseOrchestrator, BaseSubagent, custom agents)
    must implement either this protocol or AsyncBaseAgent to ensure compatibility.
    """

    def process_message(self, request: T) -> R:
        """Process a message request and return a structured response.

        The default implementation creates an asyncio event loop in another
        thread (taken from a thread pool), and then runs process_message_async
        within. If your application already has a running event loop, then you
        should use process_message_async instead.

        Args:
            request: The message request containing the message content and
                    conversation context.

        Returns:
            A structured response containing the agent result
        """


class AsyncBaseAgent(Protocol[T, R]):
    """Base protocol for all asynchronous agent implementations.

    This protocol defines the minimal interface that any agent must implement
    to be compatible with the platform's runtime infrastructure, including
    AgentRuntimeServer, QueueRequestHandler, and other core components.

    All agent implementations (BaseOrchestrator, BaseSubagent, custom agents)
    must implement either this protocol or BaseAgent to ensure compatibility.
    """

    async def process_message_async(self, request: T) -> R:
        """Asynchronously process a message request and return a structured response.

        Args:
            request: The message request containing the message content and
                    conversation context.

        Returns:
            A structured response containing the agent result
        """


AnyBaseAgent = BaseAgent[T, R] | AsyncBaseAgent[T, R]


class StreamingCapable(ABC):
    """Capability contract for agents that support streaming (message/stream).

    An agent declares "I can stream" by inheriting this; not inheriting means not supported
    (e.g. the sync agents don't). Inheriting means implementing every method below, so the
    server can drive a streaming turn and read the agent's streaming policy without knowing
    the concrete agent type. Streaming is async-only, so this lives only on async agents.
    """

    @abstractmethod
    def process_message_stream(
        self,
        request: "ProcessMessageRequest",
        conversation_id: str,
        cfg: "StreamingConfig",
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream one turn as A2A frames."""

    @abstractmethod
    def get_streaming_hook_providers(self, cfg: "StreamingConfig") -> "List[HookProvider]":
        """Hooks to attach to a per-turn streaming agent (e.g. response persistence). Empty if none."""

    @abstractmethod
    def requires_context_id(self) -> bool:
        """Whether a streaming turn must carry a contextId (the reply-routing key)."""

    async def reply_frames(
        self, text: str, conversation_id: str, context_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Frames that end a streaming turn with ``text`` without running the agent (e.g. the
        job-busy reply). Default: the raw agent-to-agent failed terminal, whose text a relaying
        caller reads as the error. A chat-facing agent overrides this to emit a normal reply."""
        from agent_builder_sdk.streaming.raw_a2a_emitter import RawStreamState, error_frames

        return error_frames(RawStreamState(context_id=context_id), text)
