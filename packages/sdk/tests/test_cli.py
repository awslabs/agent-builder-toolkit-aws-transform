"""Tests for the CLI module."""

import os
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from strands.tools.mcp import MCPClient

from agent_builder_sdk.checkpoint.checkpoint_triggers import (
    ConversationTurnTrigger,
    TimeBasedTrigger,
)
from agent_builder_sdk.cli import (
    cleanup_process_safely,
    create_checkpoint_trigger,
    create_orchestrator,
    create_parser,
    initialize_background_checkpointer,
    main,
    run_api_server_sync,
    run_console,
    run_main,
    setup_agent,
    setup_ab_mcp_client,
    setup_tracing,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import BaseOrchestrator


@pytest.fixture
def mock_orchestrator():
    """Create a mock BaseOrchestrator."""
    with patch("agent_builder_sdk.cli.BaseOrchestrator") as mock:
        instance = Mock(spec=BaseOrchestrator)
        mock.return_value = instance
        yield instance


@pytest.fixture
def parser():
    """Create an argument parser instance."""
    return create_parser()


def test_create_parser_defaults(parser):
    """Test create_parser with default values."""
    args = parser.parse_args(["--binaryLocation", "/path/to/binary"])

    assert args.binaryLocation == "/path/to/binary"
    # Check default values
    assert args.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert args.region == "us-west-2"
    assert args.storage_dir == "/ramdisk/orchestrator_agent"
    assert args.queueStoragePath == "/tmp/agent_queue"
    assert args.tracing is None
    assert args.localTesting is False
    assert args.disableAgentLifecycle is False
    assert args.disableProdBedrockUsage is False
    # Check checkpoint defaults
    assert args.checkpoint_strategy is None
    assert args.checkpoint_interval == 30
    assert args.checkpoint_dir == "/ramdisk/orchestrator_agent"


def test_create_parser_checkpoint_args():
    """Test create_parser with checkpoint arguments."""
    with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

        parser = create_parser()
        args = parser.parse_args(
            [
                "--checkpoint-strategy",
                "conversation",
                "--checkpoint-interval",
                "50",
                "--checkpoint-dir",
                "/custom/checkpoint/path",
            ]
        )

    assert args.checkpoint_strategy == "conversation"
    assert args.checkpoint_interval == 50
    assert args.checkpoint_dir == "/custom/checkpoint/path"


def test_create_parser_checkpointing_disabled():
    """Test parser with checkpointing disabled (no strategy specified)."""
    parser = create_parser()
    args = parser.parse_args([])  # No checkpoint strategy specified

    # Checkpointing should be disabled when no strategy is provided
    assert args.checkpoint_strategy is None
    assert args.checkpoint_interval == 30  # Default value still set


def test_create_checkpoint_trigger():
    """Test create_checkpoint_trigger function."""

    # Test time trigger
    time_trigger = create_checkpoint_trigger("time", 15)
    assert isinstance(time_trigger, TimeBasedTrigger)
    assert time_trigger.interval_second == 900  # 15 minutes * 60

    # Test conversation trigger
    conv_trigger = create_checkpoint_trigger("conversation", 25)
    assert isinstance(conv_trigger, ConversationTurnTrigger)
    assert conv_trigger.turn_threshold == 25

    # Test invalid strategy
    with pytest.raises(ValueError, match="Unknown checkpoint strategy: invalid"):
        create_checkpoint_trigger("invalid", 10)


def test_initialize_background_checkpointer_disabled():
    """Test initialize_background_checkpointer when disabled."""

    mock_args = Mock()
    mock_args.checkpoint_strategy = None

    result = initialize_background_checkpointer(mock_args)
    assert result is None


def test_initialize_background_checkpointer_enabled():
    """Test initialize_background_checkpointer when enabled."""
    with patch(
        "agent_builder_sdk.cli.create_checkpoint_repository"
    ) as mock_create_manager, patch(
        "agent_builder_sdk.cli.create_checkpoint_trigger"
    ) as mock_create_trigger, patch(
        "agent_builder_sdk.cli.CheckpointManager"
    ) as mock_orchestrator, patch(
        "agent_builder_sdk.cli.BackgroundCheckpointer"
    ) as mock_checkpointer:

        mock_args = Mock()
        mock_args.checkpoint_strategy = "time"
        mock_args.checkpoint_dir = "/test/path"
        mock_args.checkpoint_interval = 20

        mock_manager = Mock()
        mock_trigger = Mock()
        mock_manager_instance = Mock()
        mock_bg_checkpointer = Mock()

        mock_create_manager.return_value = mock_manager
        mock_create_trigger.return_value = mock_trigger
        mock_orchestrator.return_value = mock_manager_instance
        mock_checkpointer.return_value = mock_bg_checkpointer

        result = initialize_background_checkpointer(mock_args)

        mock_create_manager.assert_called_once_with("/test/path")
        mock_manager.restore_if_available.assert_called_once()
        mock_create_trigger.assert_called_once_with("time", 20)
        mock_orchestrator.assert_called_once_with(mock_manager, mock_trigger)
        mock_checkpointer.assert_called_once_with(mock_manager_instance)
        mock_bg_checkpointer.enable.assert_called_once()

        assert result == mock_bg_checkpointer


def test_initialize_background_checkpointer_failure():
    """Test initialize_background_checkpointer handles failures gracefully."""
    with patch(
        "agent_builder_sdk.cli.create_checkpoint_repository",
        side_effect=Exception("Test error"),
    ):
        mock_args = Mock()
        mock_args.checkpoint_strategy = "time"
        mock_args.checkpoint_dir = "/test/path"
        mock_args.checkpoint_interval = 20

        result = initialize_background_checkpointer(mock_args)
        assert result is None


def test_create_parser_tracing_localhost_default():
    """Test create_parser with --tracing flag (requires a value)."""
    with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

        parser = create_parser()
        args = parser.parse_args(["--tracing", "local"])

    assert args.tracing == "local"


def test_create_parser_custom_args():
    """Test create_parser with custom arguments."""
    with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

        parser = create_parser()
        args = parser.parse_args(
            [
                "--model_id",
                "custom-model",
                "--region",
                "us-east-1",
                "--storage-dir",
                "/custom/storage",
                "--queueStoragePath",
                "/custom/queue",
                "--localTesting",
                "--disableAgentLifecycle",
                "--disableProdBedrockUsage",
                "--disableMcpUsage",
                "--tracing",
                "cloudwatch",
            ]
        )

    assert args.model_id == "custom-model"
    assert args.region == "us-east-1"
    assert args.storage_dir == "/custom/storage"
    assert args.queueStoragePath == "/custom/queue"
    assert args.tracing == "cloudwatch"
    assert args.localTesting is True
    assert args.disableAgentLifecycle is True
    assert args.disableProdBedrockUsage is True
    assert args.disableMcpUsage is True

    @pytest.mark.asyncio
    async def test_create_orchestrator_with_memory_components(self):
        """Test create_orchestrator creates memory components correctly."""
        # Mock all the dependencies individually
        with patch("agent_builder_sdk.cli.FileSystemRepository") as mock_fs_repo, patch(
            "agent_builder_sdk.cli.EpisodicMemory"
        ) as mock_episodic, patch(
            "agent_builder_sdk.cli.MemoryManager"
        ) as mock_memory_mgr, patch(
            "agent_builder_sdk.cli.MemoryTool"
        ) as mock_memory_tool, patch(
            "agent_builder_sdk.cli.FileMultiSourceConversationRepository"
        ) as mock_conv_repo, patch(
            "agent_builder_sdk.cli.ConversationHookProvider"
        ) as mock_conv_hook, patch(
            "agent_builder_sdk.cli.MemoryHookProvider"
        ) as mock_memory_hook, patch(
            "agent_builder_sdk.cli.BaseOrchestrator"
        ) as mock_orchestrator, patch(
            "agent_builder_sdk.cli.get_prompt_with_name", return_value="test_prompt"
        ):

            # Create mock args
            args = Mock()
            args.storage_dir = "/test/storage"
            args.model_id = "test-model"
            args.region = "us-west-2"
            args.guardrail_id = "test-guardrail-id"
            args.guardrail_version = "test-guardrail-version"

            mock_mcp_client = Mock(spec=MCPClient)
            mock_orchestrator_instance = Mock()
            mock_orchestrator.return_value = mock_orchestrator_instance

            result = create_orchestrator(args, mock_mcp_client)

            # Verify FileSystemRepository was created with correct path
            mock_fs_repo.assert_called_once_with(storage_path="/test/storage/memories")

            # Verify EpisodicMemory was created with repository
            mock_episodic.assert_called_once_with(repository=mock_fs_repo.return_value)

            # Verify MemoryManager was created with episodic memory
            mock_memory_mgr.assert_called_once_with(memories=[mock_episodic.return_value])

            # Verify MemoryTool was created with memory manager
            mock_memory_tool.assert_called_once_with(mock_memory_mgr.return_value)

            # Verify conversation repository was created
            mock_conv_repo.assert_called_once_with(storage_dir="/test/storage")

            # Verify hooks were created
            mock_conv_hook.assert_called_once_with(repository=mock_conv_repo.return_value)
            mock_memory_hook.assert_called_once_with(memory_manager=mock_memory_mgr.return_value)

            # Verify BaseOrchestrator was created with correct parameters
            mock_orchestrator.assert_called_once_with(
                system_prompt="test_prompt",
                hooks=[
                    mock_conv_hook.return_value,
                    mock_memory_hook.return_value,
                ],
                model_id="test-model",
                region_name="us-west-2",
                custom_tools=[mock_memory_tool.return_value.memory],
            )

            # Verify the result is the orchestrator
            assert result == mock_orchestrator.return_value

    @pytest.mark.asyncio
    async def test_setup_agent_local_testing(self):
        """Test setup_agent in local testing mode."""
        with patch("agent_builder_sdk.cli.QueueService") as mock_queue_service, patch(
            "agent_builder_sdk.cli.QueueRequestHandler"
        ) as mock_request_handler, patch(
            "agent_builder_sdk.cli.create_orchestrator"
        ) as mock_create_orchestrator, patch(
            "agent_builder_sdk.cli.setup_ab_mcp_client"
        ) as mock_setup_mcp:

            # Create mock args
            args = Mock()
            args.localTesting = True
            args.queueStoragePath = "/test/queue"

            # Create mock mcp_args
            mcp_args = {"binaryLocation": "/path/to/binary", "workspaceId": "test-workspace"}

            # Call the function
            agent, queue_service, request_handler = setup_agent(args, mcp_args)

            # Verify setup_ab_mcp_client was called
            mock_setup_mcp.assert_called_once_with(mcp_args)

            # Verify queue service was created
            mock_queue_service.assert_called_once_with(storage_path="/test/queue")

            # Verify request handler was created
            mock_request_handler.assert_called_once_with(
                request_queue=mock_queue_service.return_value.request_queue,
                response_store=mock_queue_service.return_value.response_store,
            )

            # Verify create_orchestrator was called with args and mcp_client
            mock_create_orchestrator.assert_called_once_with(args, mock_setup_mcp.return_value)

            # Verify return values
            assert agent == mock_create_orchestrator.return_value
            assert queue_service == mock_queue_service.return_value
            assert request_handler == mock_request_handler.return_value

    @pytest.mark.asyncio
    async def test_setup_agent_production_mode(self):
        """Test setup_agent in production mode."""
        with patch("agent_builder_sdk.cli.QueueService") as mock_queue_service, patch(
            "agent_builder_sdk.cli.QueueRequestHandler"
        ) as mock_request_handler, patch(
            "agent_builder_sdk.cli.create_orchestrator", new_callable=AsyncMock
        ) as mock_create_orchestrator:

            # Create mock args
            args = Mock()
            args.localTesting = False
            args.queueStoragePath = "/test/queue"

            # Call the function
            agent, queue_service, request_handler = await setup_agent(args)

            # Verify queue service was created
            mock_queue_service.assert_called_once_with(storage_path="/test/queue")

            # Verify request handler was created
            mock_request_handler.assert_called_once_with(
                request_queue=mock_queue_service.return_value.request_queue,
                response_store=mock_queue_service.return_value.response_store,
            )

            # Verify create_orchestrator was called with request_handler for production mode
            mock_create_orchestrator.assert_called_once_with(
                args, mock_request_handler.return_value
            )

            # Verify return values
            assert agent == mock_create_orchestrator.return_value
            assert queue_service == mock_queue_service.return_value
            assert request_handler == mock_request_handler.return_value

    @pytest.mark.asyncio
    async def test_run_console_exit_command(self):
        """Test run_console with exit command."""
        with patch("builtins.input", side_effect=["exit"]), patch("builtins.print"):

            mock_orchestrator = Mock()
            await run_console(mock_orchestrator)

            # Verify orchestrator was not called since we exited immediately
            mock_orchestrator.process_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_console_process_message(self):
        """Test run_console processes messages correctly."""
        # Mock the response
        mock_response = Mock()
        mock_response.message = "Test response"

        mock_orchestrator = Mock()
        mock_orchestrator.process_message.return_value = mock_response

        with patch("builtins.input", side_effect=["test message", "exit"]), patch(
            "builtins.print"
        ) as mock_print:

            await run_console(mock_orchestrator)

            # Verify orchestrator was called with correct message
            mock_orchestrator.process_message.assert_called_once()
            call_args = mock_orchestrator.process_message.call_args[0][0]
            assert call_args.message == "test message"
            assert call_args.context.user_id == "tester"

            # Verify response was printed
            mock_print.assert_any_call("\nAgent Response: Test response")

    @pytest.mark.asyncio
    async def test_run_console_handles_exceptions(self):
        """Test run_console handles exceptions gracefully."""
        mock_orchestrator = Mock()
        mock_orchestrator.process_message.side_effect = Exception("Test error")

        with patch("builtins.input", side_effect=["test message", "exit"]), patch(
            "builtins.print"
        ) as mock_print:

            await run_console(mock_orchestrator)

            # Verify error was printed
            mock_print.assert_any_call("\nError: Test error")

    def test_cleanup_process_safely_graceful_termination(self):
        """Test cleanup_process_safely with graceful termination."""

        mock_process = Mock()
        mock_process.is_alive.side_effect = [True, False]  # Alive initially, then terminated

        cleanup_process_safely(mock_process, "TestProcess", timeout=1)

        mock_process.terminate.assert_called_once()
        mock_process.join.assert_called_once_with(timeout=1)
        mock_process.kill.assert_not_called()

    def test_cleanup_process_safely_force_kill(self):
        """Test cleanup_process_safely with force kill."""

        mock_process = Mock()
        mock_process.is_alive.side_effect = [True, True, False]  # Alive, still alive, then killed

        cleanup_process_safely(mock_process, "TestProcess", timeout=1)

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert mock_process.join.call_count == 2  # Called after terminate and kill

    def test_cleanup_process_safely_already_dead(self):
        """Test cleanup_process_safely with already dead process."""
        mock_process = Mock()
        mock_process.is_alive.return_value = False

        cleanup_process_safely(mock_process, "TestProcess")

        mock_process.terminate.assert_not_called()
        mock_process.kill.assert_not_called()

    def test_cleanup_process_safely_none_process(self):
        """Test cleanup_process_safely with None process."""
        # Should not raise any exceptions
        cleanup_process_safely(None, "TestProcess")


class TestCLIIntegration:
    """Integration tests for CLI components."""

    @pytest.mark.asyncio
    async def test_create_orchestrator_integration(self):
        """Test create_orchestrator creates all components correctly."""
        with patch("agent_builder_sdk.cli.FileSystemRepository"), patch(
            "agent_builder_sdk.cli.EpisodicMemory"
        ), patch("agent_builder_sdk.cli.MemoryManager"), patch(
            "agent_builder_sdk.cli.MemoryTool"
        ), patch(
            "agent_builder_sdk.cli.FileMultiSourceConversationRepository"
        ), patch(
            "agent_builder_sdk.cli.ConversationHookProvider"
        ), patch(
            "agent_builder_sdk.cli.MemoryHookProvider"
        ), patch(
            "agent_builder_sdk.cli.BaseOrchestrator"
        ), patch(
            "agent_builder_sdk.cli.get_prompt_with_name", return_value="test_prompt"
        ):

            args = Mock()
            args.storage_dir = "/test/storage"
            args.model_id = "test-model"
            args.region = "us-west-2"
            args.guardrail_id = "test-guardrail-id"
            args.guardrail_version = "test-guardrail-version"

            mock_mcp_client = Mock(spec=MCPClient)
            mock_orchestrator_instance = Mock()
            mock_orchestrator.return_value = mock_orchestrator_instance

            result = create_orchestrator(args, mock_mcp_client)

            # Verify we get a result (the mocked orchestrator)
            assert result is not None

    def test_run_api_server_sync(self):
        """Test run_api_server_sync function."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch("agent_builder_sdk.cli.start_api_server") as mock_start_server, patch(
                "agent_builder_sdk.cli.logger"
            ):

                # Create mock args
                args = Mock()
                args.region = "us-west-2"
                args.storage_dir = "./test_storage"

                # Create mock queue service
                queue_service_instance = Mock()

                # Run API server
                run_api_server_sync(args, queue_service_instance)

                # Verify start_api_server was called with just queue_service
                mock_start_server.assert_called_once_with(queue_service_instance)

    def test_run_api_server_sync_error(self):
        """Test run_api_server_sync with exception handling."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch("agent_builder_sdk.cli.start_api_server") as mock_start_server, patch(
                "agent_builder_sdk.cli.logger"
            ) as mock_logger:

                # Setup mock to raise exception
                mock_start_server.side_effect = Exception("API server failed")

                # Create mock args
                args = Mock()
                args.region = "us-west-2"
                args.storage_dir = "./test_storage"

                # Create mock queue service
                queue_service_instance = Mock()

                # Run API server and expect exception
                with pytest.raises(Exception):
                    run_api_server_sync(args, queue_service_instance)

                # Verify error was logged
                mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_initialization_success(self):
        """Test main function with successful agent initialization."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch(
                "agent_builder_sdk.cli.get_auth_token_refresher"
            ) as mock_get_auth_token_refresher, patch(
                "agent_builder_sdk.cli.initialize_agent_instance"
            ) as mock_init, patch(
                "agent_builder_sdk.cli.Process"
            ) as mock_process, patch(
                "argparse.ArgumentParser.parse_args"
            ) as mock_parse_args, patch(
                "agent_builder_sdk.cli.logger"
            ) as mock_logger, patch(
                "agent_builder_sdk.cli.setup_agent"
            ) as mock_setup_agent, patch(
                "agent_builder_sdk.cli.run_queue_mode_async", new_callable=AsyncMock
            ) as mock_run_queue, patch(
                "agent_builder_sdk.cli.setup_tracing"
            ) as mock_setup_tracing, patch(
                "agent_builder_sdk.cli.initialize_background_checkpointer"
            ) as mock_init_checkpointer:

                # Setup mock args with all required attributes
                mock_args = Mock()
                mock_args.localTesting = False
                mock_args.disableAgentLifecycle = False
                mock_args.disableProdBedrockUsage = False
                mock_args.disableMcpUsage = False
                mock_args.model_id = "test-model"
                mock_args.region = "us-west-2"
                mock_args.storage_dir = "./test_storage"
                mock_args.queueStoragePath = "./test_queue"
                mock_args.workingDir = "/test/working"
                mock_args.binaryLocation = "/path/to/binary"
                mock_args.workspaceId = "test-workspace"
                mock_args.jobId = "test-job"
                mock_args.agentInstanceId = "test-agent"
                mock_args.agenticApiEndpoint = "https://test-endpoint"
                mock_args.authTokenRefreshSessionDuration = 43200
                mock_args.tracing = None
                # Add checkpoint arguments
                mock_args.checkpoint_strategy = "time"
                mock_args.checkpoint_interval = 30
                mock_args.checkpoint_dir = "/tmp/agent_state"
                mock_parse_args.return_value = mock_args
                mock_args.new_aws_data_path = "/home/amazon/.aws/models"

                # Setup mock process
                mock_process_instance = Mock()
                mock_process_instance.pid = 12345
                mock_process.return_value = mock_process_instance

                # Setup mock agent components
                mock_orchestrator = Mock()
                mock_queue_service = Mock()
                mock_queue_service.stop = AsyncMock()
                mock_request_handler = Mock()
                mock_setup_agent.return_value = (
                    mock_orchestrator,
                    mock_queue_service,
                    mock_request_handler,
                )

                # Setup mock background checkpointer
                mock_background_checkpointer = Mock()
                mock_background_checkpointer.shutdown = AsyncMock()
                mock_init_checkpointer.return_value = mock_background_checkpointer

                # Run main
                await main()

                # Verify auth token refresher was called
                mock_get_auth_token_refresher.assert_called_once_with(session_duration=43200)

                # Verify agent lifecycle
                mock_init.assert_called_once()
                mock_logger.info.assert_any_call(
                    "Base orchestrator instance initialized successfully"
                )

                # Verify setup_agent was called
                mock_setup_agent.assert_called_once_with(mock_args, ANY)

                # Verify setup_tracing was not called since tracing is None
                mock_setup_tracing.assert_not_called()

                # Verify API server process started
                mock_process.assert_called_once()
                mock_process_instance.start.assert_called_once()
                mock_logger.info.assert_any_call(
                    f"API server started with PID: {mock_process_instance.pid}"
                )

                # Verify queue mode was started
                mock_run_queue.assert_called_once_with(
                    mock_orchestrator,
                    mock_queue_service,
                    mock_request_handler,
                    mock_background_checkpointer,
                )

    @pytest.mark.asyncio
    async def test_main_initialization_failure(self):
        """Test main function when agent initialization fails."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch(
                "agent_builder_sdk.cli.get_auth_token_refresher"
            ) as mock_get_auth_token_refresher, patch(
                "agent_builder_sdk.cli.initialize_agent_instance"
            ) as mock_init, patch(
                "argparse.ArgumentParser.parse_args"
            ) as mock_parse_args, patch(
                "agent_builder_sdk.cli.logger"
            ) as mock_logger:

                # Setup mock args with required attributes
                mock_args = Mock()
                mock_args.localTesting = False
                mock_args.disableAgentLifecycle = False
                mock_args.disableProdBedrockUsage = False
                mock_args.disableMcpUsage = False
                mock_args.workingDir = "/test/working"
                mock_args.authTokenRefreshSessionDuration = 43200  # Add missing attribute
                mock_parse_args.return_value = mock_args
                mock_args.new_aws_data_path = "/home/amazon/.aws/models"

                # Setup initialization failure
                mock_init.side_effect = Exception("Initialization failed")

                # Run main and expect SystemExit
                with pytest.raises(SystemExit) as exc_info:
                    await main()

                # Verify exit code
                assert exc_info.value.code == 1

                # Verify auth token refresher was called
                mock_get_auth_token_refresher.assert_called_once_with(session_duration=43200)

                # Verify agent lifecycle
                mock_init.assert_called_once()
                mock_logger.error.assert_called_with(
                    "Failed to initialize base orchestrator instance: Initialization failed"
                )

    @pytest.mark.asyncio
    async def test_main_disabled_agent_lifecycle(self):
        """Test main function with disabled agent lifecycle."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch(
                "agent_builder_sdk.cli.get_auth_token_refresher"
            ) as mock_get_auth_token_refresher, patch(
                "agent_builder_sdk.cli.initialize_agent_instance"
            ) as mock_init, patch(
                "argparse.ArgumentParser.parse_args"
            ) as mock_parse_args, patch(
                "agent_builder_sdk.cli.logger"
            ) as mock_logger, patch(
                "agent_builder_sdk.cli.setup_agent"
            ) as mock_setup_agent, patch(
                "agent_builder_sdk.cli.run_console", new_callable=AsyncMock
            ) as mock_run_console, patch(
                "agent_builder_sdk.cli.setup_tracing"
            ) as mock_setup_tracing:

                # Setup mock args with disabled lifecycle and local testing
                mock_args = Mock()
                mock_args.localTesting = True
                mock_args.disableAgentLifecycle = True
                mock_args.disableProdBedrockUsage = False
                mock_args.disableMcpUsage = False
                mock_args.region = "us-west-2"
                mock_args.workingDir = "/test/working"
                mock_args.binaryLocation = "/path/to/binary"
                mock_args.workspaceId = "test-workspace"
                mock_args.jobId = "test-job"
                mock_args.agentInstanceId = "test-agent"
                mock_args.agenticApiEndpoint = "https://test-endpoint"
                mock_args.authTokenRefreshSessionDuration = 43200
                mock_args.tracing = None
                mock_parse_args.return_value = mock_args
                mock_args.new_aws_data_path = "/home/amazon/.aws/models"

                # Setup mock agent components
                mock_orchestrator = Mock()
                mock_queue_service = Mock()
                mock_request_handler = Mock()
                mock_setup_agent.return_value = (
                    mock_orchestrator,
                    mock_queue_service,
                    mock_request_handler,
                )

                # Run main
                await main()

                # Verify auth token refresher was called
                mock_get_auth_token_refresher.assert_called_once_with(session_duration=43200)

                # Verify agent lifecycle was disabled
                mock_init.assert_not_called()
                mock_logger.info.assert_any_call("Agent lifecycle management disabled")

                # Verify setup_agent was called
                mock_setup_agent.assert_called_once_with(mock_args, ANY)

                # Verify setup_tracing was not called since tracing is None
                mock_setup_tracing.assert_not_called()

                # Verify console mode was started
                mock_run_console.assert_called_once_with(mock_orchestrator)

    @pytest.mark.asyncio
    async def test_main_setup_agent_failure(self):
        """Test main function when setup_agent fails."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch(
                "agent_builder_sdk.cli.get_auth_token_refresher"
            ) as mock_get_auth_token_refresher, patch(
                "agent_builder_sdk.cli.initialize_agent_instance"
            ) as mock_init, patch(
                "argparse.ArgumentParser.parse_args"
            ) as mock_parse_args, patch(
                "agent_builder_sdk.cli.logger"
            ) as mock_logger, patch(
                "agent_builder_sdk.cli.setup_agent"
            ) as mock_setup_agent, patch(
                "agent_builder_sdk.cli.setup_tracing"
            ) as mock_setup_tracing:

                # Setup mock args
                mock_args = Mock()
                mock_args.localTesting = False
                mock_args.disableAgentLifecycle = False
                mock_args.disableProdBedrockUsage = False
                mock_args.disableMcpUsage = False
                mock_args.region = "us-west-2"
                mock_args.workingDir = "/test/working"
                mock_args.binaryLocation = "/path/to/binary"
                mock_args.workspaceId = "test-workspace"
                mock_args.jobId = "test-job"
                mock_args.agentInstanceId = "test-agent"
                mock_args.agenticApiEndpoint = "https://test-endpoint"
                mock_args.authTokenRefreshSessionDuration = 43200
                mock_args.tracing = None
                mock_parse_args.return_value = mock_args
                mock_args.new_aws_data_path = "/home/amazon/.aws/models"

                # Setup setup_agent to fail
                mock_setup_agent.side_effect = Exception("Setup failed")

                # Run main and expect SystemExit
                with pytest.raises(SystemExit) as exc_info:
                    await main()

                # Verify exit code
                assert exc_info.value.code == 1

                # Verify auth token refresher was called
                mock_get_auth_token_refresher.assert_called_once_with(session_duration=43200)

                # Verify agent lifecycle succeeded
                mock_init.assert_called_once()

                # Verify setup_agent was called and failed
                mock_setup_agent.assert_called_once_with(mock_args, ANY)

                # Verify setup_tracing was not called since tracing is None
                mock_setup_tracing.assert_not_called()

                mock_logger.error.assert_called_with("Application failed: Setup failed")

    def test_run_main(self):
        """Test run_main function."""
        with patch.dict("sys.modules", {"agent_builder_sdk.fastapi_server": Mock()}):

            with patch("agent_builder_sdk.cli.asyncio.run") as mock_asyncio_run:
                # Run the function
                run_main()

                # Verify asyncio.run was called with main
                mock_asyncio_run.assert_called_once()


def test_setup_ab_mcp_client_success():
    """Test successful MCP client setup."""
    with patch("agent_builder_sdk.cli.MCPClient") as mock_mcp_client:
        mcp_args = {
            "binaryLocation": "/path/to/binary",
            "workspaceId": "test-workspace",
            "jobId": "test-job",
        }

        mock_client_instance = Mock(spec=MCPClient)
        mock_mcp_client.return_value = mock_client_instance

        result = setup_ab_mcp_client(mcp_args)

        mock_mcp_client.assert_called_once()
        assert result == mock_client_instance


def test_setup_ab_mcp_client_no_args():
    """Test MCP client setup with no additional args."""
    with patch("agent_builder_sdk.cli.MCPClient") as mock_mcp_client:
        mcp_args = {"binaryLocation": "/path/to/binary"}

        mock_client_instance = Mock(spec=MCPClient)
        mock_mcp_client.return_value = mock_client_instance

        result = setup_ab_mcp_client(mcp_args)

        mock_mcp_client.assert_called_once()
        assert result == mock_client_instance


def test_setup_ab_mcp_client_failure():
    """Test MCP client setup failure."""
    with patch("agent_builder_sdk.cli.MCPClient", side_effect=Exception("Connection failed")):
        mcp_args = {"binaryLocation": "/path/to/binary"}

        with pytest.raises(Exception, match="Connection failed"):
            setup_ab_mcp_client(mcp_args)


def test_create_orchestrator():
    """Test orchestrator creation with MCP client."""
    with patch("agent_builder_sdk.cli.BaseOrchestrator") as mock_orchestrator, patch(
        "agent_builder_sdk.cli.get_prompt_with_name"
    ) as mock_prompt:

        mock_args = Mock()
        mock_args.model_id = "test-model"
        mock_args.region = "us-west-2"
        mock_args.storage_dir = "./test_storage"
        mock_args.disableProdBedrockUsage = False
        mock_args.guardrail_id = "test-guardrail-id"
        mock_args.guardrail_version = "test-guardrail-version"

        mock_mcp_client = Mock(spec=MCPClient)
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance
        mock_prompt.return_value = "test prompt"

        result = create_orchestrator(mock_args, mock_mcp_client)

        mock_orchestrator.assert_called_once_with(
            system_prompt="test prompt",
            hooks=ANY,
            model_id="test-model",
            mcp_clients=[mock_mcp_client],
            region_name="us-west-2",
            custom_tools=ANY,
            guardrail_id="test-guardrail-id",
            guardrail_version="test-guardrail-version",
        )
        assert result == mock_orchestrator_instance


def test_setup_agent():
    """Test complete agent setup with MCP enabled (default behavior)."""
    # Mock environment without MCP disabled (default state)
    with patch.dict("os.environ", {}, clear=True), patch(
        "agent_builder_sdk.cli.setup_ab_mcp_client"
    ) as mock_setup_mcp, patch(
        "agent_builder_sdk.cli.QueueService"
    ) as mock_queue_service, patch(
        "agent_builder_sdk.cli.QueueRequestHandler"
    ) as mock_handler, patch(
        "agent_builder_sdk.cli.create_orchestrator"
    ) as mock_create_orch:

        mock_args = Mock()
        mock_args.queueStoragePath = "/tmp/test_queue"
        mock_args.disableProdBedrockUsage = False

        # Add mock mcp_args
        mock_mcp_args = {"binaryLocation": "/path/to/binary", "workspaceId": "test-workspace"}

        mock_mcp_client = Mock(spec=MCPClient)
        mock_setup_mcp.return_value = mock_mcp_client

        mock_queue_instance = Mock()
        mock_queue_service.return_value = mock_queue_instance

        mock_handler_instance = Mock()
        mock_handler.return_value = mock_handler_instance

        mock_orchestrator = Mock()
        mock_create_orch.return_value = mock_orchestrator

        # Call setup_agent
        agent, queue_service, request_handler = setup_agent(mock_args, mock_mcp_args)

        # Verify MCP client setup WAS called (since MCP is enabled by default)
        mock_setup_mcp.assert_called_once_with(mock_mcp_args)

        # Verify other components were set up
        mock_queue_service.assert_called_once_with(storage_path="/tmp/test_queue")
        mock_handler.assert_called_once_with(
            request_queue=mock_queue_instance.request_queue,
            response_store=mock_queue_instance.response_store,
        )

        # Verify create_orchestrator was called with the mcp_client
        mock_create_orch.assert_called_once_with(mock_args, mock_mcp_client)

        assert agent == mock_orchestrator
        assert queue_service == mock_queue_instance
        assert request_handler == mock_handler_instance


def test_setup_agent_without_mcp():
    """Test complete agent setup without MCP when MCP usage is disabled."""
    # Mock environment with MCP disabled
    with patch.dict("os.environ", {"DISABLE_MCP_USAGE": "true"}), patch(
        "agent_builder_sdk.cli.setup_ab_mcp_client"
    ) as mock_setup_mcp, patch(
        "agent_builder_sdk.cli.QueueService"
    ) as mock_queue_service, patch(
        "agent_builder_sdk.cli.QueueRequestHandler"
    ) as mock_handler, patch(
        "agent_builder_sdk.cli.create_orchestrator"
    ) as mock_create_orch:

        mock_args = Mock()
        mock_args.queueStoragePath = "/tmp/test_queue"
        mock_args.disableProdBedrockUsage = False

        # MCP args should still be provided but won't be used
        mock_mcp_args = {"binaryLocation": "/path/to/binary", "workspaceId": "test-workspace"}

        mock_queue_instance = Mock()
        mock_queue_service.return_value = mock_queue_instance

        mock_handler_instance = Mock()
        mock_handler.return_value = mock_handler_instance

        mock_orchestrator = Mock()
        mock_create_orch.return_value = mock_orchestrator

        # Call setup_agent
        agent, queue_service, request_handler = setup_agent(mock_args, mock_mcp_args)

        # Verify MCP client setup was NOT called (since MCP is disabled)
        mock_setup_mcp.assert_not_called()

        # Verify other components were still set up
        mock_queue_service.assert_called_once_with(storage_path="/tmp/test_queue")
        mock_handler.assert_called_once_with(
            request_queue=mock_queue_instance.request_queue,
            response_store=mock_queue_instance.response_store,
        )

        # Verify create_orchestrator was called with None as mcp_client
        mock_create_orch.assert_called_once_with(mock_args, None)

        assert agent == mock_orchestrator
        assert queue_service == mock_queue_instance
        assert request_handler == mock_handler_instance


def test_setup_tracing_default():
    """Test setup_tracing with local tracing type."""
    with patch("agent_builder_sdk.cli.StrandsTelemetry") as mock_telemetry, patch.dict(
        "os.environ", {}, clear=True
    ):
        mock_telemetry_instance = Mock()
        mock_telemetry.return_value = mock_telemetry_instance

        setup_tracing("local")

        assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4318"
        mock_telemetry.assert_called_once()
        mock_telemetry_instance.setup_otlp_exporter.assert_called_once()
        mock_telemetry_instance.setup_console_exporter.assert_called_once()


def test_setup_tracing_cloudwatch():
    """Test setup_tracing with cloudwatch tracing type."""
    with patch("agent_builder_sdk.cli.StrandsTelemetry") as mock_telemetry, patch.dict(
        "os.environ", {}, clear=True
    ):
        mock_telemetry_instance = Mock()
        mock_telemetry.return_value = mock_telemetry_instance

        setup_tracing("cloudwatch")

        assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4318"
        mock_telemetry.assert_called_once()
        mock_telemetry_instance.setup_otlp_exporter.assert_called_once()
        mock_telemetry_instance.setup_console_exporter.assert_called_once()


def test_setup_tracing_custom_endpoint():
    """Test setup_tracing with custom tracing type (treated as local)."""
    with patch("agent_builder_sdk.cli.StrandsTelemetry") as mock_telemetry, patch.dict(
        "os.environ", {}, clear=True
    ):
        mock_telemetry_instance = Mock()
        mock_telemetry.return_value = mock_telemetry_instance

        setup_tracing("custom")

        assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4318"
        mock_telemetry.assert_called_once()
        mock_telemetry_instance.setup_otlp_exporter.assert_called_once()
        mock_telemetry_instance.setup_console_exporter.assert_called_once()
