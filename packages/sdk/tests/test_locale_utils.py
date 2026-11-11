# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for locale utilities."""

from agent_builder_sdk.locale_utils import get_locale_instruction


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
