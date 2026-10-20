# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the SendMessageTools class."""

import uuid
from unittest.mock import Mock, patch

import pytest
from strands import ToolContext

from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.orchestrator_strands.tools.send_message_tools import SendMessageTools
from agent_builder_sdk.utils import A2A_SOURCE_INFORMATION_EXT


@pytest.fixture
def send_message_tools():
    """Create a SendMessageTools instance."""
    return SendMessageTools()


class TestSendMessageTools:
    """Test class for SendMessageTools."""

    def test_initialization(self):
        """Test SendMessageTools initialization."""
        tools = SendMessageTools()
        assert isinstance(tools, SendMessageTools)

    def test_construct_message(self, send_message_tools):
        """Test _construct_message method."""
        message = send_message_tools._construct_message("Test message", "sender")
        assert isinstance(message, A2AMessage)
        assert message.role == "agent"
        assert message.parts == [{"kind": "text", "text": "Test message"}]
        assert message.kind == "message"
        assert message.metadata == {A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "sender"}}
        assert message.extensions == [A2A_SOURCE_INFORMATION_EXT]
        assert isinstance(message.messageId, str)
        # Verify messageId is a valid UUID
        uuid.UUID(message.messageId)

    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    def test_send_message_to_subagent_success(
        self, mock_get_context, mock_get_client, send_message_tools
    ):
        """Test successful send_message_to_subagent."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )

        # Call the tool
        result = send_message_tools.send_message_to_subagent("subagent-456", "Test message")

        # Verify result
        assert result == mock_client.send_message.return_value

        # Verify client was called correctly
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["agentInstanceId"] == "subagent-456"
        message_dict = call_kwargs["params"]["message"]
        assert message_dict["role"] == "agent"
        assert message_dict["parts"] == [{"kind": "text", "text": "Test message"}]
        assert message_dict["kind"] == "message"
        assert message_dict["metadata"] == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "sender"}
        }
        assert message_dict["extensions"] == [A2A_SOURCE_INFORMATION_EXT]
        assert "messageId" in message_dict
        assert call_kwargs["requestContext"] == mock_get_context.return_value.to_dict()

    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    def test_send_message_to_subagent_client_exception(self, mock_get_client, send_message_tools):
        """Test send_message_to_subagent when client raises exception."""
        # Setup mock to raise exception
        mock_get_client.side_effect = Exception("API error")

        # Call the tool and expect exception
        with pytest.raises(Exception) as exc_info:
            send_message_tools.send_message_to_subagent("subagent-456", "Test message")

        # Verify exception message
        assert "API error" in str(exc_info.value)

    @patch("agent_builder_sdk.orchestrator_strands.tools.send_message_tools.logger")
    def test_initialization_logging(self, mock_logger):
        """Test that initialization logs appropriately."""
        SendMessageTools()
        mock_logger.info.assert_called_with("Initialized SendMessageTools")

    @patch("agent_builder_sdk.orchestrator_strands.tools.send_message_tools.logger")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    def test_success_logging(
        self, mock_get_context, mock_get_client, mock_logger, send_message_tools
    ):
        """Test that successful operations are logged appropriately."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_context = Mock()
        mock_context.to_dict.return_value = {"job_id": "job-123"}
        mock_get_context.return_value = mock_context

        # Call the tool
        send_message_tools.send_message_to_subagent("subagent-456", "Test message")

        # Verify success was logged
        mock_logger.info.assert_called_with("Message sent to subagent subagent-456.")

    @pytest.mark.asyncio
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_async_send_message_to_subagent_success(
        self, mock_get_context, mock_get_client, send_message_tools
    ):
        """Test successful async_send_message_to_subagent."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )

        # Call the async tool
        result = await send_message_tools.async_send_message_to_subagent(
            "subagent-456", "Test message"
        )

        # Verify result
        assert result == mock_client.send_message.return_value

        # Verify client was called correctly
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["agentInstanceId"] == "subagent-456"
        message_dict = call_kwargs["params"]["message"]
        assert message_dict["role"] == "agent"
        assert message_dict["parts"] == [{"kind": "text", "text": "Test message"}]
        assert message_dict["kind"] == "message"
        assert message_dict["metadata"] == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "sender"}
        }
        assert message_dict["extensions"] == [A2A_SOURCE_INFORMATION_EXT]
        assert "messageId" in message_dict
        assert call_kwargs["requestContext"] == mock_get_context.return_value.to_dict()

    @pytest.mark.asyncio
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    async def test_async_send_message_to_subagent_client_exception(
        self, mock_get_client, send_message_tools
    ):
        """Test async_send_message_to_subagent when client raises exception."""
        # Setup mock to raise exception
        mock_get_client.side_effect = Exception("API error")

        # Call the async tool and expect exception
        with pytest.raises(Exception) as exc_info:
            await send_message_tools.async_send_message_to_subagent("subagent-456", "Test message")

        # Verify exception message
        assert "API error" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("agent_builder_sdk.orchestrator_strands.tools.send_message_tools.logger")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_async_success_logging(
        self, mock_get_context, mock_get_client, mock_logger, send_message_tools
    ):
        """Test that successful async operations are logged appropriately."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_context = Mock()
        mock_context.to_dict.return_value = {"job_id": "job-123"}
        mock_get_context.return_value = mock_context

        # Call the async tool
        await send_message_tools.async_send_message_to_subagent("subagent-456", "Test message")

        # Verify success was logged
        mock_logger.info.assert_called_with("Message sent to subagent subagent-456.")


class TestRelayMessageFromSubagent:
    """Tests for the terminating relay tool send_message_to_subagent_and_relay."""

    def test_registered_tool_name_matches_relay_constant(self):
        """Drift guard: the AG-UI adapter identifies relayed tool_stream events by matching the
        tool name against RELAY_TOOL_NAME. If this tool is renamed without updating the constant,
        the relay branch would silently stop matching — so pin them together here."""
        from agent_builder_sdk.streaming.a2a_frame_utils import RELAY_TOOL_NAME

        assert SendMessageTools.send_message_to_subagent_and_relay.tool_name == RELAY_TOOL_NAME

    def _sse_iter(self, *frames):
        """A plain sync iterator of frame dicts (what stream_send_message returns)."""
        return iter(frames)

    @staticmethod
    def _working(event):
        from agent_builder_sdk.streaming.a2a_frame_utils import RAW_EXT_URI

        return {
            "kind": "status-update",
            "final": False,
            "status": {
                "state": "working",
                "message": {"parts": [{"kind": "data", "data": {RAW_EXT_URI: event}}]},
            },
        }

    @staticmethod
    def _failed(event):
        """A failed/final terminal frame carrying an event (matches raw_a2a_emitter.error_frames)."""
        from agent_builder_sdk.streaming.a2a_frame_utils import RAW_EXT_URI

        return {
            "kind": "status-update",
            "final": True,
            "status": {
                "state": "failed",
                "message": {"parts": [{"kind": "data", "data": {RAW_EXT_URI: event}}]},
            },
        }

    @staticmethod
    def _tool_context(request_state):
        return ToolContext(
            tool_use=Mock(), agent=Mock(), invocation_state={"request_state": request_state}
        )

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_success_terminates_and_relays_text(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"data": "Jupiter"}),
            self._working({"data": " is largest"}),
            {"kind": "status-update", "final": True, "status": {"state": "completed"}},
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        # Live: the sub-agent's text-delta events are yielded as they arrive (relayed to the user);
        # the final yield is the aggregated answer (the tool result -> orchestrator context).
        assert {"data": "Jupiter"} in outputs
        assert outputs[-1] == "Jupiter is largest"
        # Terminating: the subagent's answer becomes the final response and the loop stops.
        assert request_state["force_stop_response"] == "Jupiter is largest"
        assert request_state["stop_event_loop"] is True

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_completed_with_no_content_is_non_terminating(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        """A subagent that completes without any answer text must NOT force-stop on an empty
        response (that would end the turn silently); it hands control back to the orchestrator."""
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            {"kind": "status-update", "final": True, "status": {"state": "completed"}},
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        # Reports the empty completion to the orchestrator as the tool result...
        assert "subagent-456" in outputs[-1]
        assert "no content" in outputs[-1]
        # ...and stays non-terminating so the orchestrator can decide the next step.
        assert "force_stop_response" not in request_state
        assert "stop_event_loop" not in request_state

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_whitespace_only_answer_is_non_terminating(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        """Content that strips to empty is treated the same as no content (not a forced empty stop)."""
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            self._working({"data": "   "}),
            self._working({"data": "\n"}),
            {"kind": "status-update", "final": True, "status": {"state": "completed"}},
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        # The whitespace chunks were still relayed live, but the empty aggregate does not force-stop.
        assert "no content" in outputs[-1]
        assert "force_stop_response" not in request_state
        assert "stop_event_loop" not in request_state

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_failed_terminal_is_non_terminating(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "status-update", "final": True, "status": {"state": "failed"}},
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        assert "subagent-456" in outputs[-1]
        # Non-terminating on failure: the orchestrator stays in control.
        assert "force_stop_response" not in request_state
        assert "stop_event_loop" not in request_state

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_failed_terminal_error_text_goes_to_orchestrator_not_user(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        err_event = {"data": "The request took too long to process.", "error": True}
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._failed(err_event),
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        # The error text is the tool result (goes to the orchestrator)...
        assert outputs[-1] == "The request took too long to process."
        # ...but is NOT streamed live to the user as a relayed event.
        assert err_event not in outputs
        # Non-terminating: the orchestrator stays in control.
        assert "force_stop_response" not in request_state
        assert "stop_event_loop" not in request_state

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_content_then_error_relays_content_then_hands_error_to_orchestrator(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        err_event = {"data": "An internal error occurred.", "error": True}
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            self._working({"data": "Partial "}),
            self._working({"data": "answer"}),
            self._failed(err_event),
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        # Content that arrived before the failure was relayed live...
        assert {"data": "Partial "} in outputs
        assert {"data": "answer"} in outputs
        # ...the error text is handed to the orchestrator as the result, not streamed...
        assert outputs[-1] == "An internal error occurred."
        assert err_event not in outputs
        # ...and the turn stays non-terminating.
        assert "force_stop_response" not in request_state

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_truncated_stream_without_terminal_is_non_terminating(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        """A stream that ends with partial content and NO terminal frame (dropped connection,
        LB/upstream timeout, subagent death mid-turn) must NOT be persisted as the final answer;
        it hands the truncation back to the orchestrator like the failure/empty branches."""
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        # Content arrives, then the iterator simply exhausts — no completed/failed terminal frame.
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"data": "Partial "}),
            self._working({"data": "answer"}),
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        # The partial content was relayed live as it arrived...
        assert {"data": "Partial "} in outputs
        assert {"data": "answer"} in outputs
        # ...but the truncation is reported to the orchestrator, not force-stopped as the answer.
        assert "truncated" in outputs[-1]
        assert outputs[-1] != "Partial answer"
        assert "force_stop_response" not in request_state
        assert "stop_event_loop" not in request_state

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_terminal_completed_frame_still_terminates(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        """Control for the truncation case: identical content but WITH a completed terminal frame
        must take the success path and force-stop with the relayed answer."""
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"data": "Partial "}),
            self._working({"data": "answer"}),
            {"kind": "status-update", "final": True, "status": {"state": "completed"}},
        )
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        assert outputs[-1] == "Partial answer"
        assert request_state["force_stop_response"] == "Partial answer"
        assert request_state["stop_event_loop"] is True

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_exception_is_non_terminating(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.side_effect = RuntimeError("boom")
        mock_get_manager.return_value = manager

        request_state: dict = {}
        gen = send_message_tools.send_message_to_subagent_and_relay(
            "subagent-456", "Q", tool_context=self._tool_context(request_state)
        )
        outputs = [chunk async for chunk in gen]

        assert "Error streaming" in outputs[-1]
        assert request_state == {}


class TestStreamMessageToSubagent:
    """Tests for the aggregate-and-return tool stream_message_to_subagent.

    Unlike the relay tool, this one streams the subagent's reply, aggregates the FINAL answer text,
    and RETURNS it (a plain coroutine tool) so the orchestrator keeps working — it never yields events
    live and never touches request_state.
    """

    def test_registered_tool_name(self):
        """The tool name Strands exposes to the LLM must stay stable."""
        assert SendMessageTools.stream_message_to_subagent.tool_name == "stream_message_to_subagent"

    @staticmethod
    def _sse_iter(*frames):
        return iter(frames)

    @staticmethod
    def _working(event):
        from agent_builder_sdk.streaming.a2a_frame_utils import RAW_EXT_URI

        return {
            "kind": "status-update",
            "final": False,
            "status": {
                "state": "working",
                "message": {"parts": [{"kind": "data", "data": {RAW_EXT_URI: event}}]},
            },
        }

    @staticmethod
    def _failed(event):
        from agent_builder_sdk.streaming.a2a_frame_utils import RAW_EXT_URI

        return {
            "kind": "status-update",
            "final": True,
            "status": {
                "state": "failed",
                "message": {"parts": [{"kind": "data", "data": {RAW_EXT_URI: event}}]},
            },
        }

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_success_aggregates_final_text_only(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        """Aggregates text deltas only; reasoning and tool-use frames are ignored (matches the
        buffered final-answer text)."""
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"reasoningText": "thinking...", "reasoning": True}),
            self._working({"data": "Jupiter"}),
            self._working({"type": "tool_use_stream", "current_tool_use": {"name": "x"}}),
            self._working({"data": " is largest"}),
            {"kind": "status-update", "final": True, "status": {"state": "completed"}},
        )
        mock_get_manager.return_value = manager

        result = await send_message_tools.stream_message_to_subagent("subagent-456", "Q")

        assert result == "Jupiter is largest"
        manager.stream_send_message.assert_called_once()
        call_kwargs = manager.stream_send_message.call_args[1]
        assert call_kwargs["agent_instance_id"] == "subagent-456"

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_completed_with_no_content(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"data": "   "}),
            {"kind": "status-update", "final": True, "status": {"state": "completed"}},
        )
        mock_get_manager.return_value = manager

        result = await send_message_tools.stream_message_to_subagent("subagent-456", "Q")

        assert "subagent-456" in result
        assert "no content" in result

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_failed_terminal_returns_error_text(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        err_event = {"data": "An internal error occurred.", "error": True}
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"data": "Partial "}),
            self._failed(err_event),
        )
        mock_get_manager.return_value = manager

        result = await send_message_tools.stream_message_to_subagent("subagent-456", "Q")

        # The subagent's error text is returned as the tool result, not the partial content.
        assert result == "An internal error occurred."

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_failed_terminal_without_error_text(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "status-update", "final": True, "status": {"state": "failed"}},
        )
        mock_get_manager.return_value = manager

        result = await send_message_tools.stream_message_to_subagent("subagent-456", "Q")

        assert "subagent-456" in result
        assert "failure" in result

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_truncated_stream_without_terminal(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.return_value = self._sse_iter(
            {"kind": "task", "status": {"state": "submitted"}},
            self._working({"data": "Partial "}),
            self._working({"data": "answer"}),
        )
        mock_get_manager.return_value = manager

        result = await send_message_tools.stream_message_to_subagent("subagent-456", "Q")

        assert "truncated" in result
        assert result != "Partial answer"

    @patch("agent_builder_sdk.agentic_framework.a2a_manager.get_a2a_manager")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_exception_returns_error_string(
        self, mock_get_context, mock_get_manager, send_message_tools
    ):
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )
        manager = Mock()
        manager.stream_send_message.side_effect = RuntimeError("boom")
        mock_get_manager.return_value = manager

        result = await send_message_tools.stream_message_to_subagent("subagent-456", "Q")

        assert "Error streaming from subagent subagent-456" in result
        assert "boom" in result
