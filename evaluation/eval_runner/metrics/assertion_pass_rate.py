# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in assertion_pass_rate metric."""

from __future__ import annotations

from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase


class AssertionPassRateMetric:
    """Evaluates what fraction of test case assertions pass.

    Supports assertion types:
    - transcript_contains: check if transcript contains a substring
    - output_contains: check if output contains a substring
    - tool_called: check if a specific tool was invoked

    Score is (passed / total) * 10.0. Passes if score >= 7.0.
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
            details["assertions"].append(result)
            if result["passed"]:
                passed += 1

        total = len(assertions)
        score = (passed / total) * 10.0
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 7.0,
            details=details,
        )

    def _check_assertion(
        self, assertion: dict, execution: ExecutionResult
    ) -> dict:
        a_type = assertion.get("type", "")
        check = assertion.get("check", "")
        a_name = assertion.get("name", a_type)

        reason = None
        if a_type == "transcript_contains":
            ok = check.lower() in execution.transcript.lower()
        elif a_type == "output_contains":
            ok = check.lower() in execution.output.lower()
        elif a_type == "tool_called":
            tool_name = assertion.get("tool") or check
            ok = any(tc.get("name") == tool_name for tc in execution.tool_calls)
        else:
            ok = False
            reason = f"unknown assertion type: {a_type!r}"

        result = {"name": a_name, "type": a_type, "passed": ok}
        if reason:
            result["reason"] = reason
        return result
