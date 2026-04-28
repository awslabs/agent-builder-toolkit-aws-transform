"""Tests for the SubagentRegistryTools class."""

from unittest.mock import patch

import pytest

from agent_builder_sdk.custom_types.agent_registry_types import (
    AgentType,
    GetAgentVersionOutput,
    VersionStatus,
)
from agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools import (
    SubagentRegistryTools,
)


@pytest.fixture
def subagent_registry_tools():
    """Create a SubagentRegistryTools instance."""
    return SubagentRegistryTools()


class TestSubagentRegistryTools:
    """Test class for SubagentRegistryTools."""

    def test_initialization(self):
        """Test SubagentRegistryTools initialization."""
        tools = SubagentRegistryTools()
        assert isinstance(tools, SubagentRegistryTools)

    @pytest.mark.asyncio
    async def test_discover_subagents_success(self, subagent_registry_tools):
        """Test successful discover_subagents operation."""
        # Call the tool
        result = await subagent_registry_tools.discover_subagents()

        # Verify result
        assert isinstance(result, list)
        assert len(result) == 1

        # Verify the mock agent
        mock_agent = result[0]
        assert isinstance(mock_agent, GetAgentVersionOutput)
        assert mock_agent.version == "1.0.0"
        assert mock_agent.metadata.type == AgentType.SUB_AGENT
        assert mock_agent.metadata.description == "A subagent for weather related tasks"
        assert mock_agent.configuration.agent_card.name == "dynamic-showcase-subagent"
        assert mock_agent.status == VersionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_discover_subagents_exception_handling(self, subagent_registry_tools):
        """Test discover_subagents operation when an exception occurs."""
        # Mock the GetAgentVersionOutput constructor to raise an exception
        with patch(
            "agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.GetAgentVersionOutput"
        ) as mock_output:
            mock_output.side_effect = Exception("Mock error")

            # Call the tool and expect an exception
            with pytest.raises(Exception) as exc_info:
                await subagent_registry_tools.discover_subagents()

            # Verify the exception message
            assert "Subagent registry operation failed: Mock error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_return_type_annotation(self, subagent_registry_tools):
        """Test that the return type is correctly annotated."""
        # Call the tool
        result = await subagent_registry_tools.discover_subagents()

        # Verify result matches List[GetAgentVersionOutput] type
        assert isinstance(result, list)
        for agent in result:
            assert isinstance(agent, GetAgentVersionOutput)

    @pytest.mark.asyncio
    async def test_tool_decorator_functionality(self, subagent_registry_tools):
        """Test that the @tool decorator works correctly."""
        # Verify the discover_subagents method has tool attributes
        assert hasattr(subagent_registry_tools.discover_subagents, "__wrapped__")
        assert callable(subagent_registry_tools.discover_subagents)

        # Verify we can call it as an async function
        result = await subagent_registry_tools.discover_subagents()
        assert isinstance(result, list)

    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.logger")
    def test_initialization_logging(self, mock_logger):
        """Test that initialization logs appropriately."""
        SubagentRegistryTools()

        # Verify initialization was logged
        mock_logger.info.assert_called_with("Initialized SubagentRegistryTools")

    @patch("agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.logger")
    @pytest.mark.asyncio
    async def test_exception_logging(self, mock_logger, subagent_registry_tools):
        """Test that exceptions are logged appropriately."""
        # Mock GetAgentVersionOutput to raise an exception
        with patch(
            "agent_builder_sdk.orchestrator_strands.tools.subagent_registry_tools.GetAgentVersionOutput"
        ) as mock_output:
            test_error = Exception("Test error")
            mock_output.side_effect = test_error

            # Call the tool and expect an exception
            with pytest.raises(Exception):
                await subagent_registry_tools.discover_subagents()

            # Verify error was logged
            mock_logger.error.assert_called_with(f"Subagent registry operation error: {test_error}")


class TestSubagentRegistryToolsIntegration:
    """Integration tests for SubagentRegistryTools."""

    @pytest.mark.asyncio
    async def test_mock_agent_properties(self):
        """Test that the mock agent has all required properties."""
        # Create tool and get subagents
        tools = SubagentRegistryTools()
        result = await tools.discover_subagents()

        # Verify mock agent has all required fields
        mock_agent = result[0]
        assert hasattr(mock_agent, "version")
        assert hasattr(mock_agent, "metadata")
        assert hasattr(mock_agent, "configuration")
        assert hasattr(mock_agent, "status")
        assert hasattr(mock_agent, "visibility")

        # Verify field values are not None or empty
        assert mock_agent.version
        assert mock_agent.metadata
        assert mock_agent.configuration
        assert mock_agent.status
        assert mock_agent.visibility

    @pytest.mark.asyncio
    async def test_agent_type_enum_values(self):
        """Test that AgentType enum values are correctly used."""
        # Create tool and get subagents
        tools = SubagentRegistryTools()
        result = await tools.discover_subagents()

        # Verify agent type is a valid enum value
        mock_agent = result[0]
        assert isinstance(mock_agent.metadata.type, AgentType)
        assert mock_agent.metadata.type in [AgentType.SUB_AGENT, AgentType.ORCHESTRATOR_AGENT]

    @pytest.mark.asyncio
    async def test_multiple_calls_consistency(self):
        """Test that multiple calls return consistent results."""
        # Create tool
        tools = SubagentRegistryTools()

        # Call multiple times
        result1 = await tools.discover_subagents()
        result2 = await tools.discover_subagents()

        # Verify results are consistent
        assert len(result1) == len(result2)
        assert result1[0].version == result2[0].version
        assert result1[0].configuration.agent_card.name == result2[0].configuration.agent_card.name
        assert result1[0].metadata.type == result2[0].metadata.type
