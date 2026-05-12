# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the subagent CLI module."""

from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from agent_builder_sdk.base_subagent.base_subagent import BaseSubagent
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.subagent_cli import (
    cleanup_process_safely,
    create_parser,
    main,
    run_console,
    setup_agent,
)


@pytest.fixture
def mock_subagent():
    """Create a mock BaseSubagent."""
    with patch("agent_builder_sdk.subagent_cli.BaseSubagent") as mock:
        instance = Mock(spec=BaseSubagent)
        mock.return_value = instance
        yield instance


@pytest.fixture
def parser():
    """Create an argument parser instance."""
    return create_parser()


def test_create_parser_defaults(parser):
    """Test create_parser with default values."""
    args = parser.parse_args([])

    # Check default values
    assert args.binary_location == "/home/amazon/AgentBuilderAgenticMCP/bin/agent-builder-agentic-mcp"
    assert args.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert args.region == "us-west-2"
    assert args.local_testing is False
    assert args.guardrail_version == "1"
    assert args.auth_token_refresh_session_duration == 43200  # New parameter


def test_create_parser_custom_args():
    """Test create_parser with custom arguments."""
    parser = create_parser()
    args = parser.parse_args(
        [
            "--binary-location",
            "/custom/binary",
            "--model-id",
            "custom-model",
            "--region",
            "us-east-1",
            "--guardrail-id",
            "test-guardrail",
            "--auth-token-refresh-session-duration",
            "3600",
            "--local-testing",
        ]
    )

    assert args.binary_location == "/custom/binary"
    assert args.model_id == "custom-model"
    assert args.region == "us-east-1"
    assert args.guardrail_id == "test-guardrail"
    assert args.auth_token_refresh_session_duration == 3600
    assert args.local_testing is True


def test_setup_agent():
    """Test setup_agent creates BaseSubagent correctly."""
    with patch("agent_builder_sdk.subagent_cli.BaseSubagent") as mock_subagent:

        # Create mock args
        args = Mock()
        args.model_id = "test-model"
        args.region = "us-west-2"
        args.guardrail_id = None
        args.guardrail_version = "1"

        mcp_args = {"binaryLocation": "/test/binary"}

        mock_subagent_instance = Mock()
        mock_subagent.return_value = mock_subagent_instance

        result = setup_agent(args, mcp_args)

        # Verify BaseSubagent was created with correct parameters
        mock_subagent.assert_called_once()
        call_args = mock_subagent.call_args
        assert call_args[1]["system_prompt"] == "You are a helpful assistant"
        assert call_args[1]["model_id"] == "test-model"
        assert call_args[1]["region_name"] == "us-west-2"

        # Verify the result is the subagent
        assert result == mock_subagent_instance


@pytest.mark.asyncio
async def test_run_console_exit_command():
    """Test run_console with exit command."""
    with patch("builtins.input", side_effect=["exit"]), patch("builtins.print"):
        mock_subagent = Mock()
        await run_console(mock_subagent)

        # Verify subagent was not called since we exited immediately
        mock_subagent.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_run_console_process_message():
    """Test run_console processes messages correctly."""
    # Mock the response
    mock_response = Mock()
    mock_response.message = "Test response"

    mock_subagent = Mock()
    mock_subagent.process_message.return_value = mock_response

    with patch("builtins.input", side_effect=["test message", "exit"]), patch(
        "builtins.print"
    ) as mock_print:
        await run_console(mock_subagent)

        # Verify subagent was called with correct message
        expected_request = ProcessMessageRequest(
            message="test message", context=ConversationContext()
        )
        mock_subagent.process_message.assert_called_once()
        actual_call = mock_subagent.process_message.call_args[0][0]
        assert actual_call.message == expected_request.message

        # Verify response was printed
        mock_print.assert_any_call("\nAgent Response: Test response")


@pytest.mark.asyncio
async def test_run_console_handles_exceptions():
    """Test run_console handles exceptions gracefully."""
    mock_subagent = Mock()
    mock_subagent.process_message.side_effect = Exception("Test error")

    with patch("builtins.input", side_effect=["test message", "exit"]), patch(
        "builtins.print"
    ) as mock_print:
        await run_console(mock_subagent)

        # Verify error was printed
        mock_print.assert_any_call("\nError: Test error")


def test_cleanup_process_safely_graceful_termination():
    """Test cleanup_process_safely with graceful termination."""
    mock_process = Mock()
    mock_process.is_alive.side_effect = [True, False]  # Alive initially, then terminated

    cleanup_process_safely(mock_process, "TestProcess", timeout=1)

    mock_process.terminate.assert_called_once()
    mock_process.join.assert_called_once_with(timeout=1)
    mock_process.kill.assert_not_called()


def test_cleanup_process_safely_force_kill():
    """Test cleanup_process_safely with force kill."""
    mock_process = Mock()
    mock_process.is_alive.side_effect = [True, True, False]  # Alive, still alive, then killed

    cleanup_process_safely(mock_process, "TestProcess", timeout=1)

    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_called_once()
    assert mock_process.join.call_count == 2  # Called after terminate and kill


def test_cleanup_process_safely_already_dead():
    """Test cleanup_process_safely with already dead process."""
    mock_process = Mock()
    mock_process.is_alive.return_value = False

    cleanup_process_safely(mock_process, "TestProcess")

    mock_process.terminate.assert_not_called()
    mock_process.kill.assert_not_called()


def test_cleanup_process_safely_none_process():
    """Test cleanup_process_safely with None process."""
    # Should not raise any exceptions
    cleanup_process_safely(None, "TestProcess")


def test_run_api_server_sync():
    """Test run_api_server_sync function."""
    with patch(
        "agent_builder_sdk.subagent_cli.start_subagent_api_server"
    ) as mock_start_server, patch("agent_builder_sdk.subagent_cli.logger"):
        # Create mock args and subagent
        args = Mock()
        mock_subagent = Mock()

        # Run API server
        from agent_builder_sdk.subagent_cli import run_api_server_sync

        run_api_server_sync(args, mock_subagent)

        # Verify start_subagent_api_server was called with subagent
        mock_start_server.assert_called_once_with(mock_subagent)


def test_run_api_server_sync_error():
    """Test run_api_server_sync with exception handling."""
    with patch(
        "agent_builder_sdk.subagent_cli.start_subagent_api_server"
    ) as mock_start_server, patch("agent_builder_sdk.subagent_cli.logger") as mock_logger:
        # Setup mock to raise exception
        mock_start_server.side_effect = Exception("API server failed")

        # Create mock args and subagent
        args = Mock()
        mock_subagent = Mock()

        # Run API server and expect exception
        from agent_builder_sdk.subagent_cli import run_api_server_sync

        with pytest.raises(Exception):
            run_api_server_sync(args, mock_subagent)

        # Verify error was logged
        mock_logger.error.assert_called_once()


class TestSubagentCLIIntegration:
    """Integration tests for subagent CLI components."""

    @pytest.mark.asyncio
    async def test_main_local_testing_mode(self):
        """Test main function in local testing mode."""
        with patch(
            "agent_builder_sdk.subagent_cli.create_parser"
        ) as mock_create_parser, patch(
            "agent_builder_sdk.subagent_cli.setup_agent"
        ) as mock_setup_agent, patch(
            "agent_builder_sdk.subagent_cli.run_console", new_callable=AsyncMock
        ) as mock_run_console, patch(
            "agent_builder_sdk.subagent_cli.build_mcp_args_from_parsed_args"
        ) as mock_build_mcp_args, patch(
            "agent_builder_sdk.subagent_cli.get_auth_token_refresher"
        ) as mock_auth_refresher, patch(
            "agent_builder_sdk.subagent_cli.initialize_agent_instance"
        ):
            from agent_builder_sdk.subagent_cli import main

            # Setup mock parser and args
            mock_parser = Mock()
            mock_args = Mock()
            mock_args.local_testing = True
            mock_args.auth_token_refresh_session_duration = 43200
            mock_parser.parse_args.return_value = mock_args
            mock_create_parser.return_value = mock_parser

            # Setup mock MCP args
            mock_mcp_args = {"binaryLocation": "/test/binary"}
            mock_build_mcp_args.return_value = mock_mcp_args

            # Setup mock subagent
            mock_subagent = Mock()
            mock_setup_agent.return_value = mock_subagent

            # Run main
            await main()

            # Verify auth token refresher was called
            mock_auth_refresher.assert_called_once_with(session_duration=43200)

            # Verify setup_agent was called with both args and mcp_args
            mock_setup_agent.assert_called_once_with(mock_args, mock_mcp_args)

            # Verify console mode was started
            mock_run_console.assert_called_once_with(mock_subagent)

    @pytest.mark.asyncio
    async def test_main_api_server_mode(self):
        """Test main function in API server mode."""
        with patch(
            "agent_builder_sdk.subagent_cli.create_parser"
        ) as mock_create_parser, patch(
            "agent_builder_sdk.subagent_cli.setup_agent"
        ) as mock_setup_agent, patch(
            "agent_builder_sdk.subagent_cli.Process"
        ) as mock_process, patch(
            "agent_builder_sdk.subagent_cli.logger"
        ) as mock_logger, patch(
            "agent_builder_sdk.subagent_cli.cleanup_process_safely"
        ) as mock_cleanup, patch(
            "asyncio.sleep", new_callable=AsyncMock
        ), patch(
            "agent_builder_sdk.subagent_cli.get_auth_token_refresher"
        ), patch(
            "agent_builder_sdk.subagent_cli.initialize_agent_instance"
        ), patch(
            "agent_builder_sdk.subagent_cli.build_mcp_args_from_parsed_args"
        ) as mock_build_mcp_args, patch(
            "agent_builder_sdk.subagent_cli.get_auth_token_refresher"
        ) as mock_auth_refresher:

            # Setup mock parser and args
            mock_parser = Mock()
            mock_args = Mock()
            mock_args.local_testing = False
            mock_args.auth_token_refresh_session_duration = 43200
            mock_parser.parse_args.return_value = mock_args
            mock_create_parser.return_value = mock_parser

            # Setup mock MCP args
            mock_mcp_args = {"binaryLocation": "/test/binary"}
            mock_build_mcp_args.return_value = mock_mcp_args

            # Setup mock subagent
            mock_subagent = Mock()
            mock_setup_agent.return_value = mock_subagent

            # Setup mock process
            mock_process_instance = Mock()
            mock_process_instance.pid = 12345
            mock_process_instance.is_alive.side_effect = [True, False]  # Alive once, then dead
            mock_process.return_value = mock_process_instance

            # Run main
            await main()

            # Verify auth token refresher was called
            mock_auth_refresher.assert_called_once_with(session_duration=43200)

            # Verify setup_agent was called
            mock_setup_agent.assert_called_once_with(mock_args, mock_mcp_args)

            # Verify API server process started
            mock_process.assert_called_once_with(
                target=ANY,
                args=[mock_args, mock_subagent],
                name="SubagentAPIServer",
                daemon=False,
            )
            mock_process_instance.start.assert_called_once()
            mock_logger.info.assert_any_call(
                f"API server started with PID: {mock_process_instance.pid}"
            )

            # Verify cleanup was called
            mock_cleanup.assert_called_once_with(mock_process_instance, "SubagentAPIServer")

    @pytest.mark.asyncio
    async def test_main_setup_failure(self):
        """Test main function when setup_agent fails."""
        with patch(
            "agent_builder_sdk.subagent_cli.create_parser"
        ) as mock_create_parser, patch(
            "agent_builder_sdk.subagent_cli.setup_agent"
        ) as mock_setup_agent, patch(
            "agent_builder_sdk.subagent_cli.logger"
        ) as mock_logger, patch(
            "agent_builder_sdk.subagent_cli.build_mcp_args_from_parsed_args"
        ) as mock_build_mcp_args, patch(
            "agent_builder_sdk.subagent_cli.get_auth_token_refresher"
        ) as mock_auth_refresher, patch(
            "agent_builder_sdk.subagent_cli.initialize_agent_instance"
        ):
            from agent_builder_sdk.subagent_cli import main

            # Setup mock parser and args
            mock_parser = Mock()
            mock_args = Mock()
            mock_args.local_testing = True
            mock_args.auth_token_refresh_session_duration = 43200
            mock_parser.parse_args.return_value = mock_args
            mock_create_parser.return_value = mock_parser

            # Setup mock MCP args
            mock_mcp_args = {"binaryLocation": "/test/binary"}
            mock_build_mcp_args.return_value = mock_mcp_args

            # Setup setup_agent to fail
            mock_setup_agent.side_effect = Exception("Setup failed")

            # Run main and expect SystemExit
            with pytest.raises(SystemExit) as exc_info:
                await main()

            # Verify exit code
            assert exc_info.value.code == 1

            # Verify auth token refresher was called before failure
            mock_auth_refresher.assert_called_once_with(session_duration=43200)

            # Verify setup_agent was called and failed
            mock_setup_agent.assert_called_once_with(mock_args, mock_mcp_args)
            mock_logger.error.assert_called_with("Application failed: Setup failed")

    @pytest.mark.asyncio
    async def test_main_initialize_agent_instance_failure(self):
        """Test main function when initialize_agent_instance fails."""
        with patch(
            "agent_builder_sdk.subagent_cli.create_parser"
        ) as mock_create_parser, patch(
            "agent_builder_sdk.subagent_cli.get_auth_token_refresher"
        ) as mock_auth_refresher, patch(
            "agent_builder_sdk.subagent_cli.initialize_agent_instance"
        ) as mock_initialize_agent, patch(
            "agent_builder_sdk.subagent_cli.logger"
        ) as mock_logger:
            from agent_builder_sdk.subagent_cli import main

            # Setup mock parser and args
            mock_parser = Mock()
            mock_args = Mock()
            mock_args.auth_token_refresh_session_duration = 43200
            mock_parser.parse_args.return_value = mock_args
            mock_create_parser.return_value = mock_parser

            # Setup initialize_agent_instance to fail
            mock_initialize_agent.side_effect = Exception("Initialization failed")

            # Run main and expect SystemExit
            with pytest.raises(SystemExit) as exc_info:
                await main()

            # Verify exit code
            assert exc_info.value.code == 1

            # Verify auth token refresher was called before failure
            mock_auth_refresher.assert_called_once_with(session_duration=43200)

            # Verify initialize_agent_instance was called and failed
            mock_initialize_agent.assert_called_once()
            mock_logger.error.assert_called_with(
                "Failed to initialize subagent instance: Initialization failed"
            )

    def test_run_main(self):
        """Test run_main function."""
        with patch("agent_builder_sdk.subagent_cli.asyncio.run") as mock_asyncio_run:
            from agent_builder_sdk.subagent_cli import run_main

            # Run the function
            run_main()

            # Verify asyncio.run was called with main
            mock_asyncio_run.assert_called_once()

    def test_run_main_keyboard_interrupt(self):
        """Test run_main handles KeyboardInterrupt."""
        with patch("agent_builder_sdk.subagent_cli.asyncio.run") as mock_asyncio_run, patch(
            "agent_builder_sdk.subagent_cli.logger"
        ) as mock_logger:
            from agent_builder_sdk.subagent_cli import run_main

            # Setup mock to raise KeyboardInterrupt
            mock_asyncio_run.side_effect = KeyboardInterrupt()

            # Run the function
            run_main()

            # Verify asyncio.run was called
            mock_asyncio_run.assert_called_once()
            # Verify interrupt was logged
            mock_logger.info.assert_called_with("Application interrupted by user")

    def test_run_main_exception(self):
        """Test run_main handles general exceptions."""
        with patch("agent_builder_sdk.subagent_cli.asyncio.run") as mock_asyncio_run, patch(
            "agent_builder_sdk.subagent_cli.logger"
        ) as mock_logger:
            from agent_builder_sdk.subagent_cli import run_main

            # Setup mock to raise exception
            mock_asyncio_run.side_effect = Exception("Test error")

            # Run the function and expect exception to be re-raised
            with pytest.raises(Exception, match="Test error"):
                run_main()

            # Verify asyncio.run was called
            mock_asyncio_run.assert_called_once()
            # Verify error was logged
            mock_logger.error.assert_called_with("Application failed with error: Test error")
