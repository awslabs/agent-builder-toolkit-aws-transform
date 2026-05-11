# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Shared ATX Agent Registry client configuration."""

import os
from typing import Any

import boto3

SERVICE_NAME = "awstransformagentregistryexternal"

REGION_TO_AIRPORT_CODE = {
    "us-east-1": "iad",
    "us-east-2": "cmh",
    "us-west-1": "sfo",
    "us-west-2": "pdx",
    "eu-west-1": "dub",
    "eu-west-2": "lhr",
    "eu-central-1": "fra",
    "ap-southeast-1": "sin",
    "ap-southeast-2": "syd",
    "ap-northeast-1": "nrt",
    "ap-northeast-2": "icn",
    "ap-south-1": "bom",
    "sa-east-1": "gru",
    "ca-central-1": "yul",
}


def registry_client(
    stage: str | None = None,
    region: str | None = None,
    endpoint_url: str | None = None,
) -> Any:
    """Create ATX Agent Registry client.

    Args:
        stage: Deployment stage (default: from ATX_STAGE env var or "prod")
        region: AWS region (default: from AWS_REGION env var or "us-east-1")
        endpoint_url: Explicit endpoint URL override (default: derived from region + stage)

    Returns:
        Configured boto3 client
    """
    region = region or os.environ.get("AWS_REGION") or "us-east-1"
    stage = stage or os.environ.get("ATX_STAGE") or "prod"

    if not endpoint_url:
        airport_code = REGION_TO_AIRPORT_CODE.get(region)
        if not airport_code:
            raise ValueError(
                f'Unsupported region "{region}". Supported: {", ".join(REGION_TO_AIRPORT_CODE.keys())}'
            )
        endpoint_url = os.environ.get(
            "ATX_REGISTRY_ENDPOINT",
            f"https://{airport_code}.{stage}.agent-registry-external.elastic-gumby.ai.aws.dev",
        )

    return boto3.client(
        SERVICE_NAME,
        region_name=region,
        endpoint_url=endpoint_url,
    )
