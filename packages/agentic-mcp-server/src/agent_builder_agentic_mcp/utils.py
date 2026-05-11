# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Utility functions for the Agent Builder Agentic MCP package.
"""

from typing import Any, List, cast


def dig(d: dict, keys: List[str], default: Any = None) -> Any:
    """
    Dig into a nested dictionary safely

    :param d: The dictionary to dig into
    :param keys: The list of keys to dig for
    :param default: The default value to return if key is not found
    :return: The nested value or default if it is not found
    """
    for k in keys:
        if d is not None and isinstance(d, dict):
            if k not in d:
                return default
            d = cast(Any, d.get(k))
        else:
            return d
    return d
