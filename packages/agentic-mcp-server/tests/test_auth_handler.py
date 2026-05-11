# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
import pathlib
from unittest import mock

import pytest
from agent_builder_agentic_mcp.server._auth_handler import (
    AuthHandler,
    AuthTokenError,
    get_auth_handler,
    get_auth_token,
)


class TestAuthHandler:
    """Test suite for authentication handler."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        # Clear the cache before each test
        get_auth_handler.cache_clear()
        yield
        # Clear again after each test if needed
        get_auth_handler.cache_clear()

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/path/to/credentials"})
    def test_get_auth_handler_singleton(self):
        """Test that get_auth_handler returns a singleton instance."""
        handler1 = get_auth_handler()
        handler2 = get_auth_handler()

        assert handler1 is handler2
        assert isinstance(handler1, AuthHandler)

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/path/to/credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_success(self, mock_home, mock_open, mock_exists):
        """Test successful retrieval of auth token."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock file content
        test_token = "test_auth_token_value"
        mock_file = mock.MagicMock()
        mock_file.__iter__.return_value = [f"ATX_AUTHZ_TOKEN={test_token}\n"]
        mock_open.return_value.__enter__.return_value = mock_file

        # Call the function and verify the result
        token = get_auth_token()
        assert token == test_token

        # Verify the correct file was opened
        expected_path = pathlib.Path("/mock/path/to/credentials")
        mock_open.assert_called_once_with(expected_path, "r")

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/home/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_file_not_found(self, mock_home, mock_exists):
        """Test error handling when credentials file is not found."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = False

        # Verify exception is raised
        with pytest.raises(AuthTokenError) as excinfo:
            get_auth_token()

        assert "Authentication credentials file not found" in str(excinfo.value)
        assert "/mock/home/.aws/transform-credentials" in str(excinfo.value)

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/home/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_key_not_present(self, mock_home, mock_open, mock_exists):
        """Test error handling when ATX_AUTHZ_TOKEN key is not in the file."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock file content without the token
        mock_file = mock.MagicMock()
        mock_file.__iter__.return_value = ["OTHER_KEY=some_value\n"]
        mock_open.return_value.__enter__.return_value = mock_file

        # Verify exception is raised
        with pytest.raises(AuthTokenError) as excinfo:
            get_auth_token()

        assert "ATX_AUTHZ_TOKEN not found" in str(excinfo.value)

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/home/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_empty_file(self, mock_home, mock_open, mock_exists):
        """Test error handling with an empty credentials file."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock empty file
        mock_file = mock.MagicMock()
        mock_file.__iter__.return_value = []
        mock_open.return_value.__enter__.return_value = mock_file

        # Verify exception is raised
        with pytest.raises(AuthTokenError) as excinfo:
            get_auth_token()

        assert "ATX_AUTHZ_TOKEN not found" in str(excinfo.value)

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/home/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_file_read_error(self, mock_home, mock_exists):
        """Test error handling when file cannot be read."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock file read error
        with mock.patch("builtins.open", side_effect=IOError("Permission denied")):
            with pytest.raises(AuthTokenError) as excinfo:
                get_auth_token()

            assert "Error reading credentials file" in str(excinfo.value)
            assert "Permission denied" in str(excinfo.value)

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/home/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_with_multiple_entries(self, mock_home, mock_open, mock_exists):
        """Test retrieving token when file has multiple entries."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock file content with multiple entries
        test_token = "multi_entry_token"
        mock_file = mock.MagicMock()
        mock_file.__iter__.return_value = [
            "FIRST_KEY=first_value\n",
            f"ATX_AUTHZ_TOKEN={test_token}\n",
            "ANOTHER_KEY=another_value\n",
        ]
        mock_open.return_value.__enter__.return_value = mock_file

        # Call the function and verify the result
        token = get_auth_token()
        assert token == test_token

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/mock/home/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_with_commented_lines(self, mock_home, mock_open, mock_exists):
        """Test retrieving token when file has commented lines."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock file content with comments
        test_token = "commented_file_token"
        mock_file = mock.MagicMock()
        mock_file.__iter__.return_value = [
            "# This is a comment\n",
            f"ATX_AUTHZ_TOKEN={test_token}\n",
            "# Another comment\n",
        ]
        mock_open.return_value.__enter__.return_value = mock_file

        # Call the function and verify the result
        token = get_auth_token()
        assert token == test_token

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/root/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("pathlib.Path.home")
    def test_get_auth_token_with_sudo(self, mock_home, mock_exists):
        """Test behavior when running as root/sudo user."""
        # Setup mocks to simulate root user
        mock_home.return_value = pathlib.Path("/root")
        mock_exists.return_value = False

        # Verify exception is raised with root path
        with pytest.raises(AuthTokenError) as excinfo:
            get_auth_token()

        assert "/root/.aws/transform-credentials" in str(excinfo.value)

    @mock.patch.dict(os.environ, {"QT_AUTH_TOKEN_FILE": "/root/.aws/transform-credentials"})
    @mock.patch("pathlib.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("pathlib.Path.home")
    def test_auth_handler_direct_usage(self, mock_home, mock_open, mock_exists):
        """Test using AuthHandler directly."""
        # Setup mocks
        mock_home.return_value = pathlib.Path("/mock/home")
        mock_exists.return_value = True

        # Mock file content
        test_token = "direct_handler_token"
        mock_file = mock.MagicMock()
        mock_file.__iter__.return_value = [f"ATX_AUTHZ_TOKEN={test_token}\n"]
        mock_open.return_value.__enter__.return_value = mock_file

        # Call the handler directly and verify the result
        handler = AuthHandler()
        token = handler.get_auth_token()
        assert token == test_token
