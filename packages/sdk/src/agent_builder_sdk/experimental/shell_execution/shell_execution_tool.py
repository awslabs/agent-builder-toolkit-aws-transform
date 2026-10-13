# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Command-allowlisted shell execution tool.

Lets the agent run inspection commands (ls, cat, find, grep, ...) and, when
``ATX_SHELL_ALLOW_PYTHON`` is not "false", ``python``/``python3`` — the latter is
what skill scripts are launched with.

AgentCore provides container-level isolation (each agent runs in its own
container), so filesystem sandboxing is handled at the infrastructure layer.
This tool adds application-level defense-in-depth:

1. Command allowlist — only known-safe commands are permitted
2. Sanitized environment — only safe env vars passed to subprocess. No credential
   vars are passed (AWS_PROFILE and the AWS_CONTAINER_CREDENTIALS_* URIs are all
   dropped), and the shared credential/config files and the instance metadata
   endpoint are switched off, so a subprocess boto3 client has no ambient credential
   chain and must use connector-vended temporary credentials instead.
3. Timeout + output limits — prevent runaway commands
"""

import logging
import os
import re
import shlex
import signal
import subprocess
import time
from typing import FrozenSet, Optional, Tuple

from strands.tools import tool

from agent_builder_sdk.util.decorators import experimental

logger = logging.getLogger(__name__)

# Set ATX_SHELL_ALLOW_PYTHON=false to remove python/python3 from the allowlist.
ALLOW_PYTHON_ENV_VAR = "ATX_SHELL_ALLOW_PYTHON"

# Default working directory
_DEFAULT_CWD = "/tmp"

# Timeout limits (seconds)
_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 120

# Output size limits (bytes)
_MAX_STDOUT_BYTES = 20 * 1024  # 20 KB
_MAX_STDERR_BYTES = 10 * 1024  # 10 KB

# Only these environment variables are passed to subprocesses. No credential vars
# are included: AWS_PROFILE and the AWS_CONTAINER_CREDENTIALS_* / AWS_WEB_IDENTITY_*
# vars are all excluded, and _NO_AMBIENT_CREDENTIALS below closes the providers that
# need no env var, so a subprocess has no ambient AWS credential chain (a bare boto3
# client fails at call time). Scripts needing AWS access use connector-vended
# temporary credentials. AWS_REGION is kept so the region resolves for those clients.
_SAFE_ENV_VARS = frozenset(
    {
        "PATH",
        # boto3/botocore live in /usr/local but their deps (s3transfer, dateutil,
        # etc.) are only on the base-agent site-packages that PYTHONPATH points at;
        # without it a script's `import boto3` fails with ModuleNotFoundError.
        "PYTHONPATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TMPDIR",
        "TZ",
        "USER",
        "LOGNAME",
        "SHELL",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    }
)

# Set in every subprocess env. botocore also finds credentials without any env var:
# in ~/.aws/credentials and ~/.aws/config under the forwarded HOME, in the legacy
# ~/.boto and /etc/boto.cfg, and from the instance metadata endpoint (on AgentCore,
# the MicroVM metadata service hands out the execution role). Point the files at
# /dev/null and switch the metadata lookup off.
_NO_AMBIENT_CREDENTIALS = {
    "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
    "AWS_CONFIG_FILE": os.devnull,
    "BOTO_CONFIG": os.devnull,
    "AWS_EC2_METADATA_DISABLED": "true",
}

# Commands allowlisted only when ATX_SHELL_ALLOW_PYTHON is not "false".
_PYTHON_COMMANDS: FrozenSet[str] = frozenset({"python", "python3"})

_ALLOWED_COMMANDS: FrozenSet[str] = frozenset(
    {
        # Directory listing / tree
        "ls",
        "tree",
        "du",
        "stat",
        "file",
        "readlink",
        # Cleanup
        "rm",
        "rmdir",
        "mkdir",
        # File reading
        "cat",
        "head",
        "tail",
        "less",
        "more",
        # Search
        "find",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        # Text processing (read-only)
        "awk",
        "sed",
        "cut",
        "sort",
        "uniq",
        "wc",
        "tr",
        "diff",
        "comm",
        "paste",
        "column",
        "fmt",
        "fold",
        "nl",
        "strings",
        "hexdump",
        "xxd",
        "od",
        # Archive inspection and extraction
        "unzip",
        "tar",
        "gzip",
        "gunzip",
        "zcat",
        "bzip2",
        "bunzip2",
        "bzcat",
        "xz",
        "unxz",
        "xzcat",
        "jar",
        "zipinfo",
        # Misc inspection
        "echo",
        "printf",
        "pwd",
        "basename",
        "dirname",
        "realpath",
        "sha256sum",
        "md5sum",
        "date",
        "true",
        "false",
        "test",
        "[",
        "expr",
        "seq",
        "yes",
    }
)


def _python_allowed() -> bool:
    return os.environ.get(ALLOW_PYTHON_ENV_VAR, "true").lower() != "false"


def _sanitized_env() -> dict:
    """Build a minimal environment dict with only safe variables and no credential sources."""
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_VARS}
    env.update(_NO_AMBIENT_CREDENTIALS)
    return env


def _truncate(text: str, max_bytes: int) -> str:
    """Truncate text to max_bytes (UTF-8), appending an indicator if truncated."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
    return truncated + "\n[output truncated]"


def _split_on_unquoted_separators(command: str) -> list:
    """Split on ``|`` and newlines that are not inside single or double quotes."""
    stages: list = [""]
    quote: str = ""  # current quote char, or empty
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            stages[-1] += ch + command[i + 1]
            i += 2
        elif ch in ("'", '"') and (not quote or quote == ch):
            quote = "" if quote else ch
            stages[-1] += ch
            i += 1
        elif ch in ("|", "\n", "\r") and not quote:
            stages.append("")
            i += 1
        else:
            stages[-1] += ch
            i += 1
    return stages


def _mask_quoted(command: str) -> str:
    """Blank out characters the shell treats as literal, for the operator check.

    Single-quoted content and backslash-escaped characters are fully literal —
    blanked. Inside double quotes ``$`` and backticks STAY ACTIVE (command
    substitution still runs there in a real shell), so those are preserved,
    along with parens so the ``$(`` pattern survives; everything else quoted
    is blanked. An unquoted newline stays unmasked so the operator scan catches
    it as a command separator; a quoted newline is literal content and is
    blanked like any other quoted character.
    """
    out: list = []
    quote: str = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            out.append("  ")
            i += 2
            continue
        if ch in ("'", '"') and (not quote or quote == ch):
            quote = "" if quote else ch
            out.append(" ")
        elif quote == "'":
            out.append(" ")
        elif quote == '"':
            out.append(ch if ch in "$`()" else " ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


# Commands whose whole job is to run another command from their arguments. The
# allowlist only checks the first token of each stage, so these would let any
# non-allowlisted binary (and, via `env KEY=VALUE`, a re-injected AWS_PROFILE)
# run through the allowlisted wrapper. They are NOT on the allowlist; this set
# guards against re-adding them and gives a clear error if a model tries one.
_COMMAND_WRAPPERS: FrozenSet[str] = frozenset({"env", "xargs", "nice", "nohup", "timeout", "time"})

# Flags on otherwise-useful, allowlisted commands that hand execution to an
# arbitrary child process. These are matched whole-word (== or flag=VALUE), which
# is correct for find's primaries — matching a prefix would wrongly reject the
# safe `find -executable` because it startswith `-exec` — and for tar/sort/rg long
# options. tar's SHORT `-I` is handled separately below because it also has
# attached/bundled getopt forms (`-Iprog`, `-cIprog`) that a whole-word check misses.
_EXEC_FLAG_PATTERNS = (
    ("find", ("-exec", "-execdir", "-ok", "-okdir")),
    ("tar", ("--checkpoint-action", "--to-command", "--use-compress-program")),
    # sort --compress-program=PROG runs PROG to (de)compress temp files; ripgrep
    # --pre=CMD / --hostname-bin=CMD each exec CMD. Same escape as find -exec.
    ("sort", ("--compress-program",)),
    ("rg", ("--pre", "--hostname-bin")),
)

# tar -I / --use-compress-program runs an arbitrary program. The long form is in
# the table above; the short form attaches its argument in getopt style, so it
# appears as `-Iprog`, `-cIprog` (bundled after no-arg flags), or a bare `-I`
# with the program as the next token. This matches an `I` inside any single-dash
# cluster, stopping the letter run at `f`/`F` so an archive name attached to
# `-f` (e.g. `-fInput.tar`) is not mistaken for the `-I` option.
_TAR_COMPRESS_SHORT_FLAG = re.compile(r"-[^-fF]*I")


def _validate_command(command: str) -> Tuple[bool, str]:
    """Validate that every command in the pipeline is on the allowlist.

    Splits on unquoted pipes (|) and newlines and checks the first token of
    each stage. Rejects unquoted shell operators that could bypass the
    allowlist (;, &&, ||, $(), ``, unquoted newline) and the exec-delegating
    flags of otherwise-allowlisted commands (find -exec, tar --to-command).
    Quoted operator characters are fine — payloads like CSS (full of
    semicolons) inside python3 -c '...' or printf '...' must not trip it.

    Note: python3/awk/sed are Turing-complete and can spawn subprocesses from
    their own scripts; the allowlist trusts them by design. This validator
    stops shell-level bypasses, not intentional code execution by a trusted
    interpreter.

    Returns:
        (is_valid, error_message) — error_message is empty when valid.
    """
    allowed = _ALLOWED_COMMANDS | _PYTHON_COMMANDS if _python_allowed() else _ALLOWED_COMMANDS

    # Block unquoted chaining/substitution operators. Pipes (|) and newlines are
    # allowed as separators since each resulting stage is validated below; a
    # bare ; && || & $() `` <( ) >( ) or unquoted newline is not. Run on the
    # quote-masked command so operators inside quotes (e.g. python3 -c 'a; b')
    # don't trip it. `[<>]\(` catches process substitution — its inner command
    # runs under shell=True but is never seen by the per-stage allowlist check —
    # while leaving plain redirection (>, >>, <), which is not followed by `(`.
    # `(?<![>&])&(?![>&])` catches a lone `&`, which backgrounds a command and
    # runs whatever follows unchecked, while leaving the redirection forms that
    # legitimately contain it: in 2>&1 / 1>&2 / >& / &> the `&` always sits beside
    # a `>` (never directly after a bare digit), so those pass and `-5&curl` does not.
    if re.search(r"[;`\n\r]|\$\(|[<>]\(|&&|\|\||(?<![>&])&(?![>&])", _mask_quoted(command)):
        return False, (
            "Error: Unquoted shell operators (;, newline, &, &&, ||, $(), ``, <(, >() are not "
            "allowed. Use pipes (|) to chain commands."
        )

    stages = _split_on_unquoted_separators(command)
    for stage in stages:
        stage = stage.strip()
        if not stage:
            continue
        try:
            tokens = shlex.split(stage)
        except ValueError:
            # shlex can't parse — let it through to subprocess which will also fail
            tokens = stage.split()
        if not tokens:
            continue

        cmd_name = os.path.basename(tokens[0])
        if cmd_name not in allowed:
            return False, (
                f"Error: Command '{cmd_name}' is not allowed. "
                f"Allowed commands: {', '.join(sorted(allowed))}"
            )

        if cmd_name in _COMMAND_WRAPPERS:
            return False, (
                f"Error: '{cmd_name}' runs another command from its arguments, which would "
                f"bypass the allowlist. Run the target command directly instead."
            )

        for wrapper, exec_flags in _EXEC_FLAG_PATTERNS:
            if cmd_name == wrapper and any(
                token == flag or token.startswith(flag + "=")
                for token in tokens[1:]
                for flag in exec_flags
            ):
                return False, (
                    f"Error: '{cmd_name}' with an exec flag ({', '.join(exec_flags)}) can run an "
                    f"arbitrary command, which would bypass the allowlist."
                )

        if cmd_name == "tar" and any(
            _TAR_COMPRESS_SHORT_FLAG.match(token) for token in tokens[1:] if token.startswith("-")
        ):
            return False, (
                "Error: 'tar' with -I (--use-compress-program) can run an arbitrary command, "
                "which would bypass the allowlist."
            )

    return True, ""


@tool
@experimental("Shell runs in-container without a sandbox beyond the command allowlist.")
def execute_shell(
    command: str,
    working_directory: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
) -> str:
    """Execute a shell command in the agent's container environment.

    Use this to explore downloaded artifact contents, extract archives, run
    bundled skill scripts (via ``python``/``python3``), or clean up temp files.

    Only allowlisted commands are permitted: file inspection (ls, cat, head,
    tail, find, grep, wc, file, tree, diff), text processing (awk, sed, sort,
    uniq, cut, tr), archive handling (unzip, tar, gzip), cleanup (rm, rmdir,
    mkdir), and python/python3 (unless ATX_SHELL_ALLOW_PYTHON=false). Blocked:
    network (curl, wget, ssh), package managers (pip, npm), command wrappers
    that run an arbitrary binary (env, xargs) or exec-delegating flags
    (find -exec, tar --to-command), and anything else. Unquoted shell chaining
    (;, newline, &&, ||, $(), ``, <(, >() is blocked; use pipes (|) instead.
    Operators inside quotes are fine. Output redirection (>, >>) is allowed.

    The subprocess has no AWS credentials: AWS_PROFILE is stripped, no
    credential env vars are passed, and the shared credential/config files and
    instance metadata are switched off, so a bare boto3 client will fail at call
    time even though `import boto3` resolves (PYTHONPATH is kept). Scripts that
    need AWS access must use connector-vended temporary credentials rather than
    ambient ones.

    Args:
        command: The shell command to execute. Only allowlisted commands are permitted.
        working_directory: Working directory for the command. Defaults to /tmp.
        timeout_seconds: Maximum execution time in seconds (1-120). Defaults to 30.

    Returns:
        Command output (stdout/stderr) and exit code.
    """
    if not command or not command.strip():
        return "Error: Command cannot be empty."

    is_valid, error_msg = _validate_command(command)
    if not is_valid:
        # Log the length and reason, never the text: the command may embed sensitive
        # values, even in the rejected word the reason quotes (e.g. `KEY=secret python3 x.py`).
        logger.warning(
            "Command rejected by allowlist: command_length=%d, reason=%s",
            len(command),
            re.sub(r"'[^']*'", "'<redacted>'", error_msg),
        )
        return error_msg

    cwd = working_directory or _DEFAULT_CWD
    if not os.path.isdir(cwd):
        return f"Error: Working directory does not exist: {cwd}"

    timeout = _DEFAULT_TIMEOUT
    if timeout_seconds is not None:
        try:
            timeout = int(timeout_seconds)
        except (ValueError, TypeError):
            timeout = _DEFAULT_TIMEOUT
    timeout = max(1, min(timeout, _MAX_TIMEOUT))

    # Log command length, not content — the command may embed sensitive values.
    logger.info(
        "execute_shell starting: command_length=%d, cwd=%s, timeout=%ds",
        len(command),
        cwd,
        timeout,
    )

    start_time = time.monotonic()
    try:
        # Run in its own session/process group so a timeout kills the whole tree,
        # not just the top-level shell. subprocess.run(timeout=) would SIGKILL only
        # the direct child, orphaning any descendant (e.g. a python3 skill script)
        # to run past the deadline — defeating the runaway-command protection.
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # Decode leniently: one non-UTF-8 byte (a binary file, an odd filename)
            # must not throw away the output and exit code of a command that already
            # ran, nor mask the timeout message on the post-kill reap.
            encoding="utf-8",
            errors="replace",
            env=_sanitized_env(),
            start_new_session=True,
        )
        try:
            stdout_raw, stderr_raw = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill the entire process group, then reap so no orphan survives.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                # The process exited on its own between the timeout and the kill; nothing left to reap.
                pass
            # Bound the reap: a descendant that escaped the group (setsid/double-fork)
            # could hold the pipe open and hang communicate() forever, reintroducing
            # the very hang the timeout guards against. Give up after a short grace.
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                # The reap wait also timed out; the primary timeout failure is already
                # being reported, so don't block the caller any longer.
                logger.debug("post-timeout reap timed out; continuing")
            logger.error(
                "execute_shell timed out after %ds (command_length=%d)", timeout, len(command)
            )
            return f"Error: Command timed out after {timeout} seconds."

        duration = time.monotonic() - start_time
        logger.info(
            "execute_shell completed: exit_code=%d, duration=%.2fs, "
            "stdout_bytes=%d, stderr_bytes=%d",
            proc.returncode,
            duration,
            len(stdout_raw) if stdout_raw else 0,
            len(stderr_raw) if stderr_raw else 0,
        )

        # Output is buffered fully then truncated, so the byte caps bound the
        # returned text, not peak memory: an allowlisted high-volume command
        # (`yes`, `cat` of a huge file) can accumulate for up to `timeout` before
        # being cut off. Acceptable for this timeout-bounded sample tool; switch to
        # an incremental read with a running cap + early kill if memory matters.
        stdout = _truncate(stdout_raw, _MAX_STDOUT_BYTES) if stdout_raw else ""
        stderr = _truncate(stderr_raw, _MAX_STDERR_BYTES) if stderr_raw else ""

        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        parts.append(f"[exit code: {proc.returncode}]")

        return "\n".join(parts)

    except Exception as e:
        logger.error("Shell execution error: %s", e, exc_info=True)
        return f"Error: Shell execution failed: {e}"
