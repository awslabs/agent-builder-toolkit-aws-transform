# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
import functools
import logging
import os
import time
from multiprocessing import Process
from typing import Any, Dict

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.env_var import ENV_KEY_QT_AUTH_TOKEN_FILE
from agent_builder_agentic_mcp.server._inject_qt_request_context import _inject_qt_request_context

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/qt-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)

SAFETY_FACTOR = 0.5  # Refresh at 50% of token lifetime
MIN_SLEEP_SECONDS = 60
ERROR_RETRY_SECONDS = 60
SESSION_DURATION = 43200


class AuthTokenRefresher:
    def __init__(self) -> None:
        """Initialize the AuthTokenRefresher and start the token refresh process."""
        logger.info("Initializing AuthTokenRefresher")
        self._child_process = self.start_child_process_for_token_refresh()

    def start_child_process_for_token_refresh(self) -> Process:
        """
        Start a child process that handles token refreshing.

        Returns:
            Process: The started child process
        """
        logger.info("Starting token refresh child process")
        process = Process(target=self._auth_process_main, daemon=True)
        process.start()
        logger.info(f"Token refresh process started with PID {process.pid}")
        return process

    @property
    def child_process(self) -> Process:
        """
        Get the child process that handles token refreshing.

        Returns:
            Process: The token refresh child process
        """
        return self._child_process

    def _auth_process_main(self) -> None:
        """
        Main function for the token refresh process.
        Continuously refreshes the token and sleeps until next refresh.
        """
        logger.info("Starting token refresh process")

        while True:
            try:
                time_to_sleep = self._refresh_token()
                logger.info(f"Sleeping for {time_to_sleep} seconds before next token refresh")
                time.sleep(time_to_sleep)
            except KeyboardInterrupt:
                logger.info("Token refresh process interrupted, shutting down gracefully")
                break
            except Exception:
                logger.warning("Token refresh process error, retrying: ", exc_info=True)
                time.sleep(ERROR_RETRY_SECONDS)
        logger.info("Token refresh process stopped")

    def _refresh_token(self) -> int:
        """
        Refresh the authentication token and calculate time to sleep until next refresh.

        Returns:
            int: Number of seconds to sleep before next refresh
        """
        logger.info("Refreshing authentication token")

        try:
            refresh_token_response = self._refresh_auth_token_from_agentic_api()
            refreshed_auth_token = refresh_token_response["authorizationToken"]
            expiration_timestamp = refresh_token_response["authorizationExpiration"]

            # Write token back to the file
            self._write_token_to_file(refreshed_auth_token)

            # Calculate time to sleep based on expiration timestamp
            now = datetime.datetime.now(datetime.timezone.utc)

            # Refresh at 50% of remaining lifetime to provide hours of retry
            # headroom instead of seconds. For a 12h token this means refreshing
            # at ~6h, giving plenty of time to retry on transient failures.
            remaining = (expiration_timestamp - now).total_seconds()
            time_diff = remaining * SAFETY_FACTOR

            seconds_to_sleep = max(MIN_SLEEP_SECONDS, time_diff)

            logger.info(f"Token will expire at {expiration_timestamp.isoformat()}")
            logger.info(f"Next token refresh in {seconds_to_sleep:.2f} seconds")

            # Return time to sleep in seconds
            return int(seconds_to_sleep)

        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            # If there's an error, retry after a short delay
            return ERROR_RETRY_SECONDS

    def _write_token_to_file(self, auth_token: str) -> None:
        """
        Write the authentication token to the token file.

        Args:
            auth_token: The authentication token to write
        """
        logger.info("Writing token to file")

        try:
            auth_token_file_path = os.environ.get(ENV_KEY_QT_AUTH_TOKEN_FILE)
            if auth_token_file_path is None:
                logger.error(f"Environment variable {ENV_KEY_QT_AUTH_TOKEN_FILE} not set")
                return

            with open(auth_token_file_path, "w") as file:
                file.write(f"ATX_AUTHZ_TOKEN={auth_token}")
                file.flush()

            logger.info("Token successfully written to file")
        except Exception as e:
            logger.error(f"Error writing token to file: {str(e)}")

    def _refresh_auth_token_from_agentic_api(self) -> Dict[str, Any]:
        """
        Call the Agentic API to refresh the authentication token.

        Returns:
            Dict[str, Any]: Response containing the new token and expiration
        """
        logger.info("Calling Agentic API to refresh token")

        client = atx_agenticapi_client()
        kwargs: Dict[str, Any] = {"sessionDuration": SESSION_DURATION}  # 12 hours in seconds
        response = client.refresh_auth_token(**_inject_qt_request_context(kwargs=kwargs))

        logger.info("Successfully refreshed token from Agentic API")
        return dict(response)


@functools.lru_cache(maxsize=1)
def get_auth_token_refresher() -> AuthTokenRefresher:
    """
    Start the authentication token refresher as a singleton.

    Returns:
        AuthTokenRefresher: Singleton instance of the AuthTokenRefresher
    """
    logger.info("Starting AuthTokenRefresher singleton")
    return AuthTokenRefresher()
