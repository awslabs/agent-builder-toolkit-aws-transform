# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for EvalAgentInterface and EvolvableAgent Protocols."""

from pathlib import Path


class TestEvalAgentInterface:
    def test_structural_typing_satisfied(self):
        from eval_runner.agent_interface import EvalAgentInterface
        from eval_runner.models import ExecutionResult
        from eval_runner.test_case import TestCase

        class FakeAgent:
            def execute(self, test_case: TestCase) -> ExecutionResult:
                return ExecutionResult(
                    transcript=f"Processed: {test_case.user_message}",
                    output="done",
                    duration_ms=100,
                )

        agent = FakeAgent()
        assert isinstance(agent, EvalAgentInterface)
        tc = TestCase(id="t1", name="test", user_message="hello")
        result = agent.execute(tc)
        assert result.transcript == "Processed: hello"
        assert result.duration_ms == 100

    def test_missing_method_not_satisfied(self):
        from eval_runner.agent_interface import EvalAgentInterface

        class NotAnAgent:
            pass

        assert not isinstance(NotAnAgent(), EvalAgentInterface)


class TestEvolvableAgent:
    def test_requires_both_methods(self):
        from eval_runner.agent_interface import EvolvableAgent
        from eval_runner.models import ExecutionResult
        from eval_runner.test_case import TestCase

        class IncompleteAgent:
            def execute(self, test_case: TestCase) -> ExecutionResult:
                return ExecutionResult(transcript="t", output="o")

        assert not isinstance(IncompleteAgent(), EvolvableAgent)

    def test_complete_implementation(self):
        from eval_runner.agent_interface import EvolvableAgent
        from eval_runner.models import ExecutionResult
        from eval_runner.test_case import TestCase

        class FullAgent:
            def execute(self, test_case: TestCase) -> ExecutionResult:
                return ExecutionResult(transcript="t", output="o")

            def get_source_dir(self) -> Path:
                return Path("/tmp/agent-source")

        agent = FullAgent()
        assert isinstance(agent, EvolvableAgent)
        assert agent.get_source_dir() == Path("/tmp/agent-source")
