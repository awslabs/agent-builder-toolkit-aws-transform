# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Skills prompt generation helper.

Generates system prompt content to inform the agent about available skills.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from agent_builder_sdk.skills.skills_tool import (
    DEFAULT_SKILLS_DIR,
    ENV_KEY_STRANDS_SKILLS_DIR,
    SKILL_MANIFEST,
    _parse_skill_manifest,
    _validate_skill_name,
)

logger = logging.getLogger(__name__)


def get_skills_prompt(skills_dir: Optional[str] = None) -> str:
    """Generate a system prompt section describing available skills.

    This function scans the skills directory and generates an XML-formatted
    prompt section that can be appended to an agent's system prompt to inform
    it about available skills.

    Args:
        skills_dir: Path to the skills directory. If None, uses STRANDS_SKILLS_DIR
                   environment variable or defaults to ./skills

    Returns:
        A formatted string containing the skills prompt section. Returns empty
        string if no skills are found or the directory doesn't exist.

    Example output:
        ## Available Skills
        You have access to specialized skills. Use `skills(action='list')` to see details,
        or `skills(action='use', skill_name='<name>')` to load one.

        <available_skills>
          <skill>
            <name>web-research</name>
            <description>Searches web, synthesizes findings into reports.</description>
          </skill>
        </available_skills>

    Usage:
        from agent_builder_sdk.skills import get_skills_prompt

        system_prompt = base_prompt + get_skills_prompt("./my_skills")
    """
    # Determine skills directory
    if skills_dir:
        dir_path = Path(skills_dir)
    else:
        dir_path = Path(os.environ.get(ENV_KEY_STRANDS_SKILLS_DIR, DEFAULT_SKILLS_DIR))

    if not dir_path.exists():
        logger.debug(f"Skills directory does not exist: {dir_path}")
        return ""

    # Collect skills
    skills = []
    for item in dir_path.iterdir():
        if item.is_dir() and _validate_skill_name(item.name):
            manifest_path = item / SKILL_MANIFEST
            if manifest_path.exists():
                manifest = _parse_skill_manifest(manifest_path)
                skills.append(
                    {
                        "name": manifest.get("name") or item.name,
                        "description": manifest.get("description", "No description available"),
                    }
                )

    if not skills:
        logger.debug(f"No skills found in: {dir_path}")
        return ""

    # Sort skills by name
    skills = sorted(skills, key=lambda x: x["name"])

    # Build XML block
    xml_lines = ["<available_skills>"]
    for skill in skills:
        # Escape XML special characters in description
        description = (
            skill["description"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        xml_lines.append("  <skill>")
        xml_lines.append(f"    <name>{skill['name']}</name>")
        xml_lines.append(f"    <description>{description}</description>")
        xml_lines.append("  </skill>")
    xml_lines.append("</available_skills>")

    xml_block = "\n".join(xml_lines)

    # Build full prompt section
    prompt = f"""## Available Skills
You have access to specialized skills. Use `skills(action='list')` to see details,
or `skills(action='use', skill_name='<name>')` to load one.

{xml_block}"""

    return prompt
