# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

import pytest

from agent_builder_sdk.agentic_framework.client_factory import (
    create_agentic_api_client,
    get_agentic_api_client,
)


@mock.patch("agent_builder_sdk.agentic_framework.client_factory.boto3.client")
def test_create_agentic_api_client_with_endpoint_url(mock_boto_client):
    """Test client creation with explicit endpoint URL."""
    mock_client = mock.Mock()
    mock_boto_client.return_value = mock_client

    result = create_agentic_api_client(endpoint_url="https://test-endpoint.com", region="us-west-2")

    assert result == mock_client
    mock_boto_client.assert_called_once()
    call_args = mock_boto_client.call_args
    assert call_args[1]["service_name"] == "transformagenticservice"
    assert call_args[1]["endpoint_url"] == "https://test-endpoint.com"
    assert call_args[1]["region_name"] == "us-west-2"


@mock.patch("agent_builder_sdk.agentic_framework.client_factory.boto3.client")
def test_create_agentic_api_client_with_stage_region(mock_boto_client):
    """Test client creation with stage and region."""
    mock_client = mock.Mock()
    mock_boto_client.return_value = mock_client

    result = create_agentic_api_client(stage="alpha-intg", region="us-west-2")

    assert result == mock_client
    mock_boto_client.assert_called_once()
    call_args = mock_boto_client.call_args
    assert (
        call_args[1]["endpoint_url"] == "https://pdx.alpha-intg.agenticapi.elastic-gumby.ai.aws.dev"
    )


@mock.patch.dict("os.environ", {"STAGE": "gamma", "AWS_REGION": "us-east-1"}, clear=True)
@mock.patch("agent_builder_sdk.agentic_framework.client_factory.boto3.client")
def test_create_agentic_api_client_from_env(mock_boto_client):
    """Test client creation using environment variables."""
    mock_client = mock.Mock()
    mock_boto_client.return_value = mock_client

    result = create_agentic_api_client()

    assert result == mock_client
    mock_boto_client.assert_called_once()
    call_args = mock_boto_client.call_args
    assert call_args[1]["endpoint_url"] == "https://iad.gamma.agenticapi.elastic-gumby.ai.aws.dev"


@mock.patch.dict("os.environ", {"QT_AGENTIC_API_ENDPOINT": "https://env-endpoint.com"})
@mock.patch("agent_builder_sdk.agentic_framework.client_factory.boto3.client")
def test_create_agentic_api_client_env_endpoint(mock_boto_client):
    """Test client creation with endpoint from environment."""
    mock_client = mock.Mock()
    mock_boto_client.return_value = mock_client

    result = create_agentic_api_client()

    assert result == mock_client
    call_args = mock_boto_client.call_args
    assert call_args[1]["endpoint_url"] == "https://env-endpoint.com"


@mock.patch.dict("os.environ", {}, clear=True)
def test_create_agentic_api_client_missing_params():
    """Test client creation with missing required parameters."""
    with pytest.raises(
        ValueError, match="Either endpoint_url or both stage and region must be provided"
    ):
        create_agentic_api_client()


@mock.patch("agent_builder_sdk.agentic_framework.client_factory.create_agentic_api_client")
def test_get_agentic_api_client_cached(mock_create_client):
    """Test that get_agentic_api_client uses caching."""
    mock_client = mock.Mock()
    mock_create_client.return_value = mock_client

    # Clear cache first
    get_agentic_api_client.cache_clear()

    # First call
    result1 = get_agentic_api_client()
    # Second call
    result2 = get_agentic_api_client()

    assert result1 == mock_client
    assert result2 == mock_client
    # Should only create client once due to caching
    mock_create_client.assert_called_once()


@mock.patch.dict("os.environ", {"USE_EXTERNAL_AGENTIC_API": "true"}, clear=False)
@mock.patch.dict("os.environ", {"QT_AGENTIC_API_ENDPOINT": ""}, clear=False)
@mock.patch("agent_builder_sdk.agentic_framework.client_factory.boto3.client")
def test_create_agentic_api_client_external_api(mock_boto_client):
    """Test client creation with external agentic API enabled."""
    mock_client = mock.Mock()
    mock_boto_client.return_value = mock_client

    result = create_agentic_api_client(stage="prod", region="us-east-1")

    assert result == mock_client
    mock_boto_client.assert_called_once()
    call_args = mock_boto_client.call_args
    assert call_args[1]["service_name"] == "transformagenticservice"
    assert call_args[1]["endpoint_url"] == "https://transform-agents.us-east-1.api.aws"
