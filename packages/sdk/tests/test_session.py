# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.session import RefreshableSession


class TestRefreshableSession:
    """Tests for RefreshableSession class"""

    def test_init_with_required_params(self):
        """Test initialization with required parameters."""
        session = RefreshableSession(
            role_arn="arn:aws:iam::123456789012:role/TestRole", session_name="test-session"
        )

        assert session.role_arn == "arn:aws:iam::123456789012:role/TestRole"
        assert session.session_name == "test-session"
        assert session.session_duration == 3600  # default
        assert session.region_name is None  # default

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        mock_sts_client = Mock()

        session = RefreshableSession(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            session_name="test-session",
            session_duration=7200,
            region_name="us-west-2",
            sts_client=mock_sts_client,
            custom_param="test",
        )

        assert session.role_arn == "arn:aws:iam::123456789012:role/TestRole"
        assert session.session_name == "test-session"
        assert session.session_duration == 7200
        assert session.region_name == "us-west-2"
        assert session.sts_client == mock_sts_client
        assert session.session_kwargs == {"custom_param": "test"}

    def test_init_validates_role_arn(self):
        """Test that initialization validates role_arn is provided."""
        with pytest.raises(ValueError, match="role_arn is required"):
            RefreshableSession(role_arn="", session_name="test-session")

    def test_init_validates_session_name(self):
        """Test that initialization validates session_name is provided."""
        with pytest.raises(ValueError, match="session_name is required"):
            RefreshableSession(role_arn="arn:aws:iam::123456789012:role/TestRole", session_name="")

    @patch("agent_builder_sdk.session.get_session")
    @patch("agent_builder_sdk.session.RefreshableCredentials")
    def test_refreshable_session_success(self, mock_refreshable_creds, mock_get_session):
        """Test successful creation of refreshable session."""
        # Setup mocks
        mock_botocore_session = Mock()
        mock_get_session.return_value = mock_botocore_session

        mock_credentials = Mock()
        mock_refreshable_creds.create_from_metadata.return_value = mock_credentials

        # Mock the credential fetching
        session = RefreshableSession(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            session_name="test-session",
            region_name="us-east-1",
        )

        with patch.object(
            session, "_RefreshableSession__get_session_credentials"
        ) as mock_get_creds:
            mock_get_creds.return_value = {
                "access_key": "AKIATEST123",
                "secret_key": "secret123",
                "token": "token123",
                "expiry_time": "2024-01-01T12:00:00",
            }

            with patch("boto3.Session") as mock_boto_session:
                session.refreshable_session()

                # Verify RefreshableCredentials was created correctly
                mock_refreshable_creds.create_from_metadata.assert_called_once()

                # Verify botocore session was configured
                assert mock_botocore_session._credentials == mock_credentials

                # Verify boto3.Session was created with correct parameters
                mock_boto_session.assert_called_once_with(
                    botocore_session=mock_botocore_session, region_name="us-east-1"
                )

    @patch("boto3.client")
    def test_refreshable_session_handles_sts_exceptions(self, mock_boto_client):
        """Test that refreshable_session handles STS exceptions properly."""
        # Mock the STS client to raise an exception
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.side_effect = Exception("STS call failed")

        session = RefreshableSession(
            role_arn="arn:aws:iam::123456789012:role/TestRole", session_name="test-session"
        )

        with pytest.raises(Exception, match="STS call failed"):
            session.refreshable_session()

    @patch("agent_builder_sdk.session.get_session")
    @patch("boto3.client")
    def test_refreshable_session_handles_botocore_exceptions(
        self, mock_boto_client, mock_get_session
    ):
        """Test that refreshable_session handles botocore session creation exceptions."""
        # Mock successful STS call
        mock_sts = Mock()
        mock_boto_client.return_value = mock_sts
        mock_credentials = {
            "AccessKeyId": "AKIATEST123",
            "SecretAccessKey": "secret123",
            "SessionToken": "token123",
            "Expiration": datetime(2024, 1, 1, 12, 0, 0),
        }
        mock_sts.assume_role.return_value = {"Credentials": mock_credentials}

        # Mock get_session to raise an exception
        mock_get_session.side_effect = Exception("Botocore session creation failed")

        session = RefreshableSession(
            role_arn="arn:aws:iam::123456789012:role/TestRole", session_name="test-session"
        )

        with pytest.raises(Exception, match="Botocore session creation failed"):
            session.refreshable_session()
