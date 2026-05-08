# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Main entry point for the MCP server."""

import argparse

from agent_builder_mcp.server import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATX Agent Builder MCP Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--log-file", type=str, help="Path to log file (default: no logging)")
    args = parser.parse_args()

    main(log_file=args.log_file, verbose=args.verbose)
