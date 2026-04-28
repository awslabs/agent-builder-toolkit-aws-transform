import datetime
import os
from multiprocessing import Event as MPEvent
from pathlib import Path
from unittest import mock

import pytest

from agent_builder_sdk._auth_token_refresher import (
    DEFAULT_SESSION_DURATION,
    ERROR_RETRY_SECONDS,
    MAX_SESSION_DURATION,
    MIN_SESSION_DURATION,
    MIN_SLEEP_SECONDS,
    TOKEN_REFRESH_BUFFER_SECONDS,
    AuthTokenRefresher,
    get_auth_token_refresher,
)
from agent_builder_sdk.env_var import ATX_AUTH_TOKEN_KEY, ENV_KEY_AUTH_TOKEN_FILE
from agent_builder_sdk.utils import get_default_auth_token_file_path


def test_auth_token_refresher_shutdown():
    """Test AuthTokenRefresher shutdown method."""
    with mock.patch("agent_builder_sdk._auth_token_refresher.Process") as mock_process_class:
        mock_process = mock.Mock()
        mock_process.is_alive.return_value = True
        mock_process_class.return_value = mock_process

        refresher = AuthTokenRefresher(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            first_token="test-token",
        )
        refresher._child_process = mock_process

        refresher.shutdown()

        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.join.assert_called()


def test_auth_token_refresher_shutdown_force_kill():
    """Test AuthTokenRefresher shutdown with force kill."""
    with mock.patch("agent_builder_sdk._auth_token_refresher.Process") as mock_process_class:
        mock_process = mock.Mock()
        mock_process.is_alive.side_effect = [True, True, False]  # Still alive after terminate
        mock_process_class.return_value = mock_process

        refresher = AuthTokenRefresher(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            first_token="test-token",
        )
        refresher._child_process = mock_process

        refresher.shutdown()

        # Verify process was terminated and killed
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()


def test_auth_token_refresher_shutdown_no_process():
    """Test AuthTokenRefresher shutdown when no process exists."""
    refresher = AuthTokenRefresher(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        first_token="test-token",
    )
    refresher._child_process = None

    # Should not raise any exception
    refresher.shutdown()


def test_auth_process_main_exception(caplog):
    """Test _auth_process_main handles general exceptions with proper logging."""
    refresher = AuthTokenRefresher(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        first_token="test-token",
    )

    # Mock _refresh_token to raise an exception
    refresher._refresh_token = mock.Mock(side_effect=Exception("Test error"))

    # Should handle exception gracefully and not raise
    refresher._auth_process_main()

    # Verify proper error logging with exc_info
    assert "Token refresh process error:" in caplog.text


@pytest.fixture
def mock_auth_dependencies():
    """Fixture to mock the common AuthTokenRefresher dependencies."""
    with mock.patch.object(
        AuthTokenRefresher, "start_child_process_for_token_refresh"
    ) as mock_start_process:
        mock_start_process.return_value = mock.Mock()
        yield {
            "mock_start_process": mock_start_process,
        }


class TestConstants:
    """Tests for module constants"""

    def test_constants_values(self):
        """Test that constants have expected values."""
        assert MIN_SESSION_DURATION == 300
        assert MAX_SESSION_DURATION == 43200
        assert DEFAULT_SESSION_DURATION == 43200
        assert TOKEN_REFRESH_BUFFER_SECONDS == 40
        assert MIN_SLEEP_SECONDS == 60
        assert ERROR_RETRY_SECONDS == 60


class TestGetDefaultAuthTokenFilePath:
    """Tests for get_default_auth_token_file_path function"""

    @mock.patch("os.environ.get")
    def test_container_environment_env_var(self, mock_env_get):
        """Test container environment detection via CONTAINER_ENV variable."""
        # Arrange
        mock_env_get.return_value = "true"  # CONTAINER_ENV is set

        # Act
        result = get_default_auth_token_file_path()

        # Assert
        assert result == "/home/amazon/.aws/transform-credentials"
        mock_env_get.assert_called_once_with("CONTAINER_ENV")

    @mock.patch("os.environ.get")
    @mock.patch("pathlib.Path.home")
    def test_local_environment(self, mock_home, mock_env_get):
        """Test local environment path resolution."""
        # Arrange
        mock_env_get.return_value = None  # CONTAINER_ENV not set
        mock_home.return_value = Path("/Users/testuser")

        # Act
        result = get_default_auth_token_file_path()

        # Assert
        assert result == "/Users/testuser/.aws/transform-credentials"
        mock_home.assert_called_once()


class TestAuthTokenRefresherInit:
    """Tests for AuthTokenRefresher constructor and initialization"""

    def test_init_with_default_session_duration(self, mock_auth_dependencies):
        """Test initialization with default session duration."""
        # Act
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path"
        ) as mock_get_path:
            with mock.patch(
                "agent_builder_sdk._auth_token_refresher.write_content_to_file"
            ) as mock_write:
                mock_get_path.return_value = "/test/path/credentials"

                refresher = AuthTokenRefresher()

                # Assert
                assert refresher.session_duration == DEFAULT_SESSION_DURATION
                assert refresher.token_refresh_buffer == TOKEN_REFRESH_BUFFER_SECONDS
                assert refresher.token_refreshed_event is None
                assert refresher.auth_token_file_path == "/test/path/credentials"
                assert os.environ[ENV_KEY_AUTH_TOKEN_FILE] == "/test/path/credentials"
                mock_write.assert_called_once()
                mock_auth_dependencies["mock_start_process"].assert_called_once()

    def test_init_with_custom_session_duration(self, mock_auth_dependencies):
        """Test initialization with custom session duration."""
        # Act
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path"
        ) as mock_get_path:
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                mock_get_path.return_value = "/test/path/credentials"

                refresher = AuthTokenRefresher(session_duration=1800)

                # Assert
                assert refresher.session_duration == 1800

    def test_init_with_custom_token_refresh_buffer(self, mock_auth_dependencies):
        """Test initialization with custom token refresh buffer."""
        # Act
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path"
        ) as mock_get_path:
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                mock_get_path.return_value = "/test/path/credentials"

                refresher = AuthTokenRefresher(token_refresh_buffer=1800)

                # Assert
                assert refresher.token_refresh_buffer == 1800

    def test_init_with_custom_token_refreshed_event(self, mock_auth_dependencies):
        """Test initialization with custom token refreshed event."""
        # Act
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path"
        ) as mock_get_path:
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                mock_get_path.return_value = "/test/path/credentials"

                test_event = MPEvent()
                refresher = AuthTokenRefresher(token_refreshed_event=test_event)

                # Assert
                assert refresher.token_refreshed_event is test_event

    def test_init_session_duration_validation_too_low(self):
        """Test that session duration below minimum raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            AuthTokenRefresher(session_duration=299)

        assert (
            f"The range of session duration should be between {MIN_SESSION_DURATION} and {MAX_SESSION_DURATION}"
            in str(exc_info.value)
        )

    def test_init_session_duration_validation_too_high(self):
        """Test that session duration above maximum raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            AuthTokenRefresher(session_duration=43201)

        assert (
            f"The range of session duration should be between {MIN_SESSION_DURATION} and {MAX_SESSION_DURATION}"
            in str(exc_info.value)
        )

    def test_init_session_duration_validation_boundary_values(self, mock_auth_dependencies):
        """Test that boundary values for session duration are accepted."""
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/boundary/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                # Test minimum boundary
                refresher_min = AuthTokenRefresher(session_duration=MIN_SESSION_DURATION)
                assert refresher_min.session_duration == MIN_SESSION_DURATION

                # Test maximum boundary
                refresher_max = AuthTokenRefresher(session_duration=MAX_SESSION_DURATION)
                assert refresher_max.session_duration == MAX_SESSION_DURATION


class TestAuthTokenRefresherFileOperations:
    """Tests for file writing operations"""

    def test_write_token_to_file_success(self):
        """Test successful token writing to file using utils function."""
        # Arrange
        test_token = "test-auth-token-12345"

        with mock.patch.object(AuthTokenRefresher, "start_child_process_for_token_refresh"):
            with mock.patch(
                "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
                return_value="/test/path",
            ):
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                ) as mock_write:
                    refresher = AuthTokenRefresher()

                    # Act
                    refresher._write_token_to_file(test_token)

                    # Assert
                    mock_write.assert_called_with(
                        f"{ATX_AUTH_TOKEN_KEY}={test_token}", "/test/path"
                    )
                    assert mock_write.call_count == 2

    def test_write_token_to_file_error(self, caplog):
        """Test handling of file write errors with proper logging."""
        # Arrange
        test_token = "test-token"

        with mock.patch.object(AuthTokenRefresher, "start_child_process_for_token_refresh"):
            with mock.patch(
                "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
                return_value="/test/path",
            ):
                # Allow successful initialization
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                ):
                    refresher = AuthTokenRefresher()

                # Now mock write_content_to_file to fail for the actual method call
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file",
                    side_effect=OSError("Write failed"),
                ) as mock_write:
                    # Act
                    refresher._write_token_to_file(test_token)

                    # Assert
                    mock_write.assert_called_once_with(
                        f"{ATX_AUTH_TOKEN_KEY}={test_token}", "/test/path"
                    )
                    assert "Error writing token to file:" in caplog.text


class TestAuthTokenRefresherApiCalls:
    """Tests for API interaction methods"""

    @mock.patch.object(AuthTokenRefresher, "start_child_process_for_token_refresh")
    @mock.patch("agent_builder_sdk._auth_token_refresher.get_agentic_api_client")
    @mock.patch("agent_builder_sdk._auth_token_refresher.get_agent_context_from_env")
    def test_refresh_auth_token_from_agentic_api_success(
        self, mock_get_context, mock_get_client, mock_start_child_process
    ):
        """Test successful API call for token refresh."""
        # Arrange
        mock_response = {
            "authorizationToken": "new-token-12345",
            "authorizationExpiration": datetime.datetime.now(datetime.timezone.utc),
        }

        mock_client = mock.Mock()
        mock_client.refresh_auth_token.return_value = mock_response
        mock_get_client.return_value = mock_client

        mock_context = mock.Mock()
        mock_context.to_dict.return_value = {
            "JOB_ID": "test-job-id",
            "WORKSPACE_ID": "test-workspace-id",
            "AGENT_INSTANCE_ID": "test-agent-instance-id",
            "AUTHORIZATION_TOKEN": "test-token",
        }
        mock_get_context.return_value = mock_context

        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/api/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                refresher = AuthTokenRefresher()

                # Act
                result = refresher._refresh_auth_token_from_agentic_api()

                # Assert
                assert result == mock_response
                # Verify that get_agentic_api_client was called lazily during the API call
                mock_get_client.assert_called_once()
                mock_client.refresh_auth_token.assert_called_once_with(
                    requestContext={
                        "JOB_ID": "test-job-id",
                        "WORKSPACE_ID": "test-workspace-id",
                        "AGENT_INSTANCE_ID": "test-agent-instance-id",
                        "AUTHORIZATION_TOKEN": "test-token",
                    },
                    sessionDuration=DEFAULT_SESSION_DURATION,
                )

    @mock.patch.object(AuthTokenRefresher, "start_child_process_for_token_refresh")
    @mock.patch("agent_builder_sdk._auth_token_refresher.get_agentic_api_client")
    def test_refresh_auth_token_client_creation_error(
        self, mock_get_client, mock_start_child_process, caplog
    ):
        """Test error handling when API client creation fails."""
        # Arrange
        mock_get_client.side_effect = Exception("Client creation failed")

        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/client/error/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                refresher = AuthTokenRefresher()

        # Act & Assert
        with pytest.raises(Exception, match="Client creation failed"):
            refresher._refresh_auth_token_from_agentic_api()


class TestAuthTokenRefresherTokenRefresh:
    """Tests for token refresh logic and timing calculations"""

    @mock.patch("agent_builder_sdk._auth_token_refresher.datetime")
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_refresh_token_success_with_timing(self, mock_datetime, mock_auth_dependencies):
        """Test successful token refresh with proper timing calculation."""
        # Arrange
        current_time = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        expiration_time = datetime.datetime(
            2024, 1, 1, 14, 0, 0, tzinfo=datetime.timezone.utc
        )  # 2 hours later

        mock_datetime.datetime.now.return_value = current_time
        mock_datetime.timezone = datetime.timezone

        mock_api_response = {
            "authorizationToken": "refreshed-token",
            "authorizationExpiration": expiration_time,
        }

        with mock.patch.object(
            AuthTokenRefresher,
            "_refresh_auth_token_from_agentic_api",
            return_value=mock_api_response,
        ):
            with mock.patch.object(AuthTokenRefresher, "_write_token_to_file") as mock_write:
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
                    return_value="/test/timing/path",
                ):
                    with mock.patch(
                        "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                    ):
                        refresher = AuthTokenRefresher()

                # Act
                sleep_time = refresher._refresh_token()

                # Assert
                # Expected: (2 hours * 3600 seconds) - TOKEN_REFRESH_BUFFER_SECONDS = 7160 seconds
                expected_sleep_time = (2 * 3600) - TOKEN_REFRESH_BUFFER_SECONDS
                assert sleep_time == expected_sleep_time
                mock_write.assert_called_once_with("refreshed-token")

    @mock.patch("agent_builder_sdk._auth_token_refresher.datetime")
    def test_refresh_token_minimum_sleep_time(self, mock_datetime, mock_auth_dependencies):
        """Test that minimum sleep time is enforced."""
        # Arrange
        current_time = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        expiration_time = datetime.datetime(
            2024, 1, 1, 12, 0, 30, tzinfo=datetime.timezone.utc
        )  # 30 seconds later

        mock_datetime.datetime.now.return_value = current_time
        mock_datetime.timezone = datetime.timezone

        mock_api_response = {
            "authorizationToken": "token",
            "authorizationExpiration": expiration_time,
        }

        with mock.patch.object(
            AuthTokenRefresher,
            "_refresh_auth_token_from_agentic_api",
            return_value=mock_api_response,
        ):
            with mock.patch.object(AuthTokenRefresher, "_write_token_to_file"):
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
                    return_value="/test/sleep/path",
                ):
                    with mock.patch(
                        "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                    ):
                        refresher = AuthTokenRefresher()

                # Act
                sleep_time = refresher._refresh_token()

                # Assert
                assert sleep_time == MIN_SLEEP_SECONDS

    def test_refresh_token_api_error_handling(self, caplog, mock_auth_dependencies):
        """Test that API errors are handled gracefully with proper logging."""
        # Arrange
        with mock.patch.object(
            AuthTokenRefresher,
            "_refresh_auth_token_from_agentic_api",
            side_effect=Exception("API Error"),
        ):
            with mock.patch(
                "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
                return_value="/test/error/path",
            ):
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                ):
                    refresher = AuthTokenRefresher()

            # Act
            sleep_time = refresher._refresh_token()

            # Assert
            assert sleep_time == ERROR_RETRY_SECONDS
            assert "Error refreshing token:" in caplog.text


class TestGetAuthTokenRefresherSingleton:
    """Tests for the singleton function"""

    def test_get_auth_token_refresher_returns_instance(self, mock_auth_dependencies):
        """Test that get_auth_token_refresher returns AuthTokenRefresher instance."""
        # Arrange & Act
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/singleton/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                refresher = get_auth_token_refresher()

        # Assert
        assert isinstance(refresher, AuthTokenRefresher)

    def test_get_auth_token_refresher_singleton_behavior(self, mock_auth_dependencies):
        """Test that get_auth_token_refresher returns the same instance (singleton)."""
        # Arrange & Act
        # Clear the cache first
        get_auth_token_refresher.cache_clear()

        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/singleton2/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                refresher1 = get_auth_token_refresher()
                refresher2 = get_auth_token_refresher()

        # Assert
        assert refresher1 is refresher2  # Same object instance

    def test_get_auth_token_refresher_custom_session_duration(self, mock_auth_dependencies):
        """Test get_auth_token_refresher with custom session duration."""
        # Arrange & Act
        get_auth_token_refresher.cache_clear()

        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/custom/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                refresher = get_auth_token_refresher(session_duration=1800)

        # Assert
        assert refresher.session_duration == 1800

    def test_get_auth_token_refresher_custom_token_refresh_buffer(self, mock_auth_dependencies):
        """Test get_auth_token_refresher with custom token refresh buffer."""
        # Arrange & Act
        get_auth_token_refresher.cache_clear()

        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/custom/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                refresher = get_auth_token_refresher(token_refresh_buffer=1800)

        # Assert
        assert refresher.token_refresh_buffer == 1800

    def test_get_auth_token_refresher_custom_token_refreshed_event(self, mock_auth_dependencies):
        """Test get_auth_token_refresher with custom token refreshed event."""
        # Arrange & Act
        get_auth_token_refresher.cache_clear()

        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
            return_value="/test/custom/path",
        ):
            with mock.patch("agent_builder_sdk._auth_token_refresher.write_content_to_file"):
                test_event = MPEvent()
                refresher = get_auth_token_refresher(token_refreshed_event=test_event)

        # Assert
        assert refresher.token_refreshed_event is test_event


class TestAuthTokenRefresherIntegration:
    """Integration tests for AuthTokenRefresher"""

    def test_write_token_uses_utils_function(self):
        """Test that _write_token_to_file uses the utils write_content_to_file function."""
        # Arrange
        test_token = "integration-test-token"

        with mock.patch.object(AuthTokenRefresher, "start_child_process_for_token_refresh"):
            with mock.patch(
                "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path",
                return_value="/test/integration/path",
            ):
                # Allow successful initialization
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                ):
                    refresher = AuthTokenRefresher()

                # Mock the utils function to verify it's called correctly
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                ) as mock_write:
                    # Act
                    refresher._write_token_to_file(test_token)

                    # Assert
                    mock_write.assert_called_once_with(
                        f"{ATX_AUTH_TOKEN_KEY}={test_token}", "/test/integration/path"
                    )

    def test_full_initialization_flow(self, caplog):
        """Test the complete initialization flow without mocking internal calls."""
        # Arrange
        with mock.patch(
            "agent_builder_sdk._auth_token_refresher.Process"
        ) as mock_process_class:
            mock_process = mock.Mock()
            mock_process.pid = 99999
            mock_process_class.return_value = mock_process

            with mock.patch(
                "agent_builder_sdk._auth_token_refresher.get_default_auth_token_file_path"
            ) as mock_get_path:
                with mock.patch(
                    "agent_builder_sdk._auth_token_refresher.write_content_to_file"
                ) as mock_write:
                    mock_get_path.return_value = "/test/integration/path"

                    # Act
                    refresher = AuthTokenRefresher()

                    # Assert
                    # Environment variable setup
                    assert os.environ[ENV_KEY_AUTH_TOKEN_FILE] == "/test/integration/path"

                    # Instance attributes
                    assert refresher.auth_token_file_path == "/test/integration/path"
                    # agentic_api_client is initialized as None and created lazily
                    assert refresher.agentic_api_client is None
                    assert refresher._child_process == mock_process

                    # File write operation (setup_initial_auth_token)
                    mock_write.assert_called_once()

                    # Process creation
                    mock_process_class.assert_called_once_with(
                        target=refresher._auth_process_main, daemon=True
                    )
                    mock_process.start.assert_called_once()
