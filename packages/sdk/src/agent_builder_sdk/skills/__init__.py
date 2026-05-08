# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Experimental Agent Skills support (Pattern 2: Tool-based skills).

This module vendors the skills implementation from strands-agents/tools PR #379
to enable early integration while the upstream PR is pending merge.

WARNING: This is an experimental feature. The API may change when the
upstream PR merges. Migration path:
1. When PR #379 merges, update strands-agents-tools dependency
2. Change imports from:
   `from agent_builder_sdk.skills import skills, get_skills_prompt`
   to:
   `from strands_tools import skills`
3. Remove this experimental module

Usage:
    # Enable via environment variable
    os.environ["ENABLE_EXPERIMENTAL_SKILLS"] = "true"
    os.environ["STRANDS_SKILLS_DIR"] = "./my_skills"

    # Or use directly
    from agent_builder_sdk.skills import skills, get_skills_prompt

    # Add skills tool to your agent
    agent = create_default_async_orchestrator_with_subagent(
        system_prompt=base_prompt + get_skills_prompt("./my_skills"),
        custom_tools=[skills],
    )
"""

import logging
import warnings

from agent_builder_sdk.skills.skills_prompt import get_skills_prompt
from agent_builder_sdk.skills.skills_tool import skills

# Emit warning on import to notify users this is experimental
warnings.warn(
    "This vendored skills module is deprecated. Use strands.vended_plugins.skills.AgentSkills (strands-agents>=1.30.0) instead. See agent_factory.py for usage example.",
    category=FutureWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)
logger.info("Loading experimental skills module (vendored from strands-agents/tools PR #379)")

__all__ = ["skills", "get_skills_prompt"]
