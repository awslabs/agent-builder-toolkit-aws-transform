"""Tests for TransformAgentBuilderMCPPythonClient module."""


def test_agent_builder_mcp_client_importable():
    """Test agent_builder_mcp_client is importable."""
    import agent_builder_mcp_client  # noqa: F401


def test_async_mcp_client_importable():
    """Test agent_builder_mcp_client is importable."""
    from agent_builder_mcp_client import AsyncMCPClient  # noqa: F401
    from agent_builder_mcp_client import McpToolRepr  # noqa: F401
