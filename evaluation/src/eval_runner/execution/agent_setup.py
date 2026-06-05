# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent setup: auto-generates and installs eval agents to .kiro/agents/.

The agent-under-test config is auto-generated from the agent's ``mcp.json``
and/or skill plugin's ``.mcp.json``. Scenario and judge agent configs are
shipped by the framework.

Placeholders resolved at install time:
    __BUILD_DIR__: The framework's deployed build directory.
    __POWER_DIR__: The agent directory containing AGENT.md and steering/.

Usage::

    from eval_runner.execution.agent_setup import install_agents
    from eval_runner.config import ExecutionConfig

    config = ExecutionConfig(agent_name="my-agent", agent_dir=Path("/path/to/agent"))
    install_agents(config)
"""

from __future__ import annotations

import json
import logging
import os
import fcntl
import time
from pathlib import Path
from typing import Any

from ..config import ExecutionConfig

logger = logging.getLogger(__name__)

FRAMEWORK_AGENTS = [
    "agent-eval-scenario.json",
    "agent-eval-judge.json",
]


def _find_build_dir() -> Path:
    """Return the bundled data directory (holds ``agents/`` + ``skills/``).

    The agent JSONs and system-prompt markdown are packaged under
    ``eval_runner/execution/data/`` relative to this module, so the location is
    deterministic — no upward directory search needed.
    """
    data_dir = Path(__file__).resolve().parent / "data"
    if not (data_dir / "agents").is_dir():
        raise FileNotFoundError(
            f"Bundled agents directory not found at {data_dir / 'agents'}. "
            "The eval_runner.execution package data is missing or misinstalled."
        )
    return data_dir


def _find_global_mcp_servers() -> list[str]:
    """Discover MCP server names from the global kiro settings."""
    search_paths = [
        Path.home() / ".kiro" / "settings" / "mcp.json",
        Path.home() / ".kiro" / "mcp.json",
    ]
    for mcp_path in search_paths:
        if mcp_path.exists():
            try:
                data = json.loads(mcp_path.read_text())
                servers = data.get("mcpServers", {})
                return list(servers.keys())
            except (json.JSONDecodeError, KeyError):
                continue
    return []


def _disable_global_mcp_servers(agent_data: dict) -> dict:
    """Disable all global MCP servers not explicitly configured in the agent."""
    global_servers = _find_global_mcp_servers()
    agent_servers = agent_data.get("mcpServers") or {}

    for server_name in global_servers:
        if server_name not in agent_servers:
            agent_servers[server_name] = {"command": "echo", "disabled": True}

    if agent_servers:
        agent_data["mcpServers"] = agent_servers

    return agent_data


def _resolve_mcp_commands(agent_data: dict, required_env_vars: list[str] | None = None) -> dict:
    """Resolve MCP server commands to full paths and propagate env vars."""
    import shutil
    import sysconfig

    python_lib_dir = sysconfig.get_config_var("LIBDIR") or ""
    ld_library_path = python_lib_dir if os.path.isdir(python_lib_dir) else ""

    for server_name, server_config in agent_data.get("mcpServers", {}).items():
        command = server_config.get("command")
        if not command or server_config.get("disabled"):
            continue
        if "/" not in command:
            full_path = shutil.which(command)
            if full_path:
                server_config["command"] = full_path
        env = server_config.get("env") or {}
        if ld_library_path and "LD_LIBRARY_PATH" not in env:
            env["LD_LIBRARY_PATH"] = ld_library_path
        for var in required_env_vars or []:
            val = os.environ.get(var)
            if val and var not in env:
                env[var] = val
        if "FASTMCP_LOG_LEVEL" not in env:
            env["FASTMCP_LOG_LEVEL"] = "ERROR"
        if env:
            server_config["env"] = env

    return agent_data


def _patch_mcp_for_mock(agent_data: dict, mcp_server_name: str, mock_mcp_context: Any) -> dict:
    """Replace the named MCP server with the mock MCP server."""
    from .mocking import MockManager

    mcp_servers = agent_data.get("mcpServers", {})
    if mcp_server_name not in mcp_servers:
        return agent_data

    mock_server_script = str(MockManager.mock_mcp_server_path())
    mcp_servers[mcp_server_name] = {
        "type": "stdio",
        "command": "python3",
        "args": [mock_server_script],
        "env": {
            "MOCK_MCP_RESPONSES": str(mock_mcp_context.mcp_responses_file),
        },
        "timeout": 60000,
    }
    agent_data["mcpServers"] = mcp_servers
    return agent_data


def _collect_mcp_servers(config: ExecutionConfig) -> dict[str, Any]:
    """Collect MCP server definitions from agent_dir and skill_dirs."""
    mcp_servers: dict[str, Any] = {}

    if config.agent_dir:
        mcp_json_path = config.agent_dir / "mcp.json"
        if mcp_json_path.exists():
            data = json.loads(mcp_json_path.read_text())
            mcp_servers.update(data.get("mcpServers", {}))

    for skill_dir in config.skill_dirs:
        mcp_json_path = skill_dir / ".mcp.json"
        if mcp_json_path.exists():
            data = json.loads(mcp_json_path.read_text())
            for name in data.get("mcpServers", {}):
                if name in mcp_servers:
                    logger.warning(
                        f"MCP server '{name}' in {mcp_json_path} overwrites "
                        f"a previously defined server with the same name."
                    )
            mcp_servers.update(data.get("mcpServers", {}))

    return mcp_servers


def _generate_agent_config(config: ExecutionConfig, build_dir: Path) -> dict:
    """Auto-generate the agent-under-test config.

    Reads MCP server definitions from ``agent_dir/mcp.json`` and/or
    ``skill_dirs/.mcp.json``. Composes the agent based on what's set:
    - agent_dir → system prompt for progressive AGENT.md reading
    - skill_dirs → skill:// resources for auto-loaded SKILL.md
    - Both → agent system prompt + skill resources together
    """
    mcp_servers = _collect_mcp_servers(config)

    tools = ["read", "write", "shell"]
    allowed_tools = ["read"]
    clean_servers: dict[str, Any] = {}

    for server_name, server_config in mcp_servers.items():
        if server_config.get("disabled"):
            continue
        tools.append(f"@{server_name}")
        for tool in server_config.get("autoApprove", []):
            allowed_tools.append(f"@{server_name}/{tool}")
        clean_servers[server_name] = {
            k: v
            for k, v in server_config.items()
            if k not in ("autoApprove", "disabledTools", "disabled")
        }

    if config.system_prompt_path:
        prompt = f"file://{config.system_prompt_path}"
    elif config.agent_dir:
        prompt = f"file://{build_dir}/agents/default-agent-system-prompt.md"
    else:
        prompt = f"file://{build_dir}/agents/default-skill-system-prompt.md"

    resources: list[str] = []
    for skill_dir in config.skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            resources.append(f"skill://{skill_md}")
        else:
            found = False
            for nested in (skill_dir / "skills").glob("*/SKILL.md"):
                resources.append(f"skill://{nested}")
                found = True
                break
            if not found:
                logger.warning(
                    f"No SKILL.md found in {skill_dir} or {skill_dir / 'skills/'}. "
                    f"Agent will have no skill resources loaded."
                )

    return {
        "name": config.agent_name,
        "description": f"{config.report_title} agent under test",
        "model": config.agent_model,
        "prompt": prompt,
        "includeMcpJson": False,
        "tools": tools,
        "allowedTools": allowed_tools,
        "toolsSettings": {"shell": {"allowedCommands": ["*"]}},
        "resources": resources,
        "mcpServers": clean_servers,
    }


def install_agents(
    config: ExecutionConfig,
    agents_dir: Path | None = None,
    build_dir: Path | None = None,
    mock_mcp_context: Any | None = None,
) -> list[Path]:
    """Install eval agent configurations to .kiro/agents/.

    Auto-generates the agent-under-test config from MCP server definitions.
    Scenario and judge agents are installed from framework templates.

    Thread-safe: Uses file locking to prevent race conditions when called
    concurrently by parallel test execution.
    """
    for var in config.required_env_vars:
        if not os.environ.get(var):
            raise RuntimeError(f"{var} environment variable is required.")

    if agents_dir is None:
        agents_dir = Path.home() / ".kiro" / "agents"
    if build_dir is None:
        build_dir = _find_build_dir()

    agents_dir.mkdir(parents=True, exist_ok=True)

    # Acquire lock to prevent concurrent installations (critical for parallel test execution)
    lock_file = agents_dir / ".install.lock"
    lock_fd = None
    max_retries = 30  # Wait up to 30 seconds for lock
    retry_count = 0

    try:
        # Try to acquire exclusive lock
        lock_fd = open(lock_file, 'w')
        while retry_count < max_retries:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.debug(f"Acquired installation lock: {lock_file}")
                break
            except BlockingIOError:
                # Lock held by another process - wait and retry
                if retry_count == 0:
                    logger.info(f"Waiting for agent installation lock (another test is installing)...")
                retry_count += 1
                time.sleep(1)
                if retry_count >= max_retries:
                    raise RuntimeError(f"Timeout waiting for installation lock after {max_retries}s")

        installed = []

        # --- 1. Auto-generate and install the agent under test ---
        agent_data = _generate_agent_config(config, build_dir)
        agent_data = _disable_global_mcp_servers(agent_data)
        agent_data = _resolve_mcp_commands(agent_data, config.required_env_vars)

        mcp_server_name = config.mcp_server_name
        if (
            mock_mcp_context
            and mcp_server_name
            and getattr(mock_mcp_context, "mcp_responses_file", None)
        ):
            agent_data = _patch_mcp_for_mock(agent_data, mcp_server_name, mock_mcp_context)

        agent_dest = agents_dir / f"{config.agent_name}.json"
        agent_dest.write_text(json.dumps(agent_data, indent=2))
        installed.append(agent_dest)
        logger.info(f"Installed: {agent_dest}")

        # --- 2. Install framework agents (scenario + judge) ---
        framework_agents_dir = build_dir / "agents"
        content_dir = str(config.agent_dir) if config.agent_dir else str(config.skill_dirs[0])

        for config_name in FRAMEWORK_AGENTS:
            template_path = framework_agents_dir / config_name
            if not template_path.exists():
                logger.warning(f"Framework agent template not found: {template_path}")
                continue

            content = template_path.read_text()
            content = content.replace("__BUILD_DIR__", str(build_dir))
            content = content.replace("__POWER_DIR__", content_dir)

            framework_agent_data = json.loads(content)
            framework_agent_data = _disable_global_mcp_servers(framework_agent_data)

            content = json.dumps(framework_agent_data, indent=2)
            dest_path = agents_dir / config_name
            dest_path.write_text(content)
            installed.append(dest_path)
            logger.info(f"Installed: {dest_path}")

        # --- 3. Resolve __POWER_DIR__ in system prompt files ---
        # __POWER_DIR__ is a scoped template placeholder (a sentinel we own and
        # control), not a general-purpose substitution mechanism. It is replaced
        # verbatim with the resolved directory path in our own prompt templates.
        # Keep this contract narrow: do not widen it to interpolate
        # user-supplied tokens or paths, which would reintroduce the markdown /
        # path-escaping concerns this sentinel deliberately sidesteps.
        for md_file in framework_agents_dir.glob("*.md"):
            md_content = md_file.read_text()
            if "__POWER_DIR__" in md_content:
                md_content = md_content.replace("__POWER_DIR__", content_dir)
                resolved_path = agents_dir / md_file.name
                resolved_path.write_text(md_content)
                logger.info(f"Resolved __POWER_DIR__ → {resolved_path}")
                # Update prompt paths only on the agents this run installed —
                # never the user's other agents that share agents_dir
                # (e.g. Kiro's default.json/global.json, which may carry a null
                # prompt and aren't ours to rewrite).
                for agent_file in installed:
                    try:
                        agent_json = json.loads(agent_file.read_text())
                    except json.JSONDecodeError:
                        continue
                    current_prompt = agent_json.get("prompt") or ""
                    if md_file.name in current_prompt:
                        agent_json["prompt"] = f"file://{resolved_path}"
                        agent_file.write_text(json.dumps(agent_json, indent=2))

            if config.system_prompt_path and config.system_prompt_path.exists():
                prompt_content = config.system_prompt_path.read_text()
                if "__POWER_DIR__" in prompt_content and config.agent_dir:
                    prompt_content = prompt_content.replace("__POWER_DIR__", str(config.agent_dir))
                    resolved_path = agents_dir / config.system_prompt_path.name
                    resolved_path.write_text(prompt_content)
                    logger.info(f"Resolved __POWER_DIR__ → {resolved_path}")
                    # Update agent-under-test prompt path
                    agent_json = json.loads(agent_dest.read_text())
                    agent_json["prompt"] = f"file://{resolved_path}"
                    agent_dest.write_text(json.dumps(agent_json, indent=2))

        return installed

    finally:
        # Release lock
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                logger.debug(f"Released installation lock: {lock_file}")
            except Exception as e:
                logger.warning(f"Failed to release installation lock: {e}")
            finally:
                # Always close the handle, even if unlocking raised, so the
                # file descriptor never leaks.
                lock_fd.close()
