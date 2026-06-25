# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""MetricRegistry — built-in metric lookup by name (D5)."""

from __future__ import annotations

from typing import Callable, Type

from eval_runner.metrics.interface import MetricInterface


class MetricRegistry:
    """Registry that resolves metric names to instances.

    Two registration styles are supported:

    - :meth:`register` — a zero-arg metric *class* (e.g. ``assertion_pass_rate``),
      constructed fresh on each :meth:`get`.
    - :meth:`register_factory` — a zero-arg *factory* (or pre-built instance via a
      ``lambda``) for metrics that need configuration at wiring time, such as
      ``llm_judge`` which must be bound to a framework orchestrator. This keeps the
      registry's name→instance contract while allowing dependency injection.
    """

    def __init__(self) -> None:
        self._classes: dict[str, Type[MetricInterface]] = {}
        self._factories: dict[str, Callable[[], MetricInterface]] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        from eval_runner.metrics.assertion_pass_rate import AssertionPassRateMetric
        from eval_runner.metrics.completeness import CompletenessMetric
        from eval_runner.metrics.cost_budget import CostBudgetMetric
        from eval_runner.metrics.error_handling import ErrorHandlingMetric
        from eval_runner.metrics.latency import LatencyMetric
        from eval_runner.metrics.tool_usage import ToolUsageMetric

        self.register("assertion_pass_rate", AssertionPassRateMetric)
        # Generic, deterministic, zero-arg metrics (no Bedrock). The first two
        # abstain (score 10.0/pass) until a test case opts in via metadata, so
        # they are safe to resolve by name without penalizing existing tests;
        # error_handling is always active (a clean transcript is universal).
        self.register("tool_usage", ToolUsageMetric)
        self.register("error_handling", ErrorHandlingMetric)
        self.register("completeness", CompletenessMetric)
        # Resource-budget metrics; abstain (10.0/pass) until a test opts in via
        # metadata (max_latency_ms / max_credits), same as the generic ones.
        self.register("latency", LatencyMetric)
        self.register("cost_budget", CostBudgetMetric)

    def register(self, name: str, cls: Type[MetricInterface]) -> None:
        """Register a zero-arg metric class, constructed fresh on each get()."""
        self._classes[name] = cls
        self._factories.pop(name, None)

    def register_factory(self, name: str, factory: Callable[[], MetricInterface]) -> None:
        """Register a zero-arg factory for a metric that needs configuration.

        Used for ``llm_judge``: ``registry.register_factory("llm_judge", lambda:
        LLMJudgeMetric(execution_config=cfg))``.
        """
        self._factories[name] = factory
        self._classes.pop(name, None)

    def get(self, name: str) -> MetricInterface:
        if name in self._factories:
            return self._factories[name]()
        if name in self._classes:
            return self._classes[name]()
        raise KeyError(f"Metric '{name}' not found. Available: {self.list()}")

    def list(self) -> list[str]:
        return list(self._classes.keys()) + list(self._factories.keys())

    def resolve(self, names: list[str]) -> list[MetricInterface]:
        return [self.get(name) for name in names]
