# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in cost-budget metric.

Scores a run's billed cost against a per-test budget. Opt-in like the other
deterministic metrics: a test participates only if it declares a budget in
``metadata.max_credits``. Tests without a budget abstain (score 10.0, pass), so
a suite that adds this metric without setting a budget on every test is never
penalised for the un-budgeted ones.

Why credits and not raw tokens: the kiro-cli ACP driver does NOT report token
counts over the wire — on real runs ``TokenUsage.total_tokens`` is 0, while
``credits`` (billed metering credits) is the populated cost signal (see the
TokenUsage docstring in models.py). Budgeting against tokens would therefore
score a perfect 10.0 on every kiro-cli run regardless of cost. Token-based
budgeting for drivers that do emit counts (e.g. claude-code) is a separate,
additive follow-up.
"""

from __future__ import annotations

from eval_runner.metrics._metadata import coerce_positive_number
from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase


class CostBudgetMetric:
    """Scores ``execution.token_usage.credits`` against ``metadata.max_credits``.

    Scoring (lower cost is better): 10.0 at/under budget, then 10 * (budget /
    used) over budget (2x budget -> 5.0), clamped to [0, 10]. Passes at >= 7.0.

    Abstains with 10.0/pass when no budget is set, the run recorded no usage, or
    the driver reported 0 credits — a missing measurement must not read as a
    perfect (free) run.
    """

    @property
    def name(self) -> str:
        return "cost_budget"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        budget = coerce_positive_number(test_case.metadata.get("max_credits"))
        usage = execution.token_usage
        if budget is None or usage is None:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no valid max_credits budget set or no usage recorded"},
            )

        used = usage.credits
        if used <= 0:
            # kiro-cli persists credits from the session file; 0 means the driver
            # reported nothing. Abstain rather than scoring a misleading perfect.
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "driver reported no credits"},
            )

        ratio = used / budget
        score = 10.0 if ratio <= 1.0 else max(0.0, 10.0 / ratio)
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 7.0,
            details={"used_credits": used, "budget_credits": budget, "ratio": ratio},
        )
