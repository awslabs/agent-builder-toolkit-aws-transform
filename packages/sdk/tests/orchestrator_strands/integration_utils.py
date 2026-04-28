import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from strands.agent import AgentResult
from strands.hooks import HookProvider, HookRegistry, MessageAddedEvent
from strands.types.content import ContentBlock, ContentBlockStart, Message, Messages, Role
from strands.types.streaming import (
    ContentBlockDelta,
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    StreamEvent,
)
from typing_extensions import override

from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider


class MessageAddedEventHook(HookProvider):
    """Set an asyncio.Event specific to a message's text when receiving MessageAddedEvent."""

    def __init__(self, events: dict[str, asyncio.Event]):
        self.events = events

    @override
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(MessageAddedEvent, self._on_message_added)

    def _on_message_added(self, event: MessageAddedEvent) -> None:
        for block in event.message["content"]:
            if event := self.events.get(block.get("text")):
                event.set()


@dataclass
class TestMessage:
    source_id: str
    message_id: str
    source_type: MessageSourceType = MessageSourceType.USER

    invocations: list[tuple[Messages, tuple[Any, ...], dict[str, Any]]] = field(
        default_factory=list
    )
    """Arguments of Model.stream() for all invocations with this message."""

    start_after: list[asyncio.Event] = field(default_factory=list)
    """Events to wait for before invoking the model."""

    stop_after: list[asyncio.Event] = field(default_factory=list)
    """Events to wait for before yielding ContentBlockStopEvent."""

    starting: asyncio.Event = field(default_factory=asyncio.Event)
    """Event that's set before yielding ContentBlockStartEvent."""

    stopped: asyncio.Event = field(default_factory=asyncio.Event)
    """Event that's set after yielding ContentBlockStopEvent and MessageAddedEvent."""

    @property
    def input(self) -> str:
        """Input text given to the model."""
        return f"{self.source_id}.input_{self.message_id}"

    @property
    def output(self) -> str:
        """Output text received from the model."""
        return f"{self.source_id}.output_{self.message_id}"

    async def events(self) -> AsyncGenerator[StreamEvent, None]:
        """Yield model StreamEvents, waiting for start_after and stop_after if set."""
        start = ContentBlockStartEvent(contentBlockIndex=0, start=ContentBlockStart())
        delta = ContentBlockDeltaEvent(
            contentBlockIndex=0, delta=ContentBlockDelta(text=self.output)
        )
        stop = ContentBlockStopEvent(contentBlockIndex=0)

        yield StreamEvent(contentBlockStart=start)
        self.starting.set()

        yield StreamEvent(contentBlockDelta=delta)

        await wait_for_events(self.stop_after)
        yield StreamEvent(contentBlockStop=stop)


def create_message(text: str, role: Role) -> Message:
    """Create a Strands message with a single text content block."""
    return Message(content=[ContentBlock(text=text)], role=role)


def create_stream_side_effect(input_to_messages: dict[str, TestMessage]):
    """Return a StreamEvent generator based on the latest input message's text."""

    def side_effect(messages: Messages, *args, **kwargs) -> AsyncGenerator[StreamEvent, None]:
        latest_user_message = next(m for m in reversed(messages) if m["role"] == "user")
        input_text = latest_user_message["content"][0]["text"]

        test_message = input_to_messages[input_text]
        # Store a copy because the messages list is mutated by concurrent invocations
        test_message.invocations.append((messages.copy(), args, kwargs))

        return test_message.events()

    return side_effect


async def wait_for_events(events: list[asyncio.Event]) -> None:
    """Wait for all given events to be set."""
    async with asyncio.TaskGroup() as tg:
        for event in events:
            tg.create_task(event.wait())


async def invoke(
    orchestrator: AsyncBaseOrchestrator,
    message: TestMessage,
) -> AgentResult:
    """Invoke the orchestrator after waiting for the message's start_after events."""
    await wait_for_events(message.start_after)

    args = (message.input, message.source_id, message.source_type)
    return await orchestrator.invoke_with_source_async(*args)


def get_conversation(
    hook: ConversationHookProvider,
    source_id: str,
    source_type: MessageSourceType = MessageSourceType.USER,
) -> Messages:
    """Return the conversation history for a source from the repository."""
    conversations = hook.repository.conversations[source_type]
    return [m.message for m in conversations[source_id]]
