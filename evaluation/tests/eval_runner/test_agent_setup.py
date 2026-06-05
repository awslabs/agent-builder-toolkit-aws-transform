# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for install_agents — specifically the __POWER_DIR__ prompt-resolution
pass, which must not crash on or mutate unrelated agents that happen to share
the install directory (~/.kiro/agents/).
"""

from __future__ import annotations

import json
from pathlib import Path

from eval_runner.config import ExecutionConfig
from eval_runner.execution.agent_setup import install_agents


def _make_agent_dir(tmp_path: Path) -> Path:
    """Minimal agent-under-test dir: AGENT.md + mcp.json."""
    agent_dir = tmp_path / "agent_under_test"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text("# Test agent\n")
    (agent_dir / "mcp.json").write_text(json.dumps({"mcpServers": {}}))
    return agent_dir


def _config(agent_dir: Path) -> ExecutionConfig:
    return ExecutionConfig(agent_name="agent-under-test", agent_dir=agent_dir)


class TestInstallAgentsPromptResolution:
    """The prompt-resolution pass globs the install dir for *.json files."""

    def test_sibling_agent_with_null_prompt_does_not_crash(self, tmp_path: Path) -> None:
        """A pre-existing agent JSON with `"prompt": null` (common for Kiro's
        own default.json/global.json) must not crash the install. Regression for
        `TypeError: argument of type 'NoneType' is not a container`."""
        agents_dir = tmp_path / "kiro_agents"
        agents_dir.mkdir()
        # Simulate a user's pre-existing personal agent with an explicit null prompt.
        sibling = agents_dir / "global.json"
        sibling.write_text(json.dumps({"name": "global", "prompt": None}))

        # Should complete without raising.
        installed = install_agents(_config(_make_agent_dir(tmp_path)), agents_dir=agents_dir)

        assert installed  # at least the agent-under-test was installed

    def test_sibling_agents_are_not_mutated(self, tmp_path: Path) -> None:
        """The install must only touch agents it installed, never a user's own."""
        agents_dir = tmp_path / "kiro_agents"
        agents_dir.mkdir()
        sibling = agents_dir / "my-personal-agent.json"
        original = {"name": "mine", "prompt": "default-agent-system-prompt.md keep me"}
        sibling.write_text(json.dumps(original))

        install_agents(_config(_make_agent_dir(tmp_path)), agents_dir=agents_dir)

        # The sibling references a prompt filename, but it is NOT one we installed,
        # so it must be left byte-for-byte unchanged.
        assert json.loads(sibling.read_text()) == original

    def test_installed_agent_prompt_is_resolved(self, tmp_path: Path) -> None:
        """The positive path: the agent-under-test starts with a prompt pointing at
        the bundled default-agent-system-prompt.md (which contains __POWER_DIR__),
        and the resolution pass must rewrite it to the resolved file:// copy in
        agents_dir. Guards against the scoping fix accidentally skipping our own
        agents."""
        agents_dir = tmp_path / "kiro_agents"
        agents_dir.mkdir()

        install_agents(_config(_make_agent_dir(tmp_path)), agents_dir=agents_dir)

        agent_json = json.loads((agents_dir / "agent-under-test.json").read_text())
        prompt = agent_json["prompt"]
        # Rewritten to point at the resolved copy inside agents_dir, not the bundle.
        assert prompt == f"file://{agents_dir / 'default-agent-system-prompt.md'}"
        assert (agents_dir / "default-agent-system-prompt.md").exists()
