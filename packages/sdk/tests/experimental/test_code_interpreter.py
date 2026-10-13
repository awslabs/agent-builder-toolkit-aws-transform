# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the code-interpreter tool wrapper: description notes, staging, and sessions."""

import importlib
import itertools
import os
import shutil
import sys
import tempfile
import time
import unittest
import warnings
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from strands_tools.code_interpreter import AgentCoreCodeInterpreter

from agent_builder_sdk.experimental.code_interpreter import code_interpreter_tool
from agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool import (
    CODE_INTERPRETER_ID_ENV_VAR,
    SESSION_TIMEOUT_ENV_VAR,
    create_code_interpreter_tool,
)

pytestmark = pytest.mark.filterwarnings("ignore::FutureWarning")


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

    def test_session_timeout_from_env_capped_at_service_max(self):
        fake = MagicMock()
        fake.code_interpreter.tool_spec = {"description": "base"}
        with patch(
            "agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool."
            "AgentCoreCodeInterpreter",
            return_value=fake,
        ) as ctor, patch.dict("os.environ", {SESSION_TIMEOUT_ENV_VAR: "36000"}, clear=True):
            create_code_interpreter_tool(region="us-west-2")
            create_code_interpreter_tool(region="us-west-2", session_timeout_seconds=1800)
        timeouts = [c.kwargs["session_timeout_seconds"] for c in ctor.call_args_list]
        self.assertEqual(timeouts, [28800, 1800])


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

    def test_later_build_does_not_rewrite_earlier_agents_description(self):
        # Agent A uses the default (isolated) interpreter, agent B a custom one.
        # strands resets the shared spec on every construction, so without A's own
        # copy, building B would make A's tool claim internet access.
        with patch.dict("os.environ", {}, clear=True):
            agent_a = create_code_interpreter_tool(region="us-west-2")
        custom = {CODE_INTERPRETER_ID_ENV_VAR: "my_public_interpreter-ABC123xyz"}
        with patch.dict("os.environ", custom, clear=True):
            create_code_interpreter_tool(region="us-west-2")
        desc = agent_a[0].tool_spec["description"]
        self.assertIn("NO network access", desc)
        self.assertNotIn("HAS public internet access", desc)

    def test_shared_class_spec_left_clean(self):
        # Building the tool must not mutate the interpreter's shared base spec.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            self._first_tool_description()
            baseline = AgentCoreCodeInterpreter(region="us-west-2")
        self.assertNotIn(
            "IMPORTANT ENVIRONMENT NOTES", baseline.code_interpreter.tool_spec["description"]
        )


class _FakeSandbox:
    """Stands in for the AgentCore data plane: the sessions started and the files in each."""

    def __init__(self):
        self.files = {}  # session id -> paths written to it
        self.ended = set()  # session ids the service has terminated
        self.write_error = None  # when set, writeFiles answers with isError=True
        self._ids = itertools.count(1)

    def client(self, region=None, session=None):
        return _FakeClient(self)


class _FakeClient:
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.identifier = None
        self.session_id = None

    def start(self, identifier=None, name=None, session_timeout_seconds=None):
        time.sleep(0.05)  # a real start takes about a second; widen the race window
        self.identifier = identifier
        self.session_id = f"aws-session-{next(self.sandbox._ids)}"
        self.sandbox.files[self.session_id] = []
        return self.session_id

    def get_session(self, interpreter_id=None, session_id=None):
        ended = (session_id or self.session_id) in self.sandbox.ended
        return {"status": "TERMINATED" if ended else "READY"}

    def invoke(self, method, params=None):
        if self.session_id in self.sandbox.ended:
            error = {"Error": {"Code": "ResourceNotFoundException", "Message": "session ended"}}
            raise ClientError(error, "InvokeCodeInterpreter")
        if method == "writeFiles" and self.sandbox.write_error:
            text = self.sandbox.write_error
            return {"stream": [{"result": {"content": [{"type": "text", "text": text}], "isError": True}}]}
        if method == "writeFiles":
            self.sandbox.files[self.session_id] += [c["path"] for c in params["content"]]
        return {"stream": [{"result": {"content": [{"type": "text", "text": "ok"}], "isError": False}}]}


class SandboxStagingAndSessionTest(unittest.TestCase):
    def setUp(self):
        self.sandbox = _FakeSandbox()
        client = patch(
            "strands_tools.code_interpreter.agent_core_code_interpreter."
            "BedrockAgentCoreCodeInterpreterClient",
            self.sandbox.client,
        )
        client.start()
        self.addCleanup(client.stop)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _tools(self):
        with patch.dict("os.environ", {}, clear=True):
            return create_code_interpreter_tool(region="us-west-2")

    def _file(self, name, data=b"a,b\n1,2\n"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    @staticmethod
    def _stage(tools, local_path, sandbox_path, **kwargs):
        return tools[1](local_path=local_path, sandbox_path=sandbox_path, **kwargs)

    @staticmethod
    def _list_files(tools, **action):
        return tools[0](code_interpreter_input={"action": {"type": "listFiles", "path": ".", **action}})

    def test_stage_missing_file(self):
        result = self._stage(self._tools(), os.path.join(self.tmp, "missing.csv"), "x.csv")
        self.assertIn("no such file", result)
        self.assertEqual(self.sandbox.files, {})

    def test_stage_file_over_limit(self):
        with patch.object(code_interpreter_tool, "_MAX_STAGE_BYTES", 4):
            result = self._stage(self._tools(), self._file("big.csv", b"12345"), "big.csv")
        self.assertIn("transfer limit", result)
        self.assertEqual(self.sandbox.files, {})

    def test_stage_success(self):
        result = self._stage(self._tools(), self._file("d.csv"), "data/d.csv")
        self.assertTrue(result.startswith("Staged"), result)
        self.assertEqual(list(self.sandbox.files.values()), [["data/d.csv"]])

    def test_stage_reports_sandbox_error(self):
        # The service flags a rejected write on the stream result, not the response.
        self.sandbox.write_error = "Permission denied: /etc/x"
        result = self._stage(self._tools(), self._file("d.csv"), "/etc/x")
        self.assertTrue(result.startswith("Error: staging failed"), result)
        self.assertIn("Permission denied", result)

    def test_parallel_first_use_starts_one_session(self):
        tools = self._tools()
        paths = [self._file(f"part{i}.csv") for i in range(3)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda p: self._stage(tools, p, os.path.basename(p)), paths))
        self.assertTrue(all(r.startswith("Staged") for r in results), results)
        self.assertEqual(len(self.sandbox.files), 1)
        self.assertCountEqual(next(iter(self.sandbox.files.values())), ["part0.csv", "part1.csv", "part2.csv"])

    def test_named_sessions_stay_per_agent(self):
        agent_a, agent_b = self._tools(), self._tools()
        self._stage(agent_a, self._file("a.csv"), "a.csv", session_name="analysis")
        self._stage(agent_b, self._file("b.csv"), "b.csv", session_name="analysis")
        self.assertCountEqual(self.sandbox.files.values(), [["a.csv"], ["b.csv"]])
        # Within one agent, both tools resolve the name to the same session.
        self.assertEqual(self._list_files(agent_a, session_name="analysis")["status"], "success")
        self.assertEqual(len(self.sandbox.files), 2)

    def test_ended_session_is_replaced_once(self):
        tools = self._tools()
        self._stage(tools, self._file("a.csv"), "a.csv")
        self.sandbox.ended.update(self.sandbox.files)  # the session's lifetime ran out
        result = self._stage(tools, self._file("b.csv"), "b.csv")
        self.assertTrue(result.startswith("Staged"), result)
        self.assertEqual(len(self.sandbox.files), 2)
        self.sandbox.ended.update(self.sandbox.files)
        self.assertEqual(self._list_files(tools)["status"], "success")
        self.assertEqual(len(self.sandbox.files), 3)

    def test_error_on_live_session_is_not_retried(self):
        tools = self._tools()
        self._stage(tools, self._file("a.csv"), "a.csv")
        throttled = ClientError({"Error": {"Code": "ThrottlingException"}}, "InvokeCodeInterpreter")
        with patch.object(_FakeClient, "invoke", side_effect=throttled) as invoke:
            with self.assertRaises(ClientError):
                self._list_files(tools)
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(len(self.sandbox.files), 1)


class MissingDependencyTest(unittest.TestCase):
    def test_import_error_names_the_extra(self):
        name = "agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool"
        saved = sys.modules.pop(name)
        self.addCleanup(sys.modules.__setitem__, name, saved)
        with patch.dict(sys.modules, {"strands_tools.code_interpreter": None}):
            with self.assertRaisesRegex(ImportError, r"\[code-interpreter\]"):
                importlib.import_module(name)


if __name__ == "__main__":
    unittest.main()
