# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Union

RunFn = Callable[[Path, Path], Union[None, Awaitable[None]]]


@dataclass
class Environment:
    """One unit of (what-to-evolve, what-success-means, how-to-produce-evidence).

    Attributes:
        target_dir:   The directory the evolver is allowed to edit. Agent
                      source only — no data, no evaluation harness.
        goal:         Natural-language spec of what success looks like in
                      this env. Read by the evaluator.
        run:          Callable (target_dir, artifacts_dir) -> None (or
                      awaitable) that executes the target and writes
                      whatever evidence the evaluator should see into
                      artifacts_dir.
        name:         Short slug used to name run subdirectories.
    """

    target_dir: Path
    goal: str
    run: RunFn
    name: str = "env"
