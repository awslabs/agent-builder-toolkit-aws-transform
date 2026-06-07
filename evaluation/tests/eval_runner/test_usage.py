# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for parsing real usage data out of a kiro-cli session JSON file.

kiro-cli does NOT report token usage over the ACP wire (the prompt result is
just ``{"stopReason": ...}``). The real signals it persists live in the session
file under ``session_state.conversation_metadata.user_turn_metadatas[]``:
metering credits and context-usage percentage. Raw input/output token counts
are present but always zero, so we surface what's actually populated.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from eval_runner.execution.runner import EvalOrchestrator
from eval_runner.execution.usage import format_usage_summary, usage_from_session_file
from eval_runner.models import TokenUsage

FIXTURE = Path(__file__).parent / "fixtures" / "kiro_session_sample.json"


class TestUsageFromSessionFile:
    def test_parses_credits_and_context_from_real_session(self) -> None:
        usage = usage_from_session_file(FIXTURE)
        assert isinstance(usage, TokenUsage)
        # Credits summed across every metering_usage entry in all 4 turns.
        # (Real fixture sums to ~4.0 credits.)
        assert usage.credits > 3.0
        assert usage.credits < 5.0
        # Context usage % is the latest/max turn value (~4.24%).
        assert 4.0 < usage.context_usage_percentage < 5.0
        assert usage.context_window_tokens == 1_000_000

    def test_missing_file_returns_empty_usage(self, tmp_path: Path) -> None:
        usage = usage_from_session_file(tmp_path / "nope.json")
        assert usage == TokenUsage()

    def test_malformed_json_returns_empty_usage(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert usage_from_session_file(bad) == TokenUsage()

    def test_session_without_metadata_returns_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"session_state": {}}))
        assert usage_from_session_file(empty) == TokenUsage()

    def test_nonzero_token_counts_are_summed_when_present(self, tmp_path: Path) -> None:
        """If a future kiro-cli populates real token counts, sum them."""
        f = tmp_path / "s.json"
        f.write_text(
            json.dumps(
                {
                    "session_state": {
                        "conversation_metadata": {
                            "user_turn_metadatas": [
                                {"input_token_count": 100, "output_token_count": 20},
                                {"input_token_count": 50, "output_token_count": 10},
                            ]
                        }
                    }
                }
            )
        )
        usage = usage_from_session_file(f)
        assert usage.input_tokens == 150
        assert usage.output_tokens == 30
        assert usage.total_tokens == 180

    # --- "never raise" robustness: the session file is written by an external
    # process and may be valid JSON but structurally wrong. None of these may
    # raise; all must degrade to an empty/partial TokenUsage. ---

    def _write(self, tmp_path: Path, obj: object) -> Path:
        f = tmp_path / "s.json"
        f.write_text(json.dumps(obj))
        return f

    @pytest.mark.parametrize("top_level", [42, [1, 2, 3], "a string", None, True])
    def test_non_dict_top_level_returns_empty(self, tmp_path: Path, top_level) -> None:
        assert usage_from_session_file(self._write(tmp_path, top_level)) == TokenUsage()

    @pytest.mark.parametrize("bad", [[1, 2, 3], "oops", 7])
    def test_non_dict_conversation_metadata_does_not_raise(self, tmp_path: Path, bad) -> None:
        f = self._write(tmp_path, {"session_state": {"conversation_metadata": bad}})
        assert usage_from_session_file(f) == TokenUsage()

    @pytest.mark.parametrize("bad", [[1, 2], "oops", 7])
    def test_non_dict_rts_model_state_does_not_raise(self, tmp_path: Path, bad) -> None:
        f = self._write(tmp_path, {"session_state": {"rts_model_state": bad}})
        assert usage_from_session_file(f).context_window_tokens == 0

    def test_non_dict_turn_entry_is_skipped(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            {
                "session_state": {
                    "conversation_metadata": {
                        "user_turn_metadatas": [
                            "not a dict",
                            {"input_token_count": 100, "output_token_count": 20},
                        ]
                    }
                }
            },
        )
        usage = usage_from_session_file(f)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 20

    def test_non_numeric_counts_and_pct_are_ignored(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            {
                "session_state": {
                    "conversation_metadata": {
                        "user_turn_metadatas": [
                            {
                                "input_token_count": "lots",
                                "output_token_count": None,
                                "context_usage_percentage": "oops",
                            }
                        ]
                    }
                }
            },
        )
        usage = usage_from_session_file(f)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.context_usage_percentage == 0.0

    def test_context_percentage_is_peak_not_last(self, tmp_path: Path) -> None:
        """Use a non-monotonic sequence so 'peak' and 'last' differ."""
        f = self._write(
            tmp_path,
            {
                "session_state": {
                    "conversation_metadata": {
                        "user_turn_metadatas": [
                            {"context_usage_percentage": 2.0},
                            {"context_usage_percentage": 9.5},  # peak
                            {"context_usage_percentage": 4.0},  # last
                        ]
                    }
                }
            },
        )
        assert usage_from_session_file(f).context_usage_percentage == 9.5

    def test_float_context_window_is_accepted(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            {"session_state": {"rts_model_state": {"model_info": {"context_window_tokens": 1000000.0}}}},
        )
        assert usage_from_session_file(f).context_window_tokens == 1_000_000

    def test_bool_counts_do_not_inflate(self, tmp_path: Path) -> None:
        """bool is an int subclass — True must not count as 1 token / 1%."""
        f = self._write(
            tmp_path,
            {
                "session_state": {
                    "conversation_metadata": {
                        "user_turn_metadatas": [
                            {"input_token_count": True, "context_usage_percentage": True}
                        ]
                    }
                }
            },
        )
        usage = usage_from_session_file(f)
        assert usage.input_tokens == 0
        assert usage.context_usage_percentage == 0.0

    def test_credits_only_sum_credit_unit_entries(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            {
                "session_state": {
                    "conversation_metadata": {
                        "user_turn_metadatas": [
                            {
                                "metering_usage": [
                                    {"value": 1.5, "unit": "credit"},
                                    {"value": 99.0, "unit": "token"},  # ignored
                                    {"value": "x", "unit": "credit"},  # non-numeric, ignored
                                    {"value": 0.5, "unit": "credit"},
                                ]
                            }
                        ]
                    }
                }
            },
        )
        assert usage_from_session_file(f).credits == 2.0


class TestUsageFromPowerSession:
    """The runner glue: locate the power agent's session file under ~/.kiro and
    return None (fall back to ACP usage) when there's no usable signal."""

    def test_none_session_id_returns_none(self) -> None:
        assert EvalOrchestrator._usage_from_power_session(None) is None

    def test_missing_session_file_returns_none(self, tmp_path: Path) -> None:
        with patch("eval_runner.execution.runner.Path.home", return_value=tmp_path):
            assert EvalOrchestrator._usage_from_power_session("does-not-exist") is None

    def test_session_with_signal_is_returned(self, tmp_path: Path) -> None:
        # Lay the real fixture down where the runner expects it: ~/.kiro/sessions/cli/<id>.json
        sessions = tmp_path / ".kiro" / "sessions" / "cli"
        sessions.mkdir(parents=True)
        shutil.copy(FIXTURE, sessions / "sess-123.json")

        with patch("eval_runner.execution.runner.Path.home", return_value=tmp_path):
            usage = EvalOrchestrator._usage_from_power_session("sess-123")

        assert usage is not None
        assert usage.credits > 3.0
        assert usage.context_usage_percentage > 4.0

    def test_session_without_signal_returns_none(self, tmp_path: Path) -> None:
        # A session file present but carrying no credits/context/tokens → no signal.
        sessions = tmp_path / ".kiro" / "sessions" / "cli"
        sessions.mkdir(parents=True)
        (sessions / "empty.json").write_text(json.dumps({"session_state": {}}))

        with patch("eval_runner.execution.runner.Path.home", return_value=tmp_path):
            assert EvalOrchestrator._usage_from_power_session("empty") is None


class TestFormatUsageSummary:
    """The shared CLI summary formatter — used by both cli.py and execution/cli.py.
    Must suppress output entirely when there's no signal (no misleading zeros)."""

    def test_no_signal_returns_no_lines(self) -> None:
        assert format_usage_summary(TokenUsage()) == []

    def test_credits_only_renders_usage_line(self) -> None:
        lines = format_usage_summary(
            TokenUsage(credits=3.93, context_usage_percentage=4.0)
        )
        assert len(lines) == 1
        assert "3.93 credits" in lines[0]
        assert "4.0% context" in lines[0]
        # No token line when token counts are zero (the kiro-cli reality).
        assert not any("Tokens:" in line for line in lines)

    def test_tokens_line_added_when_present(self) -> None:
        lines = format_usage_summary(
            TokenUsage(
                credits=1.0,
                context_usage_percentage=2.0,
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            )
        )
        assert len(lines) == 2
        assert any("Tokens: 120 total" in line for line in lines)
