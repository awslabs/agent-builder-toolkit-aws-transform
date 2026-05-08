# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Core interfaces for the Agent Builder SDK package.

This module defines the fundamental protocols and interfaces that all agents
must implement to work with the platform infrastructure.
"""

__all__ = ("BaseAgent", "AsyncBaseAgent", "AnyBaseAgent")


from typing import Protocol, TypeVar

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
