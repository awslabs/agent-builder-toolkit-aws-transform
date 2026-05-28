# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for AutoPatcher."""

from eval_runner.validators.auto_patcher import AutoPatcher
from eval_runner.validators.interface import PatcherInterface


class FakeLLMClient:
    """Test double for LLM client."""

    def __init__(self, response: str):
        self._response = response
        self.calls: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._response


class TestAutoPatcher:
    def test_satisfies_protocol(self):
        client = FakeLLMClient(response="--- a/f.py\n+++ b/f.py\n+fix")
        p = AutoPatcher(llm_client=client)
        assert isinstance(p, PatcherInterface)
        assert p.name == "auto_patcher"

    def test_generate_patch_from_diagnosis(self):
        diff = (
            "--- a/prompt.txt\n"
            "+++ b/prompt.txt\n"
            "@@ -1 +1 @@\n"
            "-You are helpful.\n"
            "+You are helpful and concise.\n"
        )
        client = FakeLLMClient(response=diff)
        p = AutoPatcher(llm_client=client)
        result = p.generate(
            source="You are helpful.",
            diagnosis="Agent is too verbose",
            context={"file_path": "prompt.txt"},
        )
        assert result.patch == diff
        assert result.success is True

    def test_prompt_includes_source_and_diagnosis(self):
        client = FakeLLMClient(response="+patched")
        p = AutoPatcher(llm_client=client)
        p.generate(
            source="original content",
            diagnosis="issue description",
            context={},
        )
        assert len(client.calls) == 1
        prompt = client.calls[0]
        assert "original content" in prompt
        assert "issue description" in prompt

    def test_empty_llm_response_fails(self):
        client = FakeLLMClient(response="")
        p = AutoPatcher(llm_client=client)
        result = p.generate(
            source="content",
            diagnosis="fix it",
            context={},
        )
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_llm_exception_returns_failure(self):
        class FailingClient:
            def invoke(self, prompt: str) -> str:
                raise RuntimeError("Service down")

        p = AutoPatcher(llm_client=FailingClient())
        result = p.generate(
            source="content",
            diagnosis="fix",
            context={},
        )
        assert result.success is False
        assert "service down" in result.error.lower()

    def test_custom_model_id(self):
        client = FakeLLMClient(response="+fix")
        p = AutoPatcher(llm_client=client, model_id="anthropic.claude-opus-4-0-20250514")
        assert p.model_id == "anthropic.claude-opus-4-0-20250514"

    def test_generate_with_file_context(self):
        client = FakeLLMClient(response="+improved")
        p = AutoPatcher(llm_client=client)
        p.generate(
            source="def foo(): pass",
            diagnosis="function does nothing useful",
            context={"file_path": "agent.py", "language": "python"},
        )
        prompt = client.calls[0]
        assert "agent.py" in prompt
        assert "python" in prompt

    def test_source_with_curly_braces_does_not_crash(self):
        client = FakeLLMClient(response="+fixed")
        p = AutoPatcher(llm_client=client)
        source = 'data = {"key": "{value}", "nested": {1: 2}}'
        result = p.generate(
            source=source,
            diagnosis="fix the {formatting}",
            context={"file_path": "config.py"},
        )
        assert result.success is True
        assert source in client.calls[0]
        assert "{formatting}" in client.calls[0]
