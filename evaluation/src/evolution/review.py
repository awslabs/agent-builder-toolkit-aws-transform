# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter for the ``review`` verb — PR-style diff review over a run's snapshots.

Reuses ``generate_change_review.generate_review`` shipped with the HarnessEvolver
project (it reads the snapshot ledger + trajectory.jsonl and emits one markdown
section per evolution step plus a cumulative baseline→final diff). We import it by
file path so we don't depend on it being an installed module.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# This file: evaluation/src/evolution/review.py
#   parents[0]=evolution, [1]=src, [2]=evaluation, [3]=<repo root>
_EVOLVER_ROOT = Path(__file__).resolve().parents[3] / "evolution"
_REVIEW_SCRIPT = _EVOLVER_ROOT / "scripts" / "generate_change_review.py"


def _load_review_module():
    spec = importlib.util.spec_from_file_location(
        "harness_evolver_change_review", _REVIEW_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load review script at {_REVIEW_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_change_review(
    run_env_dir: Path, output: Path | None = None, context: int = 3
) -> Path:
    """Generate a PR-style change-review markdown for one evolution run env dir.

    Args:
        run_env_dir: Directory holding trajectory.jsonl + snapshots.git
            (e.g. ``runs/<run>/<train_env_name>``).
        output: Output markdown path (default: ``<run_env_dir>/change_review.md``).
        context: Unified-diff context lines.
    """
    run_env_dir = Path(run_env_dir).resolve()
    output = output or (run_env_dir / "change_review.md")
    module = _load_review_module()
    return module.generate_review(run_env_dir, output, context=context)
