# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the eval orchestrator (runner.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from eval_runner.execution.bridge_runner import (
    BridgeResponse,
    BridgeResponseStatus,
)
from eval_runner.config import ExecutionConfig as EvalConfig
from eval_runner.models import AssertionResultStatus, EvalGrade
from eval_runner.execution.runner import (
    EvalCase,
    EvalOrchestrator,
    _build_eval_prompt,
    _build_scenario_prompt,
    _parse_eval_grades,
)


def _test_config() -> EvalConfig:
    """Create a minimal EvalConfig for tests."""
    return EvalConfig(
        agent_name="test-power",
        agent_dir=Path("/tmp/test-power"),
    )


class TestBuildScenarioPrompt:
    """Tests for scenario prompt construction."""

    def test_includes_goal_and_prompt(self) -> None:
        scenario = EvalCase(
            id="test",
            name="Test",
            prompt="Hello power",
            description="User wants to test",
            assertions=[],
        )
        result = _build_scenario_prompt(scenario)
        assert "SCENARIO GOAL: User wants to test" in result
        assert "INITIAL PROMPT TO SEND TO THE POWER: Hello power" in result
        assert "__DONE__" in result

    def test_includes_guidance_when_present(self) -> None:
        scenario = EvalCase(
            id="test",
            name="Test",
            prompt="Hello",
            description="Goal",
            assertions=[],
            simulated_human_guidance="Choose .NET when asked",
        )
        result = _build_scenario_prompt(scenario)
        assert "GUIDANCE: Choose .NET when asked" in result

    def test_omits_guidance_when_none(self) -> None:
        scenario = EvalCase(
            id="test",
            name="Test",
            prompt="Hello",
            description="Goal",
            assertions=[],
        )
        result = _build_scenario_prompt(scenario)
        assert "GUIDANCE" not in result


class TestBuildEvalPrompt:
    """Tests for eval prompt construction."""

    def test_includes_transcript_and_assertions(self) -> None:
        assertions = [{"name": "check_auth", "type": "tool_called", "check": "get_status"}]
        result = _build_eval_prompt("Turn 1: hello", assertions)
        assert "TRANSCRIPT:" in result
        assert "Turn 1: hello" in result
        assert "ASSERTIONS:" in result
        assert "check_auth" in result


class TestParseEvalGrades:
    """Tests for parsing eval agent JSON responses."""

    def test_parses_valid_json(self) -> None:
        response = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text='[{"name": "check_auth", "result": "pass", "evidence": "Found it", "turn_number": 1}]',
        )
        results = _parse_eval_grades(response)
        assert len(results) == 1
        assert results[0].name == "check_auth"
        assert results[0].result == AssertionResultStatus.PASS
        assert results[0].evidence == "Found it"
        assert results[0].turn_number == 1

    def test_parses_json_with_markdown_fences(self) -> None:
        response = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text='```json\n[{"name": "x", "result": "fail", "evidence": "missing"}]\n```',
        )
        results = _parse_eval_grades(response)
        assert len(results) == 1
        assert results[0].result == AssertionResultStatus.FAIL

    def test_handles_invalid_json(self) -> None:
        response = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text="This is not JSON",
        )
        results = _parse_eval_grades(response)
        assert len(results) == 1
        assert results[0].result == AssertionResultStatus.NEEDS_REVIEW
        assert "parse" in results[0].evidence.lower()

    def test_handles_failed_response(self) -> None:
        response = BridgeResponse(
            status=BridgeResponseStatus.FAILED,
            error="Process crashed",
        )
        results = _parse_eval_grades(response)
        assert len(results) == 1
        assert results[0].result == AssertionResultStatus.NEEDS_REVIEW

    def test_handles_multiple_assertions(self) -> None:
        response = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text="""[
                {"name": "a", "result": "pass", "evidence": "ok"},
                {"name": "b", "result": "fail", "evidence": "missing"},
                {"name": "c", "result": "needs_review", "evidence": "unclear"}
            ]""",
        )
        results = _parse_eval_grades(response)
        assert len(results) == 3
        assert results[0].result == AssertionResultStatus.PASS
        assert results[1].result == AssertionResultStatus.FAIL
        assert results[2].result == AssertionResultStatus.NEEDS_REVIEW


class TestEvalOrchestrator:
    """Tests for the orchestrator with mocked bridges."""

    @pytest.fixture()
    def orchestrator(self) -> EvalOrchestrator:
        """Create orchestrator."""
        return EvalOrchestrator(config=_test_config(), cwd="/tmp")

    @patch(
        "eval_runner.execution.runner.install_agents",
        return_value=[Path("/fake/a.json"), Path("/fake/b.json"), Path("/fake/c.json")],
    )
    @patch("eval_runner.execution.runner.BridgeRunner")
    def test_run_eval_happy_path(
        self, mock_bridge_cls: MagicMock, mock_install: MagicMock, tmp_path: Any
    ) -> None:
        """Full happy path: power responds, scenario agent signals DONE, eval grades pass."""
        # 3 bridges: power, scenario, eval
        power_bridge = MagicMock()
        scenario_bridge = MagicMock()
        eval_bridge = MagicMock()
        mock_bridge_cls.side_effect = [power_bridge, scenario_bridge, eval_bridge]

        # Turn 1: agent responds
        power_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text="I'll check your auth and scan the workspace for .NET projects.",
        )

        # Scenario agent decides human is done
        scenario_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text="__DONE__",
        )

        # Eval agent returns grades
        eval_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text='[{"name": "checks_auth", "result": "pass", "evidence": "Found auth check"}]',
        )

        orchestrator = EvalOrchestrator(
            config=_test_config(),
            cwd=str(tmp_path),
        )
        scenario = EvalCase(
            id="test-scenario",
            name="Test",
            prompt="I want to use the power",
            description="User wants to modernize .NET",
            assertions=[{"name": "checks_auth", "type": "tool_called", "check": "get_status"}],
        )

        grade = orchestrator.run_eval(scenario)

        assert grade.eval_id == "test-scenario"
        assert grade.passed is True
        assert len(grade.assertions) == 1
        assert grade.assertions[0].result == AssertionResultStatus.PASS

        # Verify all bridges use <base_cwd>/<scenario_id> as work directory
        expected_cwd = str(tmp_path / "test-scenario")
        for call in mock_bridge_cls.call_args_list:
            assert call.kwargs.get("cwd") == expected_cwd

        # Work directory is kept after run (not deleted)
        assert (tmp_path / "test-scenario").is_dir()

        # Verify bridge lifecycle — all 3 started and destroyed
        power_bridge.start.assert_called_once()
        power_bridge.destroy.assert_called_once()
        scenario_bridge.start.assert_called_once()
        scenario_bridge.destroy.assert_called_once()
        eval_bridge.start.assert_called_once()
        eval_bridge.destroy.assert_called_once()

    @patch(
        "eval_runner.execution.runner.install_agents",
        return_value=[Path("/fake/a.json"), Path("/fake/b.json"), Path("/fake/c.json")],
    )
    @patch("eval_runner.execution.runner.BridgeRunner")
    def test_run_eval_power_failure(
        self, mock_bridge_cls: MagicMock, mock_install: MagicMock, tmp_path: Any
    ) -> None:
        """Agent fails — eval still runs on partial transcript."""
        power_bridge = MagicMock()
        scenario_bridge = MagicMock()
        eval_bridge = MagicMock()
        mock_bridge_cls.side_effect = [power_bridge, scenario_bridge, eval_bridge]

        power_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.TIMEOUT,
            error="Exceeded 300s",
            text="",
        )

        eval_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text='[{"name": "checks_auth", "result": "fail", "evidence": "No auth in transcript"}]',
        )

        orchestrator = EvalOrchestrator(
            config=_test_config(),
            cwd=str(tmp_path),
        )
        scenario = EvalCase(
            id="timeout-test",
            name="Timeout",
            prompt="Hello",
            description="Test timeout",
            assertions=[{"name": "checks_auth", "type": "tool_called", "check": "get_status"}],
        )

        grade = orchestrator.run_eval(scenario)
        assert grade.passed is False
        # All bridges cleaned up
        power_bridge.destroy.assert_called_once()
        scenario_bridge.destroy.assert_called_once()
        eval_bridge.destroy.assert_called_once()

    def test_run_suite_filters_by_tags(self) -> None:
        """Suite runner filters scenarios by tags."""
        with patch("eval_runner.execution.runner.BridgeRunner"):
            orchestrator = EvalOrchestrator(config=_test_config())
            mock_grade = EvalGrade(
                eval_id="a",
                passed=True,
                assertions=[],
                duration_seconds=1.0,
                turn_count=1,
            )
            orchestrator.run_eval = MagicMock(return_value=mock_grade)  # type: ignore[method-assign]

            scenarios = [
                EvalCase(
                    id="a", name="A", prompt="", description="", assertions=[], tags=["journey"]
                ),
                EvalCase(
                    id="b", name="B", prompt="", description="", assertions=[], tags=["negative"]
                ),
            ]

            results = orchestrator.run_suite(scenarios, filter_tags=["journey"])
            assert len(results) == 1
            orchestrator.run_eval.assert_called_once()

    def test_run_suite_filters_by_ids(self) -> None:
        """Suite runner filters scenarios by IDs."""
        with patch("eval_runner.execution.runner.BridgeRunner"):
            orchestrator = EvalOrchestrator(config=_test_config())
            mock_grade = EvalGrade(
                eval_id="b",
                passed=True,
                assertions=[],
                duration_seconds=1.0,
                turn_count=1,
            )
            orchestrator.run_eval = MagicMock(return_value=mock_grade)  # type: ignore[method-assign]

            scenarios = [
                EvalCase(id="a", name="A", prompt="", description="", assertions=[]),
                EvalCase(id="b", name="B", prompt="", description="", assertions=[]),
            ]

            results = orchestrator.run_suite(scenarios, filter_ids=["b"])
            assert len(results) == 1


class TestExecutionGradingSplit:
    """run_scenario (execution) and grade (grading) are separately callable."""

    @patch(
        "eval_runner.execution.runner.install_agents",
        return_value=[Path("/fake/a.json"), Path("/fake/b.json"), Path("/fake/c.json")],
    )
    @patch("eval_runner.execution.runner.BridgeRunner")
    def test_run_scenario_returns_eval_result_without_grading(
        self, mock_bridge_cls: MagicMock, mock_install: MagicMock, tmp_path: Any
    ) -> None:
        """run_scenario produces a transcript and bookkeeping but does not grade."""
        power_bridge = MagicMock()
        scenario_bridge = MagicMock()
        # Only two bridges should be constructed (power, scenario) — no eval bridge.
        mock_bridge_cls.side_effect = [power_bridge, scenario_bridge]

        power_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS, text="Hello back"
        )
        scenario_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS, text="__DONE__"
        )

        orchestrator = EvalOrchestrator(config=_test_config(), cwd=str(tmp_path))
        scenario = EvalCase(
            id="exec-only", name="E", prompt="Hi", description="d", assertions=[]
        )

        result = orchestrator.run_scenario(scenario)

        assert result.eval_id == "exec-only"
        assert any(e.content == "Hello back" for e in result.transcript)
        assert result.work_dir == str(tmp_path / "exec-only")
        assert result.run_timestamp  # stamped
        # No eval bridge was constructed.
        assert mock_bridge_cls.call_count == 2
        power_bridge.destroy.assert_called_once()
        scenario_bridge.destroy.assert_called_once()

    @patch("eval_runner.execution.runner.BridgeRunner")
    def test_grade_transcript_parses_judge_output(
        self, mock_bridge_cls: MagicMock, tmp_path: Any
    ) -> None:
        """grade_transcript drives only the judge bridge and parses its verdict."""
        eval_bridge = MagicMock()
        mock_bridge_cls.return_value = eval_bridge
        eval_bridge.session_id = "sess-eval"
        eval_bridge.prompt.return_value = BridgeResponse(
            status=BridgeResponseStatus.SUCCESS,
            text='[{"name": "a", "result": "pass", "evidence": "ok"}]',
        )

        orchestrator = EvalOrchestrator(config=_test_config(), cwd=str(tmp_path))
        assertions = [{"name": "a", "type": "llm_judge", "description": "checks a"}]

        results, log_path, session_id = orchestrator.grade_transcript(
            "[Turn 1] AGENT: hello", assertions, eval_id="g1"
        )

        assert len(results) == 1
        assert results[0].result == AssertionResultStatus.PASS
        assert session_id == "sess-eval"
        eval_bridge.start.assert_called_once()
        eval_bridge.destroy.assert_called_once()
