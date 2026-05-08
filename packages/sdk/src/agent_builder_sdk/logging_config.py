# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import os


def configure_logging():
    """Configure logging based on stage"""
    stage = os.getenv("STAGE", "prod").lower()
    log_level = "INFO" if stage == "prod" else "DEBUG"

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured for stage: {stage}, log level: {log_level}")
