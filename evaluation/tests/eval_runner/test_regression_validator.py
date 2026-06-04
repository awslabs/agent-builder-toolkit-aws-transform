# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for RegressionValidator."""

import pytest

from eval_runner.models import EvaluationResult, ExecutionResult, MetricResult
from eval_runner.validators.interface import ValidatorInterface
from eval_runner.validators.regression import RegressionValidator


def _make_result(test_case_id: str, scores: dict[str, float]) -> EvaluationResult:
    """Helper: create an EvaluationResult with given metric scores."""
    return EvaluationResult(
        test_case_id=test_case_id,
        execution=ExecutionResult(transcript="ok", output="ok"),
        metric_results=[
            MetricResult(metric_name=name, score=score, passed=score >= 5.0)
            for name, score in scores.items()
        ],
    )


class TestRegressionValidator:
    def test_satisfies_protocol(self):
        v = RegressionValidator()
        assert isinstance(v, ValidatorInterface)
        assert v.name == "regression"

    def test_repr(self):
        v = RegressionValidator(regression_threshold=1.5)
        assert repr(v) == "RegressionValidator(regression_threshold=1.5)"

    def test_flat_scores_pass(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0, "completeness": 7.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.0, "completeness": 7.0})]

        v = RegressionValidator()
        result = v.validate("some patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True

    def test_mixed_improvement_and_flat_passes(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0, "completeness": 7.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.5, "completeness": 7.0})]

        v = RegressionValidator()
        result = v.validate("some patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True

    def test_regression_beyond_threshold_rejected(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": 7.0})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("some patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is False
        assert "accuracy" in result.reason.lower()

    def test_regression_within_threshold_passes(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": 7.6})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("some patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True

    def test_regression_at_exact_threshold_passes(self):
        # delta == -threshold uses strict <, so exact-threshold drops pass.
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": 7.5})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True

    def test_improvement_passes(self):
        baseline = [_make_result("tc1", {"accuracy": 6.0})]
        post_patch = [_make_result("tc1", {"accuracy": 9.0})]

        v = RegressionValidator()
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True

    def test_multiple_metrics_all_must_pass(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0, "safety": 9.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.5, "safety": 7.0})]

        v = RegressionValidator(regression_threshold=1.0)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is False
        assert "safety" in result.reason.lower()

    def test_multiple_test_cases_aggregated(self):
        baseline = [
            _make_result("tc1", {"accuracy": 8.0}),
            _make_result("tc2", {"accuracy": 9.0}),
        ]
        post_patch = [
            _make_result("tc1", {"accuracy": 7.0}),
            _make_result("tc2", {"accuracy": 9.5}),
        ]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        # Average accuracy: baseline 8.5, post 8.25 — delta -0.25, within threshold.
        assert result.valid is True

    def test_missing_baseline_results_rejected(self):
        post_patch = [_make_result("tc1", {"accuracy": 8.0})]

        v = RegressionValidator()
        result = v.validate("patch", context={
            "post_patch_results": post_patch,
        })
        assert result.valid is False
        assert "baseline" in result.reason.lower()

    def test_missing_post_patch_results_rejected(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0})]

        v = RegressionValidator()
        result = v.validate("patch", context={
            "baseline_results": baseline,
        })
        assert result.valid is False
        assert "post" in result.reason.lower()

    def test_empty_results_rejected(self):
        v = RegressionValidator()
        result = v.validate("patch", context={
            "baseline_results": [],
            "post_patch_results": [],
        })
        assert result.valid is False
        assert "empty" in result.reason.lower()

    def test_details_contain_metric_deltas(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0, "completeness": 7.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.5, "completeness": 6.8})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert "metric_deltas" in result.details
        assert result.details["metric_deltas"]["accuracy"] == pytest.approx(0.5)
        assert result.details["metric_deltas"]["completeness"] == pytest.approx(-0.2)

    def test_metric_dropped_post_patch_flagged(self):
        # Baseline has a metric that post-patch drops entirely — treated as 0.
        baseline = [_make_result("tc1", {"accuracy": 8.0, "safety": 9.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.0})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is False
        assert "safety" in result.reason.lower()
        assert result.details["metric_deltas"]["safety"] == pytest.approx(-9.0)

    def test_metric_added_post_patch_zero_score_recorded(self):
        # New metric scoring 0.0: delta = 0 - 0 = 0, not flagged.
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.0, "new_metric": 0.0})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True
        assert result.details["metric_deltas"]["new_metric"] == pytest.approx(0.0)

    def test_metric_added_post_patch_positive_score_passes(self):
        # New metric scoring 7.5: delta = 7.5 - 0 = +7.5, an improvement.
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": 8.0, "new_metric": 7.5})]

        v = RegressionValidator(regression_threshold=0.5)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True
        assert result.details["metric_deltas"]["new_metric"] == pytest.approx(7.5)

    def test_custom_threshold_allows_big_drops(self):
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": 6.0})]

        v = RegressionValidator(regression_threshold=3.0)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is True

    def test_negative_threshold_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            RegressionValidator(regression_threshold=-0.5)

    @pytest.mark.parametrize(
        "post_score",
        [7.99, 7.0, 3.0],
        ids=["tiny_drop_0.01", "moderate_drop_1.0", "large_drop_5.0"],
    )
    def test_zero_threshold_rejects_any_drop(self, post_score):
        baseline = [_make_result("tc1", {"accuracy": 8.0})]
        post_patch = [_make_result("tc1", {"accuracy": post_score})]

        v = RegressionValidator(regression_threshold=0.0)
        result = v.validate("patch", context={
            "baseline_results": baseline,
            "post_patch_results": post_patch,
        })
        assert result.valid is False
        assert "regression detected" in result.reason.lower()
