# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""TestCase dataclass and loader utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval_runner.execution.runner import EvalCase


@dataclass
class TestCase:
    """A single evaluation test case, matching the PR #43 schema."""

    id: str
    name: str
    user_message: str
    description: str = ""
    complexity: str = "medium"
    tags: list[str] = field(default_factory=list)
    max_turns: int = 1
    timeout_seconds: int = 300
    simulated_human_guidance: str | None = None
    metadata: dict = field(default_factory=dict)
    assertions: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> TestCase:
        user_message = data.get("user_message") or data.get("prompt")
        if not user_message:
            raise ValueError("TestCase requires 'user_message' or 'prompt'")
        if "id" not in data:
            raise ValueError("TestCase requires 'id'")
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            user_message=user_message,
            description=data.get("description", ""),
            complexity=data.get("complexity", "medium"),
            tags=data.get("tags", []),
            max_turns=data.get("max_turns", 1),
            timeout_seconds=data.get("timeout_seconds", 300),
            simulated_human_guidance=data.get("simulated_human_guidance"),
            metadata=data.get("metadata", {}),
            assertions=data.get("assertions", []),
        )

    def to_scenario(self) -> "EvalCase":
        """Convert this TestCase into an execution-engine ``EvalCase``.

        Bridges the canonical eval_runner test model onto the ACP engine's
        scenario model so it can be run. The two schemas are near-identical; the
        only renames are ``user_message`` → ``prompt`` and ``metadata`` →
        (dropped, the scenario model has no equivalent field). ``complexity``
        carries through so per-complexity aggregation works on the live path.

        Imported lazily so eval_runner's core stays importable without pulling in
        the ACP engine.
        """
        from eval_runner.execution.runner import EvalCase

        return EvalCase(
            id=self.id,
            name=self.name,
            prompt=self.user_message,
            description=self.description,
            assertions=self.assertions,
            complexity=self.complexity,
            tags=self.tags,
            max_turns=self.max_turns,
            timeout_seconds=self.timeout_seconds,
            simulated_human_guidance=self.simulated_human_guidance,
        )


class TestCaseLoader:
    """Load test cases from files and directories."""

    @staticmethod
    def from_file(path: Path) -> list[TestCase]:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = [data]
        return [TestCase.from_dict(item) for item in data]

    @staticmethod
    def from_directory(directory: Path) -> list[TestCase]:
        cases: list[TestCase] = []
        for path in sorted(directory.glob("*.json")):
            cases.extend(TestCaseLoader.from_file(path))
        return cases

    @staticmethod
    def filter_by_complexity(cases: list[TestCase], complexity: str) -> list[TestCase]:
        return [tc for tc in cases if tc.complexity == complexity]

    @staticmethod
    def filter_by_tag(cases: list[TestCase], tag: str) -> list[TestCase]:
        return [tc for tc in cases if tag in tc.tags]
