# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Request bodies the test data generator sends to Bedrock."""

import io
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from test_data_generator import cli
from test_data_generator.domain_analyzer import DomainAnalyzer
from test_data_generator.intelligent_generator import IntelligentTestGenerator

MODEL_ID = "us.anthropic.claude-opus-5-5"


def _sent_body(
    obj: Any,
    content: Sequence[dict[str, str]] = ({"type": "text", "text": "ok"},),
    stop_reason: str = "end_turn",
) -> dict[str, Any]:
    obj.bedrock = MagicMock()
    response = {"content": list(content), "stop_reason": stop_reason}
    obj.bedrock.invoke_model.return_value = {"body": io.BytesIO(json.dumps(response).encode())}
    assert obj._call_bedrock("prompt") == "ok"
    return json.loads(obj.bedrock.invoke_model.call_args.kwargs["body"])


@pytest.mark.parametrize("cls", [IntelligentTestGenerator, DomainAnalyzer])
def test_sends_no_sampling_parameters(cls: type) -> None:
    with patch("boto3.client"):
        obj = cls(region_name="us-west-2", model_id=MODEL_ID)
    assert not {"temperature", "top_p", "top_k"} & _sent_body(obj).keys()


def test_cli_fails_when_no_tests_are_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "README.md").write_text("An agent that books meetings.")
    argv = ["cli", "--source-context", str(tmp_path), "--output", str(tmp_path / "out")]
    monkeypatch.setattr(sys, "argv", argv)
    with patch.object(cli, "IntelligentTestGenerator") as generator:
        generator.return_value.generate_test_cases.return_value = []
        with pytest.raises(SystemExit) as exit_info:
            cli.main()
    assert exit_info.value.code == 1


def test_cli_analyze_only_fails_when_analysis_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "README.md").write_text("An agent that books meetings.")
    argv = ["cli", "--source-context", str(tmp_path), "--output", str(tmp_path / "out"), "--analyze-only"]
    monkeypatch.setattr(sys, "argv", argv)
    failed = {
        "domain_understanding": {"error": "The provided model identifier is invalid."},
        "complexity_distribution": {"distribution": {}},
    }
    with patch.object(cli, "IntelligentTestGenerator"), patch.object(cli, "DomainAnalyzer") as analyzer:
        analyzer.return_value.analyze_test_samples.return_value = failed
        with pytest.raises(SystemExit) as exit_info:
            cli.main()
    assert exit_info.value.code == 1


@pytest.mark.parametrize("cls", [IntelligentTestGenerator, DomainAnalyzer])
def test_response_text_skips_leading_thinking_block(cls: type) -> None:
    with patch("boto3.client"):
        obj = cls(region_name="us-west-2", model_id=MODEL_ID)
    _sent_body(obj, content=(
        {"type": "thinking", "thinking": "reasoning", "signature": "sig"},
        {"type": "text", "text": "ok"},
    ))


@pytest.mark.parametrize("cls", [IntelligentTestGenerator, DomainAnalyzer])
@pytest.mark.parametrize(
    ("stop_reason", "warned"), [("max_tokens", True), ("refusal", True), ("end_turn", False)]
)
def test_warns_only_when_the_response_stopped_early(
    cls: type, stop_reason: str, warned: bool, caplog: pytest.LogCaptureFixture
) -> None:
    with patch("boto3.client"):
        obj = cls(region_name="us-west-2", model_id=MODEL_ID)
    with caplog.at_level(logging.WARNING):
        _sent_body(obj, stop_reason=stop_reason)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    expected = f"Bedrock response stopped early ({stop_reason}); output may be incomplete"
    assert warnings == ([expected] if warned else [])
