# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ToolUsageMetric (task 2.3)."""

from eval_runner.metrics.tool_usage import ToolUsageMetric
from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


class TestToolUsageMetric:
    def _make_execution(self, tool_calls: list | None = None) -> ExecutionResult:
        return ExecutionResult(
            transcript="", output="", tool_calls=tool_calls or []
        )

    def _make_tc(self, metadata: dict | None = None) -> TestCase:
        return TestCase(
            id="t1", name="test", user_message="hi", metadata=metadata or {}
        )

    def test_abstains_when_no_config(self):
        """No expected/forbidden tools in metadata -> abstain (10.0/pass)."""
        metric = ToolUsageMetric()
        result = metric.evaluate(self._make_execution(), self._make_tc())
        assert result.score == 10.0
        assert result.passed is True
        assert "no expected_tools" in result.details["reason"]

    def test_expected_tool_called_passes(self):
        metric = ToolUsageMetric()
        tc = self._make_tc({"expected_tools": ["keyword_search"]})
        execution = self._make_execution(
            tool_calls=[{"name": "keyword_search", "tool": "keyword_search", "turn": 3}]
        )
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_expected_tool_not_called_fails(self):
        metric = ToolUsageMetric()
        tc = self._make_tc({"expected_tools": ["keyword_search"]})
        result = metric.evaluate(self._make_execution(tool_calls=[]), tc)
        assert result.score == 0.0
        assert result.passed is False

    def test_forbidden_tool_called_fails(self):
        metric = ToolUsageMetric()
        tc = self._make_tc({"forbidden_tools": ["delete_agent"]})
        execution = self._make_execution(
            tool_calls=[{"name": "delete_agent", "tool": "delete_agent", "turn": 2}]
        )
        result = metric.evaluate(execution, tc)
        assert result.score == 0.0
        assert result.passed is False

    def test_forbidden_tool_absent_passes(self):
        metric = ToolUsageMetric()
        tc = self._make_tc({"forbidden_tools": ["delete_agent"]})
        execution = self._make_execution(
            tool_calls=[{"name": "keyword_search", "turn": 1}]
        )
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_mixed_expected_and_forbidden(self):
        """2 expected (1 called) + 1 forbidden (absent) -> 2/3 pass."""
        metric = ToolUsageMetric()
        tc = self._make_tc(
            {
                "expected_tools": ["keyword_search", "register_agent"],
                "forbidden_tools": ["delete_agent"],
            }
        )
        execution = self._make_execution(
            tool_calls=[{"name": "keyword_search", "turn": 1}]
        )
        result = metric.evaluate(execution, tc)
        # passes: keyword_search (expected, called) + delete_agent (forbidden, absent)
        # fail: register_agent (expected, not called) -> 2/3
        assert abs(result.score - (2 / 3 * 10.0)) < 0.01
        assert result.passed is False

    def test_single_string_expected_tool_coerced(self):
        """A bare string (not a list) is accepted as a single tool name."""
        metric = ToolUsageMetric()
        tc = self._make_tc({"expected_tools": "keyword_search"})
        execution = self._make_execution(
            tool_calls=[{"name": "keyword_search", "turn": 1}]
        )
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_details_report_tools_called(self):
        metric = ToolUsageMetric()
        tc = self._make_tc({"expected_tools": ["a"]})
        execution = self._make_execution(
            tool_calls=[{"name": "a", "turn": 1}, {"name": "b", "turn": 2}]
        )
        result = metric.evaluate(execution, tc)
        assert result.details["tools_called"] == ["a", "b"]
        assert result.details["checks"][0]["passed"] is True

    def test_forbidden_check_details_shape(self):
        """The forbidden-branch check dict reports kind/called/passed correctly."""
        metric = ToolUsageMetric()
        tc = self._make_tc({"forbidden_tools": ["delete_agent"]})
        execution = self._make_execution(
            tool_calls=[{"name": "delete_agent", "turn": 2}]
        )
        result = metric.evaluate(execution, tc)
        check = result.details["checks"][0]
        assert check == {
            "tool": "delete_agent",
            "kind": "forbidden",
            "called": True,
            "passed": False,
        }

    def test_blank_or_missing_tool_names_ignored(self):
        """Records with blank/missing names don't spuriously satisfy a check."""
        metric = ToolUsageMetric()
        tc = self._make_tc({"forbidden_tools": ["delete_agent"]})
        # A blank-named and a name-less record must not be treated as tool calls.
        execution = self._make_execution(
            tool_calls=[{"name": "   ", "turn": 1}, {"turn": 2}]
        )
        result = metric.evaluate(execution, tc)
        assert result.details["tools_called"] == []
        assert result.passed is True  # forbidden tool absent

    def test_non_string_metadata_entries_dropped(self):
        """A null in expected_tools must not become a phantom 'None' tool."""
        metric = ToolUsageMetric()
        tc = self._make_tc({"expected_tools": [None, "keyword_search"]})
        execution = self._make_execution(
            tool_calls=[{"name": "keyword_search", "turn": 1}]
        )
        result = metric.evaluate(execution, tc)
        # Only the real tool is checked (1/1), not a bogus "None" expectation.
        assert result.score == 10.0
        assert result.passed is True

    def test_name(self):
        assert ToolUsageMetric().name == "tool_usage"
