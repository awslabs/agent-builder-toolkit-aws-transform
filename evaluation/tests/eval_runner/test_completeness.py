# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for CompletenessMetric (task 2.3)."""

from eval_runner.metrics.completeness import CompletenessMetric
from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


class TestCompletenessMetric:
    def _make_execution(
        self,
        transcript: str = "",
        output: str = "done",
        turn_count: int | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(transcript=transcript, output=output, turn_count=turn_count)

    def _make_tc(self, metadata: dict | None = None, max_turns: int = 1) -> TestCase:
        return TestCase(
            id="t1", name="test", user_message="hi",
            metadata=metadata or {}, max_turns=max_turns,
        )

    # --- abstain paths -----------------------------------------------------

    def test_abstains_when_no_signal(self):
        """No markers and no turn_count -> abstain (10.0/pass)."""
        metric = CompletenessMetric()
        result = metric.evaluate(self._make_execution(turn_count=None), self._make_tc(max_turns=12))
        assert result.score == 10.0
        assert result.passed is True
        assert "no completion signal" in result.details["reason"]

    def test_abstains_when_max_turns_too_small(self):
        """max_turns<=1 leaves no room to end early -> heuristic abstains."""
        metric = CompletenessMetric()
        result = metric.evaluate(self._make_execution(turn_count=1), self._make_tc(max_turns=1))
        assert result.score == 10.0
        assert result.passed is True
        assert "no completion signal" in result.details["reason"]

    # --- turn-budget signal ------------------------------------------------

    def test_completed_below_budget_with_output_passes(self):
        """Ended before the ceiling + non-empty output -> 10.0/pass."""
        metric = CompletenessMetric()
        execution = self._make_execution(turn_count=5, output="here are the results")
        result = metric.evaluate(execution, self._make_tc(max_turns=12))
        assert result.score == 10.0
        assert result.passed is True
        assert result.details["completed"] is True
        assert result.details["completion_signal"] == "turn_budget"

    def test_truncated_at_budget_fails(self):
        """Hit the turn ceiling (truncated) -> not completed -> 5.0/fail."""
        metric = CompletenessMetric()
        execution = self._make_execution(turn_count=12, output="still going")
        result = metric.evaluate(execution, self._make_tc(max_turns=12))
        assert result.score == 5.0
        assert result.passed is False
        assert result.details["completed"] is False

    def test_completed_but_empty_output_fails(self):
        metric = CompletenessMetric()
        execution = self._make_execution(turn_count=5, output="   ")
        result = metric.evaluate(execution, self._make_tc(max_turns=12))
        assert result.score == 5.0
        assert result.passed is False
        assert result.details["output_non_empty"] is False

    def test_truncated_and_empty_scores_zero(self):
        metric = CompletenessMetric()
        execution = self._make_execution(turn_count=12, output="")
        result = metric.evaluate(execution, self._make_tc(max_turns=12))
        assert result.score == 0.0
        assert result.passed is False

    # --- explicit marker override (takes precedence over turn budget) ------

    def test_marker_present_passes_even_at_budget(self):
        """An explicit completion marker overrides the turn-budget check."""
        metric = CompletenessMetric()
        tc = self._make_tc({"completion_markers": ["__DONE__"]}, max_turns=12)
        # turn_count == max_turns would fail the budget check, but the marker wins.
        execution = self._make_execution(transcript="human: __DONE__", output="ok", turn_count=12)
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True
        assert result.details["completion_signal"] == "marker"
        assert result.details["matched_markers"] == ["__DONE__"]

    def test_marker_absent_fails(self):
        metric = CompletenessMetric()
        tc = self._make_tc({"completion_markers": ["__DONE__"]}, max_turns=12)
        execution = self._make_execution(transcript="conversation truncated", output="x", turn_count=3)
        result = metric.evaluate(execution, tc)
        assert result.score == 5.0
        assert result.passed is False
        assert result.details["completed"] is False
        assert result.details["matched_markers"] == []

    def test_case_insensitive_marker(self):
        metric = CompletenessMetric()
        tc = self._make_tc({"completion_markers": ["__DONE__"]}, max_turns=12)
        execution = self._make_execution(transcript="agent emitted __done__", output="ok", turn_count=4)
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_multiple_markers_any_match(self):
        """Markers are OR-matched; matched_markers lists only those present."""
        metric = CompletenessMetric()
        tc = self._make_tc({"completion_markers": ["FINISHED", "COMPLETE"]}, max_turns=12)
        execution = self._make_execution(transcript="task COMPLETE now", output="ok", turn_count=4)
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.details["matched_markers"] == ["COMPLETE"]

    def test_single_string_marker_coerced(self):
        metric = CompletenessMetric()
        tc = self._make_tc({"completion_markers": "FINISHED"}, max_turns=12)
        execution = self._make_execution(transcript="FINISHED", output="ok", turn_count=4)
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_name(self):
        assert CompletenessMetric().name == "completeness"
