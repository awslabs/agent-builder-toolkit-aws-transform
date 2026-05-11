# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import os
import typing

from agent_builder_agentic_mcp import env_var
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext
from agent_builder_agentic_mcp.server._auth_handler import get_auth_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/qt-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


def _get_request_context() -> AgenticRequestContext:
    # Get auth token directly from the auth_handler
    auth_token = get_auth_token()

    return AgenticRequestContext(
        job_id=os.environ[env_var.ENV_KEY_QT_JOB_ID],
        workspace_id=os.environ[env_var.ENV_KEY_QT_WORKSPACE_ID],
        agent_instance_id=os.environ[env_var.ENV_KEY_QT_AGENT_INSTANCE_ID],
        authorization_token=auth_token,
    )


def _inject_qt_request_context(
    kwargs: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    if "requestContext" in kwargs:
        return kwargs

    logging.info(f"Injecting request context for agent {_get_request_context()}")

    kwargs["requestContext"] = _get_request_context().to_dict()
    return kwargs
