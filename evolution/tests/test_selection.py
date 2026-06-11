# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for checkpoint selection + restore (orchestrator).

These guard the selection->restore contract:
  - the score recorded at ``step_NNN`` measures the *pre-edit* tree, so the
    selected checkpoint must be ``pre_step_NNN`` (``pre_step_000`` == baseline),
    not ``post_step_NNN`` (an off-by-one that ships an unmeasured tree);
  - ``final_eval`` measures the last *post-edit* tree and must be selectable;
  - restore reconstructs exactly the selected snapshot's tree.
"""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from harness_evolver.orchestrator import (
    _checkpoint_for_measurement,
    _restore_checkpoint,
    _select_best_train_checkpoint,
    _select_best_validation_checkpoint,
)
from harness_evolver.snapshots import TargetSnapshots


@dataclass
class _Env:
    name: str
    target_dir: Path = Path(".")
    goal: str = ""
    run: Callable = lambda *a, **k: None


def _write_summary(path: Path, pass_rate: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "assertion_pass_rate": pass_rate,
                "total_tests": 1,
                "tests": [{"test_id": "t", "passed": pass_rate >= 0.5}],
            }
        )
    )


def _make_run_dir(tmp: Path, val_scores: dict[str, float], env_name="train", val_name="val") -> Path:
    """Build a synthetic run dir: {step name -> validation pass rate}."""
    run_dir = tmp / "run"
    train_run = run_dir / env_name
    for step_name, score in val_scores.items():
        _write_summary(train_run / step_name / val_name / "run" / "evaluation_summary.json", score)
    return run_dir


def test_measurement_to_checkpoint_mapping():
    # step_000 measures baseline; step_N (N>0) measures post_step_{N-1} (the
    # snapshot guaranteed to exist even when early stopping breaks at step N
    # before pre_step_N/post_step_N are taken); final_eval measures the last
    # post-edit tree.
    assert _checkpoint_for_measurement("step_000", max_step=3) == "baseline"
    assert _checkpoint_for_measurement("step_002", max_step=3) == "post_step_001"
    assert _checkpoint_for_measurement("final_eval", max_step=3) == "post_step_003"


def test_selection_picks_measured_tree_not_post_edit():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # step_001 has the best validation score.
        run_dir = _make_run_dir(tmp, {"step_000": 0.30, "step_001": 0.90, "step_002": 0.50})
        pair = (_Env("train"), _Env("val"))

        best = _select_best_validation_checkpoint(run_dir, [pair])
        # The off-by-one bug would return "post_step_001" (the edit step_001 made,
        # never scored); step_001's score measured post_step_000.
        assert best == "post_step_000"


def test_selection_can_pick_baseline():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Baseline (step_000) is best -> "no edit helped" must be representable.
        run_dir = _make_run_dir(tmp, {"step_000": 0.80, "step_001": 0.40, "step_002": 0.40})
        best = _select_best_validation_checkpoint(run_dir, [(_Env("train"), _Env("val"))])
        assert best == "baseline"


def test_selection_includes_final_eval():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # The final edit, measured only in final_eval/, is the best — must win.
        run_dir = _make_run_dir(
            tmp, {"step_000": 0.30, "step_001": 0.40, "final_eval": 0.95}
        )
        best = _select_best_validation_checkpoint(run_dir, [(_Env("train"), _Env("val"))])
        assert best == "post_step_001"  # last edited step index is 1


def test_train_selection_maps_to_measured_tree():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run_dir = tmp / "run"
        train_run = run_dir / "train"
        for step, score in {"step_000": 0.2, "step_001": 0.7}.items():
            _write_summary(train_run / step / "train" / "run" / "evaluation_summary.json", score)
        best = _select_best_train_checkpoint(run_dir, [(_Env("train"), None)])
        assert best == "post_step_000"


def test_no_validation_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _make_run_dir(Path(tmp), {"step_000": 0.5})
        assert _select_best_validation_checkpoint(run_dir, [(_Env("train"), None)]) is None


def test_restore_checkpoint_reconstructs_selected_tree():
    """End-to-end: selection name -> _restore_checkpoint -> correct on-disk tree."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        target = tmp / "target"
        target.mkdir()
        run_dir = tmp / "run"
        # The ledger lives under run_dir/<env>/snapshots.git, where _restore looks.
        ledger = run_dir / "train" / "snapshots.git"
        ledger.parent.mkdir(parents=True)

        snaps = TargetSnapshots(target_dir=target, ledger_dir=ledger)

        # baseline (the tree step_000 measures)
        (target / "AGENT.md").write_text("baseline\n")
        snaps.snapshot("baseline")
        snaps.snapshot("pre_step_000")
        # step 0 edits, then post_step_000 (the tree step_001 measures)
        (target / "AGENT.md").write_text("after step 0\n")
        (target / "new.md").write_text("added\n")
        snaps.snapshot("post_step_000")
        snaps.snapshot("pre_step_001")
        # step 1 edits again
        (target / "AGENT.md").write_text("after step 1\n")
        snaps.snapshot("post_step_001")

        # Restoring baseline must bring back baseline AGENT.md and drop new.md.
        _restore_checkpoint("baseline", target, run_dir)
        assert (target / "AGENT.md").read_text() == "baseline\n"
        assert not (target / "new.md").exists()


def test_early_stop_selection_resolves_to_an_existing_snapshot():
    """Early stopping breaks before pre_step_N/post_step_N are taken.

    If validation peaks at the early-stopped step N, selection must map to a
    snapshot that actually exists (post_step_{N-1}), not the never-created
    pre_step_N — otherwise restore silently fails and ships the wrong tree.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        target = tmp / "target"
        target.mkdir()
        run_dir = tmp / "run"
        train_run = run_dir / "train"
        ledger = train_run / "snapshots.git"
        ledger.parent.mkdir(parents=True)

        snaps = TargetSnapshots(target_dir=target, ledger_dir=ledger)
        # Snapshots that a real loop creates through step 1's edit. Crucially,
        # step 2 is the early-stop step: its summary is written but NO
        # pre_step_002 / post_step_002 snapshot is ever taken.
        (target / "AGENT.md").write_text("baseline\n")
        snaps.snapshot("baseline")
        snaps.snapshot("pre_step_000")
        (target / "AGENT.md").write_text("step0\n")
        snaps.snapshot("post_step_000")
        snaps.snapshot("pre_step_001")
        (target / "AGENT.md").write_text("step1 — best validation\n")
        snaps.snapshot("post_step_001")

        # step_002 (early-stopped) scores best on validation.
        for step, score in {"step_000": 0.3, "step_001": 0.5, "step_002": 0.9}.items():
            _write_summary(train_run / step / "val" / "run" / "evaluation_summary.json", score)

        best = _select_best_validation_checkpoint(run_dir, [(_Env("train"), _Env("val"))])
        assert best == "post_step_001"  # the tree step_002 actually measured

        # And it must resolve + restore (regression guard: pre_step_002 would not).
        (target / "AGENT.md").write_text("uncommitted drift\n")
        _restore_checkpoint(best, target, run_dir)
        assert (target / "AGENT.md").read_text() == "step1 — best validation\n"
