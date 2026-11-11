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

    May be transient: the token is written by a separate refresh process, so a read that
    finds the file unreadable or without the token key can succeed on a later attempt, and
    retrieve_auth_token re-reads a bounded number of times before raising this. A missing
    env var or missing file is treated as configuration and is not retried.
    Also subclasses ValueError, which this used to be raised as, so existing callers that
    catch ValueError keep working.
    """
