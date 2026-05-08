# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Extension handler types.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtensionResponse:
    """Standard response from extension handlers."""

    message: str
    metadata: Optional[dict] = None
    extensions: Optional[list] = None
