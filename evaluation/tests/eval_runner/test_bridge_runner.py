# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bridge_runner.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from eval_runner.execution.bridge_runner import (
    BridgeResponseStatus,
    BridgeRunner,
)


class TestBridgeResponseParsing:
    """Tests for _make_response logic via BridgeRunner."""

    @pytest.fixture()
    def runner(self) -> BridgeRunner:
        """Create a BridgeRunner."""
        r = BridgeRunner(session_name="test")
        return r

    def test_parse_success(self, runner: BridgeRunner) -> None:
        """SUCCESS result extracts text from response field."""
        result = runner._make_response("SUCCESS", {"response": "world", "usage": None}, [])
        assert result.status == BridgeResponseStatus.SUCCESS
        assert result.text == "world"

    def test_parse_approval_needed(self, runner: BridgeRunner) -> None:
        """APPROVAL_NEEDED extracts tool_call_id and options."""
        data = {
            "tool_call_id": "tc-123",
            "tool": "fs_write",
            "title": "Creating file.txt",
            "options": ["allow_once", "reject_once"],
        }
        result = runner._make_response("APPROVAL_NEEDED", data, [])
        assert result.status == BridgeResponseStatus.APPROVAL_NEEDED
        assert result.tool_call_id == "tc-123"
        assert result.tool_name == "fs_write"
        assert result.approval_options == ["allow_once", "reject_once"]

    def test_parse_timeout(self, runner: BridgeRunner) -> None:
        """TIMEOUT status is parsed correctly."""
        result = runner._make_response("TIMEOUT", {"error": "Exceeded 60s"}, [])
        assert result.status == BridgeResponseStatus.TIMEOUT
        assert "60s" in (result.error or "")

    def test_parse_error_status(self, runner: BridgeRunner) -> None:
        """FAILED status is handled."""
        result = runner._make_response("FAILED", {"error": "ACP process died"}, [])
        assert result.status == BridgeResponseStatus.FAILED
        assert "ACP process died" in (result.error or "")

    def test_parse_with_tool_calls(self, runner: BridgeRunner) -> None:
        """Tool calls from on_event are included in response."""
        tool_calls = [
            {"tool": "shell", "kind": "execute", "status": "success"},
            {"tool": "read", "kind": "read", "status": "success"},
        ]
        result = runner._make_response("SUCCESS", {"response": "done"}, tool_calls)
        assert result.status == BridgeResponseStatus.SUCCESS
        assert len(result.tool_calls) == 2

    def test_parse_with_usage(self, runner: BridgeRunner) -> None:
        """Token usage is extracted from data."""
        usage = {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150}
        result = runner._make_response("SUCCESS", {"response": "hi", "usage": usage}, [])
        assert result.usage == usage


class TestBridgeRunnerPrompt:
    """Tests for the prompt method with auto-approval."""

    @pytest.fixture()
    def runner_with_mock(self) -> tuple[BridgeRunner, MagicMock]:
        """Create a BridgeRunner with a mocked ACPClient."""
        r = BridgeRunner(
            session_name="test",
            cwd="/tmp",
        )
        # Create a mock client
        mock_client = MagicMock()
        mock_client.log_path = "/tmp/test.log"
        r._client = mock_client
        r._started = True
        return r, mock_client

    def test_prompt_success_no_approval(
        self, runner_with_mock: tuple[BridgeRunner, MagicMock]
    ) -> None:
        """Simple prompt that succeeds without tool approval."""
        runner, mock_client = runner_with_mock
        mock_client.prompt.return_value = ("SUCCESS", {"response": "hi there"})

        response = runner.prompt(agent="test-agent", text="hello")
        assert response.status == BridgeResponseStatus.SUCCESS
        assert response.text == "hi there"
        assert response.log_path == "/tmp/test.log"

    def test_prompt_auto_approve_loop(
        self, runner_with_mock: tuple[BridgeRunner, MagicMock]
    ) -> None:
        """Prompt that triggers approval, auto-approves, and succeeds."""
        runner, mock_client = runner_with_mock

        # First call: APPROVAL_NEEDED
        mock_client.prompt.return_value = (
            "APPROVAL_NEEDED",
            {
                "tool_call_id": "tc-abc",
                "tool": "fs_write",
                "options": ["allow_once", "reject_once"],
            },
        )
        # Second call: SUCCESS after approval
        mock_client.send_approval.return_value = (
            "SUCCESS",
            {"response": "File written."},
        )

        response = runner.prompt(agent="test-agent", text="write file")
        assert response.status == BridgeResponseStatus.SUCCESS
        assert response.text == "File written."

        # Verify send_approval was called with on_event callback
        mock_client.send_approval.assert_called_once()
        call_args = mock_client.send_approval.call_args
        assert call_args[0][0] == "allow_once"
        assert call_args[1].get("on_event") is not None

    def test_prompt_no_auto_approve(self, runner_with_mock: tuple[BridgeRunner, MagicMock]) -> None:
        """When auto_approve=False, APPROVAL_NEEDED is returned to caller."""
        runner, mock_client = runner_with_mock
        mock_client.prompt.return_value = (
            "APPROVAL_NEEDED",
            {
                "tool_call_id": "tc-abc",
                "tool": "fs_write",
                "options": ["allow_once"],
            },
        )

        response = runner.prompt(agent="test-agent", text="write file", auto_approve=False)
        assert response.status == BridgeResponseStatus.APPROVAL_NEEDED
        assert response.tool_call_id == "tc-abc"
        mock_client.send_approval.assert_not_called()

    def test_prompt_exceeds_max_approvals(
        self, runner_with_mock: tuple[BridgeRunner, MagicMock]
    ) -> None:
        """Auto-approve loop stops after max_approvals and returns ERROR."""
        runner, mock_client = runner_with_mock
        # Always return APPROVAL_NEEDED
        approval_data = {
            "tool_call_id": "tc-loop",
            "tool": "shell",
            "options": ["allow_once"],
        }
        mock_client.prompt.return_value = ("APPROVAL_NEEDED", approval_data)
        mock_client.send_approval.return_value = ("APPROVAL_NEEDED", approval_data)

        response = runner.prompt(agent="test-agent", text="loop", max_approvals=3)
        assert response.status == BridgeResponseStatus.ERROR
        assert "max approvals" in (response.error or "").lower()
        assert mock_client.send_approval.call_count == 3
        assert response.log_path is not None  # log_path preserved on error

    def test_prompt_timeout(self, runner_with_mock: tuple[BridgeRunner, MagicMock]) -> None:
        """TIMEOUT from ACPClient is propagated correctly."""
        runner, mock_client = runner_with_mock
        mock_client.prompt.return_value = ("TIMEOUT", {"error": "Exceeded 120s"})

        response = runner.prompt(agent="test-agent", text="slow")
        assert response.status == BridgeResponseStatus.TIMEOUT
        assert "120s" in (response.error or "")
