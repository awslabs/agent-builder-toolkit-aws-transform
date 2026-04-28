"""
Boto3 client creation utility.

This module provides a utility function for creating boto3 clients.
"""

import logging
import os
from typing import Optional

import boto3
from botocore.client import BaseClient
from botocore.config import Config

# Configure logging
logger = logging.getLogger(__name__)

# Configure boto3 retry strategy
DEFAULT_BOTO_CONFIG = Config(
    retries={
        "max_attempts": 3,
        "mode": "adaptive",
        "total_max_attempts": 3,
    },
    connect_timeout=15,
    read_timeout=45,
    max_pool_connections=10,
)


def create_bedrock_client(
    region: Optional[str] = None,
    session: Optional[boto3.Session] = None,
) -> BaseClient:
    """
    Create a boto3 client for Bedrock.

    Args:
        region: AWS region (defaults to environment variable or us-east-1)
        session: The boto3 Session to use to construct the client

    Returns:
        A configured boto3 client
    """
    # Get region from environment or use default
    if region is None:
        region = os.getenv("AWS_REGION", "us-east-1")

    # Initialize AWS Bedrock client for Claude with custom retry config
    session = session or boto3.Session()

    logger.info(f"Creating Bedrock client for region {region}")

    return session.client(
        service_name="bedrock-runtime", region_name=region, config=DEFAULT_BOTO_CONFIG
    )
