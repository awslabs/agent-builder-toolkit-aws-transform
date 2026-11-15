# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Command-allowlisted execution tool.

Lets the agent run inspection commands (ls, cat, find, grep, ...) and, when
``ATX_SHELL_ALLOW_PYTHON`` is not "false", ``python``/``python3`` — the latter is
what skill scripts are launched with.

This is not a shell, and no shell reads the command. The tool reads it in the grammar
below and starts each program itself with the argument list it read:

    command      = stage { "|" stage }
    stage        = ( word | redirection ) { word | redirection }
    redirection  = "2>&1" | ">/dev/null" | "1>/dev/null" | "2>/dev/null"

- Words are separated by spaces and tabs. A word is made of plain characters,
  'single-quoted' text (every character literal), "double-quoted" text (a backslash
  makes ``"``, ``\\``, ``$`` and a backtick literal) and backslash escapes (the next
  character is literal).
- An unquoted ``*``, ``?`` or ``[`` makes the word a file-name pattern. It is replaced
  by the sorted matches of Python's ``glob`` in the working directory, or left as
  written when nothing matches. There is no other expansion. A quoted or escaped
  character inside an unquoted ``[...]``, and a class such as ``[[:digit:]]``, are
  rejected: ``glob`` would read them differently from a shell.
- ``|`` connects the stdout of a stage to the stdin of the next with an OS pipe. The
  exit code is that of the last stage.
- A redirection is a word of its own (``> /dev/null`` with a space is read too) and is
  not an argument. Redirections apply in the order written.
- The first word of a stage, after pattern expansion, is the program: a name on the
  allowlist, without a path. Its file is looked up in the absolute directories of the
  sanitized PATH.
- Everything else that a shell would act on is rejected, not run: ``;``, ``&``, ``&&``,
  ``||``, every other redirection, ``$`` and backticks outside single quotes,
  parentheses, ``{``, a leading ``~`` or ``#``, an assignment in front of a program, a
  line break outside quotes and a backslash at the end of a line.

AgentCore provides container-level isolation (each agent runs in its own
container), so filesystem sandboxing is handled at the infrastructure layer.
This tool adds application-level defense-in-depth:

1. Command allowlist — only known-safe commands are permitted, and the options of
   find, tar, sort and rg that run another program are rejected. The option check
   reads the argument list the program gets, after pattern expansion.
2. Sanitized environment — only safe env vars passed to subprocess. No credential
   vars are passed (AWS_PROFILE and the AWS_CONTAINER_CREDENTIALS_* URIs are all
   dropped), and the shared credential/config files and the instance metadata
   endpoint are switched off, so a subprocess boto3 client has no ambient credential
   chain and must use connector-vended temporary credentials instead.
3. Timeout + output limits — a command is killed, with the process group of every
   stage, after its timeout (30 seconds by default, 120 at most), which counts from
   before pattern expansion. At most 20 KB of stdout and 10 KB of stderr are kept, in
   the agent's memory as well as in the result: the rest is read and dropped, so a
   high-volume command cannot grow the agent process.

The allowlist is not a sandbox. awk, sed and python start other programs from their
own scripts by design. Treat the tool as able to run any program the container user
can run; the container is the security boundary.
"""

import contextlib
import glob
import itertools
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import IO, Dict, FrozenSet, Iterator, List, NamedTuple, Optional, Sequence, Tuple

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

# After a timeout kill, how long to wait for the processes and their output to end.
_REAP_SECONDS = 5

# Most file names one pattern may expand to. The matches are held in the agent's memory.
_MAX_PATTERN_MATCHES = 10_000

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

    def __init__(self, fd: int, limit: int) -> None:
        super().__init__(daemon=True)
        # The reader owns the descriptor from here on: run() closes it at end of input.
        self._stream: IO[bytes] = os.fdopen(fd, "rb")
        self._limit = limit
        self.kept = bytearray()
        self.total_bytes = 0
        self.start()

    def run(self) -> None:
        with self._stream:
            while chunk := self._stream.read(_READ_CHUNK_BYTES):
                self.total_bytes += len(chunk)
                self.kept += chunk[: self._limit - len(self.kept)]


def _finished(
    procs: Sequence["subprocess.Popen[bytes]"], readers: Sequence[_CappedReader], seconds: float
) -> bool:
    """Wait up to ``seconds`` for the output to end and every process to exit; False if either did not."""
    deadline = time.monotonic() + seconds
    for reader in readers:
        reader.join(max(0.0, deadline - time.monotonic()))
    try:
        for proc in procs:
            proc.wait(max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return False
    return not any(reader.is_alive() for reader in readers)


def _kill(procs: Sequence["subprocess.Popen[bytes]"]) -> None:
    """SIGKILL the process group of every stage, so that no descendant outlives the command."""
    for proc in procs:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            # The stage and its descendants ended on their own.
            pass


class _Rejected(Exception):
    """The command is outside the grammar, the allowlist or the option rules."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.message = message  # for the model; may quote the command
        self.reason = reason  # a fixed category, safe to log


class _Word(NamedTuple):
    text: str  # quotes and escapes removed
    pattern: Optional[str]  # set when the word has an unquoted *, ? or [; quoted ones are escaped in it


# (2, 1) is 2>&1; (1, None) and (2, None) send stdout and stderr to /dev/null.
_Redirection = Tuple[int, Optional[int]]


class _Stage(NamedTuple):
    argv: List[str]
    redirections: List[_Redirection]


_MAGIC = re.compile("[*?[]")  # the characters that make glob read a pattern
_REDIRECTION = re.compile(r"(?:2>&1|([12]?)>[ \t]*/dev/null)(?=[ \t|]|\Z)")

# Unquoted characters that a shell acts on and this tool does not; `$` and the backtick
# also inside double quotes. The text names the form in the error message.
_UNSUPPORTED = {
    ";": "';' between commands",
    "&": "'&' (a background command, '&&', '&>')",
    "(": "a parenthesis (a subshell, a process substitution)",
    ")": "a parenthesis (a subshell, a process substitution)",
    "<": "'<' (input from a file, a here-document)",
    ">": "a redirection other than 2>&1, >/dev/null and 2>/dev/null (each a word of its own)",
    "$": "'$' outside single quotes (a variable, $(...), ${...}, $((...)), $'...')",
    "`": "a backtick outside single quotes (command substitution)",
    "{": "an unquoted '{' (brace expansion)",
    "\n": "a line break outside quotes",
    "\r": "a line break outside quotes",
}

_SYNTAX = (
    "execute_shell is not a shell. It runs allowlisted programs joined by pipes (|). The only "
    "other syntax is 'single quotes', \"double quotes\", backslash escapes, the file-name "
    "patterns *, ? and [...], and the redirections 2>&1, >/dev/null and 2>/dev/null."
)


def _unsupported(form: str) -> _Rejected:
    return _Rejected(f"Error: {form} is not supported. {_SYNTAX}", "unsupported shell syntax")


def _split_stages(command: str) -> List[Tuple[List[_Word], List[_Redirection]]]:
    """Read ``command`` in the grammar of the module docstring: the words and redirections of each stage.

    Raises:
        _Rejected: The command has a form that is not in the grammar.
    """
    stages: List[Tuple[List[_Word], List[_Redirection]]] = [([], [])]
    text: List[str] = []
    pattern: List[str] = []
    in_word = is_pattern = False
    quote = ""
    # The members after an unquoted [ that no unquoted ] has closed yet. glob.escape writes a
    # quoted *, ? or [ as [c], which inside a bracket would close it, and a quoted ! or ] bare.
    bracket: Optional[str] = None

    def end_word() -> None:
        nonlocal in_word, is_pattern, bracket
        if in_word:
            stages[-1][0].append(_Word("".join(text), "".join(pattern) if is_pattern else None))
        text.clear()
        pattern.clear()
        in_word = is_pattern = False
        bracket = None

    i = 0
    while i < len(command):
        ch, following = command[i], command[i + 1 : i + 2]
        i += 1
        literal = ""
        plain = False
        if ch == quote:
            quote = ""
        elif quote == "'" or (quote and ch not in "\\$`"):
            literal = ch
        elif ch == "\\" and (not quote or following in ('"', "\\", "$", "`", "\n")):
            if not following:
                raise _Rejected("Error: The command ends with a backslash.", "unterminated quote or escape")
            if following == "\n":
                raise _unsupported("a backslash at the end of a line")
            literal = following
            i += 1
        elif ch == "\\":
            literal = ch  # inside double quotes, in front of any other character
        elif quote:
            raise _unsupported(_UNSUPPORTED[ch])
        elif ch in ("'", '"'):
            quote = ch
            in_word = True  # '' is a word: an empty argument
        elif ch in " \t":
            end_word()
        elif ch == "|":
            if following in ("|", "&"):
                raise _unsupported(f"'|{following}'")
            end_word()
            stages.append(([], []))
        elif not in_word and (redirection := _REDIRECTION.match(command, i - 1)):
            stages[-1][1].append((2, 1) if redirection[1] is None else (int(redirection[1] or 1), None))
            i = redirection.end()
        elif ch in _UNSUPPORTED:
            raise _unsupported(_UNSUPPORTED[ch])
        elif ch in "#~" and not in_word:
            raise _unsupported("a word that starts with '#' (a comment) or '~' (a home directory)")
        elif ch in "*?[":
            if bracket is not None and ch == "[" and following in (":", ".", "="):
                raise _unsupported("a character class inside [...] ([[:digit:]], [[.a.]], [[=a=]])")
            if bracket is not None:
                bracket += ch
            elif ch == "[":
                bracket = ""
            in_word = is_pattern = True
            text.append(ch)
            pattern.append(ch)
        else:
            literal = ch
            plain = True
        if literal:
            if bracket is not None:
                if not plain:
                    raise _unsupported("a quoted or escaped character inside an unquoted [...]")
                # A ] first in the bracket is a member ([]a], [!]a]); glob does not read one across a /.
                closes = literal == "/" or (literal == "]" and bracket not in ("", "!"))
                bracket = None if closes else bracket + literal
            in_word = True
            text.append(literal)
            pattern.append(glob.escape(literal))
    if quote:
        raise _Rejected("Error: The command has an unterminated quote.", "unterminated quote or escape")
    end_word()
    if not all(words for words, _ in stages):
        raise _Rejected(
            "Error: A program name is missing: the command, or one side of a pipe (|), is empty.",
            "empty pipeline stage",
        )
    return stages


def _expand(word: _Word, cwd: str, deadline: float) -> List[str]:
    """The sorted file names that match the word's pattern; the word itself without a pattern or a match.

    Raises:
        _Rejected: More than ``_MAX_PATTERN_MATCHES`` names match, or ``time.monotonic()``
            passes ``deadline`` before every directory that the pattern names has been read.
    """
    if word.pattern is None:
        return [word.text]
    matches = list(itertools.islice(_glob(word.pattern, cwd, deadline), _MAX_PATTERN_MATCHES + 1))
    if len(matches) > _MAX_PATTERN_MATCHES:
        raise _Rejected(
            f"Error: A file-name pattern matches more than {_MAX_PATTERN_MATCHES} names. Narrow the pattern.",
            "pattern with too many matches",
        )
    return sorted(matches) or [word.text]


def _glob(pattern: str, cwd: str, deadline: float) -> Iterator[str]:
    """The matches of ``glob.iglob(pattern, root_dir=cwd)``, with ``deadline`` checked before each directory read."""
    # One iglob call reads every directory of a pattern such as /*/*/*/x before it yields
    # a name, and cannot be stopped; one call per directory of the parent pattern can be.
    parent, name = os.path.split(pattern)
    parents = _glob(parent, cwd, deadline) if parent != pattern and _MAGIC.search(parent) else [parent]
    for directory in parents:
        if time.monotonic() > deadline:
            raise _Rejected(
                "Error: A file-name pattern took too long to expand. Narrow the pattern.",
                "pattern expansion timed out",
            )
        yield from glob.iglob(os.path.join(glob.escape(directory), name), root_dir=cwd)


# Options of otherwise-useful, allowlisted commands that run the program named in
# their argument: find's exec primaries, tar's compressor, volume-script, remote-shell,
# checkpoint and per-member hooks, sort's temp-file compressor, and ripgrep's
# preprocessor and hostname helper. tar's -T / --files-from is listed with them: older
# GNU tar (1.26, for one) reads options, these included, from the list file, which a
# command of the allowlist can write.
_EXEC_OPTIONS = {
    "find": ("-exec", "-execdir", "-ok", "-okdir"),
    "tar": (
        "-I",
        "-F",
        "-T",
        "--files-from",
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

# tar's -I, -F and -T inside a cluster of short options (`-cIprog`, `-xFscript`). The
# scan stops at `f` and `C`, whose argument is the rest of the word, so an archive
# name attached to `-f` (`-cfInput.tar`) is not read as the `-I` option.
_TAR_EXEC_SHORT_OPTION = re.compile(r"-[^-fC]*[IFT]")


def _is_exec_option(arg: str, exec_options: Tuple[str, ...]) -> bool:
    name = arg.partition("=")[0]
    if name.startswith("--"):
        # GNU getopt takes any unambiguous prefix of a long option (`--to-comm` is
        # `--to-command`), so a prefix is rejected like the full name. An exact name
        # wins over a prefix: tar's `--file` is not `--files-from`.
        return len(name) > 2 and name != "--file" and any(option.startswith(name) for option in exec_options)
    # Single-dash names are matched whole: find's `-o` and `-executable` are not `-ok` or `-exec`.
    return name in exec_options


def _tar_short_option_runs_program(args: List[str]) -> bool:
    # tar reads a first word without a dash as a cluster in which every letter is an
    # option and the arguments follow as separate words: `tar cIf prog a.tar`.
    if args and not args[0].startswith("-") and re.search("[IFT]", args[0]):
        return True
    return any(_TAR_EXEC_SHORT_OPTION.match(arg) for arg in args)


def _parse_command(command: str, cwd: str, deadline: float) -> List[_Stage]:
    """The stages of ``command``, each with the exact argument list its program gets.

    Reads the command in the grammar of the module docstring, expands file-name patterns
    in ``cwd`` until ``deadline`` (a ``time.monotonic()`` value), and then checks every
    stage: the program name is on the allowlist and has no path, and the arguments hold
    none of the options in ``_EXEC_OPTIONS``, abbreviated or bundled, nor tar's -T /
    --files-from, which can bring them in from a file.

    Note: python3/awk/sed are Turing-complete and can spawn subprocesses from
    their own scripts; the allowlist trusts them by design.

    Raises:
        _Rejected: The command is outside the grammar, the allowlist or the option rules, or a
            pattern has too many matches or is not expanded by the deadline.
    """
    if "\0" in command:
        raise _Rejected("Error: The command contains a NUL character.", "unsupported shell syntax")
    allowed = _ALLOWED_COMMANDS | _PYTHON_COMMANDS if _python_allowed() else _ALLOWED_COMMANDS

    stages: List[_Stage] = []
    for words, redirections in _split_stages(command):
        argv = [argument for word in words for argument in _expand(word, cwd, deadline)]
        name, args = argv[0], argv[1:]
        if "=" in name:
            raise _Rejected(
                f"Error: A variable assignment in front of a program (NAME=value) is not supported. {_SYNTAX}",
                "assignment before the command",
            )
        if "/" in name:
            # A path could name a file that the agent wrote; a bare name is looked up in PATH.
            raise _Rejected(
                f"Error: Give the program by its name ('{os.path.basename(name)}'), not by a path.",
                "command given with a path",
            )
        if name not in allowed:
            raise _Rejected(
                f"Error: Command '{name}' is not allowed. Allowed commands: {', '.join(sorted(allowed))}",
                "command not on the allowlist",
            )
        exec_options = _EXEC_OPTIONS.get(name)
        if exec_options and (
            any(_is_exec_option(arg, exec_options) for arg in args)
            or (name == "tar" and _tar_short_option_runs_program(args))
        ):
            raise _Rejected(
                f"Error: '{name}' options that run another program ({', '.join(exec_options)}, "
                f"also abbreviated or bundled) would bypass the allowlist and are not allowed.",
                "exec-delegating flag",
            )
        stages.append(_Stage(argv, redirections))
    return stages


def _start(
    stages: Sequence[_Stage], programs: Sequence[str], cwd: str, env: Dict[str, str]
) -> Tuple[List["subprocess.Popen[bytes]"], _CappedReader, _CappedReader]:
    """Start every stage without a shell, the stages connected by OS pipes.

    ``programs`` holds the executable file of each stage; the program still gets its
    name as typed in ``argv[0]``.

    Each stage is the leader of a session and a process group of its own, so a timeout
    can kill it with its descendants. The first stage reads an empty stdin: not the
    agent's, which a command would wait on and could take input from.

    Returns:
        The processes, and the readers of the last stage's stdout and of the stderr that
        the stages share.
    """
    procs: List["subprocess.Popen[bytes]"] = []
    # The parent's copies of the descriptors it hands to the stages are closed when the
    # block ends, on every path: a pipe ends only when no copy of its write end is open,
    # and a stage gets SIGPIPE only when no copy of the read end is.
    with contextlib.ExitStack() as parent_copies:
        devnull = os.open(os.devnull, os.O_RDWR)
        parent_copies.callback(os.close, devnull)
        stderr_read, stderr_write = os.pipe()
        parent_copies.callback(os.close, stderr_write)
        # One byte over each limit is kept so that _decode can tell that output was cut.
        stderr_reader = _CappedReader(stderr_read, _MAX_STDERR_BYTES + 1)
        stdin = devnull
        try:
            for stage, program in zip(stages, programs):
                stdout_read, stdout_write = os.pipe()
                parent_copies.callback(os.close, stdout_write)
                if stage is stages[-1]:
                    stdout_reader = _CappedReader(stdout_read, _MAX_STDOUT_BYTES + 1)
                else:
                    parent_copies.callback(os.close, stdout_read)
                streams = {1: stdout_write, 2: stderr_write}
                for stream, source in stage.redirections:
                    streams[stream] = devnull if source is None else streams[source]
                procs.append(
                    subprocess.Popen(
                        stage.argv,
                        executable=program,
                        stdin=stdin,
                        stdout=streams[1],
                        stderr=streams[2],
                        cwd=cwd,
                        env=env,
                        start_new_session=True,
                    )
                )
                stdin = stdout_read
        except BaseException:
            _kill(procs)
            for proc in procs:
                proc.wait()
            raise
    return procs, stdout_reader, stderr_reader


@tool
@experimental("Programs run in the agent container without a sandbox beyond the command allowlist.")
def execute_shell(
    command: str,
    working_directory: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
) -> str:
    """Run allowlisted programs in the agent's container. This is not a shell.

    Use this to explore downloaded artifact contents, extract archives, run
    bundled skill scripts (via ``python``/``python3``), or clean up temp files.

    Only allowlisted programs are permitted: file inspection (ls, cat, head,
    tail, find, grep, wc, file, tree, diff), text processing (awk, sed, sort,
    uniq, cut, tr), archive handling (unzip, tar, gzip), cleanup (rm, rmdir,
    mkdir), and python/python3 (unless ATX_SHELL_ALLOW_PYTHON=false). Give the
    program by its name, not by a path. Blocked: network (curl, wget, ssh),
    package managers (pip, npm), command wrappers that run an arbitrary binary
    (env, xargs), the options that run another program (find -exec,
    tar --to-command, tar -I, tar -T, sort --compress-program, rg --pre), and
    anything else.

    No shell reads the command. The whole syntax is:

    - ``program arg ... | program arg ...``: pipes; the exit code is that of
      the last program.
    - 'single quotes' (every character literal), "double quotes" and backslash
      escapes.
    - An unquoted *, ? or [...] is matched against file names in the working
      directory (sorted; left as written when nothing matches). Inside an unquoted
      [...], quotes, backslashes and classes such as [[:digit:]] are rejected.
    - 2>&1, >/dev/null and 2>/dev/null, each as a word of its own.

    Everything else that a shell would act on is rejected and nothing runs:
    ; && || &, $NAME, $(...), ${...}, backticks, any other redirection
    (> file, >> file, < file, <<EOF), parentheses, {a,b}, a leading ~ or #,
    NAME=value in front of a program, and a line break outside quotes. Put a
    literal $ or backtick in single quotes and write paths in full (no $HOME,
    no ~). Make one call for each command instead of chaining. To write a
    file, use an option of the program (sort -o, tar -f, unzip -d) or a script.

    The command reads no input (stdin is empty). At most 20 KB of stdout and
    10 KB of stderr are kept; a result over that ends with "[output truncated]".

    The AWS SDK and CLI find no credentials in the subprocess by default:
    AWS_PROFILE is stripped, no credential env vars are passed, and the shared
    credential/config files and instance metadata are switched off, so a bare
    boto3 client will fail at call time even though `import boto3` resolves
    (PYTHONPATH is kept). Scripts that need AWS access must use connector-vended
    temporary credentials rather than ambient ones.

    Args:
        command: The programs to run, in the syntax above. Only allowlisted programs are permitted.
        working_directory: Working directory for the command. Defaults to /tmp.
        timeout_seconds: Maximum execution time in seconds (1-120), file-name pattern
            expansion included. Defaults to 30.

    Returns:
        Command output (stdout/stderr) and exit code. A program that a signal ended has
        the exit code 128 plus the signal number.
    """
    if not command or not command.strip():
        return "Error: Command cannot be empty."

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

    env = _sanitized_env()
    # A relative directory in PATH would name files in the working directory, which a
    # command can write; only absolute directories are searched.
    search_path = os.pathsep.join(
        directory for directory in env.get("PATH", os.defpath).split(os.pathsep) if os.path.isabs(directory)
    )
    start_time = time.monotonic()
    deadline = start_time + timeout
    try:
        stages = _parse_command(command, cwd, deadline)
        programs: List[str] = []
        for stage in stages:
            program = shutil.which(stage.argv[0], path=search_path)
            if program is None:
                return f"Error: Command '{stage.argv[0]}' is on the allowlist but is not installed in this container."
            programs.append(program)

        # Log command length, not content — the command may embed sensitive values.
        logger.info(
            "execute_shell starting: command_length=%d, cwd=%s, timeout=%ds",
            len(command),
            cwd,
            timeout,
        )
        procs, stdout_reader, stderr_reader = _start(stages, programs, cwd, env)
        readers = (stdout_reader, stderr_reader)
        if not _finished(procs, readers, deadline - time.monotonic()):
            _kill(procs)
            # Bound the reap: a descendant that escaped its group (setsid/double-fork)
            # could hold a pipe open forever, reintroducing the very hang the timeout
            # guards against. Give up after a short grace.
            if not _finished(procs, readers, _REAP_SECONDS):
                # The primary timeout failure is already being reported, so don't
                # block the caller any longer.
                logger.debug("post-timeout reap timed out; continuing")
            logger.error(
                "execute_shell timed out after %ds (command_length=%d)", timeout, len(command)
            )
            return f"Error: Command timed out after {timeout} seconds."

        # As a shell reports it: 128 plus the signal number for a program that a signal ended.
        returncode = procs[-1].returncode
        exit_code = returncode if returncode >= 0 else 128 - returncode
        duration = time.monotonic() - start_time
        logger.info(
            "execute_shell completed: exit_code=%d, duration=%.2fs, "
            "stdout_bytes=%d, stderr_bytes=%d",
            exit_code,
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
        parts.append(f"[exit code: {exit_code}]")

        return "\n".join(parts)

    except _Rejected as rejected:
        # Log the length and fixed reason, never the text or the message: the command may
        # embed sensitive values, even in the rejected word the message quotes
        # (e.g. `KEY=secret python3 x.py`).
        logger.warning(
            "Command rejected by allowlist: command_length=%d, reason=%s", len(command), rejected.reason
        )
        return rejected.message
    except Exception as e:
        logger.error("Shell execution error: %s", e, exc_info=True)
        return f"Error: Shell execution failed: {e}"
