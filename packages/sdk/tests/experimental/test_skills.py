# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for experimental agent skills feature.

Tests cover:
- Skill listing (empty dir, valid skills, invalid names)
- Skill loading via `use` action
- Resource loading with path traversal protection
- Dynamic import from additional directories
- Feature flag enabling/disabling
- Integration with agent factory
- System prompt injection via get_skills_prompt()
"""

import os
import tempfile
import warnings
from pathlib import Path
from unittest import mock

import pytest


class TestSkillsTool:
    """Tests for the skills tool functionality."""

    @pytest.fixture
    def skills_dir(self):
        """Create a temporary skills directory with test skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir)

            # Create a valid skill
            hello_skill = skills_path / "hello-world"
            hello_skill.mkdir()
            (hello_skill / "SKILL.md").write_text(
                """---
name: hello-world
description: A test skill for greeting users
---

# Hello World Skill

When activated, greet the user warmly and professionally.
"""
            )

            # Create another skill with resources
            web_skill = skills_path / "web-research"
            web_skill.mkdir()
            (web_skill / "SKILL.md").write_text(
                """---
name: web-research
description: Searches web and synthesizes findings
---

# Web Research Skill

Use this skill to search the web and create reports.
"""
            )
            (web_skill / "template.txt").write_text("Report template content")
            (web_skill / "config.json").write_text('{"timeout": 30}')

            yield str(skills_path)

    @pytest.fixture
    def empty_skills_dir(self):
        """Create an empty skills directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_list_skills_with_valid_skills(self, skills_dir):
        """Test listing skills returns all valid skills."""
        # Import inside test to avoid warning at module load
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="list")

        assert "Available skills:" in result
        assert "hello-world" in result
        assert "web-research" in result
        assert "A test skill for greeting users" in result
        assert "Searches web and synthesizes findings" in result

    def test_list_skills_empty_directory(self, empty_skills_dir):
        """Test listing skills in empty directory."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": empty_skills_dir}):
            result = skills(action="list")

        assert "No skills available" in result

    def test_list_skills_nonexistent_directory(self):
        """Test listing skills when directory doesn't exist."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": "/nonexistent/path"}):
            result = skills(action="list")

        assert "No skills available" in result

    def test_use_skill_loads_instructions(self, skills_dir):
        """Test using a skill returns its instructions."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="use", skill_name="hello-world")

        assert "# Skill: hello-world" in result
        assert "Hello World Skill" in result
        assert "greet the user warmly" in result

    def test_use_skill_not_found(self, skills_dir):
        """Test using a nonexistent skill returns error."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="use", skill_name="nonexistent-skill")

        assert "Error:" in result
        assert "not found" in result

    def test_use_skill_requires_skill_name(self, skills_dir):
        """Test using skill without name returns error."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="use")

        assert "Error:" in result
        assert "skill_name is required" in result

    def test_list_resources_returns_skill_files(self, skills_dir):
        """Test listing resources returns available files."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="list_resources", skill_name="web-research")

        assert "Resources for skill 'web-research':" in result
        assert "template.txt" in result
        assert "config.json" in result

    def test_list_resources_skill_without_resources(self, skills_dir):
        """Test listing resources for skill without extra files."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="list_resources", skill_name="hello-world")

        assert "No additional resources" in result

    def test_get_resource_returns_file_content(self, skills_dir):
        """Test getting a resource returns file content."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(
                action="get_resource", skill_name="web-research", resource_path="template.txt"
            )

        assert result == "Report template content"

    def test_get_resource_not_found(self, skills_dir):
        """Test getting nonexistent resource returns error."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(
                action="get_resource", skill_name="web-research", resource_path="nonexistent.txt"
            )

        assert "Error:" in result
        assert "not found" in result

    def test_get_resource_path_traversal_protection(self, skills_dir):
        """Test path traversal attempts are blocked."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            # Test relative path traversal
            result = skills(
                action="get_resource",
                skill_name="web-research",
                resource_path="../hello-world/SKILL.md",
            )
            assert "Error:" in result

            # Test absolute path
            result = skills(
                action="get_resource", skill_name="web-research", resource_path="/etc/passwd"
            )
            assert "Error:" in result

    def test_import_skills_from_additional_directory(self, skills_dir, empty_skills_dir):
        """Test importing skills from additional directory."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()

        # Create a new skill in the empty dir
        extra_skill = Path(empty_skills_dir) / "extra-skill"
        extra_skill.mkdir()
        (extra_skill / "SKILL.md").write_text(
            """---
name: extra-skill
description: An extra skill from imported directory
---

# Extra Skill Instructions
"""
        )

        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            # Import the additional directory
            result = skills(action="import", directory=empty_skills_dir)
            assert "Successfully imported" in result

            # List should now include skills from both directories
            result = skills(action="list")
            assert "hello-world" in result
            assert "extra-skill" in result

    def test_import_nonexistent_directory(self, skills_dir):
        """Test importing from nonexistent directory returns error."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="import", directory="/nonexistent/path")

        assert "Error:" in result
        assert "Failed to import" in result

    def test_invalid_skill_name_rejected(self, skills_dir):
        """Test invalid skill names are rejected."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            # Test path traversal in skill name
            result = skills(action="use", skill_name="../etc/passwd")
            assert "Error:" in result

            # Test special characters
            result = skills(action="use", skill_name="skill;rm -rf /")
            assert "Error:" in result

    def test_unknown_action_returns_error(self, skills_dir):
        """Test unknown action returns error message."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills

        clear_imported_skills()
        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = skills(action="unknown_action")

        assert "Error:" in result
        assert "Unknown action" in result
        assert "Valid actions" in result


class TestSkillsPrompt:
    """Tests for get_skills_prompt helper."""

    @pytest.fixture
    def skills_dir(self):
        """Create a temporary skills directory with test skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir)

            # Create skills
            for name, desc in [
                ("skill-a", "First skill"),
                ("skill-b", "Second skill"),
            ]:
                skill_dir = skills_path / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"""---
name: {name}
description: {desc}
---

Instructions for {name}.
"""
                )

            yield str(skills_path)

    def test_get_skills_prompt_generates_xml(self, skills_dir):
        """Test that get_skills_prompt generates proper XML format."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills import get_skills_prompt

        result = get_skills_prompt(skills_dir)

        assert "## Available Skills" in result
        assert "<available_skills>" in result
        assert "</available_skills>" in result
        assert "<skill>" in result
        assert "<name>skill-a</name>" in result
        assert "<description>First skill</description>" in result
        assert "<name>skill-b</name>" in result

    def test_get_skills_prompt_empty_dir_returns_empty(self):
        """Test empty skills directory returns empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                from agent_builder_sdk.skills import get_skills_prompt

            result = get_skills_prompt(tmpdir)
            assert result == ""

    def test_get_skills_prompt_nonexistent_dir_returns_empty(self):
        """Test nonexistent directory returns empty string."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills import get_skills_prompt

        result = get_skills_prompt("/nonexistent/path")
        assert result == ""

    def test_get_skills_prompt_uses_env_var(self, skills_dir):
        """Test get_skills_prompt uses STRANDS_SKILLS_DIR env var."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from agent_builder_sdk.skills import get_skills_prompt

        with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
            result = get_skills_prompt()  # No argument, should use env var

        assert "<name>skill-a</name>" in result

    def test_get_skills_prompt_escapes_xml_chars(self):
        """Test that special XML characters are escaped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir)
            skill_dir = skills_path / "special-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: special-skill
description: Uses <tags> & "quotes"
---

Instructions here.
"""
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                from agent_builder_sdk.skills import get_skills_prompt

            result = get_skills_prompt(tmpdir)

            # XML special chars should be escaped
            assert "&lt;tags&gt;" in result
            assert "&amp;" in result


class TestAgentFactoryIntegration:
    """Tests for skills integration with agent factory."""

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    def test_create_orchestrator_with_skills_enabled(
        self,
        mock_send_message_tools,
        mock_subagent_registry_tools,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with skills enabled uses AgentSkills plugin."""
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        # Setup mocks
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        mock_memory_tool_instance = mock.Mock()
        mock_memory_tool_instance.memory = mock.Mock(name="memory_tool")
        mock_memory_tool.return_value = mock_memory_tool_instance

        mock_subagent_registry = mock.Mock()
        mock_subagent_registry.discover_subagents = mock.Mock(name="discover_subagents")
        mock_subagent_registry_tools.return_value = mock_subagent_registry

        mock_send_message = mock.Mock()
        mock_send_message.send_message_to_subagent = mock.Mock(name="send_message_to_subagent")
        mock_send_message_tools.return_value = mock_send_message

        # Call with skills enabled
        result = create_default_async_orchestrator_with_subagent(
            system_prompt="test prompt",
            enable_skills=True,
        )

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs

        # Verify AgentSkills plugin is passed
        from strands.vended_plugins.skills import AgentSkills

        plugins = call_kwargs["plugins"]
        assert plugins is not None
        assert len(plugins) == 1
        assert isinstance(plugins[0], AgentSkills)

        # Verify vendored skills tool is NOT in custom_tools
        custom_tools = call_kwargs["custom_tools"]
        tool_names = [getattr(t, "tool_name", None) for t in custom_tools]
        assert "skills" not in tool_names

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    def test_create_orchestrator_without_skills(
        self,
        mock_send_message_tools,
        mock_subagent_registry_tools,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with skills disabled (default)."""
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        # Setup mocks
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        mock_memory_tool_instance = mock.Mock()
        mock_memory_tool_instance.memory = mock.Mock(name="memory_tool")
        mock_memory_tool.return_value = mock_memory_tool_instance

        mock_subagent_registry = mock.Mock()
        mock_subagent_registry.discover_subagents = mock.Mock(name="discover_subagents")
        mock_subagent_registry_tools.return_value = mock_subagent_registry

        mock_send_message = mock.Mock()
        mock_send_message.send_message_to_subagent = mock.Mock(name="send_message_to_subagent")
        mock_send_message_tools.return_value = mock_send_message

        # Call without skills (default)
        result = create_default_async_orchestrator_with_subagent(
            system_prompt="test prompt",
        )

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs

        # Verify no plugins passed
        plugins = call_kwargs.get("plugins")
        assert plugins is None


class TestExperimentalWarning:
    """Tests for experimental warning behavior."""

    def test_skills_tool_emits_future_warning_on_use(self, skills_dir):
        """Test that using the skills tool emits FutureWarning."""
        # The FutureWarning is emitted when calling the skills() function
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Import with warning suppression since import warning may have already fired
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                from agent_builder_sdk.skills.skills_tool import clear_imported_skills, skills
            clear_imported_skills()

            # Now call skills() which emits the warning
            with mock.patch.dict(os.environ, {"STRANDS_SKILLS_DIR": skills_dir}):
                skills(action="list")

            # Check that a FutureWarning was issued by the tool call
            future_warnings = [
                warning for warning in w if issubclass(warning.category, FutureWarning)
            ]
            assert len(future_warnings) >= 1
            assert "experimental" in str(future_warnings[0].message).lower()

    @pytest.fixture
    def skills_dir(self):
        """Create a temporary skills directory with test skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
