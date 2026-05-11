# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the knowledge base tools functionality.
"""

from unittest import mock

import pytest
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext
from agent_builder_agentic_mcp.server._kb_tools import retrieve_from_knowledge_base


@pytest.fixture
def mock_request_context():
    """Mock the request context injection."""

    def mock_inject(kwargs):
        result = kwargs.copy() if kwargs else {}
        result["requestContext"] = AgenticRequestContext(
            job_id="test-job-id",
            workspace_id="test-workspace-id",
            agent_instance_id="test-agent-id",
            authorization_token="test-token",
        )
        return result

    patcher = mock.patch(
        "agent_builder_agentic_mcp.server._kb_tools._inject_qt_request_context", mock_inject
    )
    patcher.start()
    yield mock_inject
    patcher.stop()


@pytest.fixture
def mock_atx_client():
    magic_mock = mock.MagicMock()
    with mock.patch(
        "agent_builder_agentic_mcp.server._kb_tools.atx_agenticapi_client"
    ) as mock_atx_client:
        mock_atx_client.return_value = magic_mock
        yield mock_atx_client.return_value


@pytest.mark.anyio
async def test_retrieve_from_knowledge_base_aws_scope(mock_atx_client, mock_request_context):
    """Test retrieving from knowledge base with AWS scope."""
    mock_atx_client.retrieve_from_knowledge_base.return_value = {
        "retrievalResults": [{"content": {"text": "AWS Lambda info"}}]
    }

    result = await retrieve_from_knowledge_base(
        retrieval_query="What is AWS Lambda?",
        retrieval_scope="AWS",
    )

    mock_atx_client.retrieve_from_knowledge_base.assert_called_once()
    call_args = mock_atx_client.retrieve_from_knowledge_base.call_args[1]
    assert call_args["retrievalQuery"] == {"text": "What is AWS Lambda?"}
    assert call_args["retrievalScope"] == "AWS"
    assert "requestContext" in call_args
    assert result["retrieved_content"][0]["text"] == "AWS Lambda info"


@pytest.mark.anyio
async def test_retrieve_from_knowledge_base_product_scope(mock_atx_client, mock_request_context):
    """Test retrieving from knowledge base with PRODUCT scope."""
    mock_atx_client.retrieve_from_knowledge_base.return_value = {"retrievalResults": []}

    result = await retrieve_from_knowledge_base(
        retrieval_query="test query",
        retrieval_scope="PRODUCT",
    )

    call_args = mock_atx_client.retrieve_from_knowledge_base.call_args[1]
    assert call_args["retrievalScope"] == "PRODUCT"
    assert "requestContext" in call_args
    assert result["retrieved_content"] == []


@pytest.mark.anyio
async def test_retrieve_from_knowledge_base_error(mock_atx_client, mock_request_context):
    """Test error handling in retrieve_from_knowledge_base."""
    mock_atx_client.retrieve_from_knowledge_base.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await retrieve_from_knowledge_base(
            retrieval_query="test",
            retrieval_scope="AWS",
        )

    assert "Test error" in str(exc_info.value)
    mock_atx_client.retrieve_from_knowledge_base.assert_called_once()
