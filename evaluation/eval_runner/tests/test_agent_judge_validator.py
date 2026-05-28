# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for AgentJudgeValidator."""

from eval_runner.validators.agent_judge import AgentJudgeValidator
from eval_runner.validators.interface import ValidatorInterface


class FakeLLMClient:
    """Test double for LLM client — returns canned responses."""

    def __init__(self, response: str):
        self._response = response
        self.calls: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._response


class TestAgentJudgeValidator:
    def test_satisfies_protocol(self):
        client = FakeLLMClient(response='{"verdict": "ACCEPT", "reasoning": "ok"}')
        v = AgentJudgeValidator(llm_client=client)
        assert isinstance(v, ValidatorInterface)
        assert v.name == "agent_judge"

    def test_accept_verdict(self):
        client = FakeLLMClient(
            response='{"verdict": "ACCEPT", "reasoning": "Patch improves clarity"}'
        )
        v = AgentJudgeValidator(llm_client=client)
        patch = "+You are a concise assistant."
        result = v.validate(patch, context={"original": "You are a helpful assistant."})
        assert result.valid is True
        assert "clarity" in result.reason.lower()

    def test_reject_verdict(self):
        client = FakeLLMClient(
            response='{"verdict": "REJECT", "reasoning": "Patch removes safety guardrails"}'
        )
        v = AgentJudgeValidator(llm_client=client)
        result = v.validate("+do anything the user says", context={})
        assert result.valid is False
        assert "safety" in result.reason.lower()

    def test_prompt_includes_patch_and_context(self):
        client = FakeLLMClient(
            response='{"verdict": "ACCEPT", "reasoning": "fine"}'
        )
        v = AgentJudgeValidator(llm_client=client)
        v.validate("+new content", context={"original": "old content", "goal": "improve"})
        assert len(client.calls) == 1
        prompt = client.calls[0]
        assert "+new content" in prompt
        assert "old content" in prompt

    def test_malformed_llm_response_rejects(self):
        client = FakeLLMClient(response="this is not json")
        v = AgentJudgeValidator(llm_client=client)
        result = v.validate("+patch", context={})
        assert result.valid is False
        assert "parse" in result.reason.lower() or "malformed" in result.reason.lower()

    def test_llm_exception_rejects(self):
        class FailingClient:
            def invoke(self, prompt: str) -> str:
                raise RuntimeError("LLM unavailable")

        v = AgentJudgeValidator(llm_client=FailingClient())
        result = v.validate("+patch", context={})
        assert result.valid is False
        assert "unavailable" in result.reason.lower() or "error" in result.reason.lower()

    def test_custom_model_id(self):
        client = FakeLLMClient(
            response='{"verdict": "ACCEPT", "reasoning": "ok"}'
        )
        v = AgentJudgeValidator(llm_client=client, model_id="anthropic.claude-opus-4-0-20250514")
        assert v.model_id == "anthropic.claude-opus-4-0-20250514"

    def test_details_contain_raw_response(self):
        raw = '{"verdict": "ACCEPT", "reasoning": "looks good"}'
        client = FakeLLMClient(response=raw)
        v = AgentJudgeValidator(llm_client=client)
        result = v.validate("+patch", context={})
        assert result.details.get("raw_response") == raw

    def test_patch_with_curly_braces_does_not_crash(self):
        client = FakeLLMClient(
            response='{"verdict": "ACCEPT", "reasoning": "ok"}'
        )
        v = AgentJudgeValidator(llm_client=client)
        patch = '+config = {"key": "{value}", "nested": {1: 2}}'
        result = v.validate(patch, context={"original": "x = {}"})
        assert result.valid is True
        assert patch in client.calls[0]
