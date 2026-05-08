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
from agent_builder_types import TransformAgenticServiceClient

from agent_builder_sdk.env_var import is_external_agentic_api_enabled
from agent_builder_sdk.utils import TransformEndpointConfig

logger = logging.getLogger(__name__)


# Service constants
ATX_AGENTIC_API_SERVICE_NAME = "elasticgumbyagenticservice"
ATX_AGENTIC_API_COMPONENT_NAME = "agenticapi"
ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME = "transformagenticservice"


@functools.lru_cache(maxsize=1)
def get_agentic_api_client() -> TransformAgenticServiceClient:
    """Get cached agentic API client."""
    return create_agentic_api_client()


def create_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    max_retries: int = 3,
    timeout: int = 30,
) -> BaseClient:
    """
    Create boto3 client for AWS Transform Agentic API.

    Args:
        stage: Environment stage (defaults to env var)
        region: AWS region (defaults to env var)
        endpoint_url: Direct endpoint URL (overrides stage/region)
        max_retries: Maximum retries for API calls
        timeout: Timeout in seconds

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
        connect_timeout=timeout,
        read_timeout=timeout,
    )

    if is_external_agentic_api_enabled():
        return _build_external_agentic_api_client(stage, region, endpoint_url, boto_config)
    return _build_agentic_api_client(stage, region, endpoint_url, boto_config)


def _build_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    boto_config: Optional[BotocoreConfig] = None,
) -> TransformAgenticServiceClient:

    if endpoint_url:
        return boto3.client(
            service_name=ATX_AGENTIC_API_SERVICE_NAME,
            endpoint_url=endpoint_url,
            region_name=region,
            config=boto_config,
        )
    else:
        constructed_endpoint_url = TransformEndpointConfig.create_endpoint_url(
            str(stage), str(region), ATX_AGENTIC_API_COMPONENT_NAME
        )
        return boto3.client(
            service_name=ATX_AGENTIC_API_SERVICE_NAME,
            endpoint_url=constructed_endpoint_url,
            region_name=region,
            config=boto_config,
        )


def _build_external_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    boto_config: Optional[BotocoreConfig] = None,
) -> BaseClient:

    if endpoint_url:
        return boto3.client(
            service_name=ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME,
            endpoint_url=endpoint_url,
            region_name=region,
            config=boto_config,
        )
    else:
        constructed_endpoint_url = (
            TransformEndpointConfig.create_external_agenticapi_endpoint_url(
                str(stage), str(region)
            )
        )
        return boto3.client(
            service_name=ATX_EXTERNAL_AGENTIC_API_SERVICE_NAME,
            endpoint_url=constructed_endpoint_url,
            region_name=region,
            config=boto_config,
        )
