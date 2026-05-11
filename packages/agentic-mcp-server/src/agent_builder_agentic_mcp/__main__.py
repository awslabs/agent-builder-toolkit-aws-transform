# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Main entry point for the package when run as a module.

This allows the package to be run with:
python -m -m agent_builder_agentic_mcp
"""

import logging
import sys

from agent_builder_agentic_mcp.main import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/atx-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        logger.error(
            f"Unhandled exception in main: {str(e)}",
        )
        sys.exit(1)
