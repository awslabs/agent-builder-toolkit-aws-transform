# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical CLI for the evaluation system: list / run / report / clean.

This is the single user-facing entry point. ``run`` is routed through
:class:`eval_runner.engine.EvaluationEngine` — the scoring layer — so evaluation
is pluggable and parallel:

    scenarios → ACPAgent.execute (run over ACP) → metrics (assertion_pass_rate,
    llm_judge) → per-assertion verdicts → EvalGrade → result.json → HTML report.

``list`` / ``report`` / ``clean`` reuse the proven helpers from
:mod:`eval_runner.execution.cli`.

Consuming packages provide an :class:`eval_runner.config.EvalConfig` (carrying an
``execution_config``) and call :func:`main`::

    from eval_runner.cli import main
    from my_wiring import get_config

    main(get_config())
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from eval_runner.config import EvalConfig
from eval_runner.models import AssertionResult, AssertionResultStatus, EvaluationResult

logger = logging.getLogger(__name__)


def _require_execution_config(config: EvalConfig):
    """Return the ExecutionConfig or raise a clear error if absent."""
    if config.execution_config is None:
        raise ValueError(
            "EvalConfig.execution_config is required to run the CLI. Set it to an "
            "ExecutionConfig describing the agent or skill under test "
            "(see evaluation/run_eval.py)."
        )
    return config.execution_config


def _metric_assertions_to_results(result: EvaluationResult) -> list[AssertionResult]:
    """Map an EvaluationResult's metric details onto report AssertionResults.

    The report renders per-assertion name/result/evidence. Both built-in metrics
    record per-assertion detail under ``MetricResult.details["assertions"]``:

    - ``llm_judge`` → ``{name, result, evidence, turn_number}`` (richest; preferred)
    - ``assertion_pass_rate`` → ``{name, type, passed}`` (deterministic fallback)

    Prefer the richest entry per assertion name across all metrics so the report
    shows judge evidence when available. Authority — not evidence presence —
    decides precedence: an ``llm_judge`` verdict (explicit ``result``) is the
    real grade for an ``llm_judge``-typed assertion, whereas an
    ``assertion_pass_rate`` entry for that same assertion is just an "I can't
    grade this type" fallback whose ``reason`` string would otherwise masquerade
    as evidence and shadow the judge's verdict.
    """
    by_name: dict[str, tuple[int, AssertionResult]] = {}
    for mr in result.metric_results:
        for a in mr.details.get("assertions", []):
            name = a.get("name", mr.metric_name)
            if "result" in a:  # llm_judge style — explicit status + evidence (authoritative)
                rank = 1
                status = AssertionResultStatus(a["result"])
                evidence = a.get("evidence", "")
            else:  # assertion_pass_rate style — boolean passed (deterministic fallback)
                rank = 0
                status = (
                    AssertionResultStatus.PASS if a.get("passed") else AssertionResultStatus.FAIL
                )
                evidence = a.get("reason", a.get("type", ""))
            candidate = AssertionResult(
                name=name, result=status, evidence=evidence, turn_number=a.get("turn_number")
            )
            # Higher-authority entry wins; on a tie, prefer one that carries evidence.
            existing = by_name.get(name)
            if (
                existing is None
                or rank > existing[0]
                or (rank == existing[0] and not existing[1].evidence and candidate.evidence)
            ):
                by_name[name] = (rank, candidate)
    return [entry for _, entry in by_name.values()]


def cmd_list(args: argparse.Namespace, config: EvalConfig) -> int:
    """List available eval scenarios (delegates to the execution CLI helper)."""
    from eval_runner.execution.cli import cmd_list as _cmd_list

    return _cmd_list(args, _require_execution_config(config))


def cmd_report(args: argparse.Namespace) -> int:
    """Generate the HTML dashboard from eval-results/ (delegates)."""
    from eval_runner.execution.cli import cmd_report as _cmd_report

    return _cmd_report(args)


def cmd_clean(args: argparse.Namespace) -> int:
    """Remove eval-results/ for a fresh cycle (delegates)."""
    from eval_runner.execution.cli import cmd_clean as _cmd_clean

    return _cmd_clean(args)


def cmd_run(args: argparse.Namespace, config: EvalConfig) -> int:
    """Run eval scenarios through the scoring engine and render the report."""
    from eval_runner.agents.acp_agent import ACPAgent
    from eval_runner.engine import EvaluationEngine
    from eval_runner.execution.cli import _find_evals_dir
    from eval_runner.execution.loader import load_scenarios
    from eval_runner.execution.runner import EvalOrchestrator
    from eval_runner.test_case import TestCase

    exec_config = _require_execution_config(config)

    if args.clean:
        import shutil

        results_dir = Path.cwd() / "eval-results"
        if results_dir.exists():
            shutil.rmtree(results_dir)
            logger.info(f"Cleaned: {results_dir}")

    try:
        evals_dir = _find_evals_dir(exec_config)
    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        return 1

    scenarios = load_scenarios(
        evals_dir,
        filter_ids=[args.scenario] if args.scenario else None,
        filter_tags=args.tags,
        filter_target=exec_config.filter_target,
    )
    if not scenarios:
        logger.error("No scenarios matched the filter. Use 'list' to see available scenarios.")
        return 1

    logger.info(f"\nRunning {len(scenarios)} scenario(s) via EvaluationEngine...\n")

    # EvalOrchestrator is a stateless factory — it holds no live bridge; each
    # run_scenario / grade_transcript call spins up its ACP bridge(s) and tears
    # them down in a finally. So this instance just drives ACPAgent's scenario
    # execution. The llm_judge metric is wired separately in
    # EvaluationEngine.from_config and builds its own orchestrator; that costs an
    # object, not an extra process, since the judge always runs as a transient,
    # isolated bridge regardless. (Per-call bridge lifecycle is also what keeps
    # parallel batch grading thread-safe — a shared persistent bridge would not be.)
    orchestrator = EvalOrchestrator(config=exec_config, cwd=args.cwd, verbose=args.verbose)
    agent = ACPAgent(execution_config=exec_config, cwd=args.cwd, verbose=args.verbose,
                     orchestrator=orchestrator)
    engine = EvaluationEngine.from_config(config)

    # Convert scenarios → TestCases for the engine.
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

    eval_results = engine.evaluate_batch(agent, test_cases)

    all_passed = True
    for er in eval_results:
        scenario = scenarios_by_id[er.test_case_id]
        assertions = _metric_assertions_to_results(er)
        raw = agent.last_results.get(er.test_case_id)

        if raw is not None:
            grade = orchestrator.assemble_grade(raw, assertions, scenario)
        else:
            # Agent execution failed before producing an EvalResult; still report.
            from eval_runner.models import EvalGrade

            failed = any(a.result != AssertionResultStatus.PASS for a in assertions)
            grade = EvalGrade(
                eval_id=scenario.id,
                passed=not failed and er.passed,
                assertions=assertions,
                duration_seconds=(er.execution.duration_ms or 0) / 1000,
                turn_count=0,
            )

        status = "PASSED" if grade.passed else "FAILED"
        passed_count = sum(1 for a in grade.assertions if a.result == AssertionResultStatus.PASS)
        logger.info(f"=== {scenario.name} ({scenario.id}) ===")
        logger.info(
            f"  Result: {status} ({passed_count}/{len(grade.assertions)} assertions,"
            f" {grade.duration_seconds:.1f}s)"
        )
        for a in grade.assertions:
            icon = (
                "+" if a.result == AssertionResultStatus.PASS
                else "-" if a.result == AssertionResultStatus.FAIL else "?"
            )
            logger.info(f"    [{icon}] {a.name}: {a.result.value}")
        logger.info("")
        if not grade.passed:
            all_passed = False

    if args.report:
        from eval_runner.execution.report import generate_dashboard

        try:
            logger.info(f"Dashboard: {generate_dashboard()}")
        except Exception as e:
            logger.error(f"Dashboard generation failed: {e}")

    logger.info(f"{'ALL PASSED' if all_passed else 'SOME FAILED'} ({len(scenarios)} scenarios)")
    return 0 if all_passed else 1


def main(config: EvalConfig) -> None:
    """CLI entry point. Called by consuming packages with their EvalConfig."""
    report_title = (
        config.execution_config.report_title if config.execution_config else "Eval"
    )
    parser = argparse.ArgumentParser(
        prog=f"{report_title}Tests",
        description=f"{report_title} eval runner",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List available eval scenarios")

    p_run = sub.add_parser("run", help="Run eval scenarios")
    p_run.add_argument("--scenario", "-s", help="Run a single scenario by ID")
    p_run.add_argument("--tags", "-t", nargs="+", help="Filter scenarios by tags")
    p_run.add_argument("--cwd", default="/tmp", help="Working directory for bridge sessions")
    p_run.add_argument("--report", action="store_true", help="Generate HTML dashboard after run")
    p_run.add_argument("--clean", action="store_true", help="Remove eval-results/ before running")

    p_report = sub.add_parser("report", help="Generate HTML dashboard from eval results")
    p_report.add_argument("--results-dir", help="Path to eval-results/ (default: ./eval-results/)")

    p_clean = sub.add_parser("clean", help="Remove eval-results/ for a fresh eval cycle")
    p_clean.add_argument("--results-dir", help="Path to eval-results/ (default: ./eval-results/)")

    args = parser.parse_args()

    logging.Formatter.converter = time.gmtime  # UTC timestamps
    log_fmt, log_datefmt = "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=log_fmt, datefmt=log_datefmt)
        os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"
    else:
        logging.basicConfig(level=logging.INFO, format=log_fmt, datefmt=log_datefmt)

    if args.command == "list":
        raise SystemExit(cmd_list(args, config))
    elif args.command == "run":
        raise SystemExit(cmd_run(args, config))
    elif args.command == "report":
        raise SystemExit(cmd_report(args))
    elif args.command == "clean":
        raise SystemExit(cmd_clean(args))
