# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""AutoPatcher — generates inline diffs from diagnosis using LLM."""

from __future__ import annotations

from eval_runner.validators.interface import LLMClient, PatchResult

_DEFAULT_MODEL_ID = "anthropic.claude-sonnet-4-20250514"


class AutoPatcher:
    """Generates patches from source + diagnosis using an LLM."""

    def __init__(
        self,
        llm_client: LLMClient,
        model_id: str = _DEFAULT_MODEL_ID,
    ) -> None:
        self._client = llm_client
        self.model_id = model_id

    @property
    def name(self) -> str:
        return "auto_patcher"

    def generate(self, source: str, diagnosis: str, context: dict) -> PatchResult:
        file_path = context.get("file_path", "unknown")
        language = context.get("language", "unknown")

        prompt = self._build_prompt(file_path, language, source, diagnosis)

        try:
            response = self._client.invoke(prompt)
        except Exception as e:
            return PatchResult(success=False, error=str(e))

        if not response.strip():
            return PatchResult(success=False, error="Empty response from LLM")

        return PatchResult(patch=response, success=True)

    def _build_prompt(
        self, file_path: str, language: str, source: str, diagnosis: str
    ) -> str:
        return (
            "You are a patch generator for an AI agent evolution system.\n"
            "Given the original source and a diagnosis of what needs to change,\n"
            "produce a unified diff that fixes the issue.\n"
            "\n"
            "## Source File\n"
            f"Path: {file_path}\n"
            f"Language: {language}\n"
            "\n"
            "```\n"
            f"{source}\n"
            "```\n"
            "\n"
            "## Diagnosis\n"
            f"{diagnosis}\n"
            "\n"
            "## Instructions\n"
            "Output ONLY the unified diff (--- a/... +++ b/... format).\n"
            "Do not include explanations outside the diff.\n"
        )
