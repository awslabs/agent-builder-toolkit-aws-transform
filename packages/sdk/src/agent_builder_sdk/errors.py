# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
class BaseAgentError(Exception):
    """Exception from BaseAgent."""


class ClientBaseAgentError(BaseAgentError):
    """Exception caused by an LLM or user."""


class UserBaseAgentError(ClientBaseAgentError):
    """Exception for an error caused by a user."""

    def __init__(self, message: str, user_facing_message: str):
        super().__init__(message)
        self.user_facing_message = user_facing_message


class InternalBaseAgentError(BaseAgentError):
    """Internal exception from BaseAgent.

    Should not be exposed to LLMs or users because it may contain internal details.
    """


class AuthTokenUnavailableError(InternalBaseAgentError, ValueError):
    """The agent auth token could not be read from the credentials file.

    Raised when AUTH_TOKEN_FILE is unset, the file is missing or unreadable, or it has no
    ATX_AUTHZ_TOKEN value. The SDK's token refresher replaces the file atomically, so this
    is not a read racing a write and re-reading right away will not help.
    Also subclasses ValueError, which this used to be raised as, so existing callers that
    catch ValueError keep working.
    """
