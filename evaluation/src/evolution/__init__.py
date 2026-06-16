# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter layer bridging the evaluation toolkit to the (separate) HarnessEvolver.

HarnessEvolver is a self-contained project in the repo's top-level ``evolution/``
directory (its own git history, venv, and pyproject; distribution name
``harness-evolver``, import name ``harness_evolver``). It is **not** vendored
here: this package depends on it via the evaluation package's optional ``evolve``
extra, which ``[tool.uv.sources]`` resolves to ``../evolution`` as an editable
install. Install it with ``uv pip install -e ".[evolve]"`` so ``import
harness_evolver`` works.

This package provides thin adapters that the unified CLI calls:

- :mod:`evolution.eval_runner_env` — builds an evolver ``Environment`` whose
  ``run`` callback drives this repo's ``eval_runner`` engine (so ``run`` and
  ``evolve`` share one evaluation engine).
- :mod:`evolution.loop` — drives ``harness_evolver.Orchestrator`` (the evolve verb).
- :mod:`evolution.insights` — diagnosis report over an eval run (analyst).
- :mod:`evolution.review` — PR-style change review over the snapshot ledger.
- :mod:`evolution.history` — surface a run's ``evolution_history.md`` (evohistory).

Note the name distinction: this adapter package is ``evolution`` (under
``evaluation/src/``); the evolver it drives is ``harness_evolver`` (the installed
package built from the top-level ``evolution/`` directory). No import collision.

Importing harness_evolver / claude_agent_sdk is deferred to the adapter functions
so the base CLI (list / run / report / clean / review / evohistory) works without
the optional ``evolve`` dependencies installed.
"""

from __future__ import annotations
