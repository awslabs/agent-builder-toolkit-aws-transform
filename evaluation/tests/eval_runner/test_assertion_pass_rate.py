# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for AssertionPassRateMetric."""

from eval_runner.metrics.assertion_pass_rate import AssertionPassRateMetric
from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


class TestAssertionPassRateMetric:
    def _make_execution(
        self, transcript: str = "", output: str = "", tool_calls: list | None = None
    ) -> ExecutionResult:
        return ExecutionResult(
            transcript=transcript,
            output=output,
            tool_calls=tool_calls or [],
        )

    def test_no_assertions_gives_full_score(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(id="t1", name="test", user_message="hi", assertions=[])
        result = metric.evaluate(self._make_execution(), tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_transcript_contains_pass(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "transcript_contains", "check": "hello"}],
        )
        execution = self._make_execution(transcript="Agent said Hello world")
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_transcript_contains_fail(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "transcript_contains", "check": "goodbye"}],
        )
        execution = self._make_execution(transcript="Agent said Hello world")
        result = metric.evaluate(execution, tc)
        assert result.score == 0.0
        assert result.passed is False

    def test_output_contains(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "output_contains", "check": "success"}],
        )
        execution = self._make_execution(output="Operation SUCCESS completed")
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_tool_called_pass(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "tool_called", "tool": "search"}],
        )
        execution = self._make_execution(
            tool_calls=[{"name": "search", "input": {"q": "test"}}]
        )
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_tool_called_fail(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "tool_called", "tool": "deploy"}],
        )
        execution = self._make_execution(
            tool_calls=[{"name": "search", "input": {}}]
        )
        result = metric.evaluate(execution, tc)
        assert result.score == 0.0
        assert result.passed is False

    def test_ungradable_type_is_skipped_not_failed(self):
        """Types this metric doesn't own (e.g. llm_judge) are abstained on, not
        scored as failures — they emit no assertion entry and don't drag the score."""
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "llm_judge", "check": "x"}],
        )
        result = metric.evaluate(self._make_execution(), tc)
        # Abstains: no gradable assertions for this metric.
        assert result.score == 10.0
        assert result.passed is True
        assert result.details.get("assertions", []) == []

    def test_ungradable_types_excluded_from_denominator(self):
        """A mix of gradable and ungradable: score reflects only the gradable ones."""
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[
                {"name": "a1", "type": "transcript_contains", "check": "hello"},
                {"name": "a2", "type": "llm_judge", "check": "subjective"},
            ],
        )
        execution = self._make_execution(transcript="hello world")
        result = metric.evaluate(execution, tc)
        # Only a1 is gradable, and it passes → 1/1.
        assert result.score == 10.0
        assert result.passed is True
        names = [a["name"] for a in result.details["assertions"]]
        assert names == ["a1"]

    def test_mixed_assertions_partial_score(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[
                {"name": "a1", "type": "transcript_contains", "check": "hello"},
                {"name": "a2", "type": "transcript_contains", "check": "missing"},
                {"name": "a3", "type": "output_contains", "check": "done"},
            ],
        )
        execution = self._make_execution(transcript="hello world", output="done")
        result = metric.evaluate(execution, tc)
        # 2/3 passed = 6.67
        assert abs(result.score - (2 / 3 * 10.0)) < 0.01
        assert result.passed is False  # 6.67 < 7.0

    def test_case_insensitive_matching(self):
        metric = AssertionPassRateMetric()
        tc = TestCase(
            id="t1", name="test", user_message="hi",
            assertions=[{"name": "a1", "type": "transcript_contains", "check": "HELLO"}],
        )
        execution = self._make_execution(transcript="hello world")
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
