"""
Agent Skills Tool - Vendored from strands-agents/tools PR #379.

This implementation is vendored from the upstream PR to enable early adoption
while the PR is pending merge. Once PR #379 merges, this file should be removed
and imports updated to use the upstream strands_tools.skills module.

Original PR: https://github.com/strands-agents/tools/pull/379
License: Apache 2.0 (same as strands-agents)

EXPERIMENTAL: This feature is experimental and may have breaking changes.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from strands.tools import tool

from agent_builder_sdk.util.decorators import experimental

logger = logging.getLogger(__name__)

# Environment variable for skills directory
ENV_KEY_STRANDS_SKILLS_DIR = "STRANDS_SKILLS_DIR"
DEFAULT_SKILLS_DIR = "./skills"

# Valid skill name pattern (alphanumeric, hyphens, underscores)
SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Skill manifest filename
SKILL_MANIFEST = "SKILL.md"


def _get_skills_dir(skills_dir: Optional[str] = None) -> Path:
    """Get the skills directory path.

    Args:
        skills_dir: Optional explicit skills directory path

    Returns:
        Path to the skills directory
    """
    if skills_dir:
        return Path(skills_dir)
    return Path(os.environ.get(ENV_KEY_STRANDS_SKILLS_DIR, DEFAULT_SKILLS_DIR))


def _validate_skill_name(skill_name: str) -> bool:
    """Validate that a skill name is safe and well-formed.

    Args:
        skill_name: The skill name to validate

    Returns:
        True if the skill name is valid
    """
    if not skill_name:
        return False
    if not SKILL_NAME_PATTERN.match(skill_name):
        return False
    # Prevent path traversal
    if ".." in skill_name or "/" in skill_name or "\\" in skill_name:
        return False
    return True


def _parse_skill_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Parse a skill manifest file (SKILL.md).

    The manifest uses YAML frontmatter format:
    ---
    name: skill-name
    description: A description of the skill
    ---

    # Skill Instructions

    Full instructions here...

    Args:
        manifest_path: Path to the SKILL.md file

    Returns:
        Dictionary with 'name', 'description', and 'instructions' keys
    """
    try:
        content = manifest_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read skill manifest {manifest_path}: {e}")
        return {}

    result: Dict[str, Any] = {
        "name": "",
        "description": "",
        "instructions": "",
    }

    # Check for YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()

            # Parse simple YAML frontmatter (key: value pairs)
            for line in frontmatter.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key == "name":
                        result["name"] = value
                    elif key == "description":
                        result["description"] = value

            result["instructions"] = body
        else:
            # No proper frontmatter, use entire content as instructions
            result["instructions"] = content
    else:
        # No frontmatter, use entire content as instructions
        result["instructions"] = content

    return result


def _list_skills(skills_dir: Path) -> List[Dict[str, str]]:
    """List all available skills in the skills directory.

    Args:
        skills_dir: Path to the skills directory

    Returns:
        List of dictionaries with 'name' and 'description' for each skill
    """
    skills: List[Dict[str, str]] = []

    if not skills_dir.exists():
        logger.warning(f"Skills directory does not exist: {skills_dir}")
        return skills

    for item in skills_dir.iterdir():
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

    return sorted(skills, key=lambda x: x["name"])


def _get_skill_instructions(skills_dir: Path, skill_name: str) -> Optional[str]:
    """Get the full instructions for a skill.

    Args:
        skills_dir: Path to the skills directory
        skill_name: Name of the skill to load

    Returns:
        Full instructions string, or None if skill not found
    """
    if not _validate_skill_name(skill_name):
        logger.error(f"Invalid skill name: {skill_name}")
        return None

    skill_path = skills_dir / skill_name
    if not skill_path.exists() or not skill_path.is_dir():
        logger.error(f"Skill not found: {skill_name}")
        return None

    manifest_path = skill_path / SKILL_MANIFEST
    if not manifest_path.exists():
        logger.error(f"Skill manifest not found: {manifest_path}")
        return None

    manifest = _parse_skill_manifest(manifest_path)
    return manifest.get("instructions")


def _list_skill_resources(skills_dir: Path, skill_name: str) -> List[str]:
    """List all resource files available in a skill.

    Args:
        skills_dir: Path to the skills directory
        skill_name: Name of the skill

    Returns:
        List of resource file paths relative to the skill directory
    """
    if not _validate_skill_name(skill_name):
        return []

    skill_path = skills_dir / skill_name
    if not skill_path.exists() or not skill_path.is_dir():
        return []

    resources = []
    for item in skill_path.rglob("*"):
        if item.is_file() and item.name != SKILL_MANIFEST:
            rel_path = item.relative_to(skill_path)
            resources.append(str(rel_path))

    return sorted(resources)


def _get_skill_resource(skills_dir: Path, skill_name: str, resource_path: str) -> Optional[str]:
    """Get the content of a resource file from a skill.

    Args:
        skills_dir: Path to the skills directory
        skill_name: Name of the skill
        resource_path: Path to the resource file relative to the skill directory

    Returns:
        Content of the resource file, or None if not found
    """
    if not _validate_skill_name(skill_name):
        logger.error(f"Invalid skill name: {skill_name}")
        return None

    # Validate resource path to prevent path traversal
    if ".." in resource_path or resource_path.startswith("/"):
        logger.error(f"Invalid resource path (path traversal attempt): {resource_path}")
        return None

    skill_path = skills_dir / skill_name
    resource_full_path = skill_path / resource_path

    # Ensure the resolved path is within the skill directory
    try:
        resource_full_path = resource_full_path.resolve()
        skill_path_resolved = skill_path.resolve()
        if not str(resource_full_path).startswith(str(skill_path_resolved)):
            logger.error(f"Resource path traversal attempt: {resource_path}")
            return None
    except Exception as e:
        logger.error(f"Failed to resolve resource path: {e}")
        return None

    if not resource_full_path.exists() or not resource_full_path.is_file():
        logger.error(f"Resource not found: {resource_path}")
        return None

    try:
        return resource_full_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read resource {resource_path}: {e}")
        return None


# Track imported skills directories for the import action
_imported_skills_dirs: List[Path] = []


def _import_skills_dir(additional_dir: str) -> bool:
    """Import skills from an additional directory.

    Args:
        additional_dir: Path to the additional skills directory

    Returns:
        True if import was successful
    """
    path = Path(additional_dir)
    if not path.exists():
        logger.error(f"Import directory does not exist: {additional_dir}")
        return False
    if not path.is_dir():
        logger.error(f"Import path is not a directory: {additional_dir}")
        return False

    if path not in _imported_skills_dirs:
        _imported_skills_dirs.append(path)
        logger.info(f"Imported skills directory: {additional_dir}")

    return True


def _get_all_skills(base_skills_dir: Path) -> List[Dict[str, str]]:
    """Get all skills from base directory and imported directories.

    Args:
        base_skills_dir: The base skills directory

    Returns:
        Combined list of all skills
    """
    all_skills = _list_skills(base_skills_dir)

    for imported_dir in _imported_skills_dirs:
        imported_skills = _list_skills(imported_dir)
        # Avoid duplicates by name
        existing_names = {s["name"] for s in all_skills}
        for skill in imported_skills:
            if skill["name"] not in existing_names:
                all_skills.append(skill)
                existing_names.add(skill["name"])

    return sorted(all_skills, key=lambda x: x["name"])


def _find_skill_dir(skill_name: str, base_skills_dir: Path) -> Optional[Path]:
    """Find the directory containing a skill.

    Args:
        skill_name: Name of the skill to find
        base_skills_dir: The base skills directory

    Returns:
        Path to the skills directory containing the skill, or None
    """
    # Check base directory first
    if (base_skills_dir / skill_name / SKILL_MANIFEST).exists():
        return base_skills_dir

    # Check imported directories
    for imported_dir in _imported_skills_dirs:
        if (imported_dir / skill_name / SKILL_MANIFEST).exists():
            return imported_dir

    return None


@tool
@experimental("Experimental: Vendored from PR #379. API may change when upstream merges.")
def skills(
    action: str,
    skill_name: Optional[str] = None,
    resource_path: Optional[str] = None,
    directory: Optional[str] = None,
) -> str:
    """Manage and use agent skills for specialized tasks.

    Skills are reusable instruction sets that provide specialized capabilities.
    Each skill contains detailed instructions that guide how to perform specific
    tasks or workflows.

    EXPERIMENTAL: This tool is vendored from strands-agents/tools PR #379.
    The API may change when the upstream PR merges.

    Actions:
        - list: Show all available skills with their descriptions
        - use: Load a skill's full instructions (returns them for you to follow)
        - get_resource: Load a specific file from a skill
        - list_resources: List all files available in a skill
        - import: Dynamically import skills from an additional directory

    Args:
        action: The action to perform ('list', 'use', 'get_resource', 'list_resources', 'import')
        skill_name: Name of the skill (required for 'use', 'get_resource', 'list_resources')
        resource_path: Path to resource file within skill (required for 'get_resource')
        directory: Path to skills directory (required for 'import')

    Returns:
        Result of the action as a string

    Environment Variables:
        STRANDS_SKILLS_DIR: Directory containing skills (default: ./skills)

    Example skill structure:
        skills/
        └── my-skill/
            ├── SKILL.md      # Required: Contains skill instructions
            ├── template.txt  # Optional: Resource files
            └── config.json   # Optional: Additional resources
    """
    logger.debug("=" * 50)
    logger.debug("SKILLS TOOL - action=%s, skill_name=%s", action, skill_name)
    logger.debug("=" * 50)
    base_skills_dir = _get_skills_dir()

    if action == "list":
        all_skills = _get_all_skills(base_skills_dir)
        if not all_skills:
            return "No skills available. Create skills in the skills directory with SKILL.md manifests."

        result_lines = ["Available skills:"]
        for skill in all_skills:
            result_lines.append(f"  - {skill['name']}: {skill['description']}")
        return "\n".join(result_lines)

    elif action == "use":
        if not skill_name:
            return "Error: skill_name is required for 'use' action"

        skill_dir = _find_skill_dir(skill_name, base_skills_dir)
        if not skill_dir:
            return f"Error: Skill '{skill_name}' not found"

        instructions = _get_skill_instructions(skill_dir, skill_name)
        if not instructions:
            return f"Error: Could not load instructions for skill '{skill_name}'"

        return f"# Skill: {skill_name}\n\n{instructions}"

    elif action == "list_resources":
        if not skill_name:
            return "Error: skill_name is required for 'list_resources' action"

        skill_dir = _find_skill_dir(skill_name, base_skills_dir)
        if not skill_dir:
            return f"Error: Skill '{skill_name}' not found"

        resources = _list_skill_resources(skill_dir, skill_name)
        if not resources:
            return f"No additional resources available for skill '{skill_name}'"

        result_lines = [f"Resources for skill '{skill_name}':"]
        for resource in resources:
            result_lines.append(f"  - {resource}")
        return "\n".join(result_lines)

    elif action == "get_resource":
        if not skill_name:
            return "Error: skill_name is required for 'get_resource' action"
        if not resource_path:
            return "Error: resource_path is required for 'get_resource' action"

        skill_dir = _find_skill_dir(skill_name, base_skills_dir)
        if not skill_dir:
            return f"Error: Skill '{skill_name}' not found"

        content = _get_skill_resource(skill_dir, skill_name, resource_path)
        if content is None:
            return f"Error: Resource '{resource_path}' not found in skill '{skill_name}'"

        return content

    elif action == "import":
        if not directory:
            return "Error: directory is required for 'import' action"

        success = _import_skills_dir(directory)
        if success:
            return f"Successfully imported skills from: {directory}"
        else:
            return f"Error: Failed to import skills from: {directory}"

    else:
        return (
            f"Error: Unknown action '{action}'. "
            "Valid actions: 'list', 'use', 'get_resource', 'list_resources', 'import'"
        )


def clear_imported_skills() -> None:
    """Clear all imported skills directories.

    This is primarily useful for testing to reset state between tests.
    """
    global _imported_skills_dirs
    _imported_skills_dirs = []
