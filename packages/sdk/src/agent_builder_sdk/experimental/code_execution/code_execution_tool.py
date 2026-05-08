# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Local Python code execution tool.

This tool allows agents to execute Python code locally.
WARNING: Code executes in the same process without sandboxing.
For production use cases requiring isolation, use AgentCore Code Interpreter.
"""

import io
import logging
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Optional

from strands.tools import tool

from agent_builder_sdk.util.decorators import experimental

logger = logging.getLogger(__name__)


@tool
@experimental("Code executes locally without sandboxing. Use with caution.")
def python_repl(
    code: str,
    timeout_seconds: Optional[int] = 30,
) -> str:
    """
    Execute Python code and return the output.

    This tool executes Python code locally and captures stdout/stderr.
    Use this for calculations, data analysis, or any task requiring code execution.

    WARNING: Code executes locally without sandboxing. Only use with trusted input.

    Args:
        code: Python code to execute. Can be multiple lines.
        timeout_seconds: Maximum execution time in seconds. Default 30.

    Returns:
        The captured stdout/stderr output, or error message if execution fails.

    Example:
        python_repl(code="print(2 + 2)")  # Returns: "4"
        python_repl(code="import math; print(math.sqrt(16))")  # Returns: "4.0"
    """
    if not code or not code.strip():
        return "Error: No code provided"

    logger.debug("=" * 50)
    logger.debug("PYTHON_REPL - CODE:")
    logger.debug("-" * 50)
    for line in code.split("\n"):
        logger.debug("  %s", line)
    logger.debug("-" * 50)

    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    # Create a namespace for execution
    exec_globals = {
        "__builtins__": __builtins__,
        "__name__": "__main__",
    }

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Execute the code
            exec(code, exec_globals)

        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()

        # Combine outputs
        result = ""
        if stdout_output:
            result += stdout_output
        if stderr_output:
            if result:
                result += "\n"
            result += f"stderr: {stderr_output}"

        output = result if result else "(no output)"
        logger.debug("PYTHON_REPL - RESULT:")
        logger.debug("-" * 50)
        for line in output.split("\n"):
            logger.debug("  %s", line)
        logger.debug("=" * 50)
        return output

    except SyntaxError as e:
        return f"SyntaxError: {e.msg} at line {e.lineno}"
    except Exception as e:
        # Get the traceback but filter out the exec internals
        tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
        # Filter to show only relevant parts
        filtered_tb = []
        for line in tb_lines:
            if "code_execution_tool.py" not in line and "exec(code" not in line:
                filtered_tb.append(line)

        error_msg = "".join(filtered_tb).strip()
        if not error_msg:
            error_msg = f"{type(e).__name__}: {e}"

        return f"Error: {error_msg}"
