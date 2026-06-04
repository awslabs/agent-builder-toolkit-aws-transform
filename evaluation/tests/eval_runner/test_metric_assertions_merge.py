# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for _metric_assertions_to_results merge precedence."""

from eval_runner.cli import _metric_assertions_to_results
from eval_runner.models import (
    AssertionResultStatus,
    EvaluationResult,
    ExecutionResult,
    MetricResult,
)


def _result(metric_results: list[MetricResult]) -> EvaluationResult:
    return EvaluationResult(
        test_case_id="tc",
        execution=ExecutionResult(transcript="", output=""),
        metric_results=metric_results,
    )


def test_llm_judge_verdict_wins_over_unknown_type_fallback():
    """The judge's verdict must survive even when assertion_pass_rate ran first
    and emitted an 'unknown assertion type' FAIL for the same llm_judge assertion."""
    fallback = MetricResult(
        metric_name="assertion_pass_rate",
        score=0.0,
        passed=False,
        details={
            "assertions": [
                {
                    "name": "introduces_capabilities",
                    "type": "llm_judge",
                    "passed": False,
                    "reason": "unknown assertion type: 'llm_judge'",
                }
            ]
        },
    )
    judge = MetricResult(
        metric_name="llm_judge",
        score=10.0,
        passed=True,
        details={
            "assertions": [
                {
                    "name": "introduces_capabilities",
                    "result": "pass",
                    "evidence": "Agent listed five capabilities at turn 3.",
                    "turn_number": 3,
                }
            ]
        },
    )

    # assertion_pass_rate first (matches the configured metric order).
    merged = _metric_assertions_to_results(_result([fallback, judge]))

    assert len(merged) == 1
    a = merged[0]
    assert a.result == AssertionResultStatus.PASS
    assert a.turn_number == 3
    assert "unknown assertion type" not in a.evidence


def test_order_independent_judge_precedence():
    """Judge wins regardless of metric ordering."""
    fallback = MetricResult(
        metric_name="assertion_pass_rate",
        score=0.0,
        passed=False,
        details={"assertions": [{"name": "x", "type": "llm_judge", "passed": False,
                                 "reason": "unknown assertion type: 'llm_judge'"}]},
    )
    judge = MetricResult(
        metric_name="llm_judge",
        score=0.0,
        passed=False,
        details={"assertions": [{"name": "x", "result": "fail",
                                 "evidence": "Tool never invoked.", "turn_number": None}]},
    )

    for ordering in ([fallback, judge], [judge, fallback]):
        merged = _metric_assertions_to_results(_result(ordering))
        assert merged[0].evidence == "Tool never invoked."


def test_deterministic_only_assertion_preserved():
    """A genuinely deterministic assertion (no judge entry) still maps through."""
    fallback = MetricResult(
        metric_name="assertion_pass_rate",
        score=10.0,
        passed=True,
        details={"assertions": [{"name": "tool_called", "type": "tool_called", "passed": True}]},
    )
    merged = _metric_assertions_to_results(_result([fallback]))
    assert merged[0].result == AssertionResultStatus.PASS
    assert merged[0].name == "tool_called"
