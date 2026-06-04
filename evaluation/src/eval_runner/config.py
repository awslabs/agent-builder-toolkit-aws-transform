# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclasses for evaluation and evolution.

Two configs live here, separated by concern:

- :class:`ExecutionConfig` — *how to drive the agent/skill under test over ACP*
  (agent_dir, skill_dirs, acp_binary, judge/scenario agents, …). Consumed by
  :mod:`eval_runner.execution` (the ACP engine).
- :class:`EvalConfig` — *how to score and orchestrate* (test_dir, metrics,
  max_workers). Carries an optional :class:`ExecutionConfig` under
  ``execution_config``.

(``ExecutionConfig`` was previously the framework's separate ``EvalConfig``;
renamed on consolidation so the two no longer collide on one name.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass
class ExecutionConfig:
    """Configuration for driving an agent or skill under test over ACP.

    At least one of ``agent_dir`` or ``skill_dirs`` must be set. Supports three
    modes:

    - ``agent_dir`` only: evaluates an agent (AGENT.md + steering/).
    - ``skill_dirs`` only: evaluates skill plugin(s) (SKILL.md + references/).
    - Both: evaluates an agent with additional skills loaded.

    Attributes:
        agent_name: Name of the agent-cli agent under test.
        agent_dir: Path to an agent (AGENT.md + steering/ + mcp.json).
        skill_dirs: Paths to skill plugins (SKILL.md + references/ + .mcp.json).
        agent_model: Model for the agent under test.
        system_prompt_path: Custom system prompt. Auto-selected if None.
        scenario_agent: Name of the simulated-human agent.
        judge_agent: Name of the LLM grading agent.
        evals_dir: Directory containing eval scenario JSONs.
        cleanup_prompt: Prompt sent after each scenario to clean up resources.
        cli_binary_name: CLI binary name for mock scripts.
        acp_binary: ACP driver binary that runs the agents ("agent-cli", "kiro-cli").
        report_title: Title for the HTML eval dashboard.
        required_env_vars: Env vars that must be set before running.
        resource_logger: Callback ``(tool_name, raw_output)`` for each tool event.
    """

    # --- Required ---
    agent_name: str

    # --- Content sources (at least one required) ---
    agent_dir: Path | None = None
    skill_dirs: list[Path] = field(default_factory=list)

    # --- Agent options ---
    agent_model: str = "claude-opus-4.6"
    system_prompt_path: Path | None = None

    # --- Agent names ---
    scenario_agent: str = "agent-eval-scenario"
    judge_agent: str = "agent-eval-judge"

    # --- Optional ---
    evals_dir: Path | None = None
    cleanup_prompt: str | None = None
    cli_binary_name: str = "cli"
    # ACP driver binary that runs the agents (e.g. "agent-cli", "kiro-cli").
    acp_binary: str = "agent-cli"
    report_title: str = "Eval"
    required_env_vars: list[str] = field(default_factory=list)
    filter_target: str | None = None

    # --- Callbacks ---
    resource_logger: Callable[[str, Any], None] | None = None

    # --- Auto-detected ---
    mcp_server_name: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        has_agent = self.agent_dir is not None and str(self.agent_dir).strip()
        if not has_agent and not self.skill_dirs:
            raise ValueError("At least one of agent_dir or skill_dirs is required.")
        if not has_agent:
            self.agent_dir = None
        mcp_paths: list[Path] = []
        if self.agent_dir:
            mcp_paths.append(self.agent_dir / "mcp.json")
        for sd in self.skill_dirs:
            mcp_paths.append(sd / ".mcp.json")
        for mcp_json in mcp_paths:
            if mcp_json.exists():
                data = json.loads(mcp_json.read_text())
                for name, cfg in data.get("mcpServers", {}).items():
                    if not cfg.get("disabled"):
                        self.mcp_server_name = name
                        return


@dataclass
class EvalConfig:
    """Configuration for running evaluations.

    The scoring/orchestration fields (``test_dir``, ``metrics``, ``max_workers``,
    ``output_path``) drive :class:`eval_runner.engine.EvaluationEngine`. The
    ``execution_config`` field carries an :class:`ExecutionConfig` describing
    *which agent/skill to run and how to drive it over ACP*. It is optional so
    eval_runner's deterministic, execution-free scoring path keeps working with
    zero configuration.
    """

    test_dir: Path = field(default_factory=lambda: Path("."))
    agent_class: str | None = None
    metrics: list[str] = field(default_factory=lambda: ["assertion_pass_rate"])
    max_workers: int = 1
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    output_path: Path = field(default_factory=lambda: Path("results.json"))
    # ACP execution settings (set when using ACPAgent). None for the
    # execution-free scoring path.
    execution_config: ExecutionConfig | None = None

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
            execution_config=cls._execution_config_from_dict(data.get("agent")),
        )

    @staticmethod
    def _execution_config_from_dict(agent: dict[str, Any] | None) -> ExecutionConfig | None:
        """Build an :class:`ExecutionConfig` from an ``agent:`` YAML block.

        Returns None when no ``agent:`` block is present (execution-free path).
        """
        if not agent:
            return None
        kwargs: dict[str, Any] = dict(agent)
        for key in ("agent_dir", "system_prompt_path", "evals_dir"):
            if kwargs.get(key):
                kwargs[key] = Path(kwargs[key])
        if kwargs.get("skill_dirs"):
            kwargs["skill_dirs"] = [Path(p) for p in kwargs["skill_dirs"]]
        return ExecutionConfig(**kwargs)


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
