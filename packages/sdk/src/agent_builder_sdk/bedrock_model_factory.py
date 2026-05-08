# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Bedrock model factory for creating and configuring Bedrock models.
"""

import logging
import os
from typing import Any

from strands.models import BedrockModel

from agent_builder_sdk.env_var import ENV_KEY_BEDROCK_SHARED_CAPACITY_ROLE_ARN
from agent_builder_sdk.session import RefreshableSession

logger = logging.getLogger(__name__)


class BedrockModelFactory:
    """Factory for creating Bedrock model clients."""

    @staticmethod
    def create_with_shared_capacity_role(**kwargs: Any) -> BedrockModel:
        """
        Create a BedrockModel with shared capacity role assumption.

        This is useful for consuming Bedrock capacity from an account with higher
        Bedrock capacity by assuming a role that has access to shared capacity resources.

        Args:
            **kwargs: BedrockModel arguments (must include model_id and region_name)

        Returns:
            Initialized BedrockModel instance with shared capacity role configuration
        """
        region_name = kwargs["region_name"]
        role_arn = os.getenv(ENV_KEY_BEDROCK_SHARED_CAPACITY_ROLE_ARN)
        if role_arn:
            try:
                logger.info(f"Initializing BedrockModel with shared capacity role: {role_arn}")
                refreshable_session_obj = RefreshableSession(
                    role_arn=role_arn,
                    session_name="platform-base-agent",
                    region_name=region_name,
                )
                boto_session = refreshable_session_obj.refreshable_session()
                kwargs["boto_session"] = boto_session
                kwargs.pop("region_name")
            except Exception as e:
                logger.warning(
                    f"Failed to create BedrockModel with shared capacity role, falling back to default credential: {e}"
                )
                kwargs.pop("boto_session", None)
        else:
            logger.info(
                f"No BedrockSharedCapacityRole available for region {region_name}, using default credentials"
            )

        return BedrockModel(**kwargs)
