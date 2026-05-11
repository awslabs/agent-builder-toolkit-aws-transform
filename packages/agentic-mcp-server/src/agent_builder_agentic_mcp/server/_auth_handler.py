# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import os
import pathlib
from functools import lru_cache
from typing import Optional

from agent_builder_agentic_mcp.env_var import ENV_KEY_QT_AUTH_TOKEN_FILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/qt-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)

ATX_AUTH_TOKEN_KEY = "ATX_AUTHZ_TOKEN"


class AuthTokenError(Exception):
    """Exception raised for errors in the authentication token retrieval process."""

    pass


class AuthHandler:
    """Handler for authentication-related operations."""

    def __init__(self) -> None:
        """
        Initialize the AuthHandler using the auth token file path from environment variable.
        """
        # Get the credentials file path from environment variable
        auth_token_file_path = os.environ.get(ENV_KEY_QT_AUTH_TOKEN_FILE)

        if auth_token_file_path is None:
            raise AuthTokenError(
                f"Environment variable {ENV_KEY_QT_AUTH_TOKEN_FILE} not set. Please ensure proper initialization."
            )

        self.credentials_file = pathlib.Path(auth_token_file_path)

    def get_auth_token(self) -> str:
        """
        Retrieves the authentication token from the credentials file.
        Always reads from the file to ensure the most up-to-date token.

        Returns:
            str: The authentication token value.

        Raises:
            AuthTokenError: If the credentials file is not found or the token is not present.
        """
        # Check if the file exists
        if not self.credentials_file.exists():
            raise AuthTokenError(
                f"Authentication credentials file not found at {self.credentials_file}"
            )

        # Read the file and look for the ATX_AUTHZ_TOKEN
        token: Optional[str] = None
        try:
            with open(self.credentials_file, "r") as file:
                for line in file:
                    line = line.strip()
                    if line.startswith(ATX_AUTH_TOKEN_KEY):
                        token = line.split("=", 1)[1]
                        break
        except IOError as e:
            raise AuthTokenError(f"Error reading credentials file: {e}")

        # Check if the token was found
        if token is None:
            raise AuthTokenError("ATX_AUTHZ_TOKEN not found in credentials file")

        return token


@lru_cache(maxsize=1)
def get_auth_handler() -> AuthHandler:
    """
    Returns a singleton instance of the AuthHandler class.
    Uses lru_cache to ensure only one instance is created.

    Returns:
        AuthHandler: Singleton instance of the AuthHandler class.
    """
    return AuthHandler()


def get_auth_token() -> str:
    """
    Retrieves the authentication token using the AuthHandler.

    Returns:
        str: The authentication token value.

    Raises:
        AuthTokenError: If the credentials file is not found or the token is not present.
    """
    return get_auth_handler().get_auth_token()
