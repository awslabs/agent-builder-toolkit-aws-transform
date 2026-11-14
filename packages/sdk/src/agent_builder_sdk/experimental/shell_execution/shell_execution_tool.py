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
3. Timeout + output limits — a command is killed, with its process group, after its
   timeout (30 seconds by default, 120 at most). At most 20 KB of stdout and 10 KB of
   stderr are kept, in the agent's memory as well as in the result: the rest is read and
   dropped, so a high-volume command cannot grow the agent process.

The allowlist is not a sandbox. awk, sed and python start other programs from their
own scripts by design, a command given with a path is matched by its basename only,
and the validator is a set of rules, not a shell parser. Treat the tool as able to run
any program the container user can run; the container is the security boundary.
"""

import logging
import os
import re
import shlex
import signal
import subprocess
import threading
import time
from typing import IO, FrozenSet, List, Optional, Sequence, Tuple

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
_READ_CHUNK_BYTES = 64 * 1024

# After a timeout kill, how long to wait for the process and its output to end.
_REAP_SECONDS = 5

# Only these environment variables are passed to subprocesses. No credential vars
# are included: AWS_PROFILE and the AWS_CONTAINER_CREDENTIALS_* / AWS_WEB_IDENTITY_*
# vars are all excluded, and _NO_AMBIENT_CREDENTIALS below closes the providers that
# need no env var, so a subprocess has no ambient AWS credential chain (a bare boto3
# client fails at call time). Scripts needing AWS access use connector-vended
# temporary credentials. AWS_REGION is kept so the region resolves for those clients.
_SAFE_ENV_VARS = frozenset(
    {
        "PATH",
        # Some images install the agent's dependencies in a directory that only
        # PYTHONPATH names; without it a script's `import boto3` fails there with
        # ModuleNotFoundError.
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


def _decode(output: bytes, max_bytes: int) -> str:
    """Decode the first max_bytes of output, appending an indicator if more was cut off.

    Decodes leniently: one non-UTF-8 byte (a binary file, an odd filename) must not
    throw away the output and exit code of a command that already ran.
    """
    text = output[:max_bytes].decode("utf-8", errors="replace")
    return text + "\n[output truncated]" if len(output) > max_bytes else text


class _CappedReader(threading.Thread):
    """Reads a pipe to its end on its own thread and keeps only the first ``limit`` bytes.

    Reading to the end keeps the child from blocking on a full pipe; dropping what is over
    the limit keeps the agent's memory bounded whatever the command writes. A thread that
    is still alive after the wait is blocked on a pipe that a surviving descendant holds
    open; it is a daemon and ends when that descendant does.
    """

    def __init__(self, stream: IO[bytes], limit: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._limit = limit
        self.kept = bytearray()
        self.total_bytes = 0
        self.start()

    def run(self) -> None:
        with self._stream:
            while chunk := self._stream.read(_READ_CHUNK_BYTES):
                self.total_bytes += len(chunk)
                self.kept += chunk[: self._limit - len(self.kept)]


def _finished(proc: "subprocess.Popen[bytes]", readers: Sequence[_CappedReader], seconds: float) -> bool:
    """Wait up to ``seconds`` for the output to end and the process to exit; False if either did not."""
    deadline = time.monotonic() + seconds
    for reader in readers:
        reader.join(max(0.0, deadline - time.monotonic()))
    try:
        proc.wait(max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return False
    return not any(reader.is_alive() for reader in readers)


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
    blanked like any other quoted character. The quote that opens ``$'...'`` or
    ``$"..."`` also stays, and so does a ``{`` or ``[`` that follows ``$`` inside
    double quotes, so the operator scan can reject those forms. The newline of a
    backslash-newline pair stays as well: the shell removes the pair and joins the
    words around it, also inside double quotes.
    """
    out: list = []
    quote: str = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            out.append(" \n" if command[i + 1] == "\n" else "  ")
            i += 2
            continue
        if ch in ("'", '"') and (not quote or quote == ch):
            out.append(ch if not quote and out[-1:] == ["$"] else " ")
            quote = "" if quote else ch
        elif quote == "'":
            out.append(" ")
        elif quote == '"':
            out.append(ch if ch in "$`()" or (ch in "{[" and out[-1:] == ["$"]) else " ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


# What may stand in command position: a bare name or path. Any other first word is
# either not the command (after a redirection such as `2>/tmp/ls` or an assignment
# such as `X=/ls` the shell runs the NEXT word, and an assignment also sets a variable
# the sanitized environment left out) or a word the shell rewrites before it runs it.
_COMMAND_WORD = re.compile(r"[\w./+-]+|\[")

# Options of otherwise-useful, allowlisted commands that run the program named in
# their argument: find's exec primaries, tar's compressor, volume-script, remote-shell,
# checkpoint and per-member hooks, sort's temp-file compressor, and ripgrep's
# preprocessor and hostname helper.
_EXEC_OPTIONS = {
    "find": ("-exec", "-execdir", "-ok", "-okdir"),
    "tar": (
        "-I",
        "-F",
        "--checkpoint-action",
        "--info-script",
        "--new-volume-script",
        "--rmt-command",
        "--rsh-command",
        "--to-command",
        "--use-compress-program",
    ),
    "sort": ("--compress-program",),
    "rg": ("--pre", "--hostname-bin"),
}

# tar's -I and -F inside a cluster of short options (`-cIprog`, `-xFscript`). The
# scan stops at `f` and `C`, whose argument is the rest of the word, so an archive
# name attached to `-f` (`-cfInput.tar`) is not read as the `-I` option.
_TAR_EXEC_SHORT_OPTION = re.compile(r"-[^-fC]*[IF]")

# The option check reads the words as typed, so for the commands in _EXEC_OPTIONS the
# shell must hand them over unchanged. These characters, on the quote-masked stage, mark
# a word the shell rewrites first: `$` (also inside double quotes; `-exec$none` becomes
# `-exec`), a glob (`-exe[c]` or `*` matches a file named `-exec`) or a brace expansion
# (`{-exec,}`).
_SHELL_EXPANSION = re.compile(r"[$*?\[{]")

_REDIRECTION_OPERATOR = re.compile(r"[<>]+")


def _split_words(stage: str) -> List[str]:
    """Split one pipeline stage into words as the shell does.

    Like ``shlex.split``, and a redirection operator also ends a word: the shell reads
    ``-exec>/dev/null`` as the word ``-exec`` and a redirection. Each run of ``<`` and
    ``>`` is returned as a word of its own.

    Raises:
        ValueError: The stage has an unterminated quote or escape.
    """
    lexer = shlex.shlex(stage, posix=True, punctuation_chars="<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _first_argument(args: List[str]) -> str:
    """The first word the program gets: the shell takes leading redirections (``2>file``) out."""
    i = 0
    while i < len(args):
        # A number in front of an operator is its file descriptor.
        if args[i].isdigit() and i + 1 < len(args) and _REDIRECTION_OPERATOR.fullmatch(args[i + 1]):
            i += 1
        if not _REDIRECTION_OPERATOR.fullmatch(args[i]):
            return args[i]
        i += 2  # the operator and its target
    return ""


def _is_exec_option(arg: str, exec_options: Tuple[str, ...]) -> bool:
    name = arg.partition("=")[0]
    if name.startswith("--"):
        # GNU getopt takes any unambiguous prefix of a long option (`--to-comm` is
        # `--to-command`), so a prefix is rejected like the full name.
        return len(name) > 2 and any(option.startswith(name) for option in exec_options)
    # Single-dash names are matched whole: find's `-o` and `-executable` are not `-ok` or `-exec`.
    return name in exec_options


def _tar_short_option_runs_program(args: List[str]) -> bool:
    # tar reads a first word without a dash as a cluster in which every letter is an
    # option and the arguments follow as separate words: `tar cIf prog a.tar`.
    first = _first_argument(args)
    if not first.startswith("-") and re.search("[IF]", first):
        return True
    return any(_TAR_EXEC_SHORT_OPTION.match(arg) for arg in args)


def _validate_command(command: str) -> Tuple[bool, str, str]:
    """Validate that every command in the pipeline is on the allowlist.

    Splits on unquoted pipes (|) and checks the first word of each stage, which
    must be a plain command name or path. Rejects:

    - unquoted shell operators that would start another command (;, &, &&, ||,
      $(), ``, <(, >(, an unquoted newline). ``&`` passes only directly after
      ``<`` or ``>`` (``2>&1``); ``&>file`` is rejected because a shell without
      that operator runs the words after it as a second command;
    - ``${...}`` and ``$[...]``, also inside double quotes: they can assign a
      variable and evaluate arithmetic, and that evaluation runs a
      backslash-escaped ``$(...)`` that this check took as literal. Plain
      ``$NAME`` passes;
    - the forms on which this check and the shell would disagree about where a
      quote or a word ends ($'...', $"...", an unquoted #, a backslash-newline,
      ``>|``, an unterminated quote);
    - the exec-delegating options of otherwise-allowlisted commands (find -exec,
      tar --to-command), abbreviated or not. For those commands (find, tar, sort,
      rg) it also rejects ``$`` outside single quotes and an unquoted ``*``, ``?``,
      ``[`` or ``{``, so the words checked are the words the program gets.

    Quoted operator characters are fine — payloads like CSS (full of
    semicolons) inside python3 -c '...' or printf '...' must not trip it.

    Note: python3/awk/sed are Turing-complete and can spawn subprocesses from
    their own scripts; the allowlist trusts them by design. The rules above are
    not a shell parser: what the shell's own builtins evaluate (``printf -v`` or
    ``test -v`` with an array subscript) is not covered.

    Returns:
        (is_valid, error_message, reason) — both strings empty when valid. The message,
        for the model, may quote the command; the reason is a fixed category, safe to log.
    """
    allowed = _ALLOWED_COMMANDS | _PYTHON_COMMANDS if _python_allowed() else _ALLOWED_COMMANDS

    # Block unquoted chaining/substitution operators. Pipes (|) are allowed as
    # separators since each resulting stage is validated below; a bare ; && || &
    # $() `` <( ) >( ) or unquoted newline is not. Run on the quote-masked command
    # so operators inside quotes (e.g. python3 -c 'a; b') don't trip it. `[<>]\(`
    # catches process substitution — its inner command runs under shell=True but is
    # never seen by the per-stage allowlist check — while leaving plain redirection
    # (>, >>, <), which is not followed by `(`.
    # `(?<![<>])&` leaves `&` only where every shell reads it as part of a
    # redirection, directly after `<` or `>` (2>&1, >&2, >&file). Anywhere else it
    # backgrounds a command and runs whatever follows unchecked; that includes
    # `&>file`, which only bash reads as a redirection.
    # `\$[{\[]`: `${x:=word}` assigns and `${y[x]}`, `$[x]` and `${PATH:x}` evaluate
    # arithmetic, which runs a `\$(...)` stored in x.
    # `>\|` is a redirection, but the stage split below would take its `|` for a pipe.
    # `#` and `\$['"]` are not operators, but this check and the shell must agree on
    # where quotes open and close: the shell skips a quote character inside a
    # comment, and `$'...'` (when /bin/sh is bash) lets `\'` continue the quoted
    # text, so either one could present an operator to this check as quoted.
    if re.search(r"[;`#\n\r]|\$[('\"{\[]|[<>]\(|>\||\|\||(?<![<>])&", _mask_quoted(command)):
        return False, (
            "Error: Unquoted shell operators (;, newline, &, &&, ||, >|, $(), ``, <(, >(), "
            "${...} and $[...], an unquoted #, a backslash at the end of a line and $'...' or "
            "$\"...\" quoting are not allowed. Use pipes (|) to chain commands, $NAME for a "
            "variable, >file 2>&1 instead of &>file, and put a literal # inside plain quotes."
        ), "unquoted shell operator"

    stages = _split_on_unquoted_separators(command)
    for stage in stages:
        stage = stage.strip()
        if not stage:
            continue
        try:
            tokens = _split_words(stage)
        except ValueError:
            return False, "Error: The command has an unterminated quote or escape.", "unparsable command"
        if not tokens:
            continue

        if not _COMMAND_WORD.fullmatch(tokens[0]):
            return False, (
                "Error: A command must start with a plain command name. A variable assignment "
                "or a redirection in front of the command name is not allowed."
            ), "no plain command name in first position"

        cmd_name = os.path.basename(tokens[0])
        if cmd_name not in allowed:
            return False, (
                f"Error: Command '{cmd_name}' is not allowed. "
                f"Allowed commands: {', '.join(sorted(allowed))}"
            ), "command not on the allowlist"

        exec_options = _EXEC_OPTIONS.get(cmd_name)
        if not exec_options:
            continue
        if _SHELL_EXPANSION.search(_mask_quoted(stage)):
            return False, (
                f"Error: '{cmd_name}' arguments must not contain $ outside single quotes or an "
                f"unquoted *, ?, [ or {{: the shell would rewrite the word after it was checked "
                f"for options that run another program. Quote the pattern (for example '*.py') "
                f"and write paths out in full."
            ), "shell expansion in a command with exec options"
        args = tokens[1:]
        if any(_is_exec_option(arg, exec_options) for arg in args) or (
            cmd_name == "tar" and _tar_short_option_runs_program(args)
        ):
            return False, (
                f"Error: '{cmd_name}' options that run another program ({', '.join(exec_options)}, "
                f"also abbreviated or bundled) would bypass the allowlist and are not allowed."
            ), "exec-delegating flag"

    return True, "", ""


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
    that run an arbitrary binary (env, xargs) or exec-delegating options
    (find -exec, tar --to-command), and anything else. Unquoted shell chaining
    (;, newline, &, &&, ||, $(), ``, <(, >() is blocked; use pipes (|) instead.
    Operators inside quotes are fine. Output redirection (>, >>, 2>&1) is
    allowed after the command name; write >file 2>&1, not &>file. Each command
    must start with its name: no VAR=value and no redirection in front of it.
    $NAME is allowed, ${...} and $[...] are not. An unquoted #, a backslash at
    the end of a line and $'...' quoting are blocked; put a literal # inside
    plain quotes. In the arguments of find, tar, sort and rg, put $ in single
    quotes and quote *, ?, [ and { (for example find /tmp -name '*.py'), and
    write paths out in full.

    The command reads no input (stdin is empty). At most 20 KB of stdout and
    10 KB of stderr are kept; a result over that ends with "[output truncated]".

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

    is_valid, error_msg, reason = _validate_command(command)
    if not is_valid:
        # Log the length and fixed reason, never the text or the message: the command may
        # embed sensitive values, even in the rejected word the message quotes
        # (e.g. `KEY=secret python3 x.py`).
        logger.warning(
            "Command rejected by allowlist: command_length=%d, reason=%s", len(command), reason
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
            # Not the agent's stdin: a command that reads it (`cat`, `grep pattern`) would
            # wait until the timeout and could take input meant for the agent.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_sanitized_env(),
            start_new_session=True,
        )
        # One byte over each limit is kept so that _decode can tell that output was cut.
        stdout_reader = _CappedReader(proc.stdout, _MAX_STDOUT_BYTES + 1)
        stderr_reader = _CappedReader(proc.stderr, _MAX_STDERR_BYTES + 1)
        readers = (stdout_reader, stderr_reader)
        if not _finished(proc, readers, timeout):
            # Kill the entire process group, then reap so no orphan survives.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                # The process exited on its own between the timeout and the kill; nothing left to reap.
                pass
            # Bound the reap: a descendant that escaped the group (setsid/double-fork)
            # could hold the pipe open forever, reintroducing the very hang the timeout
            # guards against. Give up after a short grace.
            if not _finished(proc, readers, _REAP_SECONDS):
                # The primary timeout failure is already being reported, so don't
                # block the caller any longer.
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
            stdout_reader.total_bytes,
            stderr_reader.total_bytes,
        )

        stdout = _decode(bytes(stdout_reader.kept), _MAX_STDOUT_BYTES)
        stderr = _decode(bytes(stderr_reader.kept), _MAX_STDERR_BYTES)

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
