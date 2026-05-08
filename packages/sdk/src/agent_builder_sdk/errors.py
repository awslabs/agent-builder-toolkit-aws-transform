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
