# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for HeuristicValidator."""

from eval_runner.validators.heuristic import HeuristicValidator
from eval_runner.validators.interface import ValidatorInterface


class TestHeuristicValidator:
    def test_satisfies_protocol(self):
        v = HeuristicValidator()
        assert isinstance(v, ValidatorInterface)
        assert v.name == "heuristic"

    def test_empty_patch_rejected(self):
        v = HeuristicValidator()
        result = v.validate("", context={})
        assert result.valid is False
        assert "empty" in result.reason.lower()

    def test_whitespace_only_patch_rejected(self):
        v = HeuristicValidator()
        result = v.validate("   \n\n  ", context={})
        assert result.valid is False
        assert "empty" in result.reason.lower()

    def test_valid_patch_accepted(self):
        patch = (
            "--- a/prompt.txt\n"
            "+++ b/prompt.txt\n"
            "@@ -1,3 +1,3 @@\n"
            "-You are a helpful assistant.\n"
            "+You are a helpful and concise assistant.\n"
        )
        v = HeuristicValidator()
        result = v.validate(patch, context={})
        assert result.valid is True

    def test_patch_exceeding_max_lines_rejected(self):
        long_patch = "\n".join([f"+line {i}" for i in range(501)])
        v = HeuristicValidator(max_lines=500)
        result = v.validate(long_patch, context={})
        assert result.valid is False
        assert "lines" in result.reason.lower()

    def test_patch_at_max_lines_accepted(self):
        patch = "\n".join([f"+line {i}" for i in range(500)])
        v = HeuristicValidator(max_lines=500)
        result = v.validate(patch, context={})
        assert result.valid is True

    def test_patch_with_syntax_error_in_python_rejected(self):
        patch = (
            "--- a/agent.py\n"
            "+++ b/agent.py\n"
            "@@ -1,3 +1,3 @@\n"
            "+def broken(\n"
            "+    return None\n"
        )
        v = HeuristicValidator()
        result = v.validate(patch, context={"language": "python"})
        assert result.valid is False
        assert "syntax" in result.reason.lower()

    def test_non_python_skips_syntax_check(self):
        patch = (
            "--- a/prompt.txt\n"
            "+++ b/prompt.txt\n"
            "@@ -1 +1 @@\n"
            "+def broken(\n"
        )
        v = HeuristicValidator()
        result = v.validate(patch, context={"language": "text"})
        assert result.valid is True

    def test_python_inferred_from_patch_path(self):
        patch = (
            "--- a/agent.py\n"
            "+++ b/agent.py\n"
            "@@ -1 +1 @@\n"
            "+def broken(\n"
            "+    return None\n"
        )
        v = HeuristicValidator()
        result = v.validate(patch, context={})
        assert result.valid is False
        assert "syntax" in result.reason.lower()

    def test_custom_max_lines_via_init(self):
        v = HeuristicValidator(max_lines=10)
        patch = "\n".join([f"+line {i}" for i in range(11)])
        result = v.validate(patch, context={})
        assert result.valid is False

    def test_details_contain_line_count(self):
        patch = "+line 1\n+line 2\n+line 3"
        v = HeuristicValidator()
        result = v.validate(patch, context={})
        assert "line_count" in result.details
        assert result.details["line_count"] == 3

    def test_explicit_language_overrides_path_inference(self):
        patch = (
            "--- a/agent.py\n"
            "+++ b/agent.py\n"
            "@@ -1 +1 @@\n"
            "+def broken(\n"
        )
        v = HeuristicValidator()
        result = v.validate(patch, context={"language": "text"})
        assert result.valid is True
