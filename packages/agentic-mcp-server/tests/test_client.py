# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the AWS Transform Agentic API client utilities.
"""

import functools
import os
from unittest import mock

import pytest
from agent_builder_agentic_mcp import client, env_var
from botocore.config import Config as BotocoreConfig


@pytest.fixture
def mock_boto3_client():
    with mock.patch("boto3.client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_environment():
    original_env = dict(os.environ)
    os.environ[env_var.ENV_KEY_QT_AGENTIC_API_ENDPOINT] = "https://test-endpoint.aws.com"
    os.environ["AWS_REGION"] = "us-west-2"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def patched_client():
    # Save the original function
    original_func = client.atx_agenticapi_client

    # Apply the decorator
    client.atx_agenticapi_client = functools.lru_cache(maxsize=1)(client.atx_agenticapi_client)

    yield

    # Restore the original function
    client.atx_agenticapi_client = original_func


def test_create_atx_agenticapi_client_default_params(mock_boto3_client, mock_environment):
    """Test client creation with default parameters."""
    # Create client
    client.create_atx_agenticapi_client()

    # Verify boto3.client was called with correct parameters
    mock_boto3_client.assert_called_once()
    call_args = mock_boto3_client.call_args[1]

    assert call_args["service_name"] == client.ATX_AGENTIC_API_SERVICE_NAME
    assert call_args["region_name"] == "us-west-2"
    assert call_args["endpoint_url"] == "https://test-endpoint.aws.com"

    # Verify config
    config = call_args["config"]
    assert isinstance(config, BotocoreConfig)
    assert config.retries["max_attempts"] == 3
    assert config.connect_timeout == 30
    assert config.read_timeout == 30


def test_create_atx_agenticapi_client_custom_params(mock_boto3_client):
    """Test client creation with custom parameters."""
    custom_endpoint = "https://custom-endpoint.aws.com"
    custom_region = "eu-west-1"
    custom_max_retries = 5
    custom_timeout = 60

    # Create client with custom parameters
    client.create_atx_agenticapi_client(
        endpoint_url=custom_endpoint,
        region=custom_region,
        max_retries=custom_max_retries,
        timeout=custom_timeout,
    )

    # Verify boto3.client was called with correct parameters
    mock_boto3_client.assert_called_once()
    call_args = mock_boto3_client.call_args[1]

    assert call_args["service_name"] == client.ATX_AGENTIC_API_SERVICE_NAME
    assert call_args["region_name"] == custom_region
    assert call_args["endpoint_url"] == custom_endpoint

    # Verify config
    config = call_args["config"]
    assert isinstance(config, BotocoreConfig)
    assert config.retries["max_attempts"] == custom_max_retries
    assert config.connect_timeout == custom_timeout
    assert config.read_timeout == custom_timeout


def test_atx_agenticapi_client_caching(mock_boto3_client, mock_environment, patched_client):
    """Test that the cached client function works as expected."""
    # Clear the cache to ensure a clean test
    client.atx_agenticapi_client.cache_clear()

    # Get client twice - we don't need to store the results, just verify the call count
    client.atx_agenticapi_client()
    client.atx_agenticapi_client()

    # Verify boto3.client was called only once
    assert mock_boto3_client.call_count == 1

    # Clear cache after test
    client.atx_agenticapi_client.cache_clear()


def test_create_atx_agenticapi_client_missing_endpoint():
    """Test client creation with missing endpoint URL."""
    with pytest.raises(KeyError) as exc_info:
        client.create_atx_agenticapi_client(endpoint_url=None)
    assert env_var.ENV_KEY_QT_AGENTIC_API_ENDPOINT in str(exc_info.value)


def test_create_atx_agenticapi_client_fallback_region(mock_boto3_client):
    """Test client creation falls back to default region."""
    # Create client without setting region
    client.create_atx_agenticapi_client(endpoint_url="https://test-endpoint.aws.com")

    # Verify default region is used
    call_args = mock_boto3_client.call_args[1]
    assert call_args["region_name"] == "us-east-1"


def test_create_atx_agenticapi_client_external_api_param(mock_boto3_client, mock_environment):
    """Test client creation with external API parameter."""
    client.create_atx_agenticapi_client(use_external_agentic_api=True)

    call_args = mock_boto3_client.call_args[1]
    assert call_args["service_name"] == client.ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME


def test_create_atx_agenticapi_client_external_api_env_var(mock_boto3_client, mock_environment):
    """Test client creation with external API environment variable."""
    os.environ[env_var.ENV_KEY_USE_EXTERNAL_AGENTIC_API] = "true"

    client.create_atx_agenticapi_client()

    call_args = mock_boto3_client.call_args[1]
    assert call_args["service_name"] == client.ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME
