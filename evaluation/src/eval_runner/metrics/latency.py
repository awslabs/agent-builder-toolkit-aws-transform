# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in latency metric.

Scores how a run's wall-clock time compares to a per-test budget. Like the
other deterministic metrics, it is *opt-in*: a test only participates if it
declares a budget in ``metadata.max_latency_ms``. Tests that don't care about
latency abstain (score 10.0, pass), so a suite that adds this metric without
setting a budget on every test is never penalised for the un-budgeted ones.
"""

from __future__ import annotations

from eval_runner.metrics._metadata import coerce_positive_number
from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase


class LatencyMetric:
    """Scores ``execution.duration_ms`` against ``metadata.max_latency_ms``.

    Scoring (lower latency is better):
    - at or under budget          -> 10.0
    - over budget, degrading       -> 10 * (budget / duration), so 2x budget
      scores 5.0, 5x budget scores 2.0, etc. (never negative, never above 10)

    Passes if score >= 7.0 (i.e. within ~1.43x of budget). Abstains with 10.0/pass
    when no budget is set or the run did not record a duration — there is nothing
    to judge against, and a missing measurement should not manufacture a failure.
    """

    @property
    def name(self) -> str:
        return "latency"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        budget = coerce_positive_number(test_case.metadata.get("max_latency_ms"))
        if budget is None:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no valid max_latency_ms budget set"},
            )

        duration = execution.duration_ms
        if duration is None:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "run recorded no duration"},
            )

        ratio = duration / budget
        score = 10.0 if ratio <= 1.0 else max(0.0, 10.0 / ratio)
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 7.0,
            details={
                "duration_ms": duration,
                "budget_ms": budget,
                "ratio": ratio,
            },
        )
