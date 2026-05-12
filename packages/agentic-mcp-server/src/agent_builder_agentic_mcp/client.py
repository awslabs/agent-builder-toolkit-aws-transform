# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Client utilities for the AWS Transform Agentic API.

This module provides utility functions for creating and configuring
boto3 clients for the AWS Transform Agentic API.
"""

import functools
import logging
import os
from typing import Optional

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotocoreConfig

from agent_builder_agentic_mcp import env_var

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/atx-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)

ATX_AGENTIC_API_SERVICE_NAME = "transformagenticservice"
ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME = "transformagenticservice"


@functools.lru_cache(maxsize=1)
def atx_agenticapi_client() -> BaseClient:
    return create_atx_agenticapi_client()


def create_atx_agenticapi_client(
    endpoint_url: Optional[str] = None,
    region: Optional[str] = None,
    max_retries: int = 3,
    timeout: int = 30,
    use_external_agentic_api: Optional[bool] = None,
) -> BaseClient:
    """
    Create a boto3 client for the AWS Transform Agentic API.

    Args:
        endpoint_url: Custom endpoint URL (defaults to environment variable or standard endpoint)
        region: AWS region (defaults to environment variable or us-west-2)
        max_retries: Maximum number of retries for API calls
        timeout: Timeout in seconds for API calls
        use_external_agentic_api: flag to use external_agentic_api(service_name: transformagents)

    Returns:
        A configured boto3 client
    """
    region = region or os.environ.get("AWS_REGION", "us-east-1")
    use_external_agentic_api = use_external_agentic_api or (
        os.environ.get(env_var.ENV_KEY_USE_EXTERNAL_AGENTIC_API, "False").lower() == "true"
    )
    endpoint_url = endpoint_url or os.environ[env_var.ENV_KEY_QT_AGENTIC_API_ENDPOINT]

    boto_config = BotocoreConfig(
        retries={"max_attempts": max_retries, "mode": "standard"},
        connect_timeout=timeout,
        read_timeout=timeout,
    )

    boto3_service_name = (
        ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME
        if use_external_agentic_api
        else ATX_AGENTIC_API_SERVICE_NAME
    )
    logger.info(
        f"Inside MCP package - endpoint url: {endpoint_url}, service-name: {boto3_service_name}"
    )

    client = boto3.client(
        service_name=boto3_service_name,
        region_name=region,
        endpoint_url=endpoint_url,
        config=boto_config,
    )

    logger.info(
        f"Client created, service: {boto3_service_name}, region: {region}, endpoint: {endpoint_url}"
    )

    return client
