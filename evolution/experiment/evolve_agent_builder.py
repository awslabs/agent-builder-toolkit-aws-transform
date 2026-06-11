# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Evolve the AWS Transform agent-builder agent.

Self-evolve run on the agent under test (evaluation/agent_under_test/) using the
eval scenarios in evaluation/test_samples/. The evolver mutates AGENT.md and
mcp.json to improve assertion pass rates, measured by the in-repo evaluation
framework (eval_runner) driving the agent live over ACP.

Usage:
    cd evolution
    source .venv/bin/activate
    PYTHONPATH=. python experiment/evolve_agent_builder.py

The script supports different configurations (slices index into the scenarios
loaded from test_samples/; populate that directory with enough scenarios to
support the train/validation/test split before running a real evolution):
- Quick test: small slices, budget=5 (fast iteration)
- Standard: medium slices, budget=5
- Full: full slices, budget=5 (comprehensive)
"""

import shutil
from pathlib import Path

import anyio
from env_configs.agent_builder_env import make_env as make_agent_env
from harness_evolver import Orchestrator, configure_logging

configure_logging()


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _slice_upper_bound(test_slice: str) -> int:
    """Highest scenario index a slice spec needs present (for preflight)."""
    if ":" in test_slice:
        _, end_s = test_slice.split(":")
        # Open-ended ("0:") needs at least 1 scenario; we can't know the real
        # upper bound without the data, so treat it as 1 for the count check.
        return int(end_s) if end_s else 1
    return int(test_slice) + 1


def _preflight_scenarios(config: dict) -> None:
    """Fail fast (with guidance) if test_samples can't satisfy the slices."""
    from env_configs.agent_builder_env import TEST_DATA_DIR
    from eval_runner.execution.loader import load_scenarios

    total = len(load_scenarios(TEST_DATA_DIR))
    needed = max(
        _slice_upper_bound(config["train_slice"]),
        _slice_upper_bound(config["validation_slice"]),
        _slice_upper_bound(config["test_slice"]),
    )
    if total < needed:
        raise SystemExit(
            f"Not enough eval scenarios to run this mode.\n"
            f"  Found {total} scenario(s) in {TEST_DATA_DIR}\n"
            f"  Slices (train={config['train_slice']}, "
            f"validation={config['validation_slice']}, test={config['test_slice']}) "
            f"need at least {needed}.\n"
            f"Populate {TEST_DATA_DIR} with more scenarios, or pick smaller "
            f"slices, before running a real evolution."
        )


async def main():
    """Run evolution on the AWS Transform agent-builder agent."""

    # Configuration - adjust these as needed
    RUN_MODE = "quick"  # quick | standard | full

    # Slices index into the scenarios loaded from test_samples/. Each mode needs
    # at least `test_slice`'s upper bound scenarios present; with fewer, the env
    # now raises rather than silently producing empty val/test splits. Populate
    # test_samples/ to match the mode you run (e.g. "full" needs >= 50 scenarios).
    configs = {
        "quick": {
            "train_slice": "0:2",
            "validation_slice": "2:4",
            "test_slice": "4:6",
            "budget": 5,
            "early_stopping": 3,
            "run_dir": "runs/agent_builder_quick",
        },
        "standard": {
            "train_slice": "0:10",
            "validation_slice": "10:15",
            "test_slice": "15:20",
            "budget": 5,
            "early_stopping": 3,
            "run_dir": "runs/agent_builder_standard",
        },
        "full": {
            "train_slice": "0:30",
            "validation_slice": "30:40",
            "test_slice": "40:50",
            "budget": 5,
            "early_stopping": 3,
            "run_dir": "runs/agent_builder_full",
        },
    }

    config = configs[RUN_MODE]
    run_dir = _REPO_ROOT / config["run_dir"]

    # Preflight: make sure the committed test_samples can satisfy every slice
    # before we spend a single (expensive, live-ACP) eval. Without this the run
    # would proceed until an empty val/test slice raises mid-flight — or, worse,
    # used to silently produce empty splits.
    _preflight_scenarios(config)

    # Clean previous run
    if run_dir.exists():
        print(f"Removing previous run at {run_dir}")
        shutil.rmtree(run_dir)

    # Create environments
    agent_train = make_agent_env(
        name="agent_builder_train",
        test_slice=config["train_slice"],
        n_concurrent=1,  # Sequential for stability
    )

    agent_validation = make_agent_env(
        name="agent_builder_validation",
        test_slice=config["validation_slice"],
        n_concurrent=1,
    )

    agent_test = make_agent_env(
        name="agent_builder_test",
        test_slice=config["test_slice"],
        n_concurrent=1,
    )


    # Run evolution
    print(f"Starting evolution in {RUN_MODE} mode:")
    print(f"  Train slice: {config['train_slice']}")
    print(f"  Validation slice: {config['validation_slice']}")
    print(f"  Test slice: {config['test_slice']}")
    print(f"  Budget: {config['budget']}")
    print(f"  Early stopping patience: {config.get('early_stopping', 0)}")
    print("  Model selection: validation")
    print("  Regularization: enabled (via prompt)")
    print(f"  Output: {run_dir}")

    orch = Orchestrator(run_dir=run_dir)
    await orch.run_experiment(
        env_pairs=[(agent_train, agent_validation)],
        test = agent_test,
        budget=config["budget"],
        selection_metric="validation",                              # Phase 1: Model selection
        early_stopping_patience=config.get("early_stopping", 0),   # Phase 2: Early stopping
        early_stopping_min_delta=0.01,                             # Phase 2: 1% improvement threshold
        # Phase 3: Regularization is automatic via prompt changes
    )

    print(f"\nEvolution complete! Results in: {run_dir}")
    print("\nTo inspect edits:")
    print(f"  cd {run_dir}/agent_builder_train")
    print("  GIT_DIR=snapshots.git git log --oneline")
    print("  GIT_DIR=snapshots.git git diff baseline post_step_000")


if __name__ == "__main__":
    anyio.run(main)
