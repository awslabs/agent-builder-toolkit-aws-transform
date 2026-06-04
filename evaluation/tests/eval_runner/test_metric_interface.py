# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for MetricInterface Protocol and MetricRegistry (tasks 2.1, 2.2)."""

import pytest


class TestMetricInterface:
    def test_structural_typing_satisfied(self):
        from eval_runner.metrics import MetricInterface
        from eval_runner.models import ExecutionResult, MetricResult
        from eval_runner.test_case import TestCase

        class AlwaysPassMetric:
            @property
            def name(self) -> str:
                return "always_pass"

            def evaluate(
                self, execution: ExecutionResult, test_case: TestCase
            ) -> MetricResult:
                return MetricResult(
                    metric_name=self.name, score=10.0, passed=True
                )

        metric = AlwaysPassMetric()
        assert isinstance(metric, MetricInterface)
        assert metric.name == "always_pass"

        tc = TestCase(id="t1", name="test", user_message="hello")
        execution = ExecutionResult(transcript="t", output="o")
        result = metric.evaluate(execution, tc)
        assert result.score == 10.0
        assert result.passed is True

    def test_missing_method_not_satisfied(self):
        from eval_runner.metrics import MetricInterface

        class NotAMetric:
            pass

        assert not isinstance(NotAMetric(), MetricInterface)

    def test_evaluate_receives_correct_types(self):
        from eval_runner.metrics import MetricInterface
        from eval_runner.models import ExecutionResult, MetricResult
        from eval_runner.test_case import TestCase

        class TypeCheckMetric:
            @property
            def name(self) -> str:
                return "type_check"

            def evaluate(
                self, execution: ExecutionResult, test_case: TestCase
            ) -> MetricResult:
                assert isinstance(execution, ExecutionResult)
                assert isinstance(test_case, TestCase)
                return MetricResult(
                    metric_name=self.name, score=5.0, passed=False
                )

        metric = TypeCheckMetric()
        assert isinstance(metric, MetricInterface)
        tc = TestCase(id="t1", name="test", user_message="hello")
        execution = ExecutionResult(transcript="t", output="o")
        result = metric.evaluate(execution, tc)
        assert result.score == 5.0


class TestMetricRegistry:
    def test_register_and_get(self):
        from eval_runner.metrics import MetricInterface, MetricRegistry
        from eval_runner.models import ExecutionResult, MetricResult
        from eval_runner.test_case import TestCase

        class FakeMetric(MetricInterface):
            @property
            def name(self) -> str:
                return "fake"

            def evaluate(
                self, execution: ExecutionResult, test_case: TestCase
            ) -> MetricResult:
                return MetricResult(
                    metric_name=self.name, score=8.0, passed=True
                )

        registry = MetricRegistry()
        registry.register("fake", FakeMetric)
        metric = registry.get("fake")
        assert isinstance(metric, FakeMetric)

    def test_get_unknown_raises(self):
        from eval_runner.metrics import MetricRegistry

        registry = MetricRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_list_registered(self):
        from eval_runner.metrics import MetricInterface, MetricRegistry
        from eval_runner.models import ExecutionResult, MetricResult
        from eval_runner.test_case import TestCase

        class M1(MetricInterface):
            @property
            def name(self) -> str:
                return "m1"

            def evaluate(
                self, execution: ExecutionResult, test_case: TestCase
            ) -> MetricResult:
                return MetricResult(metric_name="m1", score=5.0, passed=False)

        class M2(MetricInterface):
            @property
            def name(self) -> str:
                return "m2"

            def evaluate(
                self, execution: ExecutionResult, test_case: TestCase
            ) -> MetricResult:
                return MetricResult(metric_name="m2", score=5.0, passed=False)

        registry = MetricRegistry()
        registry.register("m1", M1)
        registry.register("m2", M2)
        registered = set(registry.list())
        assert "m1" in registered
        assert "m2" in registered

    def test_has_builtin_assertion_pass_rate(self):
        from eval_runner.metrics import MetricRegistry

        registry = MetricRegistry()
        assert "assertion_pass_rate" in registry.list()

    def test_resolve_from_config(self):
        from eval_runner.config import EvalConfig
        from eval_runner.metrics import MetricRegistry

        config = EvalConfig(metrics=["assertion_pass_rate"])
        registry = MetricRegistry()
        metrics = registry.resolve(config.metrics)
        assert len(metrics) == 1
        assert metrics[0].name == "assertion_pass_rate"
