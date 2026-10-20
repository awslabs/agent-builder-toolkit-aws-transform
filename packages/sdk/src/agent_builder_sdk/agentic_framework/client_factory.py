# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Client factory for ATX Agentic API.
"""

import functools
import logging
import os
from typing import Optional

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotocoreConfig

from agent_builder_sdk.env_var import is_external_agentic_api_enabled
from agent_builder_sdk.utils import TransformEndpointConfig
from agent_builder_types import TransformAgenticServiceClient

logger = logging.getLogger(__name__)


# Service constants
ATX_AGENTIC_API_SERVICE_NAME = "transformagenticservice"
ATX_AGENTIC_API_COMPONENT_NAME = "agenticapi"
ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME = "transformagenticservice"
ATX_STREAMING_AGENTIC_API_SERVICE_NAME = "transformagentsstreamingservice"


@functools.lru_cache(maxsize=1)
def get_agentic_api_client() -> TransformAgenticServiceClient:
    """Get cached agentic API client."""
    return create_agentic_api_client()


@functools.lru_cache(maxsize=1)
def get_streaming_agentic_api_client() -> BaseClient:
    """Get cached streaming (ConverseStream) agentic API client."""
    return create_streaming_agentic_api_client()


def create_streaming_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    max_retries: int = 3,
    connect_timeout: int = 5,
    read_timeout: int = 10 * 60,
) -> BaseClient:
    """
    Create boto3 client for the ATX ConverseStream (streaming) agentic API.

    Mirrors ``create_agentic_api_client`` — same stage/region/endpoint_url resolution and
    the same host — but targets the ``transformagentsstreamingservice`` service and uses a
    large read timeout so the long-lived SSE body isn't cut off mid-stream.

    Args:
        stage: Environment stage (defaults to env var)
        region: AWS region (defaults to env var)
        endpoint_url: Direct endpoint URL (overrides stage/region)
        max_retries: Maximum retries for API calls
        connect_timeout: TCP connect timeout in seconds
        read_timeout: Per-read idle timeout in seconds, reset on every SSE chunk. This is not
            a cap on total turn length and should outlast the platform streaming turn cap.

    Returns:
        Configured boto3 client for the streaming service.
    """
    # Get values from environment if not provided
    stage = stage or os.environ.get("STAGE")
    endpoint_url = endpoint_url or os.environ.get("QT_AGENTIC_API_ENDPOINT")
    region = region or os.environ.get("AWS_REGION", "us-east-1")

    if not endpoint_url and not (stage and region):
        raise ValueError("Either endpoint_url or both stage and region must be provided")

    boto_config = BotocoreConfig(
        retries={"max_attempts": max_retries, "mode": "standard"},
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )

    # The streaming service shares the sync client's host, so reuse the same endpoint resolution.
    resolved_endpoint_url = endpoint_url or _resolve_agentic_api_endpoint_url(stage, region)
    logger.debug(
        f"Creating streaming agentic API client for region={region} at {resolved_endpoint_url}"
    )
    return boto3.client(
        service_name=ATX_STREAMING_AGENTIC_API_SERVICE_NAME,
        endpoint_url=resolved_endpoint_url,
        region_name=region,
        config=boto_config,
    )


def _sync_service_name() -> str:
    """The boto3 service name for the sync agentic API — external vs internal partition."""
    return (
        ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME
        if is_external_agentic_api_enabled()
        else ATX_AGENTIC_API_SERVICE_NAME
    )


def _resolve_agentic_api_endpoint_url(stage: Optional[str], region: Optional[str]) -> str:
    """Resolve the agentic API endpoint host from stage/region, honoring the external API branch.

    The streaming service shares this same host (it differs only by URL path), so all agentic API
    clients — sync, external, and streaming — resolve their endpoint through here.
    """
    if is_external_agentic_api_enabled():
        return TransformEndpointConfig.create_external_agenticapi_endpoint_url(
            str(stage), str(region)
        )
    return TransformEndpointConfig.create_endpoint_url(
        str(stage), str(region), ATX_AGENTIC_API_COMPONENT_NAME
    )


def create_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    max_retries: int = 3,
    connect_timeout: int = 5,
    read_timeout: int = 30,
) -> BaseClient:
    """
    Create boto3 client for AWS Transform Agentic API.

    Args:
        stage: Environment stage (defaults to env var)
        region: AWS region (defaults to env var)
        endpoint_url: Direct endpoint URL (overrides stage/region)
        max_retries: Maximum retries for API calls
        connect_timeout: TCP connect timeout in seconds
        read_timeout: Read timeout in seconds

    Returns:
        Configured boto3 client
    """
    # Get values from environment if not provided
    stage = stage or os.environ.get("STAGE")
    endpoint_url = endpoint_url or os.environ.get("QT_AGENTIC_API_ENDPOINT")
    region = region or os.environ.get("AWS_REGION", "us-east-1")

    if not endpoint_url and not (stage and region):
        raise ValueError("Either endpoint_url or both stage and region must be provided")

    boto_config = BotocoreConfig(
        retries={"max_attempts": max_retries, "mode": "standard"},
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )

    resolved_endpoint_url = endpoint_url or _resolve_agentic_api_endpoint_url(stage, region)
    return boto3.client(
        service_name=_sync_service_name(),
        endpoint_url=resolved_endpoint_url,
        region_name=region,
        config=boto_config,
    )
