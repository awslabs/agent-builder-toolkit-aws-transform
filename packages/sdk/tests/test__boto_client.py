"""Tests for _boto_client module."""

import os
from unittest import mock

import boto3
from botocore.client import BaseClient

from agent_builder_sdk._boto_client import DEFAULT_BOTO_CONFIG, create_bedrock_client


class TestCreateBedrockClient:
    """Tests for create_bedrock_client function."""

    def test_create_bedrock_client_with_default_region(self):
        """Test create_bedrock_client with default region."""
        with mock.patch.object(boto3, "Session") as mock_session, mock.patch.dict(
            os.environ, {}, clear=True
        ):
            mock_client = mock.MagicMock(spec=BaseClient)
            mock_session.return_value.client.return_value = mock_client

            # Call the function
            client = create_bedrock_client()

            # Verify the session was created
            mock_session.assert_called_once()

            # Verify client was created with correct parameters
            mock_session.return_value.client.assert_called_once_with(
                service_name="bedrock-runtime",
                region_name="us-east-1",
                config=DEFAULT_BOTO_CONFIG,
            )

            # Verify the returned client is the mock client
            assert client == mock_client

    def test_create_bedrock_client_with_specified_region(self):
        """Test create_bedrock_client with specified region."""
        with mock.patch.object(boto3, "Session") as mock_session:
            mock_client = mock.MagicMock(spec=BaseClient)
            mock_session.return_value.client.return_value = mock_client

            # Call the function with a specific region
            client = create_bedrock_client(region="us-west-2")

            # Verify the session was created
            mock_session.assert_called_once()

            # Verify client was created with correct parameters
            mock_session.return_value.client.assert_called_once_with(
                service_name="bedrock-runtime",
                region_name="us-west-2",
                config=DEFAULT_BOTO_CONFIG,
            )

            # Verify the returned client is the mock client
            assert client == mock_client

    def test_create_bedrock_client_with_environment_region(self):
        """Test create_bedrock_client with region from environment variable."""
        with mock.patch.object(boto3, "Session") as mock_session, mock.patch.dict(
            os.environ, {"AWS_REGION": "eu-west-1"}
        ):
            mock_client = mock.MagicMock(spec=BaseClient)
            mock_session.return_value.client.return_value = mock_client

            # Call the function without specifying a region
            client = create_bedrock_client()

            # Verify the session was created
            mock_session.assert_called_once()

            # Verify client was created with correct parameters
            mock_session.return_value.client.assert_called_once_with(
                service_name="bedrock-runtime",
                region_name="eu-west-1",
                config=DEFAULT_BOTO_CONFIG,
            )

            # Verify the returned client is the mock client
            assert client == mock_client

    def test_default_boto_config(self):
        """Test that DEFAULT_BOTO_CONFIG has expected values."""
        assert DEFAULT_BOTO_CONFIG.retries["max_attempts"] == 3
        assert DEFAULT_BOTO_CONFIG.retries["mode"] == "adaptive"
        assert DEFAULT_BOTO_CONFIG.retries["total_max_attempts"] == 3
        assert DEFAULT_BOTO_CONFIG.connect_timeout == 15
        assert DEFAULT_BOTO_CONFIG.read_timeout == 45
        assert DEFAULT_BOTO_CONFIG.max_pool_connections == 10
