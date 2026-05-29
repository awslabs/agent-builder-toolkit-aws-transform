# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""RegressionValidator — rejects patches that degrade evaluation metrics."""

from __future__ import annotations

from eval_runner.models import EvaluationResult
from eval_runner.validators.interface import ValidationResult


class RegressionValidator:
    """Validates patches by comparing pre/post evaluation results.

    Computes the per-metric average score across the test suite for both
    baseline and post-patch runs, then rejects if any metric's suite-wide
    average drops by more than ``regression_threshold``.

    Assumes higher scores are better. Metrics where lower is better
    (e.g., error rate, latency) must invert their score before reporting.

    Aggregation is suite-wide, not per-test-case: a patch that drops one
    test case's score but improves another may net to zero delta and pass.
    Use a smaller threshold or stricter validators for per-case guarantees.

    A metric present in one run but missing from the other is treated as
    score 0.0 on the missing side. A dropped metric thus registers as a
    regression (baseline 9 → 0 = -9 delta). A newly added metric is
    recorded in ``metric_deltas`` for visibility but does not trigger
    rejection on its own (delta is non-negative since scores ≥ 0).

    Crashed test executions (where an agent error produces score=0 with
    an error in details) are not distinguished from genuine zero scores.
    Filter out crashed baselines before validating, or the comparison
    will be misleading.

    The ``reason`` field is part of the public contract:
    - Rejections begin with ``"Regression detected: "`` (followed by
      ``"<metric>: <baseline> → <post> (Δ<delta>)"`` entries joined by
      ``"; "``), ``"Missing "``, or ``"Empty "``.
    - Acceptances begin with ``"No regression"``.
    The ``details`` dict always contains ``metric_deltas`` (mapping
    metric name to signed delta) and, on rejection, ``regressions``
    (the list of formatted regression strings).
    """

    def __init__(self, regression_threshold: float = 0.5) -> None:
        if regression_threshold < 0:
            raise ValueError(
                f"regression_threshold must be non-negative, got {regression_threshold}"
            )
        self.regression_threshold = regression_threshold

    def __repr__(self) -> str:
        return f"RegressionValidator(regression_threshold={self.regression_threshold})"

    @property
    def name(self) -> str:
        return "regression"

    def validate(self, patch: str, context: dict) -> ValidationResult:
        baseline_results = context.get("baseline_results")
        post_patch_results = context.get("post_patch_results")

        if baseline_results is None:
            return ValidationResult(
                valid=False,
                reason="Missing baseline_results in context",
            )

        if post_patch_results is None:
            return ValidationResult(
                valid=False,
                reason="Missing post_patch_results in context",
            )

        if not baseline_results or not post_patch_results:
            return ValidationResult(
                valid=False,
                reason="Empty evaluation results — cannot compare",
            )

        baseline_averages = self._compute_metric_averages(baseline_results)
        post_averages = self._compute_metric_averages(post_patch_results)

        all_metrics = set(baseline_averages) | set(post_averages)

        metric_deltas: dict[str, float] = {}
        regressions: list[str] = []

        for metric_name in sorted(all_metrics):
            baseline_avg = baseline_averages.get(metric_name, 0.0)
            post_avg = post_averages.get(metric_name, 0.0)
            delta = post_avg - baseline_avg
            metric_deltas[metric_name] = delta

            if delta < -self.regression_threshold:
                regressions.append(
                    f"{metric_name}: {baseline_avg:.2f} → {post_avg:.2f} (Δ{delta:+.2f})"
                )

        if regressions:
            return ValidationResult(
                valid=False,
                reason=f"Regression detected: {'; '.join(regressions)}",
                details={"metric_deltas": metric_deltas, "regressions": regressions},
            )

        return ValidationResult(
            valid=True,
            reason="No regression beyond threshold",
            details={"metric_deltas": metric_deltas},
        )

    @staticmethod
    def _compute_metric_averages(results: list[EvaluationResult]) -> dict[str, float]:
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}

        for result in results:
            for mr in result.metric_results:
                totals[mr.metric_name] = totals.get(mr.metric_name, 0.0) + mr.score
                counts[mr.metric_name] = counts.get(mr.metric_name, 0) + 1

        return {name: totals[name] / counts[name] for name in totals}
