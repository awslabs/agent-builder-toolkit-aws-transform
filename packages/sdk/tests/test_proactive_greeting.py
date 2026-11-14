# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the proactive greeting of AgentRuntimeServer.

The server, its queue and its request handler are real, and the first test also runs a real
orchestrator with its conversation history. The platform calls of agent initialization, the
model and the chat send are replaced.
"""

import asyncio
import contextlib
import copy
import functools
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator, Optional
from unittest import mock

import pytest
from strands.agent import AgentResult
from strands.models import Model
from strands.telemetry import EventLoopMetrics
from strands.types.content import ContentBlock, Message, Messages
from strands.types.streaming import StreamEvent

from agent_builder_sdk.custom_types.orchestrator_agent_types import ProcessMessageRequest
from agent_builder_sdk.message_queue import RequestStatus
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.conversation.message_type import ConversationMessage
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.server.server_models import AgentRuntimeContext

SERVER = "agent_builder_sdk.server.agent_runtime_server"
PROMPT = "Greet the user in one short message."
GREETING = "Hello! I migrate databases."

Turn = Callable[[ProcessMessageRequest], Awaitable[AgentResult]]


def _result(text: str) -> AgentResult:
    return AgentResult(
        message=Message(role="assistant", content=[ContentBlock(text=text)]),
        stop_reason="end_turn",
        metrics=EventLoopMetrics(),
        state={},
    )


class _AsyncAgent:
    """An async agent that records its turns; ``turn`` may replace the default reply."""

    def __init__(self, turn: Optional[Turn] = None) -> None:
        self.turn = turn
        self.messages: list[str] = []

    async def process_message_async(self, request: ProcessMessageRequest) -> AgentResult:
        self.messages.append(request.message)
        if self.turn is not None:
            return await self.turn(request)
        return _result(GREETING)


class _SyncAgent:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def process_message(self, request: ProcessMessageRequest) -> AgentResult:
        self.messages.append(request.message)
        return _result(GREETING)


@pytest.fixture
def send() -> Iterator[mock.AsyncMock]:
    """The chat send of the greeting."""
    with mock.patch(f"{SERVER}.send_message", new=mock.AsyncMock()) as send_message:
        yield send_message


@contextlib.asynccontextmanager
async def _running_server(
    agent: Any, storage_dir: Path, greeting_prompt: Optional[str] = PROMPT
) -> AsyncIterator[AgentRuntimeServer]:
    """A started server with its queue worker, not yet initialized."""
    server = AgentRuntimeServer(
        agent_factory=lambda mcp_client, storage_dir, **kwargs: agent,
        storage_dir=str(storage_dir),
        greeting_prompt=greeting_prompt,
    )
    server.context = AgentRuntimeContext(
        workspace_id="workspace-id", job_id="job-id", agent_instance_id="agent-instance-id"
    )
    fast_wait = functools.partial(server.queue.wait_for_response, poll_interval=0.01)
    with (
        mock.patch(f"{SERVER}.has_mde_environment", return_value=False),
        mock.patch.object(server.queue, "wait_for_response", fast_wait),
    ):
        await server._startup()
        try:
            yield server
        finally:
            await server._cleanup()


async def _initialize(
    server: AgentRuntimeServer,
    status: str = "INVOKED",
    restored: bool = False,
    wait_for_greeting: bool = True,
) -> None:
    """Initialize the agent with the platform reporting ``status`` for it."""
    checkpoints = mock.Mock()
    checkpoints.restore_if_available.return_value = restored
    with (
        mock.patch(f"{SERVER}.get_agent_status", return_value=status),
        mock.patch(f"{SERVER}.set_agent_running"),
        mock.patch(f"{SERVER}.set_runtime_env_vars"),
        mock.patch(f"{SERVER}.get_auth_token_refresher"),
        mock.patch(f"{SERVER}.build_agentic_api_endpoint_from_env"),
        mock.patch(f"{SERVER}.MCPClientFactory.setup_ab_mcp_client"),
        mock.patch(f"{SERVER}.get_agentic_api_client"),
        mock.patch(f"{SERVER}.JobManager"),
        mock.patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository",
            return_value=checkpoints,
        ),
    ):
        await server.initialize_agent()
        if server._initialization_task is not None:
            await server._initialization_task
    assert server.initialized
    if wait_for_greeting and server._greeting_task is not None:
        await server._greeting_task


async def _wait_until(condition: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout=5)


async def _user_turn(server: AgentRuntimeServer, message: str) -> None:
    request_id = await server.queue.submit_request(message=message, user_id="user-1")
    response = await server.queue.wait_for_response(request_id, timeout=5)
    assert response is not None and response.status == RequestStatus.COMPLETED


async def test_first_boot_posts_one_greeting_and_stores_no_turn(
    tmp_path: Path, send: mock.AsyncMock
) -> None:
    repository = FileMultiSourceConversationRepository(storage_dir=str(tmp_path / "history"))
    orchestrator = AsyncBaseOrchestrator("", hooks=[ConversationHookProvider(repository)])
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = mock.create_autospec(Model, spec_set=True, instance=True)
    model_inputs: list[Messages] = []

    async def stream(
        messages: Messages, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        model_inputs.append(copy.deepcopy(messages))
        text = GREETING if len(model_inputs) == 1 else "Sure."
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockDelta": {"delta": {"text": text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    orchestrator.model.stream.side_effect = stream

    async with _running_server(orchestrator, tmp_path) as server:
        await _initialize(server)

        send.assert_awaited_once()
        assert send.await_args.kwargs["message"] == GREETING
        assert send.await_args.kwargs["target_agent_instance_id"] == "ATX_CHAT"
        assert model_inputs == [[{"role": "user", "content": [{"text": PROMPT}]}]]
        assert not any(
            messages
            for sources in repository.conversations.values()
            for messages in sources.values()
        )

        await _user_turn(server, "Migrate my database")

        assert model_inputs[1] == [{"role": "user", "content": [{"text": "Migrate my database"}]}]
        stored = repository.conversations[MessageSourceType.USER.value]["user-1"]
        assert [m.message["role"] for m in stored] == ["user", "assistant"]

        await _initialize(server)
        send.assert_awaited_once()


@pytest.mark.parametrize(
    ("status", "restored", "greeting_prompt"),
    [
        pytest.param("RUNNING", False, PROMPT, id="container-rotation-running"),
        pytest.param("IDLE", False, PROMPT, id="container-rotation-idle"),
        pytest.param("INVOKED", True, PROMPT, id="checkpoint-restored"),
        pytest.param("INVOKED", False, None, id="no-prompt"),
        pytest.param("INVOKED", False, "  ", id="blank-prompt"),
    ],
)
async def test_no_greeting_without_a_prompt_or_after_the_first_boot(
    tmp_path: Path,
    send: mock.AsyncMock,
    status: str,
    restored: bool,
    greeting_prompt: Optional[str],
) -> None:
    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path, greeting_prompt) as server:
        await _initialize(server, status=status, restored=restored)

        assert server._greeting_task is None
    assert agent.messages == []
    send.assert_not_awaited()


async def test_sync_orchestrator_gets_a_warning_and_no_greeting(
    tmp_path: Path, send: mock.AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    agent = _SyncAgent()
    async with _running_server(agent, tmp_path) as server:
        with caplog.at_level(logging.WARNING, logger=SERVER):
            await _initialize(server)

        assert server._greeting_task is None
    assert agent.messages == []
    send.assert_not_awaited()
    assert "requires an async orchestrator" in caplog.text


async def test_no_greeting_when_a_turn_is_waiting_in_the_queue(
    tmp_path: Path, send: mock.AsyncMock
) -> None:
    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path) as server:
        assert server.message_processor_task is not None
        server.message_processor_task.cancel()
        await server.queue.submit_request(message="Hi", user_id="user-1")
        await _initialize(server)

        assert await server.queue.request_queue.size() == 1
    send.assert_not_awaited()


async def test_no_greeting_when_a_turn_started_before_the_agent_was_ready(
    tmp_path: Path, send: mock.AsyncMock
) -> None:
    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path) as server:
        request_id = await server.queue.submit_request(message="Hi", user_id="user-1")
        await _wait_until(lambda: server.request_handler.persisted_turns_started == 1)
        await _initialize(server)
        await server.queue.wait_for_response(request_id, timeout=5)

    assert agent.messages == ["Hi"]
    send.assert_not_awaited()


async def test_no_greeting_when_a_streamed_turn_already_wrote_history(
    tmp_path: Path, send: mock.AsyncMock
) -> None:
    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path) as server:
        repository = FileMultiSourceConversationRepository(storage_dir=str(tmp_path / "history"))
        repository.conversations[MessageSourceType.USER.value]["user-1"] = [
            ConversationMessage(Message(role="user", content=[ContentBlock(text="Hi")]))
        ]
        server._shared_conversation_repository = repository
        await _initialize(server)

    assert agent.messages == []
    send.assert_not_awaited()


async def test_greeting_is_not_sent_when_a_turn_arrives_while_it_is_written(
    tmp_path: Path, send: mock.AsyncMock
) -> None:
    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path) as server:

        async def user_writes_during_the_greeting(request: ProcessMessageRequest) -> AgentResult:
            if request.message == PROMPT:
                await server.queue.submit_request(message="Hi", user_id="user-1")
            return _result(GREETING)

        agent.turn = user_writes_during_the_greeting
        await _initialize(server)

    assert agent.messages[0] == PROMPT
    send.assert_not_awaited()


async def _fails(request: ProcessMessageRequest) -> AgentResult:
    raise RuntimeError("model unavailable")


async def _returns_blank_text(request: ProcessMessageRequest) -> AgentResult:
    result = _result("")
    result.state["force_stop_response"] = "  "
    return result


async def _never_returns(request: ProcessMessageRequest) -> AgentResult:
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


@pytest.mark.parametrize(
    ("turn", "log"),
    [
        pytest.param(_fails, "status=failed", id="turn-failed"),
        pytest.param(_returns_blank_text, "returned no text", id="blank-reply"),
        pytest.param(_never_returns, "no reply in time", id="timeout"),
    ],
)
async def test_greeting_is_not_sent_when_its_turn_gives_no_reply(
    tmp_path: Path, send: mock.AsyncMock, caplog: pytest.LogCaptureFixture, turn: Turn, log: str
) -> None:
    agent = _AsyncAgent(turn)
    async with _running_server(agent, tmp_path) as server:
        with (
            mock.patch(f"{SERVER}._GREETING_TIMEOUT_SECONDS", 0.2),
            caplog.at_level(logging.WARNING, logger=SERVER),
        ):
            await _initialize(server)

    assert agent.messages == [PROMPT]
    send.assert_not_awaited()
    assert log in caplog.text


async def test_failed_chat_send_is_logged_once_and_the_agent_keeps_serving(
    tmp_path: Path, send: mock.AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    send.side_effect = RuntimeError("chat unavailable")
    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path) as server:
        with caplog.at_level(logging.WARNING, logger=SERVER):
            await _initialize(server)

        assert server._greeting_task is not None
        assert server._greeting_task.exception() is None
        await _user_turn(server, "Hi")

    send.assert_awaited_once()
    assert [r.message for r in caplog.records if "greeting" in r.message] == [
        "Proactive greeting failed; the agent keeps serving requests"
    ]
    assert agent.messages == [PROMPT, "Hi"]


async def test_queue_whose_submit_request_takes_no_persist_runs_no_greeting_turn(
    tmp_path: Path, send: mock.AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    async def submit_request(message: str, sender: Optional[str] = None) -> str:
        raise AssertionError("the turn would be stored")

    agent = _AsyncAgent()
    async with _running_server(agent, tmp_path) as server:
        with (
            mock.patch.object(server.queue, "submit_request", submit_request),
            caplog.at_level(logging.ERROR, logger=SERVER),
        ):
            await _initialize(server)

    assert agent.messages == []
    send.assert_not_awaited()
    assert "Proactive greeting failed" in caplog.text
    assert "unexpected keyword argument 'persist'" in caplog.text


async def test_cleanup_cancels_a_greeting_that_is_still_running(
    tmp_path: Path, send: mock.AsyncMock
) -> None:
    turn_started = asyncio.Event()

    async def blocks(request: ProcessMessageRequest) -> AgentResult:
        turn_started.set()
        return await _never_returns(request)

    async with _running_server(_AsyncAgent(blocks), tmp_path) as server:
        await _initialize(server, wait_for_greeting=False)
        await asyncio.wait_for(turn_started.wait(), timeout=5)
        greeting = server._greeting_task
        assert greeting is not None

        await server._cleanup()

        assert greeting.cancelled()
    send.assert_not_awaited()
