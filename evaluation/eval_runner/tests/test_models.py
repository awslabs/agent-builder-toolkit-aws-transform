# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for eval_runner data models — ExecutionResult, MetricResult, EvaluationResult."""

from dataclasses import FrozenInstanceError

import pytest


class TestExecutionResult:
    def test_create_with_required_fields(self):
        from eval_runner.models import ExecutionResult

        result = ExecutionResult(
            transcript="Agent: Hello\nUser: Hi",
            output="Final output here",
        )
        assert result.transcript == "Agent: Hello\nUser: Hi"
        assert result.output == "Final output here"
        assert result.tool_calls == []
        assert result.duration_ms is None

    def test_create_with_all_fields(self):
        from eval_runner.models import ExecutionResult

        result = ExecutionResult(
            transcript="Agent: I'll search for that.",
            tool_calls=[{"name": "keyword_search", "input": {"query": "orchestrator"}}],
            output="Here are the results...",
            duration_ms=1523,
        )
        assert result.tool_calls == [{"name": "keyword_search", "input": {"query": "orchestrator"}}]
        assert result.duration_ms == 1523

    def test_is_immutable(self):
        from eval_runner.models import ExecutionResult

        result = ExecutionResult(transcript="test", output="out")
        with pytest.raises(FrozenInstanceError):
            result.transcript = "modified"


class TestMetricResult:
    def test_create_passing(self):
        from eval_runner.models import MetricResult

        result = MetricResult(
            metric_name="assertion_pass_rate",
            score=9.5,
            passed=True,
        )
        assert result.metric_name == "assertion_pass_rate"
        assert result.score == 9.5
        assert result.passed is True
        assert result.details == {}

    def test_create_failing_with_details(self):
        from eval_runner.models import MetricResult

        result = MetricResult(
            metric_name="tool_usage",
            score=3.0,
            passed=False,
            details={"reason": "Expected tool 'keyword_search' not called"},
        )
        assert result.passed is False
        assert result.details["reason"] == "Expected tool 'keyword_search' not called"

    def test_score_bounds(self):
        from eval_runner.models import MetricResult

        with pytest.raises(ValueError):
            MetricResult(metric_name="x", score=-1.0, passed=False)
        with pytest.raises(ValueError):
            MetricResult(metric_name="x", score=11.0, passed=True)


class TestEvaluationResult:
    def test_create_with_test_case_id(self):
        from eval_runner.models import EvaluationResult, ExecutionResult, MetricResult

        execution = ExecutionResult(transcript="t", output="o")
        metrics = [MetricResult(metric_name="m", score=8.0, passed=True)]
        result = EvaluationResult(
            test_case_id="onboarding-intermediate",
            execution=execution,
            metric_results=metrics,
        )
        assert result.test_case_id == "onboarding-intermediate"
        assert result.execution is execution
        assert result.metric_results == metrics

    def test_passed_property_all_pass(self):
        from eval_runner.models import EvaluationResult, ExecutionResult, MetricResult

        execution = ExecutionResult(transcript="t", output="o")
        metrics = [
            MetricResult(metric_name="a", score=8.0, passed=True),
            MetricResult(metric_name="b", score=7.0, passed=True),
        ]
        result = EvaluationResult(
            test_case_id="test-1", execution=execution, metric_results=metrics
        )
        assert result.passed is True

    def test_passed_property_any_fail(self):
        from eval_runner.models import EvaluationResult, ExecutionResult, MetricResult

        execution = ExecutionResult(transcript="t", output="o")
        metrics = [
            MetricResult(metric_name="a", score=8.0, passed=True),
            MetricResult(metric_name="b", score=2.0, passed=False),
        ]
        result = EvaluationResult(
            test_case_id="test-1", execution=execution, metric_results=metrics
        )
        assert result.passed is False

    def test_passed_property_no_metrics(self):
        from eval_runner.models import EvaluationResult, ExecutionResult

        execution = ExecutionResult(transcript="t", output="o")
        result = EvaluationResult(
            test_case_id="test-1", execution=execution, metric_results=[]
        )
        assert result.passed is True
