# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""MetricRegistry — built-in metric lookup by name (D5)."""

from __future__ import annotations

from typing import Type

from eval_runner.metrics.interface import MetricInterface


class MetricRegistry:
    """Registry that resolves metric names to instances."""

    def __init__(self) -> None:
        self._registry: dict[str, Type[MetricInterface]] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        from eval_runner.metrics.assertion_pass_rate import AssertionPassRateMetric

        self.register("assertion_pass_rate", AssertionPassRateMetric)

    def register(self, name: str, cls: Type[MetricInterface]) -> None:
        self._registry[name] = cls

    def get(self, name: str) -> MetricInterface:
        if name not in self._registry:
            raise KeyError(
                f"Metric '{name}' not found. Available: {list(self._registry.keys())}"
            )
        return self._registry[name]()

    def list(self) -> list[str]:
        return list(self._registry.keys())

    def resolve(self, names: list[str]) -> list[MetricInterface]:
        return [self.get(name) for name in names]
