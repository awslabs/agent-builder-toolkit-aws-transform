# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the AuthTokenRefresher class.
"""

import datetime
import os
from multiprocessing import Process
from unittest import mock

import pytest
from agent_builder_agentic_mcp._auth_refresher import (
    ERROR_RETRY_SECONDS,
    SAFETY_FACTOR,
    SESSION_DURATION,
    AuthTokenRefresher,
    get_auth_token_refresher,
)
from agent_builder_agentic_mcp.env_var import ENV_KEY_QT_AUTH_TOKEN_FILE


@pytest.fixture
def mock_process():
    with mock.patch("agent_builder_agentic_mcp._auth_refresher.Process") as mock_proc:
        mock_instance = mock.MagicMock(spec=Process)
        mock_proc.return_value = mock_instance
        yield mock_proc, mock_instance


@pytest.fixture
def mock_time_sleep():
    with mock.patch("time.sleep") as mock_sleep:
        yield mock_sleep


@pytest.fixture
def mock_datetime_now():
    with mock.patch("datetime.datetime") as mock_dt:
        mock_now = mock.MagicMock()
        mock_dt.now.return_value = mock_now
        mock_dt.timezone.utc = datetime.timezone.utc
        yield mock_dt, mock_now


@pytest.fixture
def mock_client():
    with mock.patch(
        "agent_builder_agentic_mcp._auth_refresher.atx_agenticapi_client"
    ) as mock_client:
        mock_client_instance = mock.MagicMock()
        mock_client.return_value = mock_client_instance
        yield mock_client, mock_client_instance


@pytest.fixture
def mock_open_file():
    with mock.patch("builtins.open", mock.mock_open()) as mock_file:
        yield mock_file


@pytest.fixture
def mock_environment():
    original_env = dict(os.environ)
    os.environ[ENV_KEY_QT_AUTH_TOKEN_FILE] = "/mock/path/to/token_file"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(autouse=True)
def clear_cache():
    # Clear the cache before each test
    get_auth_token_refresher.cache_clear()
    yield
    # Clear again after each test
    get_auth_token_refresher.cache_clear()


class TestAuthTokenRefresher:
    """Test suite for AuthTokenRefresher class."""

    def test_init_starts_child_process(self, mock_process):
        """Test that initializing AuthTokenRefresher starts a child process."""
        # Arrange
        mock_proc, mock_instance = mock_process

        # Act
        refresher = AuthTokenRefresher()

        # Assert
        mock_proc.assert_called_once()
        mock_instance.start.assert_called_once()
        assert refresher.child_process == mock_instance

    def test_child_process_property(self, mock_process):
        """Test the child_process property returns the process instance."""
        # Arrange
        mock_proc, mock_instance = mock_process

        # Act
        refresher = AuthTokenRefresher()
        process = refresher.child_process

        # Assert
        assert process == mock_instance

    @mock.patch("agent_builder_agentic_mcp._auth_refresher.AuthTokenRefresher._refresh_token")
    def test_auth_process_main(self, mock_refresh_token, mock_time_sleep):
        """Test the _auth_process_main method refreshes tokens and sleeps."""
        # Arrange — after two successful refreshes, raise KeyboardInterrupt to exit
        mock_refresh_token.side_effect = [120, 300, KeyboardInterrupt]
        refresher = AuthTokenRefresher()

        # Act
        refresher._auth_process_main()

        # Assert
        assert mock_refresh_token.call_count == 3
        mock_time_sleep.assert_has_calls([mock.call(120), mock.call(300)])

    @mock.patch("agent_builder_agentic_mcp._auth_refresher.AuthTokenRefresher._refresh_token")
    def test_auth_process_main_retries_on_exception(self, mock_refresh_token, mock_time_sleep):
        """Test that _auth_process_main catches exceptions and retries."""
        # Arrange — exception on first call, success on second, then exit
        mock_refresh_token.side_effect = [RuntimeError("boom"), 120, KeyboardInterrupt]
        refresher = AuthTokenRefresher()

        # Act
        refresher._auth_process_main()

        # Assert — first sleep is the error retry, second is the normal refresh sleep
        assert mock_refresh_token.call_count == 3
        mock_time_sleep.assert_has_calls([mock.call(ERROR_RETRY_SECONDS), mock.call(120)])

    def test_refresh_token_success(
        self, mock_client, mock_datetime_now, mock_environment, mock_open_file
    ):
        """Test successful token refresh with proper time calculation."""
        # Arrange
        mock_client_module, mock_client_instance = mock_client
        mock_dt, mock_now = mock_datetime_now

        # Setup mock response from API
        expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        mock_client_instance.refresh_auth_token.return_value = {
            "authorizationToken": "new_test_token",
            "authorizationExpiration": expiration_time,
        }

        # Setup mock datetime.now
        current_time = datetime.datetime.now(datetime.timezone.utc)
        mock_now.return_value = current_time

        # Mock _refresh_auth_token_from_agentic_api to avoid actual API call
        with mock.patch(
            "agent_builder_agentic_mcp._auth_refresher.AuthTokenRefresher._refresh_auth_token_from_agentic_api"
        ) as mock_refresh:
            mock_refresh.return_value = {
                "authorizationToken": "new_test_token",
                "authorizationExpiration": expiration_time,
            }

            # Mock time difference calculation
            with mock.patch("agent_builder_agentic_mcp._auth_refresher.datetime") as mock_dt_module:
                mock_dt_module.datetime = mock_dt
                mock_dt_module.timezone = datetime.timezone
                mock_dt_module.timedelta = datetime.timedelta

                # Create refresher and call refresh_token
                refresher = AuthTokenRefresher()

                # Mock the time difference calculation
                time_diff = 3600  # 1 hour remaining
                # Set up the mock to return our calculated time difference
                mock_expiration = mock.MagicMock()
                mock_expiration.__sub__.return_value = mock.MagicMock()
                mock_expiration.__sub__.return_value.total_seconds.return_value = time_diff
                mock_refresh.return_value["authorizationExpiration"] = mock_expiration

                time_to_sleep = refresher._refresh_token()

                # Assert
                mock_refresh.assert_called_once()
                mock_open_file.assert_called_once_with("/mock/path/to/token_file", "w")
                mock_open_file().write.assert_called_once_with("ATX_AUTHZ_TOKEN=new_test_token")

                # Verify sleep time is 50% of remaining
                assert time_to_sleep == int(3600 * SAFETY_FACTOR)

    def test_refresh_token_error(
        self, mock_client, mock_datetime_now, mock_environment, mock_open_file
    ):
        """Test error handling in token refresh method."""
        # Arrange
        mock_client_module, mock_client_instance = mock_client

        # Mock _refresh_auth_token_from_agentic_api to raise an exception
        with mock.patch(
            "agent_builder_agentic_mcp._auth_refresher.AuthTokenRefresher._refresh_auth_token_from_agentic_api"
        ) as mock_refresh:
            mock_refresh.side_effect = Exception("Test error")

            # Create refresher and call refresh_token
            refresher = AuthTokenRefresher()
            time_to_sleep = refresher._refresh_token()

            # Assert
            mock_refresh.assert_called_once()
            # Verify that no file write was attempted
            mock_open_file.assert_not_called()
            # Verify that the fallback sleep time is returned
            assert time_to_sleep == ERROR_RETRY_SECONDS

    def test_write_token_to_file_success(self, mock_environment, mock_open_file):
        """Test successful writing of token to file."""
        # Arrange
        test_token = "test_auth_token_value"
        refresher = AuthTokenRefresher()

        # Act
        refresher._write_token_to_file(test_token)

        # Assert
        mock_open_file.assert_called_once_with("/mock/path/to/token_file", "w")
        mock_open_file().write.assert_called_once_with(f"ATX_AUTHZ_TOKEN={test_token}")

    def test_write_token_to_file_missing_env_var(self, mock_open_file):
        """Test error handling when environment variable is not set."""
        # Arrange
        test_token = "test_auth_token_value"
        refresher = AuthTokenRefresher()

        # Act - with empty environment (no token file path)
        with mock.patch.dict(os.environ, {}, clear=True):
            refresher._write_token_to_file(test_token)

        # Assert - no file write should be attempted
        mock_open_file.assert_not_called()

    def test_write_token_to_file_io_error(self, mock_environment, mock_open_file):
        """Test error handling when file write fails."""
        # Arrange
        test_token = "test_auth_token_value"
        mock_open_file.side_effect = IOError("Permission denied")
        refresher = AuthTokenRefresher()

        # Act
        refresher._write_token_to_file(test_token)

        # Assert - exception should be caught and logged
        mock_open_file.assert_called_once_with("/mock/path/to/token_file", "w")

    def test_refresh_auth_token_from_agentic_api(self, mock_client):
        """Test refreshing auth token from Agentic API."""
        # Arrange
        mock_client_module, mock_client_instance = mock_client
        test_token = "new_test_token"
        expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        mock_client_instance.refresh_auth_token.return_value = {
            "authorizationToken": test_token,
            "authorizationExpiration": expiration_time,
        }

        # Mock _inject_qt_request_context to avoid dependency on environment variables
        with mock.patch(
            "agent_builder_agentic_mcp._auth_refresher._inject_qt_request_context"
        ) as mock_inject:
            mock_inject.return_value = {"sessionDuration": SESSION_DURATION}

            # Act
            refresher = AuthTokenRefresher()
            result = refresher._refresh_auth_token_from_agentic_api()

            # Assert
            mock_client_instance.refresh_auth_token.assert_called_once_with(
                sessionDuration=SESSION_DURATION
            )
            mock_inject.assert_called_once_with(kwargs={"sessionDuration": SESSION_DURATION})
            assert result["authorizationToken"] == test_token
            assert result["authorizationExpiration"] == expiration_time

    def test_get_auth_token_refresher_singleton(self):
        """Test that get_auth_token_refresher returns a singleton instance."""
        # Clear the cache to ensure a clean test
        get_auth_token_refresher.cache_clear()

        # Mock the AuthTokenRefresher class to avoid actual process creation
        with mock.patch(
            "agent_builder_agentic_mcp._auth_refresher.AuthTokenRefresher"
        ) as mock_refresher:
            # First call should create a new instance
            refresher1 = get_auth_token_refresher()
            # Second call should return the same instance
            refresher2 = get_auth_token_refresher()

            # Assert that AuthTokenRefresher was instantiated only once
            mock_refresher.assert_called_once()
            # Assert that both calls returned the same instance
            assert refresher1 is refresher2

        # Clear the cache after the test
        get_auth_token_refresher.cache_clear()
