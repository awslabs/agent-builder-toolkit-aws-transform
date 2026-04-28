import datetime
import functools
import logging
import os
import time
from multiprocessing import Process
from typing import TYPE_CHECKING, Any, Dict, Optional

from botocore.client import BaseClient

from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.env_var import (
    ATX_AUTH_TOKEN_KEY,
    ENV_KEY_AUTH_TOKEN_FILE,
    ENV_KEY_AUTHORIZATION_TOKEN,
    get_agent_context_from_env,
    retrieve_auth_token,
)
from agent_builder_sdk.utils import get_default_auth_token_file_path, write_content_to_file

if TYPE_CHECKING:
    from multiprocessing.synchronize import Event as EventType

logger = logging.getLogger(__name__)

# Session duration limits (in seconds)
MIN_SESSION_DURATION = 300  # 5 minutes
MAX_SESSION_DURATION = 43200  # 12 hours
DEFAULT_SESSION_DURATION = 43200  # 12 hours

# Token refresh timing constants (in seconds)
TOKEN_REFRESH_BUFFER_SECONDS = 40  # Buffer before token expiration to refresh
MIN_SLEEP_SECONDS = 60  # Minimum sleep time between refresh attempts
ERROR_RETRY_SECONDS = 60  # Retry interval when refresh fails


class AuthTokenRefresher:
    # Type annotation for lazy-initialized client
    agentic_api_client: Optional[BaseClient]

    def __init__(
        self,
        workspace_id: Optional[str] = None,
        job_id: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        session_duration: int = DEFAULT_SESSION_DURATION,
        first_token: str | None = None,
        token_refresh_buffer: int = TOKEN_REFRESH_BUFFER_SECONDS,
        token_refreshed_event: Optional["EventType"] = None,
    ) -> None:
        """Initialize the AuthTokenRefresher and start the token refresh process.

        Args:
            token_refreshed_event: Callback event that is signaled after each successful token refresh.
                The refresh process calls ``.set()`` once the new token has been written.
                The consumer should call ``.wait()`` to block until the signal arrives,
                then call ``.clear()`` to reset the event.
        """
        if session_duration < MIN_SESSION_DURATION or session_duration > MAX_SESSION_DURATION:
            raise ValueError(
                f"The range of session duration should be between {MIN_SESSION_DURATION} and {MAX_SESSION_DURATION}"
            )
        self.session_duration = session_duration
        self.token_refresh_buffer = token_refresh_buffer
        self.token_refreshed_event = token_refreshed_event

        self.workspace_id = workspace_id
        self.job_id = job_id
        self.agent_instance_id = agent_instance_id

        # create necessary files and assign env vars

        initial_token = (
            os.getenv(ENV_KEY_AUTHORIZATION_TOKEN) if first_token is None else first_token
        )
        self.auth_token_file_path = setup_initial_auth_token(str(initial_token))

        logger.info(
            f"Initializing AuthTokenRefresher, storing auth_token in {self.auth_token_file_path} and Set {ENV_KEY_AUTH_TOKEN_FILE} to: {self.auth_token_file_path}  "
        )

        # Initialize as None - will be created lazily to avoid pickling issues with multiprocessing
        self.agentic_api_client = None
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

    def shutdown(self) -> None:
        """Gracefully shutdown the auth token refresher process."""
        if self._child_process and self._child_process.is_alive():
            logger.info("Terminating auth token refresher process...")
            self._child_process.terminate()
            self._child_process.join(timeout=5)  # Wait up to 5 seconds
            if self._child_process.is_alive():
                logger.warning("Force killing auth token refresher process...")
                self._child_process.kill()
                self._child_process.join()
            logger.info("Auth token refresher process stopped")

    def _auth_process_main(self) -> None:
        """
        Main function for the token refresh process.
        Continuously refreshes the token and sleeps until next refresh.
        """
        logger.info("Starting token refresh process")

        try:
            while True:
                time_to_sleep = self._refresh_token()
                logger.info(f"Sleeping for {time_to_sleep} seconds before next token refresh")
                time.sleep(time_to_sleep)
        except KeyboardInterrupt:
            logger.info("Token refresh process interrupted, shutting down gracefully")
        except Exception:
            logger.warning("Token refresh process error: ", exc_info=True)
        finally:
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

            # Signal listeners that token was refreshed
            if self.token_refreshed_event is not None:
                self.token_refreshed_event.set()

            # Calculate time to sleep based on expiration timestamp
            now = datetime.datetime.now(datetime.timezone.utc)

            # Calculate time difference in seconds, with a buffer to refresh before token expires
            time_diff = (expiration_timestamp - now).total_seconds() - self.token_refresh_buffer

            # Ensure we don't sleep for a negative amount of time
            # and that we have at least minimum sleep time between refreshes
            seconds_to_sleep = max(MIN_SLEEP_SECONDS, time_diff)

            logger.info(f"Token will expire at {expiration_timestamp.isoformat()}")
            logger.info(f"Next token refresh in {seconds_to_sleep:.2f} seconds")

            # Return time to sleep in seconds
            return int(seconds_to_sleep)

        except Exception:
            logger.warning("Error refreshing token: ", exc_info=True)
            # If there's an error, retry after the defined interval
            return ERROR_RETRY_SECONDS

    def _write_token_to_file(self, auth_token: str) -> None:
        """
        Write the authentication token to the token file.

        Args:
            auth_token: The authentication token to write
        """
        logger.info("Writing token to file")
        try:
            write_content_to_file(f"{ATX_AUTH_TOKEN_KEY}={auth_token}", self.auth_token_file_path)
        except Exception:
            logger.warning("Error writing token to file: ", exc_info=True)

    def _refresh_auth_token_from_agentic_api(self) -> Dict[str, Any]:
        """
        Call the Agentic API to refresh the authentication token.

        Returns:
            Dict[str, Any]: Response containing the new token and expiration
        """
        logger.info("Calling Agentic API to refresh token")

        # Create client if it doesn't exist (lazy initialization to avoid pickling issues)
        if self.agentic_api_client is None:
            logger.info("Creating agentic API client in child process")
            self.agentic_api_client = get_agentic_api_client()

        if not all([self.workspace_id, self.job_id, self.agent_instance_id]):
            context = get_agent_context_from_env()
        else:
            context = AgenticApiRequestContext(
                workspace_id=self.workspace_id,  # type: ignore[arg-type]
                job_id=self.job_id,  # type: ignore[arg-type]
                agent_instance_id=self.agent_instance_id,  # type: ignore[arg-type]
                authorization_token=retrieve_auth_token(),
            )
        request = {"sessionDuration": self.session_duration, "requestContext": context.to_dict()}

        response = self.agentic_api_client.refresh_auth_token(**request)

        logger.info("Successfully refreshed token from Agentic API")
        return dict(response)


def setup_initial_auth_token(auth_token: str) -> str:
    """Set up initial auth token file to auth token file path and assign env var"""
    auth_token_file_path = get_default_auth_token_file_path()
    write_content_to_file(f"{ATX_AUTH_TOKEN_KEY}={auth_token}", auth_token_file_path)
    os.environ[ENV_KEY_AUTH_TOKEN_FILE] = auth_token_file_path
    return auth_token_file_path


@functools.lru_cache(maxsize=1)
def get_auth_token_refresher(
    workspace_id: Optional[str] = None,
    job_id: Optional[str] = None,
    agent_instance_id: Optional[str] = None,
    session_duration: int = DEFAULT_SESSION_DURATION,
    first_token: str | None = None,
    token_refresh_buffer: int = TOKEN_REFRESH_BUFFER_SECONDS,
    token_refreshed_event: Optional["EventType"] = None,
) -> AuthTokenRefresher:
    """
    Start the authentication token refresher as a singleton.

    If IDs are not provided, they will be retrieved from environment variables.

    Args:
        workspace_id: Workspace ID (optional, from env if not provided)
        job_id: Job ID (optional, from env if not provided)
        agent_instance_id: Agent instance ID (optional, from env if not provided)
        session_duration: Duration in seconds for the auth token session
        first_token: Initial token to use
        token_refresh_buffer: Buffer in seconds before token expiration to refresh
        token_refreshed_event: Callback event that is set after each successful token refresh

    Returns:
        AuthTokenRefresher: Singleton instance of the AuthTokenRefresher
    """
    return AuthTokenRefresher(
        workspace_id=workspace_id,
        job_id=job_id,
        agent_instance_id=agent_instance_id,
        session_duration=session_duration,
        first_token=first_token,
        token_refresh_buffer=token_refresh_buffer,
        token_refreshed_event=token_refreshed_event,
    )
