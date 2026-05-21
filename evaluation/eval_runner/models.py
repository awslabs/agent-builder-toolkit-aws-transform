# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core data models for the evaluation runner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionResult:
    """Result of executing a single test case against an agent."""

    transcript: str
    output: str
    tool_calls: list[dict] = field(default_factory=list)
    duration_ms: int | None = None


@dataclass(frozen=True)
class MetricResult:
    """Result of evaluating a single metric on an execution."""

    metric_name: str
    score: float
    passed: bool
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.score <= 10.0):
            raise ValueError(f"score must be between 0 and 10, got {self.score}")


@dataclass
class EvaluationResult:
    """Aggregated result for one test case: execution + all metric scores."""

    test_case_id: str
    execution: ExecutionResult
    metric_results: list[MetricResult]

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metric_results)
