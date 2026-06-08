# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import inspect
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from harness_evolver import evolver
from harness_evolver.analyst import analyze
from harness_evolver.environment import Environment


EnvPair = tuple[Environment, Environment | None]


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


async def _run_test(env: Environment, out_dir: Path) -> str:
    """Run a test env and produce an analyst report. Returns report text."""
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir = out_dir / "run"
    analyst_output_dir = out_dir / "analyst_output"
    run_dir.mkdir(parents=True, exist_ok=True)
    analyst_output_dir.mkdir(parents=True, exist_ok=True)

    result = env.run(env.target_dir, run_dir)
    await _maybe_await(result)

    report, _ = await analyze(
        artifacts_dir=run_dir,
        goal=env.goal,
        output_dir=analyst_output_dir,
        target_dir=env.target_dir,
    )
    return report


@dataclass
class Orchestrator:
    """Thin driver for evolving agents and running experiments."""

    run_dir: Path = Path("runs/default")

    async def run_evolve(
        self,
        env_pairs: list[EnvPair],
        budget: int = 3,
        early_stopping_patience: int = 0,
        early_stopping_min_delta: float = 0.01,
    ) -> None:
        """Run the evolver independently on each env pair.

        Args:
            early_stopping_patience: Stop if no improvement for N steps (0=disabled)
            early_stopping_min_delta: Minimum improvement threshold (default 1%)
        """
        run_dir = Path(self.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        for train, validation in env_pairs:
            sub_run_dir = run_dir / train.name
            await evolver.run(
                train=train,
                validation=validation,
                budget=budget,
                run_dir=sub_run_dir,
                early_stopping_patience=early_stopping_patience,
                early_stopping_min_delta=early_stopping_min_delta,
            )

    async def run_experiment(
        self,
        env_pairs: list[EnvPair],
        test: Environment,
        budget: int = 3,
        selection_metric: str = "validation",
        early_stopping_patience: int = 0,
        early_stopping_min_delta: float = 0.01,
    ) -> None:
        """Evolve with early stopping and model selection.

        1. Run test env against the current (pre-evolution) target.
        2. Run the evolution loop with early stopping.
        3. Select best checkpoint based on selection_metric.
        4. Run test env again against the selected checkpoint.

        Test reports are written to run_dir/test/{before,after}/.
        The test env is never seen by the evolver.

        Args:
            selection_metric: Which checkpoint to use for final test evaluation:
                - "validation": Use checkpoint with best validation score (recommended)
                - "final": Use final step (original behavior)
                - "train": Use checkpoint with best training score (not recommended)
            early_stopping_patience: Stop if no improvement for N steps (0=disabled)
            early_stopping_min_delta: Minimum improvement threshold (default 1%)
        """
        run_dir = Path(self.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        test_dir = run_dir / "test"
        await _run_test(test, test_dir / "before")

        await self.run_evolve(
            env_pairs,
            budget=budget,
            early_stopping_patience=early_stopping_patience,
            early_stopping_min_delta=early_stopping_min_delta,
        )

        # Select best checkpoint based on metric
        if selection_metric == "validation":
            best_checkpoint = _select_best_validation_checkpoint(run_dir, env_pairs)
            if best_checkpoint:
                _restore_checkpoint(best_checkpoint, env_pairs[0][0].target_dir, run_dir)
                print(f"\n=== Model Selection: {best_checkpoint} (best validation) ===")
            else:
                print("\n=== Model Selection: final (validation selection failed) ===")
        elif selection_metric == "train":
            best_checkpoint = _select_best_train_checkpoint(run_dir, env_pairs)
            if best_checkpoint:
                _restore_checkpoint(best_checkpoint, env_pairs[0][0].target_dir, run_dir)
                print(f"\n=== Model Selection: {best_checkpoint} (best training) ===")
            else:
                print("\n=== Model Selection: final (training selection failed) ===")
        else:  # "final"
            print("\n=== Model Selection: final (using last step) ===")

        await _run_test(test, test_dir / "after")


def _select_best_validation_checkpoint(run_dir: Path, env_pairs: list[EnvPair]) -> str | None:
    """Find the checkpoint with highest validation pass rate."""
    train, validation = env_pairs[0]
    if validation is None:
        return None

    train_run_dir = run_dir / train.name
    if not train_run_dir.exists():
        return None

    best_step = None
    best_score = -1.0
    best_step_info = ""

    # Check all training steps (including step 0)
    for step_dir in sorted(train_run_dir.glob("step_*")):
        step_match = re.search(r"step_(\d+)", step_dir.name)
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Parse pass rate from validation evaluation_summary.json
        summary_file = step_dir / validation.name / "run" / "evaluation_summary.json"
        if not summary_file.exists():
            continue

        try:
            with summary_file.open() as f:
                summary = json.load(f)
                score = summary.get("assertion_pass_rate", 0.0)
                tests_passed = sum(1 for t in summary.get("tests", []) if t.get("passed", False))
                total_tests = summary.get("total_tests", 0)

            if score > best_score:
                best_score = score
                best_step = step
                best_step_info = f"step {step}: {score:.1%} pass rate ({tests_passed}/{total_tests} tests)"
                print(f"  Found better checkpoint: {best_step_info}")
        except Exception as e:
            print(f"  Warning: Could not parse {summary_file}: {e}")
            continue

    if best_step is not None:
        print(f"\n  Best validation checkpoint: {best_step_info}")
        return f"post_step_{best_step:03d}"

    return None


def _select_best_train_checkpoint(run_dir: Path, env_pairs: list[EnvPair]) -> str | None:
    """Find the checkpoint with highest training pass rate."""
    train, _ = env_pairs[0]

    train_run_dir = run_dir / train.name
    if not train_run_dir.exists():
        return None

    best_step = None
    best_score = -1.0

    # Check all training steps
    for step_dir in sorted(train_run_dir.glob("step_*")):
        step_match = re.search(r"step_(\d+)", step_dir.name)
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Parse pass rate from training evaluation_summary.json
        summary_file = step_dir / train.name / "run" / "evaluation_summary.json"
        if not summary_file.exists():
            continue

        try:
            with summary_file.open() as f:
                summary = json.load(f)
                score = summary.get("assertion_pass_rate", 0.0)

            if score > best_score:
                best_score = score
                best_step = step
        except Exception:
            continue

    return f"post_step_{best_step:03d}" if best_step is not None else None


def _restore_checkpoint(checkpoint_name: str, target_dir: Path, run_dir: Path) -> None:
    """Restore target_dir to a specific checkpoint."""
    # Find the snapshots git repo
    snapshots_dir = None
    for env_dir in run_dir.iterdir():
        if not env_dir.is_dir():
            continue
        snapshots_git = env_dir / "snapshots.git"
        if snapshots_git.exists():
            snapshots_dir = snapshots_git
            break

    if not snapshots_dir:
        print(f"  Warning: Could not find snapshots.git to restore {checkpoint_name}")
        return

    # Resolve checkpoint_name to commit hash
    # The checkpoint name is stored as a commit message, not a branch/tag
    resolve_result = subprocess.run(
        [
            "git",
            f"--git-dir={snapshots_dir}",
            "log",
            "--all",
            "--oneline",
            "--grep",
            f"^{checkpoint_name}$",
            "--format=%H",
        ],
        capture_output=True,
        text=True,
    )

    if resolve_result.returncode != 0 or not resolve_result.stdout.strip():
        print(f"  Warning: Could not resolve checkpoint {checkpoint_name} to commit hash")
        return

    commit_hash = resolve_result.stdout.strip().split("\n")[0]

    # Restore files from git
    result = subprocess.run(
        [
            "git",
            f"--git-dir={snapshots_dir}",
            f"--work-tree={target_dir}",
            "checkout",
            commit_hash,
            "--",
            ".",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  Warning: Failed to restore checkpoint {checkpoint_name}: {result.stderr}")
    else:
        print(f"  Restored target_dir to {checkpoint_name}")
