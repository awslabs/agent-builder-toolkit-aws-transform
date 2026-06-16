# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge: an evolver ``Environment`` backed by this repo's ``eval_runner`` engine.

The evolver loop (``harness_evolver``) is engine-agnostic: it only needs an
``Environment`` with a ``run(target_dir, artifacts_dir)`` callback that evaluates
the *current* state of ``target_dir`` and leaves an ``evaluation_summary.json``
behind.

This module makes the callback drive **eval_runner**, so a single engine backs
both the ``run`` and ``evolve`` CLI verbs:

    scenarios → ACPAgent.execute (ACP) → metrics → per-assertion verdicts
              → evaluation_summary.json (evolver schema)

``target_dir`` is the agent-under-test directory the evolver mutates (the snapshot
ledger's work-tree). Each step we point a fresh :class:`ExecutionConfig` at the
mutated ``target_dir`` and re-evaluate, exactly mirroring the CLI ``run`` path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

logger = logging.getLogger(__name__)


# The evolver consumes evaluation_summary.json via
# EvolutionHistory.EvaluationStats.from_summary_json and the orchestrator's
# checkpoint selection. Both read: assertion_pass_rate, total_tests, and
# tests[] of {test_id, passed}. We emit exactly that schema below.


def _select_slice(items: list, test_slice: str | None) -> list:
    """Apply a ``"start:end"`` (or ``"n"``) slice spec to an ordered list."""
    if not test_slice:
        return items
    if ":" in test_slice:
        start, end = test_slice.split(":")
        return items[int(start) if start else None : int(end) if end else None]
    n = int(test_slice)
    return items[n : n + 1]


def make_eval_runner_env(
    *,
    name: str,
    base_execution_config,
    test_dir: Path,
    goal: str,
    metrics: list[str] | None = None,
    test_slice: str | None = None,
    scenario_ids: list[str] | None = None,
    max_workers: int = 1,
):
    """Build an evolver ``Environment`` that scores ``target_dir`` via eval_runner.

    Args:
        name: Env slug (used in run paths, e.g. ``agent_builder_train``).
        base_execution_config: An :class:`eval_runner.config.ExecutionConfig`
            template (agent_name, acp_binary, judge/scenario agents, …). Its
            ``agent_dir`` is overridden each run with the evolving ``target_dir``.
        test_dir: Directory of eval scenario JSONs to evaluate against.
        goal: Worker goal text shown to the analyst (the "insights" engine).
        metrics: Scoring metrics (default: assertion_pass_rate + llm_judge).
        test_slice: Optional ``"start:end"`` slice over the sorted scenarios,
            so train/validation/test can use disjoint slices of one test_dir.
        scenario_ids: Optional explicit scenario-id allowlist (applied before slice).
        max_workers: Parallel scenario workers for the engine.
    """
    from harness_evolver.environment import Environment

    metrics = metrics or ["assertion_pass_rate", "llm_judge"]
    test_dir = Path(test_dir)

    def run(target_dir: Path, artifacts_dir: Path) -> None:
        # Local imports keep the optional eval_runner/claude deps out of the base
        # CLI import path and avoid import cost when evolve isn't used.
        from eval_runner.agents.acp_agent import ACPAgent
        from eval_runner.cli import _metric_assertions_to_results
        from eval_runner.config import EvalConfig
        from eval_runner.engine import EvaluationEngine
        from eval_runner.execution.loader import load_scenarios
        from eval_runner.execution.runner import EvalOrchestrator
        from eval_runner.models import AssertionResultStatus
        from eval_runner.test_case import TestCase

        target_dir = Path(target_dir)
        artifacts_dir = Path(artifacts_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Re-point the execution config at the evolver's current target state.
        exec_config = replace(base_execution_config, agent_dir=target_dir)
        eval_config = EvalConfig(
            test_dir=test_dir,
            metrics=metrics,
            max_workers=max_workers,
            execution_config=exec_config,
        )

        scenarios = load_scenarios(
            test_dir,
            filter_ids=scenario_ids,
            filter_target=exec_config.filter_target,
        )
        scenarios = _select_slice(scenarios, test_slice)
        if not scenarios:
            # Fail loudly. A zeroed summary here is indistinguishable from "the
            # agent scored 0", which silently poisons checkpoint selection and
            # the before/after test numbers — exactly the honest-generalization
            # story this feature exists to produce. An empty slice is a config
            # error (slice spec or test_dir), not a 0% result.
            msg = (
                f"env {name!r}: no scenarios matched "
                f"(dir={test_dir}, slice={test_slice}, ids={scenario_ids}). "
                f"Populate {test_dir} or fix the slice/ids so this resolves to a "
                f"non-empty set."
            )
            (artifacts_dir / "ERROR.txt").write_text(msg + "\n")
            raise ValueError(msg)

        workspace = artifacts_dir / "workspace"
        orchestrator = EvalOrchestrator(
            config=exec_config,
            cwd=str(workspace),
            results_dir=str(artifacts_dir / "results"),
            verbose=False,
        )
        agent = ACPAgent(
            execution_config=exec_config,
            cwd=str(workspace),
            verbose=False,
            orchestrator=orchestrator,
        )
        engine = EvaluationEngine.from_config(eval_config)

        test_cases = [
            TestCase(
                id=s.id,
                name=s.name,
                user_message=s.prompt,
                description=s.description,
                tags=s.tags,
                max_turns=s.max_turns,
                timeout_seconds=s.timeout_seconds,
                simulated_human_guidance=s.simulated_human_guidance,
                assertions=s.assertions,
            )
            for s in scenarios
        ]
        scenarios_by_id = {s.id: s for s in scenarios}

        logger.info("env %s: evaluating %d scenario(s) via eval_runner", name, len(test_cases))
        eval_results = engine.evaluate_batch(agent, test_cases)

        # Map engine results → the evolver's per-test summary rows.
        rows = []
        for er in eval_results:
            assertions = _metric_assertions_to_results(er)
            raw = agent.last_results.get(er.test_case_id)
            if raw is not None:
                grade = orchestrator.assemble_grade(raw, assertions, scenarios_by_id[er.test_case_id])
                passed = grade.passed
                graded = grade.assertions
            else:
                graded = assertions
                passed = er.passed and all(
                    a.result == AssertionResultStatus.PASS for a in assertions
                )
            n_pass = sum(1 for a in graded if a.result == AssertionResultStatus.PASS)
            rows.append(
                {
                    "test_id": er.test_case_id,
                    "assertions_total": len(graded),
                    "assertions_passed": n_pass,
                    "passed": passed,
                }
            )

        _write_summary(artifacts_dir, name, test_slice, rows)

    return Environment(
        target_dir=base_execution_config.agent_dir,
        goal=goal,
        run=run,
        name=name,
    )


def _write_summary(
    artifacts_dir: Path, name: str, test_slice: str | None, rows: list[dict]
) -> None:
    """Write evaluation_summary.json in the schema the evolver consumes."""
    total_assertions = sum(r["assertions_total"] for r in rows)
    assertions_passed = sum(r["assertions_passed"] for r in rows)
    summary = {
        "run_id": name,
        "test_slice": test_slice,
        "total_tests": len(rows),
        "tests_run": len(rows),
        "total_assertions": total_assertions,
        "assertions_passed": assertions_passed,
        "assertion_pass_rate": (assertions_passed / total_assertions) if total_assertions else 0.0,
        "tests": rows,
    }
    (artifacts_dir / "evaluation_summary.json").write_text(json.dumps(summary, indent=2))
