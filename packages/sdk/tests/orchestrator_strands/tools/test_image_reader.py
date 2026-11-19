# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import io
import os
import stat
import threading
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from PIL import Image

from agent_builder_sdk.orchestrator_strands.tools import image_reader as image_reader_module
from agent_builder_sdk.orchestrator_strands.tools.image_reader import image_reader
from agent_builder_sdk.util import converse_image
from agent_builder_sdk.util.converse_image import MAX_EDGE


def _read(**tool_input: Any) -> Any:
    return asyncio.run(image_reader({"toolUseId": "t1", "name": "image_reader", "input": tool_input}))


def _error_text(result: Any) -> str:
    assert result["status"] == "error" and result["toolUseId"] == "t1"
    text: str = result["content"][0]["text"]
    return text


def _save(path: Path, size: tuple[int, int] = (2, 2)) -> Path:
    Image.new("RGB", size, (20, 20, 220)).save(path)
    return path


def test_an_image_within_the_limits_comes_back_as_its_own_bytes_and_format(tmp_path: Path) -> None:
    path = _save(tmp_path / "a.gif")
    result = _read(image_path=str(path))
    assert result["status"] == "success" and result["toolUseId"] == "t1"
    assert result["content"] == [
        {"image": {"format": "gif", "source": {"bytes": path.read_bytes()}}}
    ]


def test_an_image_over_the_limits_comes_back_downscaled(tmp_path: Path) -> None:
    image = _read(image_path=str(_save(tmp_path / "wide.png", (9000, 100))))["content"][0]["image"]
    assert image["format"] == "jpeg"
    with Image.open(io.BytesIO(image["source"]["bytes"])) as decoded:
        assert decoded.size[0] == MAX_EDGE


def test_a_format_the_converse_api_lacks_is_re_encoded(tmp_path: Path) -> None:
    image = _read(image_path=str(_save(tmp_path / "a.bmp")))["content"][0]["image"]
    assert image["format"] == "jpeg"
    with Image.open(io.BytesIO(image["source"]["bytes"])) as decoded:
        assert decoded.format == "JPEG"


def test_a_path_under_the_home_directory_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _save(tmp_path / "a.png")
    assert _read(image_path="~/a.png")["status"] == "success"


@pytest.mark.parametrize("tool_input", [{}, {"image_path": ""}, {"image_path": 7}])
def test_a_missing_or_non_string_path_is_an_error(tool_input: dict[str, Any]) -> None:
    assert _error_text(_read(**tool_input)) == "File path is required"


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "no.png"
    assert _error_text(_read(image_path=str(missing))) == f"File not found at path: {missing}"


@pytest.mark.parametrize(
    "content,reason",
    [
        ("secret-content", "not a PNG/JPEG/GIF/WEBP/BMP image"),
        ("P2 2 2 255 private-text-of-the-file", "not a PNG/JPEG/GIF/WEBP/BMP image"),
        ("\x89PNG\r\n\x1a\nprivate-text-of-the-file", "not a PNG/JPEG/GIF/WEBP/BMP image"),
    ],
)
def test_a_file_that_is_not_an_image_is_an_error_without_its_content(
    tmp_path: Path, content: str, reason: str
) -> None:
    secret = tmp_path / "a.png"
    secret.write_text(content)
    assert _error_text(_read(image_path=str(secret))) == f"Error reading file: {reason}"


def test_a_directory_is_an_error(tmp_path: Path) -> None:
    assert _error_text(_read(image_path=str(tmp_path))) == "Error reading file: not a regular file"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_a_named_pipe_is_an_error_and_is_never_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipe = tmp_path / "pipe.png"
    os.mkfifo(pipe)
    monkeypatch.setattr("builtins.open", Mock(side_effect=AssertionError("opened")))
    assert _error_text(_read(image_path=str(pipe))) == "Error reading file: not a regular file"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_a_named_pipe_swapped_in_after_the_check_is_an_error_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _save(tmp_path / "a.png")
    real_stat = os.stat

    def stat_then_swap(file_path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(file_path, *args, **kwargs)
        if file_path == str(path) and stat.S_ISREG(result.st_mode):
            os.remove(file_path)
            os.mkfifo(file_path)
        return result

    monkeypatch.setattr(image_reader_module.os, "stat", stat_then_swap)
    outcome: list[str] = []
    reader = threading.Thread(
        target=lambda: outcome.append(_error_text(_read(image_path=str(path)))), daemon=True
    )
    reader.start()
    reader.join(timeout=5)
    if reader.is_alive():
        # Opening the write end releases an open() that blocks on the read end.
        os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
        reader.join(timeout=5)
    assert outcome == ["Error reading file: not a regular file"]


def test_a_file_over_the_size_limit_is_an_error_and_is_never_decoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _save(tmp_path / "a.png", (64, 64))
    size = path.stat().st_size
    monkeypatch.setattr(image_reader_module, "MAX_IMAGE_FILE_BYTES", size)
    assert _read(image_path=str(path))["status"] == "success"
    monkeypatch.setattr(image_reader_module, "MAX_IMAGE_FILE_BYTES", size - 1)
    monkeypatch.setattr(converse_image, "_convert", Mock(side_effect=AssertionError("decoded")))
    assert (
        _error_text(_read(image_path=str(path)))
        == f"Error reading file: the file is over the {size - 1:,}-byte limit"
    )


def test_a_file_the_process_may_not_read_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _save(tmp_path / "a.png")
    monkeypatch.setattr("builtins.open", Mock(side_effect=PermissionError(13, "denied")))
    assert _error_text(_read(image_path=str(path))).startswith("Error reading file: [Errno 13]")


def test_a_conversion_over_the_timeout_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    def stuck_convert(raw: bytes) -> tuple[bytes, str]:
        release.wait(timeout=10)
        return raw, "png"

    monkeypatch.setattr(converse_image, "_convert", stuck_convert)
    monkeypatch.setattr(converse_image, "CONVERSION_TIMEOUT_SECONDS", 0.2)
    try:
        result = _read(image_path=str(_save(tmp_path / "a.png")))
    finally:
        release.set()
    assert _error_text(result) == "Error reading file: not converted within 0.2 s"
