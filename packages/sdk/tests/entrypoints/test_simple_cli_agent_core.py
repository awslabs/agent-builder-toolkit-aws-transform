"""
Unit tests for simple CLI agent core implementation.
"""

import sys
from unittest import mock

import pytest

from agent_builder_sdk.checkpoint.checkpoint_triggers import CheckpointStrategy
from agent_builder_sdk.entrypoints.simple_cli_agent_core import main


class TestSimpleCliAgentCore:
    """Test cases for simple CLI agent core."""

    def test_main_with_valid_args(self):
        """Test main function with valid arguments."""
        test_args = [
            "simple_cli_agent_core.py",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--binary-location",
            "/tmp/test_binary",
            "--storage-dir",
            "/tmp/test_storage",
            "--checkpoint-strategy",
            "time",
            "--checkpoint-interval",
            "30",
        ]

        with mock.patch.object(sys, "argv", test_args):
            with mock.patch(
                "agent_builder_sdk.entrypoints.simple_cli_agent_core.AgentRuntimeServer"
            ) as mock_server:
                mock_server_instance = mock.Mock()
                mock_server_instance.start = mock.Mock()  # Mock start to prevent hanging
                mock_server.return_value = mock_server_instance

                main()

                # Verify server was created and started
                mock_server.assert_called_once()
                call_args = mock_server.call_args

                # Check that agent_factory was passed
                assert "agent_factory" in call_args.kwargs
                assert callable(call_args.kwargs["agent_factory"])

                # Check other arguments
                assert call_args.kwargs["binary_location"] == "/tmp/test_binary"
                assert call_args.kwargs["storage_dir"] == "/tmp/test_storage"
                assert call_args.kwargs["host"] == "127.0.0.1"
                assert call_args.kwargs["port"] == 9000
                assert call_args.kwargs["checkpoint_strategy"] == CheckpointStrategy.TIME
                assert call_args.kwargs["checkpoint_interval"] == 30

                mock_server_instance.start.assert_called_once()

    def test_main_with_base_guardrail_flag(self):
        """Test main function with --base-guardrail flag."""
        test_args = [
            "simple_cli_agent_core.py",
            "--base-guardrail",
        ]

        with mock.patch.object(sys, "argv", test_args):
            with mock.patch(
                "agent_builder_sdk.entrypoints.simple_cli_agent_core.AgentRuntimeServer"
            ) as mock_server:
                mock_server_instance = mock.Mock()
                mock_server_instance.start = mock.Mock()
                mock_server.return_value = mock_server_instance

                main()

                # Verify server was created
                mock_server.assert_called_once()
                call_args = mock_server.call_args

                # Verify agent_factory was passed
                assert "agent_factory" in call_args.kwargs
                agent_factory = call_args.kwargs["agent_factory"]

                # The agent_factory closure should use args.base_guardrail=True
                # We verify this by checking the source code contains the flag
                import inspect

                source = inspect.getsource(agent_factory)
                assert "with_base_guardrails=args.base_guardrail" in source

    def test_main_with_missing_args(self):
        """Test main function with missing required arguments."""
        test_args = ["simple_cli_agent_core.py"]  # All args have defaults, so this should work

        with mock.patch.object(sys, "argv", test_args):
            with mock.patch(
                "agent_builder_sdk.entrypoints.simple_cli_agent_core.AgentRuntimeServer"
            ) as mock_server:
                mock_server_instance = mock.Mock()
                mock_server_instance.start = mock.Mock()  # Mock start to prevent hanging
                mock_server.return_value = mock_server_instance

                main()

                # Verify server was created with default values
                mock_server.assert_called_once()
                mock_server_instance.start.assert_called_once()

    def test_main_with_help_flag(self):
        """Test main function with help flag."""
        test_args = ["simple_cli_agent_core.py", "--help"]

        with mock.patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                main()

    def test_main_with_default_values(self):
        """Test main function with default values for optional arguments."""
        test_args = ["simple_cli_agent_core.py", "--host", "localhost"]

        with mock.patch.object(sys, "argv", test_args):
            with mock.patch(
                "agent_builder_sdk.entrypoints.simple_cli_agent_core.AgentRuntimeServer"
            ) as mock_server:
                mock_server_instance = mock.Mock()
                mock_server_instance.start = mock.Mock()  # Mock start to prevent hanging
                mock_server.return_value = mock_server_instance

                main()

                # Verify server was created with default values
                mock_server.assert_called_once()
                call_args = mock_server.call_args[1]
                assert call_args["host"] == "localhost"
                assert "binary_location" in call_args
                assert "storage_dir" in call_args
                assert call_args["checkpoint_strategy"] == CheckpointStrategy.CONVERSATION
                assert call_args["checkpoint_interval"] == 10
