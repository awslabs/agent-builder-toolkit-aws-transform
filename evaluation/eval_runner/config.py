# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclasses for evaluation and evolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class EvalConfig:
    """Configuration for running evaluations."""

    test_dir: Path = field(default_factory=lambda: Path("."))
    agent_class: str | None = None
    metrics: list[str] = field(default_factory=lambda: ["assertion_pass_rate"])
    max_workers: int = 1
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    output_path: Path = field(default_factory=lambda: Path("results.json"))

    @classmethod
    def from_yaml(cls, path: Path) -> EvalConfig:
        data = yaml.safe_load(path.read_text()) or {}
        return cls(
            test_dir=Path(data["test_dir"]) if "test_dir" in data else Path("."),
            agent_class=data.get("agent_class"),
            metrics=data.get("metrics", ["assertion_pass_rate"]),
            max_workers=data.get("max_workers", 1),
            model_id=data.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            output_path=Path(data["output_path"]) if "output_path" in data else Path("results.json"),
        )


@dataclass
class EvolutionConfig(EvalConfig):
    """Configuration for running evolution loops. Extends EvalConfig."""

    target: str = "prompt"
    max_iterations: int = 5
    target_score: float = 9.0
    require_approval: bool = True
    batch_size: int = 3

    @classmethod
    def from_yaml(cls, path: Path) -> EvolutionConfig:
        data = yaml.safe_load(path.read_text()) or {}
        return cls(
            test_dir=Path(data["test_dir"]) if "test_dir" in data else Path("."),
            agent_class=data.get("agent_class"),
            metrics=data.get("metrics", ["assertion_pass_rate"]),
            max_workers=data.get("max_workers", 1),
            model_id=data.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            output_path=Path(data["output_path"]) if "output_path" in data else Path("results.json"),
            target=data.get("target", "prompt"),
            max_iterations=data.get("max_iterations", 5),
            target_score=data.get("target_score", 9.0),
            require_approval=data.get("require_approval", True),
            batch_size=data.get("batch_size", 3),
        )
