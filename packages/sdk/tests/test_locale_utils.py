# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for locale utilities."""

import logging
from typing import Optional

import pytest

from agent_builder_sdk.locale_utils import get_locale_instruction
from agent_builder_sdk.server.server_models import AgentRuntimeContext


class TestGetLocaleInstruction:
    def test_japanese(self):
        assert "Japanese" in get_locale_instruction("ja")

    def test_korean(self):
        assert "Korean" in get_locale_instruction("ko")

    def test_simplified_chinese(self):
        assert "Simplified Chinese" in get_locale_instruction("zh-CN")

    def test_traditional_chinese(self):
        assert "Traditional Chinese" in get_locale_instruction("zh-TW")

    def test_german(self):
        assert "German" in get_locale_instruction("de")

    def test_spanish(self):
        assert "Spanish" in get_locale_instruction("es")

    def test_french(self):
        assert "French" in get_locale_instruction("fr")

    def test_indonesian(self) -> None:
        assert "Indonesian" in get_locale_instruction("id")

    def test_italian(self) -> None:
        assert "Italian" in get_locale_instruction("it")

    def test_portuguese_brazil(self):
        assert "Brazilian Portuguese" in get_locale_instruction("pt-BR")

    def test_turkish(self):
        assert "Turkish" in get_locale_instruction("tr-TR")

    def test_english_returns_empty(self):
        assert get_locale_instruction("en") == ""

    def test_none_returns_empty(self):
        assert get_locale_instruction(None) == ""

    def test_empty_string_returns_empty(self):
        assert get_locale_instruction("") == ""

    def test_unknown_locale_returns_empty(self):
        assert get_locale_instruction("th") == ""

    def test_english_variant_returns_empty(self):
        assert get_locale_instruction("en-US") == ""
        assert get_locale_instruction("en-AU") == ""

    def test_en_gb_returns_british_english(self):
        result = get_locale_instruction("en-GB")
        assert "British English" in result

    def test_non_string_returns_empty(self):
        assert get_locale_instruction(123) == ""
        assert get_locale_instruction(True) == ""
        assert get_locale_instruction(["ja"]) == ""

    def test_instruction_format(self):
        result = get_locale_instruction("ja")
        assert result.startswith("Respond to the user in Japanese")
        assert "follow their lead" in result

    @pytest.mark.parametrize("locale", ["ja-JP", "JA", "pt", "zh"])
    def test_unsupported_locale_is_logged(
        self, locale: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="agent_builder_sdk.locale_utils"):
            assert get_locale_instruction(locale) == ""

        (record,) = caplog.records
        assert record.levelno == logging.WARNING
        assert f"Locale {locale!r} is not supported" in record.getMessage()

    @pytest.mark.parametrize("locale", ["ja", "en", "en-US", "en-GB", "", None])
    def test_supported_english_and_unset_locales_are_not_logged(
        self, locale: Optional[str], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="agent_builder_sdk.locale_utils"):
            get_locale_instruction(locale)

        assert caplog.records == []


def test_runtime_context_get_locale_instruction() -> None:
    ids = {"workspace_id": "ws", "job_id": "job", "agent_instance_id": "agent"}
    assert "Japanese" in AgentRuntimeContext(**ids, locale="ja").get_locale_instruction()
    assert AgentRuntimeContext(**ids).get_locale_instruction() == ""
