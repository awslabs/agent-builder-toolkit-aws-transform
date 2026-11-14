# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the deprecated skill operations tools."""

import json
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

from agent_builder_mcp.tools.skill_operations import (
    DEPRECATION_NOTICE,
    deprecated,
    get_skill_metadata,
    register_skill_operations_tools,
)

MODULE = "agent_builder_mcp.tools.skill_operations"

SKILL_TOOL_NAMES = {
    "list_skills",
    "get_skill_metadata",
    "update_skill_metadata",
    "upload_skill",
    "download_skill",
    "list_skill_access_control",
    "update_skill_access_control",
}


class TestRegistration:
    """Every skill tool is registered under its original name with a deprecation notice."""

    def test_tool_names_unchanged(self):
        mcp = FastMCP(name="test")
        register_skill_operations_tools(mcp)

        assert {t.name for t in mcp._tool_manager.list_tools()} == SKILL_TOOL_NAMES

    def test_descriptions_carry_notice(self):
        mcp = FastMCP(name="test")
        register_skill_operations_tools(mcp)

        for tool in mcp._tool_manager.list_tools():
            assert tool.description.startswith("[DEPRECATED] ")
            assert DEPRECATION_NOTICE in tool.description

    def test_input_schema_preserved(self):
        mcp = FastMCP(name="test")
        register_skill_operations_tools(mcp)

        tool = mcp._tool_manager.get_tool("update_skill_access_control")
        assert set(tool.parameters["required"]) == {"skill_name", "skill_user_account_id", "access_status"}


class TestDeprecatedDecorator:
    """Results keep their original payload and gain a `deprecation` field."""

    def test_success_result_has_notice(self):
        mock_client = MagicMock()
        mock_client.get_skill_metadata.return_value = {"skillName": "my-skill", "status": "ACTIVE"}

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deprecated(get_skill_metadata)(skill_name="my-skill"))

        assert result["skillName"] == "my-skill"
        assert result["status"] == "ACTIVE"
        assert result["deprecation"] == DEPRECATION_NOTICE
        mock_client.get_skill_metadata.assert_called_once_with(skillName="my-skill")

    def test_error_result_has_notice(self):
        mock_client = MagicMock()
        mock_client.get_skill_metadata.side_effect = Exception("Skill missing does not exist")

        with patch(f"{MODULE}.registry_client", return_value=mock_client):
            result = json.loads(deprecated(get_skill_metadata)(skill_name="missing"))

        assert "does not exist" in result["error"]
        assert result["deprecation"] == DEPRECATION_NOTICE

    def test_wrapper_keeps_name_and_signature(self):
        wrapped = deprecated(get_skill_metadata)

        assert wrapped.__name__ == "get_skill_metadata"
        assert wrapped.__wrapped__ is get_skill_metadata
