# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import typing
from dataclasses import dataclass


@dataclass(frozen=True)
class McpToolRepr:
    """Definition for a tool the client can call."""

    name: str
    """The name of the tool."""
    input_schema: dict[str, typing.Any]
    """A JSON Schema object defining the expected parameters for the tool."""
    description: str | None = None
    """A human-readable description of the tool."""
