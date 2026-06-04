# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in assertion_pass_rate metric."""

from __future__ import annotations

from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase


_GRADABLE_TYPES = frozenset({"transcript_contains", "output_contains", "tool_called"})


class AssertionPassRateMetric:
    """Evaluates what fraction of *deterministically gradable* assertions pass.

    Supports assertion types:
    - transcript_contains: check if transcript contains a substring
    - output_contains: check if output contains a substring
    - tool_called: check if a specific tool was invoked

    Assertion types outside this set (e.g. ``llm_judge``) are *not this metric's
    responsibility* — they are skipped, contributing to neither the numerator nor
    the denominator, rather than scored as failures. Manufacturing a FAIL for
    them would inflate the denominator and emit a bogus verdict that could shadow
    the authoritative grader's result downstream. Each metric grades only the
    assertion types it owns; the engine combines metrics.

    Score is (passed / gradable) * 10.0. Passes if score >= 7.0. When no
    assertions are gradable by this metric, it abstains (score 10.0, pass).
    """

    @property
    def name(self) -> str:
        return "assertion_pass_rate"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        assertions = test_case.assertions
        if not assertions:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no assertions defined"},
            )

        passed = 0
        details: dict = {"assertions": []}

        for assertion in assertions:
            result = self._check_assertion(assertion, execution)
            if result is None:  # type not owned by this metric — abstain
                continue
            details["assertions"].append(result)
            if result["passed"]:
                passed += 1

        gradable = len(details["assertions"])
        if gradable == 0:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no assertions gradable by this metric"},
            )

        score = (passed / gradable) * 10.0
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 7.0,
            details=details,
        )

    def _check_assertion(
        self, assertion: dict, execution: ExecutionResult
    ) -> dict | None:
        """Grade one assertion, or return None if its type is not owned here."""
        a_type = assertion.get("type", "")
        if a_type not in _GRADABLE_TYPES:
            return None

        check = assertion.get("check", "")
        a_name = assertion.get("name", a_type)

        if a_type == "transcript_contains":
            ok = check.lower() in execution.transcript.lower()
        elif a_type == "output_contains":
            ok = check.lower() in execution.output.lower()
        else:  # tool_called
            tool_name = assertion.get("tool") or check
            ok = any(tc.get("name") == tool_name for tc in execution.tool_calls)

        return {"name": a_name, "type": a_type, "passed": ok}
