# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import argparse
import logging
import pathlib
import sys
import typing

from agent_builder_agentic_mcp import env_var
from agent_builder_agentic_mcp._auth_refresher import get_auth_token_refresher
from agent_builder_agentic_mcp.server import mcp
from agent_builder_agentic_mcp.server._auth_handler import AuthTokenError, get_auth_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def verify_initialization() -> None:
    """
    Verify that initialization was successful by attempting to read the auth token.
    This ensures that the environment variables are set correctly and the auth token file is readable.
    """
    try:
        # Call get_auth_token() to verify we can read the token
        get_auth_token()
        logger.info("Initialization verification successful: Auth token is readable")
    except AuthTokenError as e:
        sys.exit(f"Initialization failed due to auth token error: {e}")
    except Exception as e:
        sys.exit(f"Unexpected error during initialization verification: {e}")


def _non_empty_argparse_type(
    argument_value: typing.Optional[typing.Any],
) -> typing.Optional[typing.Any]:
    """Custom type for argparse that ensures a non-empty string."""
    if not argument_value or (isinstance(argument_value, str) and not argument_value.strip()):
        raise argparse.ArgumentTypeError("argument cannot be empty or whitespace only")
    return argument_value


def main() -> None:
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="Run ATX Platform AgenticAPI MCP server")
    parser.add_argument(
        "--agenticApiEndpoint",
        type=_non_empty_argparse_type,
        required=True,
        help="Endpoint address of the AWS Transform Agentic API",
    )
    parser.add_argument(
        "--region",
        help="Region of the ATX platform Agentic API (if not set, will try to use AWS_REGION from environment variables)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse"],
        help="Transport protocol to use (stdio or sse)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to when using SSE transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5002,
        help="Port to bind to when using SSE transport (default: 5002)",
    )
    parser.add_argument(
        "--workspaceId",
        type=_non_empty_argparse_type,
        required=True,
        help="WorkspaceID of the current agent instance (cannot be empty)",
    )
    parser.add_argument(
        "--jobId",
        type=_non_empty_argparse_type,
        required=True,
        help="Job ID of the current agent instance (cannot be empty)",
    )
    parser.add_argument(
        "--agentInstanceId",
        type=_non_empty_argparse_type,
        required=True,
        help="Agent instance ID of the current agent (cannot be empty)",
    )
    parser.add_argument(
        "--authTokenFile",
        type=str,
        default=f"{pathlib.Path.home()}/.aws/transform-credentials",
        help="Path to a custom auth token file (default: /home/<user>/.aws/transform-credentials)",
    )
    parser.add_argument(
        "--refreshToken",
        action="store_true",
        help="Let ATX MCP server automatically refresh ATX/QT platform authorization token (if False, MCP server will only be valid during the expiration of initially provided ATX_AUTHZ_TOKEN in authTokenFile)",
    )
    args = parser.parse_args()

    agentic_api_endpoint = args.agenticApiEndpoint
    workspace_id = args.workspaceId
    job_id = args.jobId
    agent_instance_id = args.agentInstanceId
    region = args.region if hasattr(args, "region") else None

    logger.info(
        "Starting MCP server with AgenticAPI endpoint: {}, region: {}, workspaceId: {}, jobId: {}, agentInstanceId: {}".format(
            agentic_api_endpoint, region, workspace_id, job_id, agent_instance_id
        )
    )

    env_var.export_agent_instance_metadata(args)

    # Verify initialization after setting environment variables
    verify_initialization()

    # Start auth sub-process if requested at launch.
    if args.refreshToken:
        logger.info("Launching sub-process for refreshing auth token")
        get_auth_token_refresher()

    if args.transport == "sse":
        env_var.load(sse_host_override=args.host, sse_port_override=args.port)
        mcp.run(transport=args.transport)
    else:
        logger.info("Starting MCP server with stdio transport")
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
