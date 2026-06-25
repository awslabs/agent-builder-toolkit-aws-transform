# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for LatencyMetric."""

from eval_runner.metrics.latency import LatencyMetric
from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


class TestLatencyMetric:
    def _make_execution(self, duration_ms: int | None) -> ExecutionResult:
        return ExecutionResult(transcript="", output="", duration_ms=duration_ms)

    def _tc(self, **metadata) -> TestCase:
        return TestCase(id="t1", name="test", user_message="hi", metadata=metadata)

    def test_no_budget_abstains(self):
        result = LatencyMetric().evaluate(self._make_execution(5000), self._tc())
        assert result.score == 10.0
        assert result.passed is True

    def test_no_duration_abstains(self):
        result = LatencyMetric().evaluate(
            self._make_execution(None), self._tc(max_latency_ms=1000)
        )
        assert result.score == 10.0
        assert result.passed is True

    def test_under_budget_full_score(self):
        result = LatencyMetric().evaluate(
            self._make_execution(800), self._tc(max_latency_ms=1000)
        )
        assert result.score == 10.0
        assert result.passed is True

    def test_at_budget_full_score(self):
        result = LatencyMetric().evaluate(
            self._make_execution(1000), self._tc(max_latency_ms=1000)
        )
        assert result.score == 10.0

    def test_double_budget_scores_five(self):
        result = LatencyMetric().evaluate(
            self._make_execution(2000), self._tc(max_latency_ms=1000)
        )
        assert result.score == 5.0
        assert result.passed is False

    def test_score_never_negative(self):
        result = LatencyMetric().evaluate(
            self._make_execution(100_000), self._tc(max_latency_ms=1000)
        )
        assert 0.0 <= result.score <= 10.0

    def test_string_budget_is_coerced(self):
        # YAML may author the budget as a quoted string; must not TypeError.
        result = LatencyMetric().evaluate(
            self._make_execution(800), self._tc(max_latency_ms="1000")
        )
        assert result.score == 10.0
        assert result.passed is True

    def test_non_numeric_budget_abstains(self):
        result = LatencyMetric().evaluate(
            self._make_execution(800), self._tc(max_latency_ms="fast")
        )
        assert result.score == 10.0
        assert "no valid max_latency_ms" in result.details["reason"]
