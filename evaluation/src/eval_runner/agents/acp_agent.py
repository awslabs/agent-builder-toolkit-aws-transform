# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""ACPAgent — execution backend that drives a real agent over ACP.

This is the concrete implementation of :class:`EvalAgentInterface` that was
missing from eval_runner. It composes :mod:`eval_runner.execution`'s ACP engine:
each :class:`TestCase` is converted to a scenario, run as a multi-turn
conversation via :meth:`EvalOrchestrator.run_scenario`, and the resulting
transcript is flattened into eval_runner's :class:`ExecutionResult` so that any
:class:`MetricInterface` (deterministic or LLM judge) can score it.

The agent-under-test, the ACP driver binary, and the judge/scenario agents are
all described by the :class:`~eval_runner.config.ExecutionConfig` carried on
:attr:`eval_runner.config.EvalConfig.execution_config`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eval_runner.execution.runner import EvalOrchestrator, _format_transcript
from eval_runner.models import ExecutionResult, TranscriptRole
from eval_runner.test_case import TestCase

if TYPE_CHECKING:
    from eval_runner.config import ExecutionConfig


class ACPAgent:
    """Runs a test case against a real agent via the ACP execution engine.

    Satisfies :class:`eval_runner.agent_interface.EvalAgentInterface` (it has an
    ``execute()`` method), so it plugs directly into :class:`EvaluationEngine`.
    """

    def __init__(
        self,
        execution_config: "ExecutionConfig",
        cwd: str = "/tmp",
        verbose: bool = False,
        orchestrator: "EvalOrchestrator | None" = None,
    ) -> None:
        """Initialize the ACP execution backend.

        Args:
            execution_config: The :class:`ExecutionConfig` describing the
                agent/skill under test and how to drive it over ACP.
            cwd: Working directory for bridge sessions (per-scenario subdirs are
                created beneath it).
            verbose: Enable debug logging for the ACP driver.
            orchestrator: Pre-built orchestrator (mainly for testing). When None,
                one is constructed from ``execution_config``.
        """
        self.execution_config = execution_config
        self.cwd = cwd
        self.verbose = verbose
        self._orchestrator = orchestrator
        # The raw EvalResult from the most recent execute(), keyed by test-case id.
        # Lets the CLI recover the structured transcript / token usage / logs that
        # the flattened ExecutionResult drops, when assembling the report.
        self.last_results: dict[str, object] = {}

    @property
    def orchestrator(self) -> "EvalOrchestrator":
        """Construct the orchestrator on first use from ``execution_config``."""
        if self._orchestrator is None:
            self._orchestrator = EvalOrchestrator(
                config=self.execution_config,
                cwd=self.cwd,
                verbose=self.verbose,
            )
        return self._orchestrator

    def execute(self, test_case: TestCase) -> ExecutionResult:
        """Run the test case as a multi-turn ACP conversation.

        Converts the test case to a framework scenario, executes it (no grading),
        and flattens the transcript into an :class:`ExecutionResult`. Grading is
        left to the metric layer (e.g. ``assertion_pass_rate`` or ``llm_judge``).
        """
        scenario = test_case.to_scenario()
        result = self.orchestrator.run_scenario(scenario, workspace_cwd=self.cwd)
        self.last_results[test_case.id] = result

        transcript = _format_transcript(result.transcript)
        output = self._last_agent_text(result.transcript)
        tool_calls = self._tool_calls(result.transcript)

        return ExecutionResult(
            transcript=transcript,
            output=output,
            tool_calls=tool_calls,
            duration_ms=int(result.duration_seconds * 1000),
            turn_count=result.turn_count,
        )

    @staticmethod
    def _last_agent_text(entries: list) -> str:
        """Return the agent's final message — the natural 'output' of the run."""
        for entry in reversed(entries):
            if entry.role == TranscriptRole.AGENT:
                return entry.content
        return ""

    @staticmethod
    def _tool_calls(entries: list) -> list[dict]:
        """Extract tool-call records keyed for the deterministic metrics.

        ``AssertionPassRateMetric`` matches ``tool_called`` assertions on a
        ``name`` key, so each record exposes the tool name under both ``name``
        and ``tool`` (the framework's native key), plus the originating turn.
        """
        calls: list[dict] = []
        for entry in entries:
            if entry.role != TranscriptRole.TOOL_CALL:
                continue
            # entry.content looks like: "tool_call: <tool> (kind=..., status=...)"
            name = ""
            text = entry.content
            if text.startswith("tool_call:"):
                name = text[len("tool_call:"):].split("(", 1)[0].strip()
            calls.append({"name": name, "tool": name, "turn": entry.turn})
        return calls
