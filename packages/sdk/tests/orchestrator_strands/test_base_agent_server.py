# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for base_agent_server module."""

from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.orchestrator_strands._base_agent_server import (
    AgentConfiguration,
    BaseAgentServer,
    PlatformFunctions,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import EvaluationCard


class TestPlatformFunctions:
    """Test PlatformFunctions enum."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert PlatformFunctions.JOB_PLAN.value == "job_plan"
        assert PlatformFunctions.WORKLOG.value == "worklog"
        assert PlatformFunctions.ARTIFACT.value == "artifact"
        assert PlatformFunctions.HITL.value == "hitl"


class TestAgentConfiguration:
    """Test AgentConfiguration enum."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert AgentConfiguration.AWS_REGION.value == "aws_region"
        assert AgentConfiguration.WORKSPACE_ID.value == "workspace_id"
        assert AgentConfiguration.JOB_ID.value == "job_id"
        assert AgentConfiguration.AGENT_INSTANCE_ID.value == "agent_instance_id"
        assert AgentConfiguration.STORAGE_DIR.value == "storage_dir"
        assert AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value == "auto_platform_mcp_support"


class TestBaseAgentServer:
    """Test BaseAgentServer class."""

    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": "us-east-1",
            "STAGE": "test",
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "QT_AGENTIC_API_ENDPOINT": "https://api.test.com",
        },
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.validate_required_env_vars"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.get_auth_token_refresher"
    )
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.setup_tracing")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueService")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueRequestHandler")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.Process")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.BaseOrchestrator")
    def test_init_minimal(
        self,
        mock_orchestrator,
        mock_process,
        mock_handler,
        mock_queue,
        mock_tracing,
        mock_refresher,
        mock_validate,
    ):
        """Test BaseAgentServer initialization with minimal parameters."""
        mock_queue_instance = Mock()
        mock_queue.return_value = mock_queue_instance
        mock_process_instance = Mock()
        mock_process.return_value = mock_process_instance

        server = BaseAgentServer(system_prompt="Test prompt")

        assert server.system_prompt == "Test prompt"
        assert server.custom_tools == []
        assert server.custom_mcp_clients == []
        assert server.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
        mock_validate.assert_called_once()
        mock_refresher.assert_called_once()
        mock_tracing.assert_called_once_with("local")

    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": "us-east-1",
            "STAGE": "test",
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "QT_AGENTIC_API_ENDPOINT": "https://api.test.com",
        },
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.validate_required_env_vars"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.get_auth_token_refresher"
    )
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.setup_tracing")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueService")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueRequestHandler")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.Process")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.BaseOrchestrator")
    def test_init_with_custom_params(
        self,
        mock_orchestrator,
        mock_process,
        mock_handler,
        mock_queue,
        mock_tracing,
        mock_refresher,
        mock_validate,
    ):
        """Test BaseAgentServer initialization with custom parameters."""
        mock_tools = [Mock()]
        mock_clients = [Mock()]
        mock_hooks = [Mock()]
        eval_card = EvaluationCard("Test Agent", "Test capabilities")
        config_override = {AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value: True}

        server = BaseAgentServer(
            system_prompt="Custom prompt",
            custom_tools=mock_tools,
            custom_mcp_clients=mock_clients,
            agent_lifecycle_hooks=mock_hooks,
            model_id="custom-model",
            agent_evaluation_card=eval_card,
            agent_config_override=config_override,
        )

        assert server.system_prompt == "Custom prompt"
        assert server.custom_tools == mock_tools
        assert server.custom_mcp_clients == mock_clients
        assert server.agent_lifecycle_hooks == mock_hooks
        assert server.model_id == "custom-model"
        assert server.agent_evaluation_card == eval_card

    def test_setup_agent_configuration_defaults(self):
        """Test _setup_agent_configuration with default values."""
        with patch.dict(
            "os.environ",
            {
                "AWS_REGION": "us-west-2",
                "WORKSPACE_ID": "workspace-123",
                "JOB_ID": "job-456",
                "AGENT_INSTANCE_ID": "agent-789",
                "QT_AGENTIC_API_ENDPOINT": "https://api.example.com",
            },
        ):
            config = BaseAgentServer._setup_agent_configuration({})

            assert config[AgentConfiguration.AWS_REGION.value] == "us-west-2"
            assert config[AgentConfiguration.WORKSPACE_ID.value] == "workspace-123"
            assert config[AgentConfiguration.JOB_ID.value] == "job-456"
            assert config[AgentConfiguration.AGENT_INSTANCE_ID.value] == "agent-789"
            assert config[AgentConfiguration.STORAGE_DIR.value] == "."
            assert config[AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value] is False

    def test_setup_agent_configuration_with_overrides(self):
        """Test _setup_agent_configuration with overrides."""
        with patch.dict(
            "os.environ",
            {
                "AWS_REGION": "us-west-2",
                "WORKSPACE_ID": "workspace-123",
                "JOB_ID": "job-456",
                "AGENT_INSTANCE_ID": "agent-789",
                "QT_AGENTIC_API_ENDPOINT": "https://api.example.com",
            },
        ):
            overrides = {
                AgentConfiguration.STORAGE_DIR.value: "/custom/storage",
                AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value: True,
            }

            config = BaseAgentServer._setup_agent_configuration(overrides)

            assert config[AgentConfiguration.STORAGE_DIR.value] == "/custom/storage"
            assert config[AgentConfiguration.AUTO_PLATFORM_MCP_SUPPORT.value] is True

    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.setup_tracing")
    def test_setup_tracing(self, mock_setup_tracing):
        """Test _setup_tracing method."""
        BaseAgentServer._setup_tracing("test")
        mock_setup_tracing.assert_called_once_with("test")

    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": "us-east-1",
            "STAGE": "test",
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "QT_AGENTIC_API_ENDPOINT": "https://api.test.com",
        },
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.validate_required_env_vars"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.get_auth_token_refresher"
    )
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.setup_tracing")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueService")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueRequestHandler")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.Process")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.BaseOrchestrator")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.run_queue_mode_async")
    def test_start(
        self,
        mock_run_queue,
        mock_orchestrator,
        mock_process,
        mock_handler,
        mock_queue,
        mock_tracing,
        mock_refresher,
        mock_validate,
    ):
        """Test start method."""
        mock_queue_instance = Mock()
        mock_queue.return_value = mock_queue_instance

        server = BaseAgentServer(system_prompt="Test prompt")

        # Mock asyncio.run to avoid actual async execution
        with patch("asyncio.run") as mock_asyncio_run:
            server.start()
            mock_asyncio_run.assert_called_once()

    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.setup_ab_mcp_client")
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.get_default_auth_token_file_path"
    )
    def test_setup_platform_mcp(self, mock_token_path, mock_setup_mcp):
        """Test _setup_platform_mcp method."""
        mock_token_path.return_value = "/path/to/token"
        mock_mcp_client = Mock()
        mock_setup_mcp.return_value = mock_mcp_client

        # Create a minimal server instance for testing
        server = Mock()
        server.agent_config = {
            AgentConfiguration.PLATFORM_MCP_BINARY_LOCATION.value: "/opt/mcp",
            AgentConfiguration.WORKSPACE_ID.value: "workspace-123",
            AgentConfiguration.JOB_ID.value: "job-456",
            AgentConfiguration.AGENT_INSTANCE_ID.value: "agent-789",
            AgentConfiguration.AGENTIC_API_ENDPOINT.value: "https://api.example.com",
        }

        result = BaseAgentServer._setup_platform_mcp(server)

        assert result == mock_mcp_client
        mock_setup_mcp.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": "us-east-1",
            "STAGE": "test",
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "QT_AGENTIC_API_ENDPOINT": "https://api.test.com",
        },
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.validate_required_env_vars"
    )
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.sys.exit")
    def test_init_validation_failure(self, mock_exit, mock_validate):
        """Test initialization fails when validation raises exception."""
        mock_validate.side_effect = ValueError("Missing env vars")

        with pytest.raises(ValueError):
            BaseAgentServer(system_prompt="Test prompt")

    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": "us-east-1",
            "STAGE": "test",
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "QT_AGENTIC_API_ENDPOINT": "https://api.test.com",
        },
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.validate_required_env_vars"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands._base_agent_server.get_auth_token_refresher"
    )
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.setup_tracing")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueService")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.QueueRequestHandler")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.Process")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.BaseOrchestrator")
    @patch("agent_builder_sdk.orchestrator_strands._base_agent_server.sys.exit")
    def test_init_agent_setup_failure(
        self,
        mock_exit,
        mock_orchestrator,
        mock_process,
        mock_handler,
        mock_queue,
        mock_tracing,
        mock_refresher,
        mock_validate,
    ):
        """Test initialization fails when agent setup raises exception."""
        mock_orchestrator.side_effect = Exception("Agent setup failed")

        BaseAgentServer(system_prompt="Test prompt")
        mock_exit.assert_called_with(1)
