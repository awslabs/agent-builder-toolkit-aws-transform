"""
Unit tests for example tools.
"""

from unittest import mock

import pytest
from strands import ToolContext

from agent_builder_sdk.custom_types.orchestrator_agent_types import A2AContext
from agent_builder_sdk.orchestrator_strands.tools.example_tools import (
    _background_tasks,
    _do_research_background,
    research_topic,
)


def create_mock_tool_context(invocation_state: dict) -> ToolContext:
    """Helper to create a mock ToolContext with required parameters."""
    mock_tool_use = mock.Mock()
    mock_agent = mock.Mock()
    return ToolContext(tool_use=mock_tool_use, agent=mock_agent, invocation_state=invocation_state)


class TestExampleTools:
    """Test cases for example tools."""

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.orchestrator_strands.tools.example_tools.send_message")
    @mock.patch("agent_builder_sdk.orchestrator_strands.tools.example_tools.asyncio.sleep")
    async def test_do_research_background_success(self, mock_sleep, mock_send_message):
        """Test background research completes all stages."""
        # Setup
        mock_send_message.return_value = None
        mock_sleep.return_value = None
        a2a_context = A2AContext(context_id="test-context-123")

        # Call function
        await _do_research_background("Test Topic", a2a_context)

        # Verify 6 progress messages + 1 final summary = 7 total
        assert mock_send_message.call_count == 7

        # Verify sleep was called 6 times (once per stage)
        assert mock_sleep.call_count == 6

        # Verify message content
        first_call = mock_send_message.call_args_list[0]
        assert "Research progress (1/6)" in first_call[1]["message"]
        assert first_call[1]["context_id"] == "test-context-123"
        assert first_call[1]["target_agent_instance_id"] == "ATX_CHAT"

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.orchestrator_strands.tools.example_tools.send_message")
    async def test_do_research_background_no_context_id(self, mock_send_message):
        """Test background research handles missing context_id."""
        # Setup
        a2a_context = A2AContext(context_id=None)

        # Call function
        await _do_research_background("Test Topic", a2a_context)

        # Verify no messages were sent
        mock_send_message.assert_not_called()

    @pytest.mark.asyncio
    @mock.patch("agent_builder_sdk.orchestrator_strands.tools.example_tools.send_message")
    @mock.patch("agent_builder_sdk.orchestrator_strands.tools.example_tools.asyncio.sleep")
    async def test_do_research_background_handles_send_error(self, mock_sleep, mock_send_message):
        """Test background research continues despite send errors."""

        # Setup - create async side effect function
        async def raise_error(*args, **kwargs):
            raise Exception("Network error")

        mock_send_message.side_effect = raise_error
        mock_sleep.return_value = None
        a2a_context = A2AContext(context_id="test-context-123")

        # Call function - should not raise exception
        await _do_research_background("Test Topic", a2a_context)

        # Verify all 7 stages attempted to send messages (6 progress + 1 final)
        assert mock_send_message.call_count == 7

    @pytest.mark.asyncio
    @mock.patch(
        "agent_builder_sdk.orchestrator_strands.tools.example_tools.asyncio.create_task"
    )
    async def test_research_topic_success(self, mock_create_task):
        """Test research_topic creates background task."""
        # Setup
        mock_task = mock.Mock()
        mock_create_task.return_value = mock_task
        a2a_context = A2AContext(context_id="test-context-456")

        tool_context = create_mock_tool_context({"a2a_context": a2a_context})

        # Call function
        result = await research_topic("Seattle Traffic", tool_context)

        # Verify result
        assert result == "Started researching 'Seattle Traffic' in the background."

        # Verify task was created
        mock_create_task.assert_called_once()

        # Verify task was added to background tasks set
        assert mock_task in _background_tasks

        # Verify done callback was added
        mock_task.add_done_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_topic_no_context(self):
        """Test research_topic handles missing A2A context."""
        # Setup
        tool_context = create_mock_tool_context({})

        # Call function
        result = await research_topic("Test Topic", tool_context)

        # Verify error message
        assert "Unable to start research" in result
        assert "no context provided" in result

    @pytest.mark.asyncio
    async def test_research_topic_no_context_id(self):
        """Test research_topic handles missing context_id."""
        # Setup
        a2a_context = A2AContext(context_id=None)
        tool_context = create_mock_tool_context({"a2a_context": a2a_context})

        # Call function
        result = await research_topic("Test Topic", tool_context)

        # Verify error message
        assert "Unable to start research" in result
        assert "no context provided" in result

    @pytest.mark.asyncio
    @mock.patch(
        "agent_builder_sdk.orchestrator_strands.tools.example_tools.asyncio.create_task"
    )
    async def test_research_topic_task_cleanup(self, mock_create_task):
        """Test background task is removed from set when done."""
        # Setup
        mock_task = mock.Mock()
        mock_create_task.return_value = mock_task
        a2a_context = A2AContext(context_id="test-context-789")

        tool_context = create_mock_tool_context({"a2a_context": a2a_context})

        # Call function
        await research_topic("Test Topic", tool_context)

        # Get the callback that was registered
        callback = mock_task.add_done_callback.call_args[0][0]

        # Verify task is in set
        assert mock_task in _background_tasks

        # Simulate task completion by calling the callback
        callback(mock_task)

        # Verify task was removed from set
        assert mock_task not in _background_tasks
