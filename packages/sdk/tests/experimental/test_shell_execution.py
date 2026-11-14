# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for experimental shell execution support."""

import os
import shutil
import subprocess
import sys
import time
import tracemalloc
import warnings
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

# Import once at module level and filter warnings
warnings.filterwarnings(
    "ignore", category=FutureWarning, module="agent_builder_sdk.experimental"
)

from agent_builder_sdk.experimental.shell_execution import execute_shell  # noqa: E402
from agent_builder_sdk.experimental.shell_execution.shell_execution_tool import (  # noqa: E402
    _MAX_STDERR_BYTES,
    _MAX_STDOUT_BYTES,
    _CappedReader,
    _decode,
    _finished,
    _sanitized_env,
    _validate_command,
)

_TOOL_MODULE = "agent_builder_sdk.experimental.shell_execution.shell_execution_tool"


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
        assert "not allowed" in result
        assert "command_length=" in caplog.text
        assert "hunter2" not in caplog.text
        assert "evil.com" not in caplog.text

    def test_rejected_word_with_a_quote_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        # The rejected first word is quoted in the message to the model; a quote inside
        # it must not let part of it into the log.
        with warnings.catch_warnings(), caplog.at_level("WARNING"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="KEY=\"it's-secret9\" curl x", working_directory="/tmp")
        assert "not allowed" in result
        assert "reason=no plain command name in first position" in caplog.text
        assert "secret9" not in caplog.text

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
        "redirection, kept, logged",
        [
            ("", "\x00" * _MAX_STDOUT_BYTES, "stdout_bytes=100000000, stderr_bytes=0"),
            (" 1>&2", "[stderr]\n" + "\x00" * _MAX_STDERR_BYTES, "stdout_bytes=0, stderr_bytes=100000000"),
        ],
        ids=["stdout", "stderr"],
    )
    def test_output_far_over_the_limit_is_not_held_in_memory(
        self, caplog: pytest.LogCaptureFixture, redirection: str, kept: str, logged: str
    ) -> None:
        # 100 MB of output on stdout, then on stderr: the result is cut at the limit of
        # the stream, and the agent process must not hold the rest while the command runs.
        tracemalloc.start()
        try:
            with warnings.catch_warnings(), caplog.at_level("INFO"):
                warnings.simplefilter("ignore", FutureWarning)
                result = execute_shell(
                    command="head -c 100000000 /dev/zero" + redirection, working_directory="/tmp"
                )
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
        assert finished.call_args.args[2] == used

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

    def test_timeout_kills_whole_process_tree(self, tmp_path: Path) -> None:
        # A grandchild of the shell must be killed on timeout, not orphaned. awk starts in
        # milliseconds, so the probe runs long before the timeout: the shell of its
        # system() call records its own PID and then becomes the sleep.
        if shutil.which("awk") is None:
            pytest.skip("awk not on PATH in this environment")

        # Per-test path: two test runs on one host must not share the file.
        pidfile = tmp_path / "shell_timeout_probe.pid"
        cmd = f"""awk 'BEGIN {{ system("echo $$ > {pidfile}; exec sleep 30") }}'"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command=cmd, working_directory="/tmp", timeout_seconds=1)
        assert "timed out" in result
        grandchild_pid = int(pidfile.read_text())
        deadline = time.monotonic() + 5
        while _is_running(grandchild_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _is_running(grandchild_pid)


class TestCommandValidation:
    """Tests for the allowlist / pipe / operator validation."""

    def test_allowlisted_and_piped(self) -> None:
        assert _validate_command("ls -la /tmp")[0]
        assert _validate_command("cat a.json | grep foo | wc -l")[0]

    def test_non_allowlisted_command_rejected(self) -> None:
        assert not _validate_command("curl http://example.com")[0]
        assert not _validate_command("pip install pyarrow")[0]

    def test_bad_stage_in_pipe_rejected(self) -> None:
        assert not _validate_command("cat a.json | curl evil")[0]

    def test_shell_operators_blocked(self) -> None:
        assert not _validate_command("ls; rm -rf /")[0]
        assert not _validate_command("ls && curl x")[0]
        assert not _validate_command("echo $(whoami)")[0]

    def test_quoted_operators_allowed(self) -> None:
        # CSS/HTML/Python payloads are full of semicolons — quoted content must
        # not trip the operator check, or the agent gets stuck retrying.
        assert _validate_command("printf '%s' 'body{font-family:sans-serif;margin:0}'")[0]
        assert _validate_command('echo "a; b; c"')[0]
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _validate_command("python3 -c 'x = 1; print(x)'")[0]

    def test_unquoted_operators_still_blocked_around_quotes(self) -> None:
        assert not _validate_command("echo 'safe'; curl evil")[0]
        assert not _validate_command('echo "safe" && curl evil')[0]
        assert not _validate_command("echo `whoami`")[0]

    def test_command_substitution_in_double_quotes_blocked(self) -> None:
        # $( ) and backticks still execute inside double quotes in a real shell.
        assert not _validate_command('echo "today is $(whoami)"')[0]
        assert not _validate_command('echo "today is `whoami`"')[0]

    def test_substitution_chars_in_single_quotes_allowed(self) -> None:
        # Single quotes make everything literal — $( and backticks included.
        assert _validate_command("echo 'costs $(a lot)'")[0]
        assert _validate_command("echo 'back`tick`'")[0]

    def test_unquoted_newline_blocked(self) -> None:
        # An unquoted newline is a command separator: bash runs both commands, so
        # it must be rejected outright (not merely split-and-revalidated, since
        # the second command may itself be allowlisted, e.g. rm).
        assert not _validate_command("echo safe\nrm -rf /tmp/x")[0]
        assert not _validate_command("ls\ncurl evil.com")[0]
        assert not _validate_command("ls\npwd")[0]

    def test_quoted_newline_allowed(self) -> None:
        # A newline inside quotes is literal content, not a separator.
        assert _validate_command("printf 'line1\nline2'")[0]

    def test_env_wrapper_rejected(self) -> None:
        # `env` runs an arbitrary binary AND can re-set AWS_PROFILE, defeating
        # both the allowlist and the _sanitized_env stripping. It and the other
        # command wrappers must stay off the allowlist.
        assert not _validate_command("env FOO=bar /bin/echo pwned")[0]
        assert not _validate_command("env AWS_PROFILE=persona env")[0]
        for wrapper in ("xargs", "nice", "nohup", "timeout", "time"):
            assert not _validate_command(f"{wrapper} rm x")[0]

    def test_exec_delegating_flags_rejected(self) -> None:
        # find -exec / tar --to-command hand execution to an arbitrary child.
        assert not _validate_command("find /tmp -exec rm {} ;")[0]
        assert not _validate_command("find /tmp -execdir curl x ;")[0]
        assert not _validate_command("tar --to-command=curl -cf - /tmp")[0]
        assert not _validate_command("tar --checkpoint-action=exec=sh -cf a.tar /tmp")[0]
        # find/tar without an exec flag stay usable for inspection.
        assert _validate_command("find /tmp -name '*.parquet'")[0]
        assert _validate_command("tar -tzf archive.tar.gz")[0]

    def test_background_operator_rejected(self) -> None:
        # A lone `&` backgrounds the first stage and the shell runs whatever
        # follows, but only the first token is allowlist-checked — so `echo & curl`
        # smuggles curl past the allowlist. Reject it while keeping the redirection
        # forms in which every shell reads `&` as part of the operator (2>&1, >&).
        assert not _validate_command("echo hi & curl evil.com")[0]
        assert not _validate_command("python3 x.py & curl evil")[0]
        assert not _validate_command("head -5&curl evil.com")[0]
        assert not _validate_command("sleep 5 &")[0]
        # Directly after > or <, & duplicates a file descriptor — these must still pass.
        assert _validate_command("ls 2>&1")[0]
        assert _validate_command("ls 1>&2")[0]
        assert _validate_command("ls > /tmp/x 2>&1")[0]
        assert _validate_command("cat f >& /tmp/x")[0]
        assert _validate_command("cat <&0")[0]
        # A literal & inside quotes is content, not an operator.
        assert _validate_command("echo 'a & b'")[0]
        assert _validate_command('echo "a & b"')[0]

    def test_ampersand_before_a_redirection_rejected(self) -> None:
        # bash reads `&>file` as a redirection. A shell without that operator (dash, the
        # /bin/sh of Debian images) reads `ls &` and then runs the rest as a command.
        assert not _validate_command("ls &>/dev/null touch /tmp/marker")[0]
        assert not _validate_command("ls &> /tmp/x")[0]
        assert not _validate_command("ls &>> /tmp/x")[0]
        assert not _validate_command("ls |& cat")[0]
        assert not _validate_command("ls >&2 & curl evil.com")[0]

    def test_tar_short_compress_flag_rejected(self) -> None:
        # tar's -I (--use-compress-program) runs an arbitrary program. GNU getopt
        # attaches the arg directly (-Icurl) or bundles the letter after other
        # no-arg flags (-cIcurl), neither of which a whole-word check catches.
        assert not _validate_command("tar -Icurl -cf - /tmp")[0]
        assert not _validate_command("tar -cIcurl -f - /tmp")[0]
        assert not _validate_command("tar -I curl -cf - /tmp")[0]
        assert not _validate_command("tar -cIgzip -f a.tar /tmp")[0]
        # Legit tar must still pass — including an archive name that starts with
        # 'I' attached to -f (-cfInput.tar), which must not read as the -I option.
        assert _validate_command("tar -tzf archive.tar.gz")[0]
        assert _validate_command("tar -czf a.tar /tmp")[0]
        assert _validate_command("tar -cf Input.tar /tmp")[0]
        assert _validate_command("tar -cfInput.tar /tmp")[0]
        # find -executable must not be mistaken for the -exec primary.
        assert _validate_command("find /tmp -executable")[0]

    def test_sort_rg_exec_flags_rejected(self) -> None:
        # sort --compress-program=PROG runs PROG on temp files; ripgrep --pre=CMD /
        # --hostname-bin=CMD each exec CMD — same escape as find -exec, so an
        # allowlisted sort/rg becomes a launcher for a non-allowlisted binary.
        assert not _validate_command("sort --compress-program=curl f")[0]
        assert not _validate_command("sort --compress-program curl f")[0]
        assert not _validate_command("rg --pre=curl pat f")[0]
        assert not _validate_command("rg --pre curl pat f")[0]
        assert not _validate_command("rg --hostname-bin=curl pat f")[0]
        # sort/rg without those flags stay usable.
        assert _validate_command("sort -u file.txt")[0]
        assert _validate_command("rg 'pattern' /tmp")[0]

    def test_process_substitution_rejected(self) -> None:
        # <(cmd) / >(cmd) run their inner command under shell=True, but the
        # per-stage allowlist only sees the outer command (cat/tee), so the
        # inner curl would slip past. Reject the operator outright.
        assert not _validate_command("cat <(curl evil.com)")[0]
        assert not _validate_command("tee >(curl evil.com)")[0]
        # Plain redirection is NOT process substitution (no paren) — still allowed.
        assert _validate_command("echo hi > /tmp/x")[0]
        assert _validate_command("cat a >> b")[0]
        assert _validate_command("sort < /tmp/f")[0]
        # A literal <( inside quotes is content, not an operator.
        assert _validate_command("echo '<(not real)'")[0]

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
        assert "not allowed" in result

    def test_redirection_before_the_command_rejected(self) -> None:
        # The shell takes `2>/tmp/ls` as a redirection and runs the next word, which
        # the allowlist never saw.
        assert not _validate_command("2>/tmp/ls curl evil.com")[0]
        assert not _validate_command(">/tmp/ls curl evil.com")[0]
        assert not _validate_command("ls | </tmp/cat curl evil.com")[0]
        assert _validate_command("ls 2>/tmp/errors")[0]
        assert _validate_command("/usr/bin/ls -la")[0]
        assert _validate_command("[ -d /tmp ]")[0]

    def test_assignment_before_the_command_rejected(self) -> None:
        # `A=/ls` is an assignment whose basename happens to be allowlisted; the shell
        # runs the next word, with a variable the sanitized environment left out.
        assert not _validate_command("A=/ls curl evil.com")[0]
        assert not _validate_command("AWS_PROFILE=/python3 python3 x.py")[0]
        assert _validate_command("ls --color=never")[0]

    def test_dollar_quoting_rejected(self) -> None:
        # In bash, $'...' lets \' continue the quoted text, so the `;` below is
        # unquoted for the shell while plain quote rules call it quoted.
        assert not _validate_command("ls $'\\'' ; curl evil.com #'")[0]
        assert not _validate_command("echo $'a'")[0]
        assert not _validate_command('echo $"a"')[0]
        # A $ beside plain quotes is not that form.
        assert _validate_command("echo 'a$' 'b'")[0]
        assert _validate_command('echo "a$" "b"')[0]
        assert _validate_command("echo \\$'a'")[0]

    def test_unquoted_comment_rejected(self) -> None:
        # The shell ignores a quote inside a comment, so for the shell the newline
        # below ends the first command and starts a second one.
        assert not _validate_command("ls #'\ncurl evil.com #'")[0]
        assert not _validate_command("ls #'\ncurl evil.com")[0]
        assert not _validate_command("ls # list")[0]
        assert _validate_command("grep '#include' main.c")[0]
        assert _validate_command('echo "a # b"')[0]
        assert _validate_command("echo a\\#b")[0]

    def test_unterminated_quote_rejected(self) -> None:
        assert not _validate_command("ls 'abc")[0]
        assert not _validate_command('cat "abc | wc -l')[0]

    def test_abbreviated_exec_options_rejected(self) -> None:
        # GNU getopt accepts any unambiguous prefix of a long option.
        assert not _validate_command("tar -cf a.tar d --checkpoint=1 --checkpoint-ac=exec=curl")[0]
        assert not _validate_command("tar -xf a.tar --to-comm=curl")[0]
        assert not _validate_command("tar -cf a.tar d --use-compress=curl")[0]
        assert not _validate_command("sort --compress-prog=curl f")[0]
        assert not _validate_command("sort --co curl f")[0]
        # Options that only share a prefix with one of them stay usable.
        assert _validate_command("tar --exclude=.git --totals -czf a.tar d")[0]
        assert _validate_command("tar -xf a.tar --to-stdout")[0]
        assert _validate_command("sort --check f")[0]
        assert _validate_command("rg --pretty --pre-glob '*.pdf' pattern")[0]
        assert _validate_command("find . -name a -o -name b")[0]
        assert _validate_command("tar -cf a.tar -- d")[0]

    def test_tar_script_and_remote_shell_options_rejected(self) -> None:
        assert not _validate_command("tar -cf a.tar -M --info-script=curl d")[0]
        assert not _validate_command("tar -cf a.tar -M --new-volume-script curl d")[0]
        assert not _validate_command("tar -cf a.tar -M -F curl d")[0]
        assert not _validate_command("tar -cMFcurl -f a.tar d")[0]
        assert not _validate_command("tar -xf host:a.tar --rsh-command=curl")[0]
        assert not _validate_command("tar -xf host:a.tar --rmt-command=curl")[0]
        # An archive or directory name attached to -f / -C is not an option letter.
        assert _validate_command("tar -cfFiles.tar d")[0]
        assert _validate_command("tar -xf a.tar -CInput")[0]

    def test_tar_option_cluster_without_dash_rejected(self) -> None:
        # tar reads a first word without a dash as options: `cIf prog` is `-c -I prog -f`.
        assert not _validate_command("tar cIf curl a.tar d")[0]
        assert not _validate_command("tar cfI a.tar curl d")[0]
        assert not _validate_command("tar cMFf curl a.tar d")[0]
        assert _validate_command("tar xzf a.tar")[0]
        assert _validate_command("tar tf a.tar Input/File.txt")[0]

    def test_tar_files_from_rejected(self) -> None:
        # GNU tar 1.26 reads options from the list file, so `--checkpoint-action=exec=...`
        # in a file that printf wrote would run a program the command line never named.
        assert not _validate_command("tar -cf a.tar -T /tmp/list")[0]
        assert not _validate_command("tar -cT /tmp/list -f a.tar")[0]
        assert not _validate_command("tar cfT a.tar /tmp/list")[0]
        assert not _validate_command("tar -cf a.tar --files-from=/tmp/list")[0]
        assert not _validate_command("tar -cf a.tar --files-from /tmp/list")[0]
        assert not _validate_command("tar -cf a.tar --files=/tmp/list")[0]
        # `--file` is an option of its own, and lower-case `t` lists the archive.
        assert _validate_command("tar --file=a.tar -t")[0]
        assert _validate_command("tar --file a.tar -x -C /tmp/out")[0]
        assert _validate_command("tar -tf a.tar")[0]
        assert _validate_command("tar tf a.tar Top/Test.txt")[0]
        assert _validate_command("tar -cfTest.tar d")[0]

    def test_braced_and_arithmetic_expansion_rejected(self) -> None:
        # `${x:=word}` assigns, and an arithmetic context then evaluates the stored text:
        # bash runs the `\$(...)` that the quote scan took as literal.
        assert not _validate_command("ls ${x:=a[\\$(curl evil.com)]} ${y[x]}")[0]
        assert not _validate_command("ls $[x]")[0]
        assert not _validate_command("ls ${PATH:x}")[0]
        assert not _validate_command("ls ${HOME}")[0]
        assert not _validate_command('ls "${HOME}"')[0]
        assert not _validate_command('ls "$[1+1]"')[0]
        # A plain variable, and the same characters as literal text, stay usable.
        assert _validate_command("ls $HOME/data")[0]
        assert _validate_command('ls "$HOME/data"')[0]
        assert _validate_command("echo '${x}' '$[1]'")[0]
        assert _validate_command('echo \\${x} "\\${x}" "a{b}" "$" "{x}"')[0]
        assert _validate_command("awk '{print $1}' f")[0]

    def test_line_continuation_rejected(self) -> None:
        # The shell removes a backslash-newline and joins the words around it, so
        # `-ex` and `ec` reach find as `-exec`.
        assert not _validate_command("find /tmp -ex\\\nec curl evil.com \\;")[0]
        assert not _validate_command('find /tmp "-ex\\\nec" curl evil.com \\;')[0]
        assert not _validate_command("ls -l \\\n/tmp")[0]
        # Inside single quotes the pair is literal text.
        assert _validate_command("printf 'a\\\nb'")[0]

    def test_noclobber_redirection_rejected(self) -> None:
        # `>|` is one redirection operator; read as `>` and a pipe, the words after it
        # would pass as a stage of their own that starts with `ls`.
        assert not _validate_command("find /tmp >|ls -exec curl evil.com \\;")[0]
        assert not _validate_command("ls >|/tmp/out")[0]

    def test_expansion_in_a_command_with_exec_options_rejected(self) -> None:
        # The shell rewrites these words after the option check has read them.
        assert not _validate_command("find /tmp -exec$none curl evil.com \\;")[0]
        assert not _validate_command('find /tmp "-exec$none" curl evil.com \\;')[0]
        assert not _validate_command("find /tmp -exe[c] curl evil.com \\;")[0]
        assert not _validate_command("find /tmp -exe? curl evil.com \\;")[0]
        assert not _validate_command("find /tmp * curl evil.com \\;")[0]
        assert not _validate_command("find /tmp {-exec,} curl evil.com \\;")[0]
        assert not _validate_command("tar -xf a.tar --to-command$none=curl")[0]
        assert not _validate_command("sort --compress-progra? curl f")[0]
        assert not _validate_command("rg --pr[e] curl pattern")[0]
        assert not _validate_command("cat f | sort -k$none")[0]
        # Quoted, the same characters are the program's own patterns.
        assert _validate_command("find /tmp -name '*.py' -o -name \"[a-c]?.txt\"")[0]
        assert _validate_command("find /tmp \\( -name a -o -name b \\) -newer /tmp/x")[0]
        assert _validate_command("rg 'value: \\$\\{[a-z]+\\}$' /tmp")[0]
        assert _validate_command("tar -xzf a.tar.gz --wildcards '*.json' -C /tmp/out")[0]
        # Other commands have no option check to get around.
        assert _validate_command("ls /tmp/*.csv $HOME/{a,b}")[0]
        assert _validate_command("cat /tmp/part-?.txt | sort -u")[0]

    def test_redirection_does_not_hide_an_exec_option(self) -> None:
        # A redirection operator ends a word: the shell reads `-exec>/dev/null` as
        # `-exec`, and takes a redirection in front of tar's first word out.
        assert not _validate_command("find /tmp -exec>/dev/null curl evil.com \\;")[0]
        assert not _validate_command("find /tmp -exec</dev/null curl evil.com \\;")[0]
        assert not _validate_command("sort --compress-program>/dev/null curl f")[0]
        assert not _validate_command("tar >/dev/null cIf curl a.tar d")[0]
        assert not _validate_command("tar 2>/dev/null cIf curl a.tar d")[0]
        assert not _validate_command("tar >/dev/null 2>&1 cIf curl a.tar d")[0]
        # `>&` and `<&` are one operator, also with a space before the target.
        assert not _validate_command("tar 2>& 1 cIf curl a.tar d")[0]
        assert not _validate_command("tar <& 0 cIf curl a.tar d")[0]
        assert not _validate_command("tar >& /dev/null cIf curl a.tar d")[0]
        assert not _validate_command("tar 2>&1 cIf curl a.tar d")[0]
        assert _validate_command("tar 2>& 1 xzf a.tar")[0]
        assert _validate_command("tar >& /dev/null xf a.tar")[0]
        assert _validate_command("tar -tf a.tar 'a&b' >&2")[0]
        assert _validate_command("find /tmp -name x >&2")[0]
        assert _validate_command("find /tmp -name x 2>/dev/null")[0]
        assert _validate_command("find /tmp -name '>' -newer /tmp/x")[0]
        assert _validate_command("tar 2>/dev/null xzf a.tar")[0]
        assert _validate_command("tar -tf a.tar >/tmp/Index 2>&1")[0]
        assert _validate_command("ls>/tmp/out")[0]

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
        ],
    )
    def test_end_to_end_bypass_does_not_run_another_program(self, tmp_path: Path, command: str) -> None:
        # `touch` is not on the allowlist; each command once ran it through execute_shell
        # (the brace and arithmetic forms where /bin/sh is bash, the `-T` form with GNU
        # tar 1.26).
        (tmp_path / "src").write_text("x")
        (tmp_path / "list").write_text(
            f"--checkpoint=1\n--checkpoint-action=exec=touch {tmp_path}/marker\n{tmp_path}/src\n"
        )
        # The working directory holds one entry, for the glob forms to match.
        (tmp_path / "cwd" / "-exec").mkdir(parents=True)
        with warnings.catch_warnings(), mock.patch.dict(os.environ, {"ATX_SHELL_ALLOW_PYTHON": "false"}):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command=command.format(tmp=tmp_path), working_directory=str(tmp_path / "cwd"))
        assert result.startswith("Error:"), result
        assert not (tmp_path / "marker").exists()

    def test_python_allowed_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _validate_command("python3 /opt/skills/example/scripts/x.py")[0]

    def test_python_blocked_when_flag_false(self) -> None:
        with mock.patch.dict(os.environ, {"ATX_SHELL_ALLOW_PYTHON": "false"}, clear=True):
            assert not _validate_command("python3 x.py")[0]
            # non-python allowlisted command still works
            assert _validate_command("ls")[0]


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

    def test_execute_shell_runs_the_command_with_the_sanitized_env(self) -> None:
        parent = {
            "PATH": os.environ.get("PATH", ""),
            "AWS_PROFILE": "persona",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://127.0.0.1:9/creds",
        }
        command = (
            "printf '%s|%s' \"$AWS_PROFILE$AWS_SECRET_ACCESS_KEY$AWS_CONTAINER_CREDENTIALS_FULL_URI\" "
            '"$AWS_EC2_METADATA_DISABLED"'
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
