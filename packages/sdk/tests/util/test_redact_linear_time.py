# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""scrub() stays linear on an unclosed quoted value full of backslashes.

Each shape is about 100,000 characters and runs in a child process: the regex holds the GIL, so
only a process can be stopped when it hangs. A linear scrub takes well under a second there; a
quadratic or exponential pattern does not finish inside the timeout.
"""

import os
import subprocess
import sys

import pytest

_N = 100_000
_SHAPES = {
    "json": f"'\"password\": \"' + '\\\\' * {_N} + 'abc def\\n'",
    "env": f"'API_SECRET=\"' + '\\\\' * {_N} + 'abc def\\n'",
    "yaml": f"'password: \"' + '\\\\' * {_N} + 'abc def\\n'",
    "nested json": f"__import__('json').dumps('{{\"password\": \"' + '\\\\' * {_N} + 'abc def')",
    "backslash run before a key": f"'\\\\' * {_N} + '\"password'",
    "windows path in a tool result": (
        f"str([{{'type': 'text', 'text': '\"password\": \"C:' + ('\\\\' * 2 + 'dir') * {_N // 5} + ' (cut)\\n'}}])"
    ),
}
_TIMEOUT_SECONDS = 10


@pytest.mark.parametrize("text", _SHAPES.values(), ids=_SHAPES.keys())
def test_an_unclosed_quoted_secret_with_many_backslashes_is_scrubbed_in_linear_time(text: str) -> None:
    code = f"from agent_builder_sdk.util.redact import scrub; scrub({text})"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    subprocess.run([sys.executable, "-c", code], check=True, timeout=_TIMEOUT_SECONDS, env=env)
