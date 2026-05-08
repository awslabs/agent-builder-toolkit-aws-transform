# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for a2a_context_id_var and a2a_user_id_var ContextVar propagation."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
    AsyncBaseOrchestrator,
    BaseOrchestrator,
    a2a_context_id_var,
    a2a_user_id_var,
)
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType


@pytest.fixture(autouse=True)
def patch_bedrock_factory(mock_model):
    target = "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    with patch(target, spec_set=True, autospec=True, return_value=mock_model):
        yield


@pytest.fixture
def orchestrator():
    return BaseOrchestrator(system_prompt="Test prompt")


@pytest.fixture
def async_orchestrator():
    return AsyncBaseOrchestrator(system_prompt="Test prompt")


# ---------------------------------------------------------------------------
# Sync BaseOrchestrator tests
# ---------------------------------------------------------------------------


def test_invoke_with_source_sets_context_id_var(orchestrator, agent_result):
    """context_id from a2a_context should be propagated to a2a_context_id_var."""
    orchestrator.state = Mock()
    a2a_context = A2AContext(context_id="ctx-abc-123")

    with patch.object(
        orchestrator, "invoke_async", new_callable=AsyncMock, return_value=agent_result
    ):
        orchestrator.invoke_with_source(
            "hello", "user-1", MessageSourceType.USER, a2a_context=a2a_context
        )

    # ContextVar was set inside a thread so we can't read it here directly,
    # but we can verify the flow by checking the async path instead (see async tests below).
    # This test verifies no exception is raised when a2a_context is provided.


def test_invoke_with_source_sets_user_id_var_for_user_source(orchestrator, agent_result):
    """user_id ContextVar should be set when source_type is USER."""
    orchestrator.state = Mock()

    with patch.object(
        orchestrator, "invoke_async", new_callable=AsyncMock, return_value=agent_result
    ):
        orchestrator.invoke_with_source("hello", "user-42", MessageSourceType.USER)

    # Same thread caveat as above — async tests below verify the actual ContextVar values.


def test_invoke_with_source_no_crash_without_a2a_context(orchestrator, agent_result):
    """Should not crash when no a2a_context is provided in kwargs."""
    orchestrator.state = Mock()

    with patch.object(
        orchestrator, "invoke_async", new_callable=AsyncMock, return_value=agent_result
    ):
        result = orchestrator.invoke_with_source("hello", "SYSTEM", MessageSourceType.NOTIFICATION)

    assert result == agent_result


# ---------------------------------------------------------------------------
# Async BaseOrchestrator tests — these can directly verify ContextVar values
# ---------------------------------------------------------------------------


async def test_async_invoke_sets_a2a_context_id_var(async_orchestrator, agent_result):
    """a2a_context_id_var should contain the context_id after _invoke_with_source."""
    async_orchestrator.state = Mock()
    a2a_context = A2AContext(context_id="ctx-async-456")

    captured_context_id = None

    async def capture_and_process(message, **kwargs):
        nonlocal captured_context_id
        captured_context_id = a2a_context_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        await async_orchestrator.invoke_with_source_async(
            "hello", "user-1", MessageSourceType.USER, a2a_context=a2a_context
        )

    assert captured_context_id == "ctx-async-456"


async def test_async_invoke_sets_a2a_user_id_var_for_user_source(async_orchestrator, agent_result):
    """a2a_user_id_var should be set to source_id when source_type is USER."""
    async_orchestrator.state = Mock()

    captured_user_id = None

    async def capture_and_process(message, **kwargs):
        nonlocal captured_user_id
        captured_user_id = a2a_user_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        await async_orchestrator.invoke_with_source_async(
            "hello", "user-99", MessageSourceType.USER
        )

    assert captured_user_id == "user-99"


async def test_async_invoke_does_not_set_user_id_for_subagent(async_orchestrator, agent_result):
    """a2a_user_id_var should NOT be set when source_type is SUBAGENT."""
    async_orchestrator.state = Mock()
    # Reset to a known value so we can detect it wasn't changed
    a2a_user_id_var.set(None)

    captured_user_id = "SENTINEL"

    async def capture_and_process(message, **kwargs):
        nonlocal captured_user_id
        captured_user_id = a2a_user_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        await async_orchestrator.invoke_with_source_async(
            "hello", "agent-sub-1", MessageSourceType.SUBAGENT
        )

    assert captured_user_id is None


async def test_async_invoke_does_not_set_user_id_for_notification(async_orchestrator, agent_result):
    """a2a_user_id_var should NOT be set when source_type is NOTIFICATION."""
    async_orchestrator.state = Mock()
    a2a_user_id_var.set(None)

    captured_user_id = "SENTINEL"

    async def capture_and_process(message, **kwargs):
        nonlocal captured_user_id
        captured_user_id = a2a_user_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        await async_orchestrator.invoke_with_source_async(
            "hello", "SYSTEM", MessageSourceType.NOTIFICATION
        )

    assert captured_user_id is None


async def test_async_invoke_without_a2a_context_leaves_context_id_default(
    async_orchestrator, agent_result
):
    """a2a_context_id_var should remain None when no a2a_context is provided."""
    async_orchestrator.state = Mock()
    a2a_context_id_var.set(None)

    captured_context_id = "SENTINEL"

    async def capture_and_process(message, **kwargs):
        nonlocal captured_context_id
        captured_context_id = a2a_context_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        await async_orchestrator.invoke_with_source_async("hello", "user-1", MessageSourceType.USER)

    assert captured_context_id is None


async def test_async_invoke_with_none_context_id_in_a2a(async_orchestrator, agent_result):
    """a2a_context_id_var should not be set when a2a_context.context_id is None."""
    async_orchestrator.state = Mock()
    a2a_context_id_var.set(None)
    a2a_context = A2AContext(context_id=None)

    captured_context_id = "SENTINEL"

    async def capture_and_process(message, **kwargs):
        nonlocal captured_context_id
        captured_context_id = a2a_context_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        await async_orchestrator.invoke_with_source_async(
            "hello", "user-1", MessageSourceType.USER, a2a_context=a2a_context
        )

    assert captured_context_id is None


async def test_process_message_async_propagates_both_vars(async_orchestrator, agent_result):
    """process_message_async should propagate both context_id and user_id."""
    async_orchestrator.state = Mock()
    a2a_context = A2AContext(context_id="ctx-pm-789")

    captured = {}

    async def capture_and_process(message, **kwargs):
        captured["context_id"] = a2a_context_id_var.get()
        captured["user_id"] = a2a_user_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        request = ProcessMessageRequest(
            message="test",
            context=ConversationContext(user_id="user-pm-42", a2a_context=a2a_context),
        )
        await async_orchestrator.process_message_async(request)

    assert captured["context_id"] == "ctx-pm-789"
    assert captured["user_id"] == "user-pm-42"


async def test_async_invoke_resets_stale_vars_between_invocations(async_orchestrator, agent_result):
    """ContextVars from a USER invocation must not leak into a subsequent NOTIFICATION."""
    async_orchestrator.state = Mock()

    captured_first = {}
    captured_second = {}

    call_count = 0

    async def capture_and_process(message, **kwargs):
        nonlocal call_count
        call_count += 1
        target = captured_first if call_count == 1 else captured_second
        target["context_id"] = a2a_context_id_var.get()
        target["user_id"] = a2a_user_id_var.get()
        return agent_result

    with patch.object(
        async_orchestrator, "_process_agent_execution", side_effect=capture_and_process
    ):
        # Invocation 1: USER with context
        a2a_context = A2AContext(context_id="ctx-user-1")
        await async_orchestrator.invoke_with_source_async(
            "hello", "user-A", MessageSourceType.USER, a2a_context=a2a_context
        )

        # Invocation 2: NOTIFICATION with no context
        await async_orchestrator.invoke_with_source_async(
            "ping", "SYSTEM", MessageSourceType.NOTIFICATION
        )

    # First invocation should have the user's values
    assert captured_first["context_id"] == "ctx-user-1"
    assert captured_first["user_id"] == "user-A"

    # Second invocation must NOT see stale values
    assert captured_second["context_id"] is None
    assert captured_second["user_id"] is None
