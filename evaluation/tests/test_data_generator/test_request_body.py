# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Request bodies the test data generator sends to Bedrock."""

import io
import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from test_data_generator import cli
from test_data_generator.domain_analyzer import DomainAnalyzer
from test_data_generator.intelligent_generator import IntelligentTestGenerator

MODEL_ID = "us.anthropic.claude-opus-5-5"


def _sent_body(obj, content=({"type": "text", "text": "ok"},)):
    obj.bedrock = MagicMock()
    obj.bedrock.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps({"content": list(content)}).encode())
    }
    assert obj._call_bedrock("prompt") == "ok"
    return json.loads(obj.bedrock.invoke_model.call_args.kwargs["body"])


@pytest.mark.parametrize("cls", [IntelligentTestGenerator, DomainAnalyzer])
def test_sends_no_sampling_parameters(cls):
    with patch("boto3.client"):
        obj = cls(region_name="us-west-2", model_id=MODEL_ID)
    assert not {"temperature", "top_p", "top_k"} & _sent_body(obj).keys()


def test_cli_fails_when_no_tests_are_generated(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("An agent that books meetings.")
    argv = ["cli", "--source-context", str(tmp_path), "--output", str(tmp_path / "out")]
    monkeypatch.setattr(sys, "argv", argv)
    with patch.object(cli, "IntelligentTestGenerator") as generator:
        generator.return_value.generate_test_cases.return_value = []
        with pytest.raises(SystemExit) as exit_info:
            cli.main()
    assert exit_info.value.code == 1


@pytest.mark.parametrize("cls", [IntelligentTestGenerator, DomainAnalyzer])
def test_response_text_skips_leading_thinking_block(cls):
    with patch("boto3.client"):
        obj = cls(region_name="us-west-2", model_id=MODEL_ID)
    _sent_body(obj, content=(
        {"type": "thinking", "thinking": "reasoning", "signature": "sig"},
        {"type": "text", "text": "ok"},
    ))
