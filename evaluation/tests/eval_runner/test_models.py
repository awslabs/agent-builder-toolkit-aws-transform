# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for eval_runner data models.

Covers both families in :mod:`eval_runner.models`:
- Scoring models: ExecutionResult, MetricResult, EvaluationResult.
- Execution models: TokenUsage, TranscriptEntry, EvalGrade (and enums).
"""

from dataclasses import FrozenInstanceError

import pytest

from eval_runner.models import (
    AssertionResult,
    AssertionResultStatus,
    EvalGrade,
    TokenUsage,
    TranscriptEntry,
    TranscriptRole,
)


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


class TestTokenUsage:
    def test_add_accumulates(self) -> None:
        usage = TokenUsage()
        usage.add(
            {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150, "cachedReadTokens": 20}
        )
        usage.add(
            {"inputTokens": 200, "outputTokens": 80, "totalTokens": 280, "cachedReadTokens": 0}
        )
        assert usage.input_tokens == 300
        assert usage.output_tokens == 130
        assert usage.total_tokens == 430
        assert usage.cached_read_tokens == 20

    def test_add_none_is_noop(self) -> None:
        usage = TokenUsage()
        usage.add(None)
        assert usage.total_tokens == 0

    def test_add_empty_dict_is_noop(self) -> None:
        usage = TokenUsage()
        usage.add({})
        assert usage.total_tokens == 0

    def test_add_handles_none_values_in_dict(self) -> None:
        usage = TokenUsage()
        usage.add({"inputTokens": None, "outputTokens": 50, "totalTokens": None})
        assert usage.input_tokens == 0
        assert usage.output_tokens == 50
        assert usage.total_tokens == 0


class TestTranscriptEntry:
    def test_defaults(self) -> None:
        entry = TranscriptEntry(role=TranscriptRole.AGENT, content="Hello")
        assert entry.turn == 0
        assert entry.raw is None
        assert entry.timestamp > 0


class TestEvalGrade:
    def test_passed_true_when_all_pass(self) -> None:
        grade = EvalGrade(
            eval_id="test",
            passed=True,
            assertions=[
                AssertionResult(name="a", result=AssertionResultStatus.PASS, evidence="ok"),
            ],
            duration_seconds=1.0,
            turn_count=1,
        )
        assert grade.passed is True

    def test_needs_review_does_not_fail(self) -> None:
        grade = EvalGrade(
            eval_id="test",
            passed=True,
            assertions=[
                AssertionResult(name="a", result=AssertionResultStatus.NEEDS_REVIEW, evidence="?"),
            ],
            duration_seconds=1.0,
            turn_count=1,
        )
        assert grade.passed is True

    def test_to_dict_serializes_all_usage_fields(self) -> None:
        """to_dict() is the report.py / result.json boundary — it must carry the
        usage fields (credits, context_usage_percentage, context_window_tokens)
        the dashboard reads, not just the legacy token counts."""
        grade = EvalGrade(
            eval_id="test",
            passed=True,
            assertions=[],
            duration_seconds=1.0,
            turn_count=2,
            token_usage=TokenUsage(
                input_tokens=300,
                output_tokens=130,
                total_tokens=430,
                cached_read_tokens=20,
                credits=3.7,
                context_usage_percentage=4.24,
                context_window_tokens=1_000_000,
            ),
        )
        tok = grade.to_dict()["token_usage"]
        assert tok == {
            "input_tokens": 300,
            "output_tokens": 130,
            "total_tokens": 430,
            "cached_read_tokens": 20,
            "credits": 3.7,
            "context_usage_percentage": 4.24,
            "context_window_tokens": 1_000_000,
        }
