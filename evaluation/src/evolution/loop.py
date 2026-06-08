# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter for the ``evolve`` verb — drive the evolution loop on eval_runner.

Wires :class:`harness_evolver.Orchestrator` to evaluate via this repo's
``eval_runner`` engine (see :mod:`evolution.eval_runner_env`). Train / validation
/ test are disjoint slices of one scenario directory, so the evolver never sees
the held-out test set.

The evolver mutates ``execution_config.agent_dir`` (the agent under test) in
place, snapshotting each step into ``<run_dir>/<train_name>/snapshots.git``. After
the loop, the best checkpoint (by validation pass rate) is restored into the
target dir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvolveSpec:
    """Inputs for one evolution run."""

    execution_config: object  # eval_runner.config.ExecutionConfig
    test_dir: Path
    goal: str
    run_dir: Path
    metrics: list[str] = field(default_factory=lambda: ["assertion_pass_rate", "llm_judge"])
    train_slice: str = "0:10"
    validation_slice: str | None = "10:15"
    test_slice: str | None = "15:20"
    budget: int = 5
    early_stopping_patience: int = 3
    early_stopping_min_delta: float = 0.01
    selection_metric: str = "validation"
    max_workers: int = 1


def run_evolution(spec: EvolveSpec) -> Path:
    """Run the full evolve experiment. Returns the train run env directory.

    Builds train/validation/test bridge envs over ``spec.test_dir`` and runs
    ``Orchestrator.run_experiment`` (evolve loop + early stopping + checkpoint
    selection + before/after test measurement). When ``test_slice`` is empty,
    falls back to ``run_evolve`` (no held-out before/after test).
    """
    import anyio
    from harness_evolver import Orchestrator, configure_logging

    from evolution.eval_runner_env import make_eval_runner_env

    configure_logging()
    run_dir = Path(spec.run_dir)

    def _env(name: str, test_slice: str | None):
        return make_eval_runner_env(
            name=name,
            base_execution_config=spec.execution_config,
            test_dir=spec.test_dir,
            goal=spec.goal,
            metrics=spec.metrics,
            test_slice=test_slice,
            max_workers=spec.max_workers,
        )

    train = _env("agent_builder_train", spec.train_slice)
    validation = _env("agent_builder_validation", spec.validation_slice) if spec.validation_slice else None
    test = _env("agent_builder_test", spec.test_slice) if spec.test_slice else None

    orch = Orchestrator(run_dir=run_dir)

    async def _go():
        if test is not None:
            await orch.run_experiment(
                env_pairs=[(train, validation)],
                test=test,
                budget=spec.budget,
                selection_metric=spec.selection_metric,
                early_stopping_patience=spec.early_stopping_patience,
                early_stopping_min_delta=spec.early_stopping_min_delta,
            )
        else:
            await orch.run_evolve(
                env_pairs=[(train, validation)],
                budget=spec.budget,
                early_stopping_patience=spec.early_stopping_patience,
                early_stopping_min_delta=spec.early_stopping_min_delta,
            )

    anyio.run(_go)
    return run_dir / train.name
