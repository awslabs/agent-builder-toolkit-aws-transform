# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for simple_subagent_cli.py
"""

import os
import sys
from unittest import mock

from agent_builder_sdk.entrypoints.simple_subagent_cli import create_parser, main


class TestSimpleSubagentCLI:
    """Test cases for simple subagent CLI."""

    def test_create_parser_defaults(self):
        """Test parser creation with default values."""
        parser = create_parser()
        args = parser.parse_args([])

        assert args.host == "0.0.0.0"
        assert args.port == 8080
        assert args.storage_dir == "/tmp/sub_agent"
        assert args.region == os.getenv("AWS_REGION", "us-west-2")
        assert args.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
        assert (
            args.binary_location == "/home/amazon/AgentBuilderAgenticMCP/bin/agent-builder-agentic-mcp"
        )

    def test_create_parser_custom_values(self):
        """Test parser with custom command line arguments."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "--host",
                "127.0.0.1",
                "--port",
                "9090",
                "--storage-dir",
                "/custom/path",
                "--region",
                "us-east-1",
                "--model-id",
                "custom-model",
                "--binary-location",
                "/custom/binary",
            ]
        )

        assert args.host == "127.0.0.1"
        assert args.port == 9090
        assert args.storage_dir == "/custom/path"
        assert args.region == "us-east-1"
        assert args.model_id == "custom-model"
        assert args.binary_location == "/custom/binary"

    def test_main_with_valid_args(self):
        """Test main function with valid arguments."""
        test_args = [
            "simple_subagent_cli.py",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--binary-location",
            "/tmp/test_binary",
            "--storage-dir",
            "/tmp/test_storage",
        ]

        with mock.patch.object(sys, "argv", test_args):
            with mock.patch(
                "agent_builder_sdk.entrypoints.simple_subagent_cli.AgentRuntimeServer"
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

                mock_server_instance.start.assert_called_once()

    def test_main_with_default_values(self):
        """Test main function with default values for optional arguments."""
        test_args = ["simple_subagent_cli.py", "--host", "localhost"]

        with mock.patch.object(sys, "argv", test_args):
            with mock.patch(
                "agent_builder_sdk.entrypoints.simple_subagent_cli.AgentRuntimeServer"
            ) as mock_server:
                mock_server_instance = mock.Mock()
                mock_server_instance.start = mock.Mock()  # Mock start to prevent hanging
                mock_server.return_value = mock_server_instance

                main()

                # Verify server was created with default values
                mock_server.assert_called_once()
                call_args = mock_server.call_args[1]
                assert call_args["host"] == "localhost"
                assert "storage_dir" in call_args
