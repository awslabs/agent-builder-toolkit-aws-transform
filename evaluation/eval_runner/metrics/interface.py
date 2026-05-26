# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""MetricInterface Protocol — structural typing contract for metrics."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase


@runtime_checkable
class MetricInterface(Protocol):
    """Protocol for evaluation metrics.

    Any class with a `name` property and `evaluate()` method satisfies this.
    """

    @property
    def name(self) -> str: ...

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult: ...
