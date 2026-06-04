# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Heuristic patch validator — syntax, size, and format checks without LLM."""

from __future__ import annotations

import ast
import re

from eval_runner.validators.interface import ValidationResult

_PATCH_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_DEFAULT_MAX_LINES = 500


class HeuristicValidator:
    """Validates patches using deterministic heuristics.

    Checks:
    - Non-empty content
    - Line count within bounds
    - Python syntax validity (when language is python or inferred from path)
    """

    def __init__(self, max_lines: int = _DEFAULT_MAX_LINES) -> None:
        self._max_lines = max_lines

    @property
    def name(self) -> str:
        return "heuristic"

    def validate(self, patch: str, context: dict) -> ValidationResult:
        if not patch.strip():
            return ValidationResult(valid=False, reason="Patch is empty")

        lines = patch.splitlines()
        line_count = len(lines)
        details: dict = {"line_count": line_count}

        if line_count > self._max_lines:
            return ValidationResult(
                valid=False,
                reason=f"Patch has {line_count} lines, exceeds max {self._max_lines} lines",
                details=details,
            )

        language = self._detect_language(patch, context)
        if language == "python":
            added_code = self._extract_added_lines(patch)
            if added_code:
                syntax_err = self._check_python_syntax(added_code)
                if syntax_err:
                    return ValidationResult(
                        valid=False,
                        reason=f"Python syntax error: {syntax_err}",
                        details={**details, "language": "python"},
                    )

        return ValidationResult(valid=True, reason="All heuristic checks passed", details=details)

    def _detect_language(self, patch: str, context: dict) -> str:
        explicit = context.get("language", "")
        if explicit:
            return explicit.lower()
        match = _PATCH_PATH_RE.search(patch)
        if match and match.group(1).endswith(".py"):
            return "python"
        return ""

    def _extract_added_lines(self, patch: str) -> str:
        added = []
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        return "\n".join(added)

    def _check_python_syntax(self, code: str) -> str:
        try:
            ast.parse(code)
            return ""
        except SyntaxError as e:
            return str(e)
