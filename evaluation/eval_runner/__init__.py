# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""eval_runner — evaluation and evolution framework for Transform agents."""

from eval_runner.agent_interface import EvalAgentInterface, EvolvableAgent
from eval_runner.config import EvalConfig, EvolutionConfig, ExecutionConfig
from eval_runner.engine import EvaluationEngine
from eval_runner.metrics import MetricInterface, MetricRegistry
from eval_runner.models import EvaluationResult, ExecutionResult, MetricResult
from eval_runner.test_case import TestCase, TestCaseLoader

__all__ = [
    "ACPAgent",
    "EvalAgentInterface",
    "EvalConfig",
    "EvaluationEngine",
    "EvaluationResult",
    "EvolutionConfig",
    "EvolvableAgent",
    "ExecutionConfig",
    "ExecutionResult",
    "MetricInterface",
    "MetricRegistry",
    "MetricResult",
    "TestCase",
    "TestCaseLoader",
]


def __getattr__(name: str):
    """Lazily expose the ACP execution backend.

    ``ACPAgent`` imports the ACP engine subpackage (:mod:`eval_runner.execution`);
    importing it lazily keeps eval_runner's core (models, metrics, engine) cheap
    to import when the ACP path isn't used.
    """
    if name == "ACPAgent":
        from eval_runner.agents.acp_agent import ACPAgent

        return ACPAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
