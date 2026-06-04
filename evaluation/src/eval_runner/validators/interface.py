# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Protocols and data types for patch validation and generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal protocol for LLM invocation."""

    def invoke(self, prompt: str) -> str:
        pass


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validator's assessment of a proposed patch."""

    valid: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PatchResult:
    """Result of a patch generation attempt."""

    patch: str = ""
    success: bool = False
    error: str = ""


@runtime_checkable
class ValidatorInterface(Protocol):
    """Protocol for patch validators in the evolution safety pipeline."""

    @property
    def name(self) -> str:
        pass

    def validate(self, patch: str, context: dict) -> ValidationResult:
        pass


@runtime_checkable
class PatcherInterface(Protocol):
    """Protocol for patch generators (auto-patchers)."""

    @property
    def name(self) -> str:
        pass

    def generate(self, source: str, diagnosis: str, context: dict) -> PatchResult:
        pass
