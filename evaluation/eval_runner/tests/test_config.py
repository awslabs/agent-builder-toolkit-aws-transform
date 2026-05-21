# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for EvalConfig and EvolutionConfig."""

from pathlib import Path

import pytest


class TestEvalConfig:
    def test_defaults(self):
        from eval_runner.config import EvalConfig

        config = EvalConfig()
        assert config.test_dir == Path(".")
        assert config.agent_class is None
        assert config.metrics == ["assertion_pass_rate"]
        assert config.max_workers == 1
        assert config.model_id == "us.anthropic.claude-sonnet-4-20250514-v1:0"
        assert config.output_path == Path("results.json")

    def test_custom_values(self):
        from eval_runner.config import EvalConfig

        config = EvalConfig(
            test_dir=Path("/tmp/tests"),
            agent_class="my_module:MyAgent",
            metrics=["assertion_pass_rate", "tool_usage"],
            max_workers=4,
        )
        assert config.test_dir == Path("/tmp/tests")
        assert config.agent_class == "my_module:MyAgent"
        assert config.max_workers == 4

    def test_from_yaml(self, tmp_path):
        from eval_runner.config import EvalConfig

        yaml_content = """
test_dir: ./test_samples
agent_class: my_agent:Agent
metrics:
  - assertion_pass_rate
  - tool_usage
max_workers: 2
"""
        yaml_file = tmp_path / "eval.yaml"
        yaml_file.write_text(yaml_content)
        config = EvalConfig.from_yaml(yaml_file)
        assert config.agent_class == "my_agent:Agent"
        assert config.max_workers == 2
        assert config.metrics == ["assertion_pass_rate", "tool_usage"]

    def test_from_yaml_empty_file(self, tmp_path):
        from eval_runner.config import EvalConfig

        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        config = EvalConfig.from_yaml(yaml_file)
        assert config.test_dir == Path(".")
        assert config.agent_class is None
        assert config.max_workers == 1


class TestEvolutionConfig:
    def test_defaults(self):
        from eval_runner.config import EvolutionConfig

        config = EvolutionConfig()
        assert config.target == "prompt"
        assert config.max_iterations == 5
        assert config.target_score == 9.0
        assert config.require_approval is True
        assert config.batch_size == 3

    def test_inherits_eval_fields(self):
        from eval_runner.config import EvolutionConfig

        config = EvolutionConfig(
            test_dir=Path("/tmp/tests"),
            max_workers=4,
            target="code",
            max_iterations=10,
        )
        assert config.test_dir == Path("/tmp/tests")
        assert config.max_workers == 4
        assert config.target == "code"

    def test_from_yaml(self, tmp_path):
        from eval_runner.config import EvolutionConfig

        yaml_content = """
test_dir: ./tests
agent_class: my:Agent
target: code
max_iterations: 10
require_approval: false
batch_size: 5
"""
        yaml_file = tmp_path / "evolve.yaml"
        yaml_file.write_text(yaml_content)
        config = EvolutionConfig.from_yaml(yaml_file)
        assert config.target == "code"
        assert config.max_iterations == 10
        assert config.require_approval is False
        assert config.batch_size == 5
