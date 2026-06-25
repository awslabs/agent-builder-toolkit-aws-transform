# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for CostBudgetMetric."""

from eval_runner.metrics.cost_budget import CostBudgetMetric
from eval_runner.models import ExecutionResult, TokenUsage
from eval_runner.test_case import TestCase


class TestCostBudgetMetric:
    def _make_execution(self, credits: float | None) -> ExecutionResult:
        usage = None if credits is None else TokenUsage(credits=credits)
        return ExecutionResult(transcript="", output="", token_usage=usage)

    def _tc(self, **metadata) -> TestCase:
        return TestCase(id="t1", name="test", user_message="hi", metadata=metadata)

    def test_no_budget_abstains(self):
        result = CostBudgetMetric().evaluate(self._make_execution(5.0), self._tc())
        assert result.score == 10.0
        assert result.passed is True

    def test_no_usage_abstains(self):
        result = CostBudgetMetric().evaluate(
            self._make_execution(None), self._tc(max_credits=10)
        )
        assert result.score == 10.0
        assert result.passed is True

    def test_zero_credits_abstains_not_perfect(self):
        # kiro-cli may report 0 credits; that must not score a misleading perfect.
        result = CostBudgetMetric().evaluate(
            self._make_execution(0.0), self._tc(max_credits=10)
        )
        assert result.score == 10.0
        assert result.details["reason"] == "driver reported no credits"

    def test_under_budget_full_score(self):
        result = CostBudgetMetric().evaluate(
            self._make_execution(8.0), self._tc(max_credits=10)
        )
        assert result.score == 10.0
        assert result.passed is True

    def test_double_budget_scores_five(self):
        result = CostBudgetMetric().evaluate(
            self._make_execution(20.0), self._tc(max_credits=10)
        )
        assert result.score == 5.0
        assert result.passed is False

    def test_string_budget_is_coerced(self):
        # YAML metadata may author the budget as a quoted string; it must work,
        # not silently TypeError into a 0.0/fail.
        result = CostBudgetMetric().evaluate(
            self._make_execution(8.0), self._tc(max_credits="10")
        )
        assert result.score == 10.0
        assert result.passed is True

    def test_non_numeric_budget_abstains(self):
        result = CostBudgetMetric().evaluate(
            self._make_execution(8.0), self._tc(max_credits="lots")
        )
        assert result.score == 10.0
        assert "no valid max_credits" in result.details["reason"]
