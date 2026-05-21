# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent interface ABCs for evaluation and evolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


class EvalAgentInterface(ABC):
    """Minimal contract for any agent to participate in evaluation.

    Implement execute() to run a test case and return results.
    """

    @abstractmethod
    def execute(self, test_case: TestCase) -> ExecutionResult: ...


class EvolvableAgent(EvalAgentInterface):
    """Extension for agents that support autonomous evolution.

    Adds get_source_dir() so the evolution framework knows where
    to find and patch harness files.
    """

    @abstractmethod
    def get_source_dir(self) -> Path: ...
