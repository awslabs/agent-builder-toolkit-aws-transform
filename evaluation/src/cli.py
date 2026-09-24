#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unified CLI for the AWS Transform agent-builder evaluation toolkit.

One entry point (``agent-builder-eval``) over the full lifecycle:

    generate     Generate test data (test_data_generator)
    list         List available eval scenarios
    run          Run scenarios against the agent under test (eval_runner engine)
    report       Generate the HTML results dashboard
    clean        Remove eval-results/ for a fresh cycle
    insights     Diagnose an eval run — root causes + citations (analyst)
    evolve       Self-improve the agent under test via the evolution loop
    review       PR-style diff review of an evolution run's changes
    evohistory   Show a run's evolution_history.md

``list`` / ``run`` / ``report`` / ``clean`` are the eval_runner verbs, delegated
to its command functions with the repo config from :mod:`run_eval`. ``generate``
forwards to the test-data generator CLI. ``insights`` / ``evolve`` / ``review`` /
``evohistory`` route to the :mod:`evolution` adapter layer (which drives the
separate HarnessEvolver). The evolution verbs import their heavier dependencies
lazily, so the core verbs work without them installed.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent

# Default goal shown to the evolver/analyst — what "better" means for this agent.
DEFAULT_GOAL = (
    "Improve the AWS Transform agent-builder's assertion pass rate across the eval "
    "scenarios. Look for missing or unclear instructions in the agent definition "
    "(AGENT.md + mcp.json) that cause skipped or wrong tool calls, missing edge-case "
    "handling, and guidance that fails to generalize to unseen scenarios. Prefer "
    "general, robust interventions over fixes tailored to individual test cases."
)


# --------------------------------------------------------------------------- #
# generate
# --------------------------------------------------------------------------- #
def cmd_generate(rest: list[str]) -> int:
    """Forward to the test-data generator CLI, preserving its full arg surface."""
    cmd = [sys.executable, "-m", "test_data_generator.cli", *rest]
    return subprocess.call(cmd, cwd=str(EVAL_DIR / "src"))


# --------------------------------------------------------------------------- #
# list / run / report / clean — delegate to eval_runner with the repo config
# --------------------------------------------------------------------------- #
def _repo_config(args: argparse.Namespace | None = None):
    from run_eval import get_config

    config = get_config()

    # `--test-dir` points list/run at a different scenario directory (e.g. a
    # generated suite), mirroring `evolve`. Override both the scoring `test_dir`
    # and the ACP engine's `evals_dir` (the latter is what `_find_evals_dir`
    # actually loads from). Validate eagerly: `_find_evals_dir` silently falls
    # back to EVALS_DIR/walk-up when the dir is missing, so a typo would quietly
    # run the wrong scenarios.
    test_dir = getattr(args, "test_dir", None) if args is not None else None
    if test_dir:
        test_dir = Path(test_dir)
        if not test_dir.is_dir():
            raise SystemExit(f"--test-dir not found: {test_dir}")
        config.test_dir = test_dir
        if config.execution_config is not None:
            config.execution_config.evals_dir = test_dir

    return config


def cmd_list(args: argparse.Namespace) -> int:
    from eval_runner.cli import cmd_list as _list

    return _list(args, _repo_config(args))


def cmd_run(args: argparse.Namespace) -> int:
    from eval_runner.cli import cmd_run as _run

    return _run(args, _repo_config(args))


def cmd_report(args: argparse.Namespace) -> int:
    from eval_runner.cli import cmd_report as _report

    return _report(args)


def cmd_clean(args: argparse.Namespace) -> int:
    from eval_runner.cli import cmd_clean as _clean

    return _clean(args)


# --------------------------------------------------------------------------- #
# insights
# --------------------------------------------------------------------------- #
def cmd_insights(args: argparse.Namespace) -> int:
    from evolution.insights import generate_insights

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.exists():
        logging.error("artifacts dir not found: %s", artifacts_dir)
        return 1

    target_dir = Path(args.target_dir) if args.target_dir else None
    report_text, report_path = generate_insights(
        artifacts_dir=artifacts_dir,
        goal=args.goal,
        output_dir=Path(args.output) if args.output else None,
        target_dir=target_dir,
    )
    logging.info("Insights written: %s", report_path)
    if args.print:
        print(report_text)
    return 0


# --------------------------------------------------------------------------- #
# evolve
# --------------------------------------------------------------------------- #
def cmd_evolve(args: argparse.Namespace) -> int:
    from run_eval import get_execution_config

    from evolution.loop import EvolveSpec, run_evolution

    exec_config = get_execution_config()
    test_dir = Path(args.test_dir) if args.test_dir else (EVAL_DIR / "test_samples")

    spec = EvolveSpec(
        execution_config=exec_config,
        test_dir=test_dir,
        goal=args.goal,
        run_dir=Path(args.run_dir),
        metrics=args.metrics,
        train_slice=args.train_slice,
        validation_slice=args.validation_slice,
        test_slice=args.test_slice,
        budget=args.budget,
        early_stopping_patience=args.patience,
        selection_metric=args.selection_metric,
        max_workers=args.max_workers,
    )
    train_run_dir = run_evolution(spec)
    logging.info("Evolution complete. Train run dir: %s", train_run_dir)

    if args.review:
        from evolution.review import generate_change_review

        review_path = generate_change_review(train_run_dir)
        logging.info("Change review written: %s", review_path)
    return 0


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #
def cmd_review(args: argparse.Namespace) -> int:
    from evolution.review import generate_change_review

    run_env_dir = Path(args.run_env_dir)
    if not (run_env_dir / "trajectory.jsonl").exists():
        logging.error(
            "no trajectory.jsonl under %s — pass the per-env run dir "
            "(e.g. runs/<run>/agent_builder_train)",
            run_env_dir,
        )
        return 1
    out = generate_change_review(
        run_env_dir,
        output=Path(args.output) if args.output else None,
        context=args.context,
    )
    logging.info("Change review written: %s", out)
    return 0


# --------------------------------------------------------------------------- #
# evohistory
# --------------------------------------------------------------------------- #
def cmd_evohistory(args: argparse.Namespace) -> int:
    from evolution.history import get_history

    try:
        text, path = get_history(Path(args.run_dir))
    except FileNotFoundError as e:
        logging.error("%s", e)
        return 1
    logging.info("Evolution history: %s", path)
    if args.output:
        Path(args.output).write_text(text)
        logging.info("Copied to: %s", args.output)
    else:
        print(text)
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-builder-eval",
        description="AWS Transform agent-builder evaluation + evolution toolkit",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    # generate (args forwarded verbatim to the generator CLI)
    sub.add_parser(
        "generate",
        help="Generate test data (forwards all args to test_data_generator.cli)",
        add_help=False,
    )

    # list
    p_list = sub.add_parser("list", help="List available eval scenarios")
    p_list.add_argument("--test-dir", help="Scenario dir (default: ./test_samples)")

    # run
    p_run = sub.add_parser("run", help="Run eval scenarios against the agent under test")
    p_run.add_argument("--test-dir", help="Scenario dir (default: ./test_samples)")
    p_run.add_argument("--scenario", "-s", help="Run a single scenario by ID")
    p_run.add_argument("--tags", "-t", nargs="+", help="Filter scenarios by tags")
    p_run.add_argument("--cwd", default="/tmp", help="Working directory for bridge sessions")
    p_run.add_argument("--report", action="store_true", help="Generate HTML dashboard after run")
    p_run.add_argument("--clean", action="store_true", help="Remove eval-results/ before running")
    p_run.add_argument(
        "--baseline", help="Path to a baseline summary.json to compare against for regressions"
    )

    # report
    p_report = sub.add_parser("report", help="Generate HTML dashboard from eval results")
    p_report.add_argument("--results-dir", help="Path to eval-results/ (default: ./eval-results/)")

    # clean
    p_clean = sub.add_parser("clean", help="Remove eval-results/ for a fresh cycle")
    p_clean.add_argument("--results-dir", help="Path to eval-results/ (default: ./eval-results/)")

    # insights
    p_ins = sub.add_parser("insights", help="Diagnose an eval run (root causes + citations)")
    p_ins.add_argument("artifacts_dir", help="Eval artifacts dir (e.g. ./eval-results/)")
    p_ins.add_argument("--goal", default=DEFAULT_GOAL, help="What success looks like")
    p_ins.add_argument("--target-dir", help="Read-only agent source for mechanism analysis")
    p_ins.add_argument("--output", "-o", help="Output dir for report.md")
    p_ins.add_argument("--print", action="store_true", help="Print the report to stdout")

    # evolve
    p_evo = sub.add_parser("evolve", help="Self-improve the agent under test (evolution loop)")
    p_evo.add_argument("--run-dir", default="runs/evolve", help="Output run directory")
    p_evo.add_argument("--test-dir", help="Scenario dir (default: ./test_samples)")
    p_evo.add_argument("--goal", default=DEFAULT_GOAL, help="What success looks like")
    p_evo.add_argument("--metrics", nargs="+", default=["assertion_pass_rate", "llm_judge"],
                       help="Scoring metrics")
    p_evo.add_argument("--train-slice", default="0:10", help="Scenario slice for training")
    p_evo.add_argument("--validation-slice", default="10:15",
                       help="Scenario slice for validation (empty to disable)")
    p_evo.add_argument("--test-slice", default="15:20",
                       help="Held-out test slice (empty to disable before/after test)")
    p_evo.add_argument("--budget", type=int, default=5, help="Max evolution steps")
    p_evo.add_argument("--patience", type=int, default=3,
                       help="Early-stopping patience (0=disabled)")
    p_evo.add_argument("--selection-metric", default="validation",
                       choices=["validation", "train", "final"],
                       help="Checkpoint selection metric")
    p_evo.add_argument("--max-workers", type=int, default=1, help="Parallel scenario workers")
    p_evo.add_argument("--review", action="store_true",
                       help="Generate a change review after evolving")

    # review
    p_rev = sub.add_parser("review", help="PR-style diff review of an evolution run")
    p_rev.add_argument("run_env_dir",
                       help="Per-env run dir with trajectory.jsonl + snapshots.git")
    p_rev.add_argument("--output", "-o", help="Output markdown path")
    p_rev.add_argument("--context", type=int, default=3, help="Diff context lines")

    # evohistory
    p_hist = sub.add_parser("evohistory", help="Show a run's evolution_history.md")
    p_hist.add_argument("run_dir",
                        help="Run dir (or per-env dir) holding evolution_history.md")
    p_hist.add_argument("--output", "-o", help="Copy the history to this path instead of printing")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # `generate` forwards everything after it verbatim (the generator owns those
    # flags). Intercept before argparse so its --help/--flags aren't consumed.
    if argv and argv[0] == "generate":
        return cmd_generate(argv[1:])
    if len(argv) >= 2 and argv[0] in ("-v", "--verbose") and argv[1] == "generate":
        return cmd_generate(argv[2:])

    args = build_parser().parse_args(argv)

    log_fmt, log_datefmt = "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    logging.Formatter.converter = time.gmtime
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=log_fmt, datefmt=log_datefmt)
        os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"
    else:
        logging.basicConfig(level=logging.INFO, format=log_fmt, datefmt=log_datefmt)

    dispatch = {
        "list": cmd_list,
        "run": cmd_run,
        "report": cmd_report,
        "clean": cmd_clean,
        "insights": cmd_insights,
        "evolve": cmd_evolve,
        "review": cmd_review,
        "evohistory": cmd_evohistory,
    }
    return dispatch[args.command](args)


def entry_point() -> None:
    """Console-script entry point (``agent-builder-eval``)."""
    raise SystemExit(main())


if __name__ == "__main__":
    entry_point()
