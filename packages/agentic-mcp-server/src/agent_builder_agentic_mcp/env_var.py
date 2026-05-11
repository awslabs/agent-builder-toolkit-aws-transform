# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import argparse
import logging
import os
import pathlib
import typing

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ENV_KEY_AWS_REGION = "AWS_REGION"
ENV_KEY_QT_WORKSPACE_ID = "QT_WORKSPACE_ID"
ENV_KEY_QT_JOB_ID = "QT_JOB_ID"
ENV_KEY_QT_AGENT_INSTANCE_ID = "QT_AGENT_INSTANCE_ID"
ENV_KEY_QT_AGENTIC_API_ENDPOINT = "QT_AGENTIC_API_ENDPOINT"
ENV_KEY_QT_AUTH_TOKEN_FILE = "QT_AUTH_TOKEN_FILE"
ENV_KEY_ISENGARD_ACCOUNT = "ISENGARD_ACCOUNT"
ENV_KEY_ISENGARD_ROLE = "ISENGARD_ROLE"
ENV_KEY_USE_EXTERNAL_AGENTIC_API = "USE_EXTERNAL_AGENTIC_API"

ENV_VAR_FASTMCP_PORT = "FASTMCP_PORT"
ENV_VAR_FASTMCP_HOST = "FASTMCP_HOST"

DEFAULT_AUTH_TOKEN_FILE_PATH = ".aws/transform/credentials"


def load(
    sse_host_override: typing.Optional[str] = None, sse_port_override: typing.Optional[int] = None
) -> None:
    load_dotenv()

    if sse_host_override is not None:
        logger.info(
            f"Overriding FASTMCP_HOST {os.environ.get(ENV_VAR_FASTMCP_HOST)} with: {sse_host_override}"
        )
        os.environ[ENV_VAR_FASTMCP_HOST] = sse_host_override

    if sse_port_override is not None:
        logger.info(
            f"Overriding FASTMCP_PORT {os.environ.get(ENV_VAR_FASTMCP_PORT)} with: {sse_port_override}"
        )
        os.environ[ENV_VAR_FASTMCP_PORT] = str(sse_port_override)


def export_agent_instance_metadata(args: argparse.Namespace) -> None:
    os.environ[ENV_KEY_QT_WORKSPACE_ID] = args.workspaceId
    os.environ[ENV_KEY_QT_JOB_ID] = args.jobId
    os.environ[ENV_KEY_QT_AGENT_INSTANCE_ID] = args.agentInstanceId
    os.environ[ENV_KEY_QT_AGENTIC_API_ENDPOINT] = args.agenticApiEndpoint

    if args.isengardCredentials:
        account_id, role_name = args.isengardCredentials
        os.environ[ENV_KEY_ISENGARD_ACCOUNT] = account_id
        os.environ[ENV_KEY_ISENGARD_ROLE] = role_name

    if hasattr(args, "region") and args.region:
        logger.info(
            f"Overriding AWS_REGION {os.environ.get(ENV_KEY_AWS_REGION)} with: {args.region}"
        )
        os.environ[ENV_KEY_AWS_REGION] = args.region

    # Handle auth token file path
    auth_token_file_path = None

    # Determine the auth token file path
    if "authTokenFile" in args:
        auth_token_file_path = args.authTokenFile
    else:
        # Default path at root of current user
        home_dir = pathlib.Path.home()
        auth_token_file_path = str(home_dir / DEFAULT_AUTH_TOKEN_FILE_PATH)

    # Check if the file exists
    if not pathlib.Path(auth_token_file_path).exists():
        raise FileNotFoundError(
            f"Authentication credentials file not found at {auth_token_file_path}"
        )

    # Set the environment variable
    logger.info(f"Setting auth token file path: {auth_token_file_path}")
    os.environ[ENV_KEY_QT_AUTH_TOKEN_FILE] = auth_token_file_path
