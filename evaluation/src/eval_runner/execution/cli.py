# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for the eval framework.

Provides commands to list and run eval scenarios. Consuming packages
create a thin wrapper that provides an ``ExecutionConfig`` and calls ``main(config)``.

Usage (from consuming package)::

    from eval_runner.execution.cli import main
    from my_agent_tests import get_config

    main(get_config())
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from ..config import ExecutionConfig
from .loader import list_scenarios, load_scenarios
from ..models import AssertionResultStatus
from .runner import EvalOrchestrator
from .usage import format_usage_summary

logger = logging.getLogger(__name__)


def _find_evals_dir(config: ExecutionConfig) -> Path:
    """Find the evals directory.

    Checks in order:
    1. ``config.evals_dir`` if set
    2. ``EVALS_DIR`` environment variable
    3. Walk up from ``agent_dir`` or first ``skill_dirs`` entry to find evals/
    """
    if config.evals_dir and config.evals_dir.is_dir():
        return config.evals_dir

    env_path = os.environ.get("EVALS_DIR")
    if env_path and Path(env_path).is_dir():
        return Path(env_path)

    search_root = config.agent_dir or (config.skill_dirs[0] if config.skill_dirs else None)
    if search_root:
        for parent in search_root.parents:
            evals = parent / "evals"
            if evals.is_dir():
                return evals
            evals = parent / "configuration" / "evals"
            if evals.is_dir():
                return evals

    raise FileNotFoundError("Cannot find evals directory. Set EVALS_DIR or config.evals_dir.")


def cmd_report(args: argparse.Namespace) -> int:
    """Generate HTML dashboard from eval-results/."""
    from .report import generate_dashboard

    results_dir = Path(args.results_dir) if args.results_dir else None
    try:
        path = generate_dashboard(results_dir)
        print(f"Dashboard: {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_clean(args: argparse.Namespace) -> int:
    """Remove eval-results/ directory for a fresh eval cycle."""
    import shutil

    results_dir = Path(args.results_dir) if args.results_dir else Path.cwd() / "eval-results"
    if not results_dir.exists():
        print(f"Nothing to clean: {results_dir} does not exist.")
        return 0

    shutil.rmtree(results_dir)
    print(f"Cleaned: {results_dir}")
    return 0


def cmd_list(args: argparse.Namespace, config: ExecutionConfig) -> int:
    """List available eval scenarios."""
    try:
        evals_dir = _find_evals_dir(config)
    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        return 1

    summaries = list_scenarios(evals_dir)
    if not summaries:
        logger.info("No scenarios found.")
        return 0

    logger.info(f"\nAvailable scenarios ({len(summaries)}):\n")
    for s in summaries:
        tags = ", ".join(s["tags"]) if s["tags"] else "none"
        logger.info(f"  {s['id']:40s} [{tags}]")
        logger.info(f"    {s['path']}")
    return 0


def cmd_run(args: argparse.Namespace, config: ExecutionConfig) -> int:
    """Run eval scenarios."""
    if args.clean:
        import shutil

        results_dir = Path.cwd() / "eval-results"
        if results_dir.exists():
            shutil.rmtree(results_dir)
            logger.info(f"Cleaned: {results_dir}")

    try:
        evals_dir = _find_evals_dir(config)
    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        return 1

    filter_ids = [args.scenario] if args.scenario else None
    filter_tags = args.tags
    filter_target = config.filter_target

    scenarios = load_scenarios(
        evals_dir, filter_ids=filter_ids, filter_tags=filter_tags, filter_target=filter_target
    )
    if not scenarios:
        logger.error("No scenarios matched the filter. Use 'list' to see available scenarios.")
        return 1

    logger.info(f"\nRunning {len(scenarios)} scenario(s)...\n")

    orchestrator = EvalOrchestrator(config=config, cwd=args.cwd, verbose=args.verbose)

    all_passed = True
    for scenario in scenarios:
        logger.info(f"=== {scenario.name} ({scenario.id}) ===")
        logger.info(f"  Goal: {scenario.description}")

        grade = orchestrator.run_eval(scenario, workspace_cwd=args.cwd)

        # --- Run summary ---
        status = "PASSED" if grade.passed else "FAILED"
        passed_count = sum(1 for a in grade.assertions if a.result == AssertionResultStatus.PASS)
        total_count = len(grade.assertions)

        if grade.work_dir:
            logger.info(f"  Work dir: {grade.work_dir}")
        if grade.tools_available:
            logger.info(f"  Tools: {grade.tools_available}")
        logger.info(f"  Turns: {grade.turn_count}")
        logger.info(
            f"  Result: {status} ({passed_count}/{total_count} assertions,"
            f" {grade.duration_seconds:.1f}s)"
        )
        for line in format_usage_summary(grade.token_usage):
            logger.info(f"  {line}")

        for a in grade.assertions:
            icon = (
                "+"
                if a.result == AssertionResultStatus.PASS
                else "-" if a.result == AssertionResultStatus.FAIL else "?"
            )
            logger.info(f"    [{icon}] {a.name}: {a.result.value}")
            if a.evidence:
                evidence = a.evidence[:200] + "..." if len(a.evidence) > 200 else a.evidence
                logger.info(f"        {evidence}")
        if grade.log_files:
            logger.info("  Logs:")
            for log_path in grade.log_files:
                logger.info(f"    {log_path}")
        logger.info("")

        if not grade.passed:
            all_passed = False

    if args.report:
        from .report import generate_dashboard

        try:
            logger.info(f"Dashboard: {generate_dashboard()}")
        except Exception as e:
            logger.error(f"Dashboard generation failed: {e}")

    logger.info(f"{'ALL PASSED' if all_passed else 'SOME FAILED'} ({len(scenarios)} scenarios)")
    return 0 if all_passed else 1


def main(config: ExecutionConfig) -> None:
    """CLI main entry point. Called by consuming packages with their ExecutionConfig."""
    parser = argparse.ArgumentParser(
        prog=f"{config.report_title}Tests",
        description=f"{config.report_title} eval framework",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output (DEBUG logging + MCP server debug logs)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List available eval scenarios")

    # run
    p_run = sub.add_parser("run", help="Run eval scenarios")
    p_run.add_argument("--scenario", "-s", help="Run a single scenario by ID")
    p_run.add_argument("--tags", "-t", nargs="+", help="Filter scenarios by tags")
    p_run.add_argument("--cwd", default="/tmp", help="Working directory for bridge sessions")
    p_run.add_argument("--report", action="store_true", help="Generate HTML dashboard after run")
    p_run.add_argument("--clean", action="store_true", help="Remove eval-results/ before running")

    # report
    p_report = sub.add_parser("report", help="Generate HTML dashboard from eval results")
    p_report.add_argument("--results-dir", help="Path to eval-results/ (default: ./eval-results/)")

    # clean
    p_clean = sub.add_parser("clean", help="Remove eval-results/ for a fresh eval cycle")
    p_clean.add_argument("--results-dir", help="Path to eval-results/ (default: ./eval-results/)")

    args = parser.parse_args()

    log_fmt = "%(asctime)s %(levelname)s %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"
    logging.Formatter.converter = time.gmtime  # UTC timestamps
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
