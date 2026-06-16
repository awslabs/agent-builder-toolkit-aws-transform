# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from pathlib import Path

from harness_evolver import evolver
from harness_evolver.analyst import analyze
from harness_evolver.environment import Environment
from harness_evolver.snapshots import TargetSnapshots

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
            if best_checkpoint and _restore_checkpoint(
                best_checkpoint, env_pairs[0][0].target_dir, run_dir
            ):
                print(f"\n=== Model Selection: {best_checkpoint} (best validation) ===")
            else:
                print("\n=== Model Selection: final (validation selection failed) ===")
        elif selection_metric == "train":
            best_checkpoint = _select_best_train_checkpoint(run_dir, env_pairs)
            if best_checkpoint and _restore_checkpoint(
                best_checkpoint, env_pairs[0][0].target_dir, run_dir
            ):
                print(f"\n=== Model Selection: {best_checkpoint} (best training) ===")
            else:
                print("\n=== Model Selection: final (training selection failed) ===")
        else:  # "final"
            print("\n=== Model Selection: final (using last step) ===")

        await _run_test(test, test_dir / "after")


def _checkpoint_for_measurement(measurement_dir_name: str, max_step: int) -> str:
    """Map an eval directory to the snapshot whose tree it measured.

    The loop measures *before* editing within a step, so each eval reflects the
    tree as captured at the *end of the previous step*:

      - ``step_000`` measures the ``baseline`` snapshot.
      - ``step_NNN`` (N>0) measures ``post_step_{NNN-1}`` — content-identical to
        ``pre_step_NNN`` (nothing edits ``target_dir`` between the two; only the
        measurement + analyst run there), but ``post_step_{NNN-1}`` is the
        snapshot guaranteed to exist: when early stopping breaks at step N, the
        loop records ``step_N``'s summary but never takes ``pre_step_N`` /
        ``post_step_N``. Restoring ``post_step_NNN`` here would instead ship the
        edit made *during* step N — a tree this score never scored (the
        off-by-one).
      - ``final_eval`` is the measurement-only pass after the last edit, so it
        measures ``post_step_{max_step}`` — the only post-edit tree no ``step_*``
        directory covers. Mapping it lets the final edit be selected.
      - When no edit step ran (``max_step < 0``, e.g. ``budget=0``), ``final_eval``
        measured the un-edited tree, so it maps to ``baseline``. Without this it
        would map to a ``post_step_000`` snapshot that was never taken, and
        restore would silently no-op while the run reported success.
    """
    m = re.search(r"step_(\d+)", measurement_dir_name)
    if m:
        step = int(m.group(1))
        return "baseline" if step == 0 else f"post_step_{step - 1:03d}"
    # final_eval (or any non-step dir): the last edit's tree, or baseline if no
    # edit step ever ran.
    if max_step < 0:
        return "baseline"
    return f"post_step_{max_step:03d}"


def _iter_score_candidates(train_run_dir: Path, env_name: str):
    """Yield ``(measurement_dir_name, summary_dict)`` for each scored eval.

    Covers both ``step_*`` directories and the terminal ``final_eval`` pass.
    """
    measurement_dirs = sorted(train_run_dir.glob("step_*"))
    final_eval = train_run_dir / "final_eval"
    if final_eval.is_dir():
        measurement_dirs.append(final_eval)

    for mdir in measurement_dirs:
        summary_file = mdir / env_name / "run" / "evaluation_summary.json"
        if not summary_file.exists():
            continue
        try:
            with summary_file.open() as f:
                yield mdir.name, json.load(f)
        except Exception as e:
            print(f"  Warning: Could not parse {summary_file}: {e}")
            continue


def _max_edited_step(train_run_dir: Path) -> int:
    """Highest ``step_NNN`` index that ran an edit (i.e. has a ``post_step``).

    Returns ``-1`` when no edit step ran (e.g. ``budget=0`` produces only a
    ``final_eval`` dir). ``_checkpoint_for_measurement`` reads that as "the final
    eval measured the baseline tree", not a never-created ``post_step_000``.
    """
    steps = [
        int(m.group(1))
        for d in train_run_dir.glob("step_*")
        if (m := re.search(r"step_(\d+)", d.name))
    ]
    return max(steps) if steps else -1


def _select_best_validation_checkpoint(run_dir: Path, env_pairs: list[EnvPair]) -> str | None:
    """Find the checkpoint (snapshot ref) with highest validation pass rate."""
    train, validation = env_pairs[0]
    if validation is None:
        return None

    train_run_dir = run_dir / train.name
    if not train_run_dir.exists():
        return None

    max_step = _max_edited_step(train_run_dir)
    best_ref = None
    best_score = -1.0
    best_info = ""

    for mdir_name, summary in _iter_score_candidates(train_run_dir, validation.name):
        score = summary.get("assertion_pass_rate", 0.0)
        if score > best_score:
            best_score = score
            best_ref = _checkpoint_for_measurement(mdir_name, max_step)
            tests_passed = sum(1 for t in summary.get("tests", []) if t.get("passed", False))
            total_tests = summary.get("total_tests", 0)
            best_info = f"{mdir_name} -> {best_ref}: {score:.1%} pass rate ({tests_passed}/{total_tests} tests)"
            print(f"  Found better checkpoint: {best_info}")

    if best_ref is not None:
        print(f"\n  Best validation checkpoint: {best_info}")
        return best_ref

    return None


def _select_best_train_checkpoint(run_dir: Path, env_pairs: list[EnvPair]) -> str | None:
    """Find the checkpoint (snapshot ref) with highest training pass rate."""
    train, _ = env_pairs[0]

    train_run_dir = run_dir / train.name
    if not train_run_dir.exists():
        return None

    max_step = _max_edited_step(train_run_dir)
    best_ref = None
    best_score = -1.0

    for mdir_name, summary in _iter_score_candidates(train_run_dir, train.name):
        score = summary.get("assertion_pass_rate", 0.0)
        if score > best_score:
            best_score = score
            best_ref = _checkpoint_for_measurement(mdir_name, max_step)

    return best_ref


def _restore_checkpoint(checkpoint_name: str, target_dir: Path, run_dir: Path) -> bool:
    """Restore target_dir to a specific checkpoint snapshot.

    Delegates to ``TargetSnapshots.rollback`` (read-tree --reset + clean -fdx) so
    the work-tree ends up *byte-for-byte* equal to the snapshot. A manual
    ``git checkout <sha> -- .`` would only overwrite tracked paths and leave
    files a later step added behind, producing a tree no evaluation ever scored.

    Returns ``True`` if the restore happened, ``False`` if the checkpoint could
    not be found/resolved/applied. A ``False`` return means target_dir was left
    untouched — callers must not report the restore as successful.
    """
    # Find the snapshots git ledger (each env's run dir owns one).
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
        return False

    snapshots = TargetSnapshots(target_dir=target_dir, ledger_dir=snapshots_dir)

    # Checkpoint names are commit messages, not refs — resolve via the ledger log.
    resolve = snapshots._git(
        "log", "--all", "--grep", f"^{checkpoint_name}$", "--format=%H", check=False
    )
    if resolve.returncode != 0 or not resolve.stdout.strip():
        print(f"  Warning: Could not resolve checkpoint {checkpoint_name} to commit hash")
        return False

    commit_hash = resolve.stdout.strip().split("\n")[0]

    try:
        snapshots.rollback(commit_hash)
    except Exception as e:
        print(f"  Warning: Failed to restore checkpoint {checkpoint_name}: {e}")
        return False

    print(f"  Restored target_dir to {checkpoint_name}")
    return True
