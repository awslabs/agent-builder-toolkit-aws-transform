# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for EvalAgentInterface and EvolvableAgent ABCs."""

from pathlib import Path

import pytest


class TestEvalAgentInterface:
    def test_cannot_instantiate_directly(self):
        from eval_runner.agent_interface import EvalAgentInterface

        with pytest.raises(TypeError):
            EvalAgentInterface()

    def test_concrete_implementation(self):
        from eval_runner.agent_interface import EvalAgentInterface
        from eval_runner.models import ExecutionResult
        from eval_runner.test_case import TestCase

        class FakeAgent(EvalAgentInterface):
            def execute(self, test_case: TestCase) -> ExecutionResult:
                return ExecutionResult(
                    transcript=f"Processed: {test_case.user_message}",
                    output="done",
                    duration_ms=100,
                )

        agent = FakeAgent()
        tc = TestCase(id="t1", name="test", user_message="hello")
        result = agent.execute(tc)
        assert result.transcript == "Processed: hello"
        assert result.duration_ms == 100


class TestEvolvableAgent:
    def test_cannot_instantiate_without_get_source_dir(self):
        from eval_runner.agent_interface import EvolvableAgent
        from eval_runner.models import ExecutionResult
        from eval_runner.test_case import TestCase

        class IncompleteAgent(EvolvableAgent):
            def execute(self, test_case: TestCase) -> ExecutionResult:
                return ExecutionResult(transcript="t", output="o")

        with pytest.raises(TypeError):
            IncompleteAgent()

    def test_complete_implementation(self):
        from eval_runner.agent_interface import EvolvableAgent
        from eval_runner.models import ExecutionResult
        from eval_runner.test_case import TestCase

        class FullAgent(EvolvableAgent):
            def execute(self, test_case: TestCase) -> ExecutionResult:
                return ExecutionResult(transcript="t", output="o")

            def get_source_dir(self) -> Path:
                return Path("/tmp/agent-source")

        agent = FullAgent()
        assert agent.get_source_dir() == Path("/tmp/agent-source")
