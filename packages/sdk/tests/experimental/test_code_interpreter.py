# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the code-interpreter tool wrapper's network-mode note selection."""

import unittest
import warnings
from unittest.mock import MagicMock, patch

from strands_tools.code_interpreter import AgentCoreCodeInterpreter

from agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool import (
    CODE_INTERPRETER_ID_ENV_VAR,
    create_code_interpreter_tool,
)


class CreateCodeInterpreterToolTest(unittest.TestCase):
    def _build(self, interpreter_id):
        """Build the tool with a mocked interpreter; return (ctor_mock, appended_description)."""
        fake = MagicMock()
        fake.code_interpreter.tool_spec = {"description": "base"}
        env = {CODE_INTERPRETER_ID_ENV_VAR: interpreter_id} if interpreter_id else {}
        with patch(
            "agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool."
            "AgentCoreCodeInterpreter",
            return_value=fake,
        ) as ctor, patch.dict("os.environ", env, clear=True):
            create_code_interpreter_tool(region="us-west-2")
        return ctor, fake.code_interpreter.tool_spec["description"]

    def test_default_id_gets_sandbox_note(self):
        ctor, desc = self._build(None)
        self.assertEqual(ctor.call_args.kwargs["identifier"], "aws.codeinterpreter.v1")
        self.assertIn("NO network access", desc)
        self.assertNotIn("public internet access", desc)

    def test_custom_id_gets_public_note(self):
        custom = "my_public_interpreter-ABC123xyz"
        ctor, desc = self._build(custom)
        self.assertEqual(ctor.call_args.kwargs["identifier"], custom)
        self.assertIn("public internet access", desc)
        self.assertIn("pip install -r requirements.txt", desc)


class ToolSpecIsolationTest(unittest.TestCase):
    """The sandbox note must be appended per-agent, not onto the shared class-level spec."""

    def _first_tool_description(self, region="us-west-2"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            with patch.dict("os.environ", {}, clear=True):
                tools = create_code_interpreter_tool(region=region)
        return tools[0].tool_spec["description"]

    def test_note_appended_once_per_build(self):
        desc = self._first_tool_description()
        self.assertEqual(desc.count("IMPORTANT ENVIRONMENT NOTES"), 1)

    def test_two_builds_do_not_stack_or_cross_contaminate(self):
        # Two agents constructed in one process must each see exactly one
        # note — the pre-fix bug appended onto a shared dict, yielding two.
        first = self._first_tool_description()
        second = self._first_tool_description()
        self.assertEqual(first.count("IMPORTANT ENVIRONMENT NOTES"), 1)
        self.assertEqual(second.count("IMPORTANT ENVIRONMENT NOTES"), 1)

    def test_shared_class_spec_left_clean(self):
        # Building the tool must not mutate the interpreter's shared base spec.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            self._first_tool_description()
            baseline = AgentCoreCodeInterpreter(region="us-west-2")
        self.assertNotIn(
            "IMPORTANT ENVIRONMENT NOTES", baseline.code_interpreter.tool_spec["description"]
        )


if __name__ == "__main__":
    unittest.main()
