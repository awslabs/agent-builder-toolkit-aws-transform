# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent interface Protocols for evaluation and evolution."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


@runtime_checkable
class EvalAgentInterface(Protocol):
    """Minimal contract for any agent to participate in evaluation.

    Any class with an execute() method satisfies this protocol.
    """

    def execute(self, test_case: TestCase) -> ExecutionResult: ...


@runtime_checkable
class EvolvableAgent(Protocol):
    """Extension for agents that support autonomous evolution.

    Requires both execute() and get_source_dir().
    """

    def execute(self, test_case: TestCase) -> ExecutionResult: ...

    def get_source_dir(self) -> Path: ...
