# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Locale utilities for agent response localization."""

from typing import Optional

LOCALE_TO_LANGUAGE = {
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "id": "Indonesian",
    "it": "Italian",
    "pt-BR": "Brazilian Portuguese",
    "tr-TR": "Turkish",
    "en-GB": "British English",
}


def get_locale_instruction(locale: Optional[str]) -> str:
    """Return a system prompt instruction for the given locale.

    Returns empty string for English, None, or unknown locales.
    Orchestrators created with ``locale=...`` append this instruction automatically; call it
    directly only when building a system prompt by hand.
    """
    if not locale or not isinstance(locale, str):
        return ""
    if locale == "en" or (locale.startswith("en") and locale not in LOCALE_TO_LANGUAGE):
        return ""
    language = LOCALE_TO_LANGUAGE.get(locale)
    if not language:
        return ""
    return f"Respond to the user in {language}. If the user writes in a different language, follow their lead."
