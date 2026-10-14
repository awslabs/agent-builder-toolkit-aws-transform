# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Request bodies the test data generator sends to Bedrock."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
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


@pytest.mark.parametrize("temperature", [None, 0.5])
def test_generator_sends_temperature_only_when_set(temperature):
    with patch("boto3.client"):
        generator = IntelligentTestGenerator(
            region_name="us-west-2", model_id=MODEL_ID, temperature=temperature
        )
    body = _sent_body(generator)
    assert ("temperature" in body) == (temperature is not None)
    assert body.get("temperature") == temperature


def test_domain_analyzer_sends_no_sampling_parameters():
    with patch("boto3.client"):
        analyzer = DomainAnalyzer(region_name="us-west-2", model_id=MODEL_ID)
    body = _sent_body(analyzer)
    assert not {"temperature", "top_p", "top_k"} & body.keys()


@pytest.mark.parametrize("cls", [IntelligentTestGenerator, DomainAnalyzer])
def test_response_text_skips_leading_thinking_block(cls):
    with patch("boto3.client"):
        obj = cls(region_name="us-west-2", model_id=MODEL_ID)
    _sent_body(obj, content=(
        {"type": "thinking", "thinking": "reasoning", "signature": "sig"},
        {"type": "text", "text": "ok"},
    ))
