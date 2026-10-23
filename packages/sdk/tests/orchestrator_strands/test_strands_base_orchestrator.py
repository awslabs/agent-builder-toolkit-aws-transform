# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the BaseOrchestrator class."""

from unittest import mock
from unittest.mock import AsyncMock, Mock, create_autospec, patch

import pytest
from strands.models import CacheConfig
from strands.tools.mcp import MCPAgentTool, MCPClient
from strands.types import PaginatedList

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
    AsyncBaseOrchestrator,
    BaseOrchestrator,
)
from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    CURRENT_SOURCE_ID_KEY,
    CURRENT_SOURCE_TYPE_KEY,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider import (
    ConversationHookProvider,
)
from agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider import (
    MemoryHookProvider,
)


@pytest.fixture(autouse=True)
def patch_create_with_shared_capacity_role(mock_model):
    target = "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    with patch(target, spec_set=True, autospec=True, return_value=mock_model) as patched:
        yield patched


@pytest.fixture
def orchestrator():
    return BaseOrchestrator(system_prompt="Test prompt")


@pytest.fixture
def async_orchestrator():
    return AsyncBaseOrchestrator(system_prompt="Test prompt")


def test_streaming_policy_persists_to_chat(async_orchestrator):
    # An orchestrator streams to a human via Chat: persist hook + contextId required.
    from agent_builder_sdk.interfaces import StreamingCapable
    from agent_builder_sdk.streaming.config import StreamingConfig
    from agent_builder_sdk.streaming.response_persist_hook import StreamingResponsePersistHook

    assert isinstance(async_orchestrator, StreamingCapable)
    hooks = async_orchestrator.get_streaming_hook_providers(StreamingConfig())
    assert len(hooks) == 1 and isinstance(hooks[0], StreamingResponsePersistHook)
    assert async_orchestrator.requires_context_id() is True


def test_initialization_defaults(orchestrator):
    """Test orchestrator initialization with default parameters."""
    assert orchestrator.system_prompt == "Test prompt"
    assert orchestrator.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert orchestrator.region_name == "us-east-1"
    assert orchestrator.custom_tools == []
    assert hasattr(orchestrator, "model")


def test_initialization_appends_locale_instruction():
    """A supported locale appends its instruction to the system prompt."""
    orchestrator = BaseOrchestrator(system_prompt="Test prompt", locale="ja")
    assert orchestrator.system_prompt.startswith("Test prompt\n")
    assert "Respond to the user in Japanese" in orchestrator.system_prompt


def test_initialization_locale_none_leaves_prompt_unchanged():
    """No locale leaves the system prompt byte-identical (no behavior change)."""
    orchestrator = BaseOrchestrator(system_prompt="Test prompt", locale=None)
    assert orchestrator.system_prompt == "Test prompt"


def test_initialization_english_or_unknown_locale_leaves_prompt_unchanged():
    """English/unknown locales produce no instruction, so the prompt is unchanged."""
    assert BaseOrchestrator(system_prompt="Test prompt", locale="en").system_prompt == "Test prompt"
    assert BaseOrchestrator(system_prompt="Test prompt", locale="xx").system_prompt == "Test prompt"


def test_initialization_with_custom_parameters(mock_model, mock_repository, mock_memory_manager):
    """Test orchestrator initialization with custom parameters."""
    mock_tools = [Mock(), Mock()]
    # Use real HookProvider instances rather than bare Mock()s. Strands >=1.27 routes each
    # item in hooks=[] to add_hook() only if it satisfies the HookProvider Protocol; anything
    # else callable goes to add_callback(None, hook), which infers the event type from the
    # callback's first type hint and raises ValueError for an untyped/`*args` signature
    # (which is what a bare Mock exposes).
    mock_hooks = [
        ConversationHookProvider(repository=mock_repository),
        MemoryHookProvider(memory_manager=mock_memory_manager),
    ]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Custom prompt",
            custom_tools=mock_tools,
            hooks=mock_hooks,
            region_name="us-west-2",
            model_id="custom-model-id",
        )

    assert orchestrator.system_prompt == "Custom prompt"
    assert orchestrator.model_id == "custom-model-id"
    assert orchestrator.region_name == "us-west-2"
    assert orchestrator.custom_tools == mock_tools


def test_initialization_with_hooks(mock_model, mock_repository, mock_memory_manager):
    """Test orchestrator initialization with explicit hooks."""
    conversation_hook = ConversationHookProvider(repository=mock_repository)
    memory_hook = MemoryHookProvider(memory_manager=mock_memory_manager)
    hooks = [conversation_hook, memory_hook]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", hooks=hooks)

    # We can't easily check the hooks after initialization since they become a HookRegistry
    # But we can verify the orchestrator was created successfully
    assert orchestrator.system_prompt == "Test prompt"


def process_message_cases():
    return [
        (
            ConversationContext(agent_instance_id="test-agent"),
            "test-agent",
            MessageSourceType.SUBAGENT,
        ),
        (ConversationContext(user_id="test-user"), "test-user", MessageSourceType.USER),
        (ConversationContext(), "SYSTEM", MessageSourceType.NOTIFICATION),
    ]


@pytest.mark.parametrize(
    ["context", "expected_id", "expected_type"],
    [
        # subagent: any non-ATX_CHAT agent_instance_id
        (
            ConversationContext(agent_instance_id="sub-agent-1"),
            "sub-agent-1",
            MessageSourceType.SUBAGENT,
        ),
        # ATX_CHAT sender is NOT a subagent — falls through to the user turn
        (
            ConversationContext(agent_instance_id="ATX_CHAT", user_id="u1"),
            "u1",
            MessageSourceType.USER,
        ),
        # plain user turn (no sender)
        (ConversationContext(user_id="u2"), "u2", MessageSourceType.USER),
        # nothing → system notification
        (ConversationContext(), "SYSTEM", MessageSourceType.NOTIFICATION),
    ],
)
def test_classify_source(context, expected_id, expected_type):
    """classify_source is the single source of truth used by the buffered and
    streaming paths + the streaming ingress. ATX_CHAT is the sentinel that means
    'this is a user turn', not a subagent."""
    from agent_builder_sdk.orchestrator_strands.conversation.constants import classify_source

    source_id, source_type = classify_source(context)
    assert source_id == expected_id
    assert source_type == expected_type


@pytest.mark.parametrize(["context", "source_id", "source_type"], process_message_cases())
def test_process_message(orchestrator, agent_result, context, source_id, source_type):
    message = "Test message"
    request = ProcessMessageRequest(message=message, context=context)

    with patch.object(
        orchestrator, "invoke_with_source", autospec=True, return_value=agent_result
    ) as invoke_with_source:
        result = orchestrator.process_message(request)

        invoke_with_source.assert_called_once_with(message, source_id, source_type)
        assert result == agent_result


@pytest.mark.parametrize(["context", "source_id", "source_type"], process_message_cases())
async def test_process_message_async(
    async_orchestrator, agent_result, context, source_id, source_type
):
    message = "Test message"
    request = ProcessMessageRequest(message=message, context=context)

    with patch.object(
        async_orchestrator, "invoke_with_source_async", autospec=True, return_value=agent_result
    ) as invoke_with_source_async:
        result = await async_orchestrator.process_message_async(request)

        invoke_with_source_async.assert_awaited_once_with(message, source_id, source_type)
        assert result == agent_result


def test_invoke_with_source_sets_context(orchestrator):
    """Test that invoke_with_source sets the source context correctly."""
    # Mock the agent's state
    orchestrator.state = Mock()

    # Create a proper mock response
    mock_response = Mock()
    mock_response.message = "Test response"

    # Mock the entire invoke_async method to avoid the streaming issue
    with patch.object(orchestrator, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.return_value = mock_response

        # Call invoke_with_source
        result = orchestrator.invoke_with_source(
            "test message", "test-source", MessageSourceType.USER
        )

        # Verify that the source context was set
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.USER)
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "test-source")

        # Verify that invoke_async was called with the message
        mock_invoke_async.assert_called_once_with("test message", invocation_state={})

        # Verify the result
        assert result == mock_response


def test_invoke_with_source_different_source_types(orchestrator):
    """Test invoke_with_source with different source types."""
    orchestrator.state = Mock()

    # Create a proper mock response
    mock_response = Mock()
    mock_response.message = "Test response"

    # Mock the entire invoke_async method to avoid the streaming issue
    with patch.object(orchestrator, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.return_value = mock_response

        # Test with SUBAGENT
        orchestrator.invoke_with_source("message1", "agent-123", MessageSourceType.SUBAGENT)
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.SUBAGENT)
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "agent-123")

        # Reset mock
        orchestrator.state.reset_mock()

        # Test with NOTIFICATION
        orchestrator.invoke_with_source("message2", "SYSTEM", MessageSourceType.NOTIFICATION)
        orchestrator.state.set.assert_any_call(
            CURRENT_SOURCE_TYPE_KEY, MessageSourceType.NOTIFICATION
        )
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "SYSTEM")


async def test_invoke_with_source_async_enters_mcp_client_context(mock_model):
    mock_tool_1 = create_autospec(MCPAgentTool, spec_set=True, instance=True)
    mock_tool_2 = create_autospec(MCPAgentTool, spec_set=True, instance=True)
    mock_mcp_client_1 = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_mcp_client_2 = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_mcp_client_1.list_tools_sync.return_value = PaginatedList([mock_tool_1])
    mock_mcp_client_2.list_tools_sync.return_value = PaginatedList([mock_tool_2])
    # Standalone (not server-shared) clients are inactive → entered/exited per turn.
    mock_mcp_client_1._is_session_active.return_value = False
    mock_mcp_client_2._is_session_active.return_value = False

    orchestrator = AsyncBaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client_1, mock_mcp_client_2],
    )

    # Called when combining tools during initialisation
    mock_mcp_client_1.__enter__.reset_mock()
    mock_mcp_client_2.__enter__.reset_mock()
    mock_mcp_client_1.__exit__.reset_mock()
    mock_mcp_client_2.__exit__.reset_mock()

    await orchestrator.invoke_with_source_async("message", "source-id", MessageSourceType.USER)

    assert orchestrator.mcp_clients == [mock_mcp_client_1, mock_mcp_client_2]
    mock_mcp_client_1.__enter__.assert_called_once()
    mock_mcp_client_2.__enter__.assert_called_once()
    mock_mcp_client_1.__exit__.assert_called_once()
    mock_mcp_client_2.__exit__.assert_called_once()


async def test_invoke_with_source_async_skips_already_active_mcp_client(mock_model):
    """The buffered path must NOT re-enter a client that is already active (e.g. a
    shared client the server keeps open for concurrent streaming); re-entering would
    raise 'session already running' and break every buffered turn."""
    mock_client = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_client.list_tools_sync.return_value = PaginatedList([])
    mock_client._is_session_active.return_value = True  # server-shared, already open

    orchestrator = AsyncBaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_client],
    )
    mock_client.__enter__.reset_mock()
    mock_client.__exit__.reset_mock()

    await orchestrator.invoke_with_source_async("message", "source-id", MessageSourceType.USER)

    # active client is used in place — never re-entered/exited by the turn
    mock_client.__enter__.assert_not_called()
    mock_client.__exit__.assert_not_called()


def test_streaming_adapter_symbols_are_lazy_imported():
    """The heavy streaming deps (ag_ui.core + a2a.types, pulled in by the adapter) must NOT
    be bound at base_orchestrator module load, so a partner who never enables concurrent
    streaming pays nothing for them. Only the lightweight StreamingConfig is top-level; the
    adapter symbols (adapt / to_a2a_frames / StreamState) are imported inside the streaming
    methods."""
    import agent_builder_sdk.orchestrator_strands.base_orchestrator as bo

    # lightweight config IS bound at module level (used as signature default)
    assert hasattr(bo, "StreamingConfig")
    assert hasattr(bo, "DEFAULT_STREAMING_CONFIG")
    # adapter symbols are NOT bound at module level (lazy-imported in the methods)
    assert not hasattr(bo, "adapt")
    assert not hasattr(bo, "to_a2a_frames")
    assert not hasattr(bo, "StreamState")


def test_streaming_config_import_does_not_pull_heavy_deps():
    """Importing streaming.config (which base_orchestrator does at module load for signature
    defaults) must NOT drag in the adapter's heavy deps (a2a.types + ag_ui.core), so an agent
    that never enables concurrent streaming doesn't load them. The streaming package __init__
    exposes adapter symbols lazily via __getattr__, so a2a/ag_ui load only when an adapter
    symbol is actually accessed. Run in a subprocess for a clean module table (a2a/ag_ui may
    already be imported by other tests in-process)."""
    import os
    import subprocess
    import sys

    code = (
        "import sys\n"
        "from agent_builder_sdk.streaming.config import StreamingConfig\n"
        "assert not any(m == 'a2a' or m.startswith('a2a.') for m in sys.modules), 'a2a loaded via config import'\n"
        "assert not any(m.startswith('ag_ui') for m in sys.modules), 'ag_ui loaded via config import'\n"
        "from agent_builder_sdk.streaming import adapt, to_a2a_frames, StreamState\n"
        "assert callable(adapt) and callable(to_a2a_frames) and StreamState is not None\n"
        "assert any(m == 'a2a' or m.startswith('a2a.') for m in sys.modules), 'a2a not loaded after adapter access'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env={**os.environ}
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK" in result.stdout


async def test_stream_message_async_error_frame_hides_exception_detail(mock_model):
    """A model/MCP/adapter failure must surface a GENERIC terminal RUN_ERROR to the
    client — the raw exception (which can carry ARNs, account ids, endpoints, or file
    paths) must never reach the SSE stream. Detail stays in the server log only."""
    orchestrator = AsyncBaseOrchestrator(system_prompt="Test prompt")

    secret = "arn:aws:bedrock:us-east-1:123456789012:model/secret-endpoint"

    async def boom(*args, **kwargs):
        raise RuntimeError(secret)
        yield  # pragma: no cover - makes this an async generator

    with patch.object(orchestrator, "stream_async", side_effect=boom):
        frames = [
            frame
            async for frame in orchestrator._stream_message_async(
                "hello",
                "user-1",
                MessageSourceType.USER,
                conversation_id="conv-1",
                a2a_context=A2AContext(context_id="ctx-1", task_id=None),
            )
        ]

    # a terminal RUN_ERROR frame is emitted, and it does not leak the exception text
    dumped = str(frames)
    assert "RUN_ERROR" in dumped
    assert secret not in dumped
    assert "123456789012" not in dumped
    assert "An internal error occurred while processing the streaming turn." in dumped


async def test_stream_message_async_error_persists_error_message(mock_model):
    """On a turn failure the same generic error is BOTH streamed AND persisted (keyed on the run_id
    the RUN_ERROR frame carries), so a reload shows the error instead of a blank turn."""
    orchestrator = AsyncBaseOrchestrator(system_prompt="Test prompt")

    async def boom(*args, **kwargs):
        raise RuntimeError("kaboom")
        yield  # pragma: no cover - async generator

    with patch.object(orchestrator, "stream_async", side_effect=boom), patch(
        "agent_builder_sdk.streaming.response_persist_hook.persist_stream_error"
    ) as mock_persist:
        frames = [
            frame
            async for frame in orchestrator._stream_message_async(
                "hello",
                "user-1",
                MessageSourceType.USER,
                conversation_id="conv-1",
                a2a_context=A2AContext(context_id="ctx-9", task_id=None),
            )
        ]

    mock_persist.assert_awaited_once()
    args = mock_persist.await_args.args
    assert args[0] == "ctx-9"  # context_id
    assert args[1] == "An internal error occurred while processing the streaming turn."  # same text
    # persisted under the SAME id the terminal RUN_ERROR frame carries (run_id), so they reconcile
    failed = [f for f in frames if f.get("status", {}).get("state") == "failed"]
    assert failed and failed[-1]["taskId"] == args[2]


async def test_stream_message_async_turn_timeout_emits_clean_terminal(mock_model):
    """A turn that never terminates within turn_timeout_seconds is aborted with a clean terminal
    RUN_ERROR (not left hanging), and the timeout message is persisted for reload."""
    import asyncio as _asyncio

    from agent_builder_sdk.streaming.config import StreamingConfig

    orchestrator = AsyncBaseOrchestrator(system_prompt="Test prompt")

    async def hang(*args, **kwargs):
        await _asyncio.sleep(60)  # far exceeds the tiny budget below
        yield  # pragma: no cover

    with patch.object(orchestrator, "stream_async", side_effect=hang), patch(
        "agent_builder_sdk.streaming.response_persist_hook.persist_stream_error"
    ) as mock_persist:
        frames = [
            frame
            async for frame in orchestrator._stream_message_async(
                "hello",
                "user-1",
                MessageSourceType.USER,
                conversation_id="conv-1",
                cfg=StreamingConfig(turn_timeout_seconds=0.05),
                a2a_context=A2AContext(context_id="ctx-t", task_id=None),
            )
        ]

    dumped = str(frames)
    assert "RUN_ERROR" in dumped
    assert "The request took too long to process and was stopped." in dumped
    mock_persist.assert_awaited_once()


async def test_stream_message_async_drains_side_events_before_terminal(mock_model):
    """Suggestion interactions the persist hook queues on state.side_events must ride the live stream
    BEFORE the terminal RUN_FINISHED frame (so chips arrive with the response, not after the run
    closed), and be drained exactly once. This guards the _stream_frames drain-before-terminal
    integration point end to end."""
    from agent_builder_sdk.streaming.a2a_agui_adapter import (
        build_suggestion_interaction_events,
    )

    orchestrator = AsyncBaseOrchestrator(system_prompt="Test prompt")

    # Fake the model stream: emit one assistant text token, then the terminal AgentResult. Just
    # before the terminal, seed side_events on the SAME per-turn StreamState the orchestrator minted
    # (invocation_state["stream_state"]) — exactly as the persist hook does on the final model call,
    # which precedes the terminal event.
    async def stream(*args, **kwargs):
        state = kwargs["invocation_state"]["stream_state"]
        yield {"data": "hello", "delta": {"text": "hello"}}
        state.side_events.extend(
            build_suggestion_interaction_events(
                chat_suggestions=["Show worklogs", "Stop the job"],
                create_job_suggestion=None,
                message_id="final-msg-1",
            )
        )
        yield {"result": object()}  # terminal AgentResultEvent -> RUN_FINISHED

    captured = {}

    async def stream_capturing(*args, **kwargs):
        captured["state"] = kwargs["invocation_state"]["stream_state"]
        async for e in stream(*args, **kwargs):
            yield e

    with patch.object(orchestrator, "stream_async", side_effect=stream_capturing):
        frames = [
            frame
            async for frame in orchestrator._stream_message_async(
                "hello",
                "user-1",
                MessageSourceType.USER,
                conversation_id="conv-1",
                a2a_context=A2AContext(context_id="ctx-se", task_id=None),
            )
        ]

    def agui_type(frame):
        parts = frame.get("status", {}).get("message", {}).get("parts", [])
        if parts and parts[0].get("kind") == "data":
            data = parts[0]["data"]
            return next(iter(data.values())).get("type")
        return None

    types_in_order = [agui_type(f) for f in frames]
    assert "INTERACTION" in types_in_order, f"expected an INTERACTION frame; got {types_in_order}"
    # the chips ride BEFORE the terminal RUN_FINISHED, not after the run closed
    assert types_in_order.index("INTERACTION") < types_in_order.index("RUN_FINISHED")
    # exactly one INTERACTION (no double-drain) and side_events drained
    assert types_in_order.count("INTERACTION") == 1
    assert captured["state"].side_events == []


async def test_stream_message_async_inner_timeout_is_generic_not_turn_timeout(mock_model):
    """An inner TimeoutError (e.g. an MCP tool / boto3 read timeout) that fires BEFORE the turn
    budget expires must be surfaced as the generic internal error, not mislabeled as a turn timeout.
    On 3.11+ TimeoutError is asyncio.TimeoutError, so the handler must guard on the timeout scope
    actually expiring and re-raise otherwise."""
    from agent_builder_sdk.streaming.config import StreamingConfig

    orchestrator = AsyncBaseOrchestrator(system_prompt="Test prompt")

    async def inner_timeout(*args, **kwargs):
        raise TimeoutError("boto3 read timed out")
        yield  # pragma: no cover

    with patch.object(orchestrator, "stream_async", side_effect=inner_timeout), patch(
        "agent_builder_sdk.streaming.response_persist_hook.persist_stream_error"
    ):
        frames = [
            frame
            async for frame in orchestrator._stream_message_async(
                "hello",
                "user-1",
                MessageSourceType.USER,
                conversation_id="conv-1",
                # generous budget so the inner TimeoutError, not the scope, is what fires
                cfg=StreamingConfig(turn_timeout_seconds=60),
                a2a_context=A2AContext(context_id="ctx-i", task_id=None),
            )
        ]

    dumped = str(frames)
    assert "RUN_ERROR" in dumped
    # the generic message, NOT the turn-timeout one
    assert "An internal error occurred while processing the streaming turn." in dumped
    assert "took too long" not in dumped


def test_set_current_source_context(orchestrator):
    """Test _set_current_source_context method."""
    orchestrator.state = Mock()
    orchestrator.agent_id = "test-agent-id"

    # Call the method
    orchestrator._set_current_source_context(MessageSourceType.USER, "user-123")

    # Verify state was set correctly
    orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.USER)
    orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "user-123")


def test_orchestrator_with_empty_hooks_list(mock_model):
    """Test orchestrator initialization with empty hooks list."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", hooks=[])

    assert orchestrator.system_prompt == "Test prompt"


def test_orchestrator_with_none_hooks(mock_model):
    """Test orchestrator initialization with None hooks."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", hooks=None)

    assert orchestrator.system_prompt == "Test prompt"


def test_orchestrator_with_tools(mock_model):
    """Test orchestrator initialization with tools."""
    mock_tools = [Mock(), Mock()]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", custom_tools=mock_tools)

    assert orchestrator.custom_tools == mock_tools


def test_orchestrator_bedrock_model_creation(mock_model):
    """Test that BedrockModel is created with correct parameters."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ) as mock_factory:
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt",
            model_id="custom-model",
            region_name="us-west-2",
        )

        # Verify factory was called with correct parameters. guardrail_stream_processing_mode is
        # NOT passed when unset — it's omitted (not None) so BedrockModel keeps its own default
        # (Bedrock treats an absent streamProcessingMode as synchronous).
        mock_factory.assert_called_once_with(
            model_id="custom-model",
            region_name="us-west-2",
            guardrail_id=None,
            guardrail_version=None,
            boto_client_config=None,
        )
        assert orchestrator.model == mock_model


def test_orchestrator_forwards_guardrail_stream_processing_mode(mock_model):
    """When a job-agent owner sets the streaming guardrail mode, it is forwarded to the model
    factory (alongside guardrail_id/version) so it reaches Bedrock's streamProcessingMode."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ) as mock_factory:
        BaseOrchestrator(
            system_prompt="Test prompt",
            model_id="custom-model",
            region_name="us-west-2",
            guardrail_id="gr-1",
            guardrail_version="2",
            guardrail_stream_processing_mode="async",
        )

        mock_factory.assert_called_once_with(
            model_id="custom-model",
            region_name="us-west-2",
            guardrail_id="gr-1",
            guardrail_version="2",
            boto_client_config=None,
            guardrail_stream_processing_mode="async",
        )


def test_orchestrator_omits_guardrail_mode_when_unset(mock_model):
    """An unset guardrail_stream_processing_mode is omitted from the factory call entirely (not
    sent as None), so BedrockModel falls back to Bedrock's default (synchronous) gating."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ) as mock_factory:
        BaseOrchestrator(
            system_prompt="Test prompt",
            guardrail_id="gr-1",
            guardrail_version="2",
        )

        _, kwargs = mock_factory.call_args
        assert "guardrail_stream_processing_mode" not in kwargs


def test_orchestrator_passes_cache_config_when_prompt_caching_is_on(
    patch_create_with_shared_capacity_role,
):
    """The flag hands Strands' automatic cache placement to the model it builds. The default
    call, with no cache_config at all, is pinned by
    test_initialize_bedrock_model_default_credentials."""
    BaseOrchestrator(system_prompt="Test prompt", enable_prompt_caching=True)

    _, kwargs = patch_create_with_shared_capacity_role.call_args
    assert kwargs["cache_config"] == CacheConfig(strategy="auto")


@patch(
    "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_initialize_bedrock_model_default_credentials(mock_factory, mock_model):
    """Test BedrockModel initialization with default credentials."""
    mock_factory.return_value = mock_model

    orchestrator = BaseOrchestrator(system_prompt="Test prompt")

    # Verify factory was called with default parameters
    mock_factory.assert_called_once_with(
        model_id="anthropic.claude-sonnet-4-5-20250929-v1:0",
        region_name="us-east-1",
        guardrail_id=None,
        guardrail_version=None,
        boto_client_config=None,
    )
    assert orchestrator.model == mock_model


class TestBaseOrchestratorIntegration:
    """Integration tests for BaseOrchestrator."""

    def test_full_message_processing_flow(self, mock_model):
        """Test the complete message processing flow."""
        with patch(
            "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
            return_value=mock_model,
        ):
            orchestrator = BaseOrchestrator(system_prompt="Test prompt")

        # Mock the necessary methods
        orchestrator.state = Mock()

        # Create a proper mock response
        mock_response = Mock()
        mock_response.message = "Test response"

        a2a_context = A2AContext(context_id="c-123", task_id=None)

        # Mock the entire invoke_async method to avoid the streaming issue
        with patch.object(
            orchestrator, "invoke_async", new_callable=AsyncMock
        ) as mock_invoke_async:
            mock_invoke_async.return_value = mock_response

            # Create a request
            request = ProcessMessageRequest(
                message="Hello",
                context=ConversationContext(user_id="test-user", a2a_context=a2a_context),
            )

            # Process the message
            result = orchestrator.process_message(request)

            # Verify the flow
            orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.USER)
            orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "test-user")

            # Verify invoke_async was called
            mock_invoke_async.assert_called_once_with(
                "Hello", invocation_state={"a2a_context": a2a_context}
            )

            # Verify the result
            assert result == mock_response


def test_initialization_with_mcp_clients(mock_model, mock_repository):
    """Test orchestrator initialization with MCP clients."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_client.list_tools_sync = Mock(return_value=[Mock(), Mock()])

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt",
            mcp_clients=[mock_mcp_client],
        )

        assert orchestrator.mcp_clients == [mock_mcp_client]
        mock_mcp_client.list_tools_sync.assert_called_once()


def test_combine_tools_with_mcp_and_custom():
    """Test combining MCP tools with custom tools."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(name="mcp_tool1"), Mock(name="mcp_tool2")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)
    custom_tools = [Mock(name="custom_tool1")]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt", mcp_clients=[mock_mcp_client], custom_tools=custom_tools
        )

        combined_tools = orchestrator._combine_tools()
        assert len(combined_tools) == 3
        assert mock_mcp_tools[0] in combined_tools
        assert mock_mcp_tools[1] in combined_tools
        assert custom_tools[0] in combined_tools


def test_combine_tools_with_multiple_mcp_and_custom():
    """Test combining multiple MCP server tools with custom tools."""
    mock_mcp_client1 = Mock()
    mock_mcp_client1.__enter__ = Mock(return_value=mock_mcp_client1)
    mock_mcp_client1.__exit__ = Mock(return_value=None)
    mock_mcp_tools1 = [Mock(name="mcp_tool1"), Mock(name="mcp_tool2")]
    mock_mcp_client1.list_tools_sync = Mock(return_value=mock_mcp_tools1)
    custom_tools = [Mock(name="custom_tool1")]
    mock_mcp_client2 = Mock()
    mock_mcp_client2.__enter__ = Mock(return_value=mock_mcp_client2)
    mock_mcp_client2.__exit__ = Mock(return_value=None)
    mock_mcp_tools2 = [Mock(name="mcp_tool3"), Mock(name="mcp_tool4")]
    mock_mcp_client2.list_tools_sync = Mock(return_value=mock_mcp_tools2)

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt",
            mcp_clients=[mock_mcp_client1, mock_mcp_client2],
            custom_tools=custom_tools,
        )

        combined_tools = orchestrator._combine_tools()
        assert len(combined_tools) == 5
        assert mock_mcp_tools1[0] in combined_tools
        assert mock_mcp_tools1[1] in combined_tools
        assert custom_tools[0] in combined_tools
        assert mock_mcp_tools2[0] in combined_tools
        assert mock_mcp_tools2[1] in combined_tools


def test_invoke_with_source_with_mcp_clients(mock_model):
    """Test invoke_with_source with MCP clients."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_client.list_tools_sync = Mock(return_value=[])

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", mcp_clients=[mock_mcp_client])

        # Test that MCP clients are properly stored
        assert orchestrator.mcp_clients == [mock_mcp_client]

        # Test context setting
        orchestrator._set_current_source_context(MessageSourceType.USER, "user123")
        assert orchestrator.state.get("current_source_type") == MessageSourceType.USER
        assert orchestrator.state.get("current_source_id") == "user123"


@mock.patch("agent_builder_sdk.orchestrator_strands.base_orchestrator.BedrockModelFactory")
def test_orchestrator_with_model_parameter(mock_bedrock_factory):
    """Test BaseOrchestrator with custom model parameter."""
    mock_model = mock.Mock()

    orchestrator = BaseOrchestrator(system_prompt="Test prompt", model=mock_model)

    # Verify Bedrock factory was not called when model provided
    mock_bedrock_factory.create_with_shared_capacity_role.assert_not_called()

    # Verify model is accessible through parent class
    assert hasattr(orchestrator, "model")


@patch(
    "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_orchestrator_excluded_mcp_tool_names(mock_factory, mock_model):
    """Test that excluded_mcp_tool_names filters MCP tools."""
    mock_factory.return_value = mock_model

    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [
        Mock(tool_name="mcp_included"),
        Mock(tool_name="mcp_excluded"),
    ]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)

    orchestrator = BaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client],
        excluded_mcp_tool_names={"mcp_excluded"},
    )

    combined_tools = orchestrator._combine_tools()
    tool_names = [tool.tool_name for tool in combined_tools]
    assert "mcp_included" in tool_names
    assert "mcp_excluded" not in tool_names


@patch(
    "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_orchestrator_excluded_mcp_and_custom_tools(mock_factory, mock_model):
    """Test that both excluded_tool_names and excluded_mcp_tool_names work together."""
    mock_factory.return_value = mock_model

    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(tool_name="mcp_excluded")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)

    custom_tools = [Mock(tool_name="custom_excluded")]

    orchestrator = BaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client],
        custom_tools=custom_tools,
        excluded_tool_names={"custom_excluded"},
        excluded_mcp_tool_names={"mcp_excluded"},
    )

    combined_tools = orchestrator._combine_tools()
    assert len(combined_tools) == 0
