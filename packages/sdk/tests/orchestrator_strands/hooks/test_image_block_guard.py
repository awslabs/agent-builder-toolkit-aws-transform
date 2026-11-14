# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import io
import json
import os
import threading
import time
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import Mock

import pytest
from PIL import Image, ImageFile, ImageSequence, PngImagePlugin
from strands import Agent, tool
from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry
from strands.models.model import Model

from agent_builder_sdk.orchestrator_strands.hooks.image_block_guard import ImageBlockGuardHook
from agent_builder_sdk.orchestrator_strands.tools import image_reader
from agent_builder_sdk.util import converse_image
from agent_builder_sdk.util.converse_image import MAX_EDGE, MAX_IMAGE_BYTES

Block = dict[str, Any]


def _encode(image: Image.Image, fmt: str, **kwargs: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def _png(width: int, height: int) -> bytes:
    return _encode(Image.new("RGB", (width, height), (20, 20, 220)), "PNG")


def _noise(size: tuple[int, int] = (256, 256)) -> Image.Image:
    return Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))


def _animation(fmt: str, frames: int = 3, size: tuple[int, int] = (256, 256)) -> bytes:
    images = [_noise(size) for _ in range(frames)]
    if fmt == "GIF":
        images = [image.convert("P") for image in images]
    return _encode(images[0], fmt, save_all=True, append_images=images[1:])


def _image(raw: bytes, fmt: str = "png") -> Block:
    return {"image": {"format": fmt, "source": {"bytes": raw}}}


def _event(content: list[Block], tool_name: str = "image_reader") -> AfterToolCallEvent:
    return AfterToolCallEvent(
        agent=Mock(),
        selected_tool=None,
        tool_use={"name": tool_name, "toolUseId": "tu-1", "input": {}},
        invocation_state={},
        result={"toolUseId": "tu-1", "status": "success", "content": content},
    )


def _run(event: AfterToolCallEvent) -> Any:
    asyncio.run(ImageBlockGuardHook()._on_after_tool_call(event))
    return event.result


def _guarded(raw: bytes, fmt: str = "png", tool_name: str = "image_reader") -> Block:
    block: Block = _run(_event([_image(raw, fmt)], tool_name))["content"][0]
    return block


def _decoded(block: Block) -> Image.Image:
    return Image.open(io.BytesIO(block["image"]["source"]["bytes"]))


def test_register_hooks_registers_after_tool_call() -> None:
    registry = Mock(spec=HookRegistry)
    ImageBlockGuardHook().register_hooks(registry)
    assert registry.add_callback.call_args.args[0] is AfterToolCallEvent


def test_small_image_and_non_image_blocks_are_untouched() -> None:
    content = [{"text": "caption"}, _image(_png(64, 64))]
    event = _event(list(content))
    _run(event)
    assert all(new is old for new, old in zip(event.result["content"], content, strict=True))


def test_a_block_without_a_bytes_source_is_untouched() -> None:
    block: Block = {"image": {"format": "png", "source": {"location": "elsewhere"}}}
    assert _run(_event([block]))["content"][0] is block


def test_a_bytearray_source_is_guarded_like_bytes() -> None:
    block: Block = {"image": {"format": "png", "source": {"bytes": bytearray(_png(9000, 100))}}}
    guarded = _run(_event([block]))["content"][0]
    assert guarded["image"]["format"] == "jpeg" and _decoded(guarded).size[0] == MAX_EDGE


def test_wide_image_over_the_edge_limit_is_downscaled_to_the_limit() -> None:
    block = _guarded(_png(9000, 100))
    assert block["image"]["format"] == "jpeg"
    width, height = _decoded(block).size
    assert width == MAX_EDGE and height <= MAX_EDGE
    assert len(block["image"]["source"]["bytes"]) <= MAX_IMAGE_BYTES


def test_heavy_image_within_the_edge_limit_is_shrunk_until_it_fits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(converse_image, "MAX_IMAGE_BYTES", 3000)
    monkeypatch.setattr(converse_image, "MIN_EDGE", 4)
    raw = _encode(_noise(), "PNG")
    assert len(raw) > 3000
    block = _guarded(raw)
    assert block["image"]["format"] == "jpeg"
    assert len(block["image"]["source"]["bytes"]) <= 3000
    assert max(_decoded(block).size) < 256


def test_transparent_image_stays_png_when_downscaled() -> None:
    block = _guarded(_encode(Image.new("RGBA", (9000, 50), (0, 0, 0, 0)), "PNG"))
    assert block["image"]["format"] == "png"
    assert max(_decoded(block).size) <= MAX_EDGE


def test_image_that_still_does_not_fit_at_the_smallest_edge_becomes_a_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(converse_image, "MAX_IMAGE_BYTES", 10)
    raw = _encode(Image.new("RGB", (256, 256), (20, 20, 220)), "BMP")
    encoded: list[tuple[int, int]] = []
    real_save = Image.Image.save

    def recording_save(self: Image.Image, *args: Any, **kwargs: Any) -> None:
        encoded.append(self.size)
        real_save(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", recording_save)
    block = _guarded(raw, tool_name="some_tool")
    assert "image" not in block
    assert block["text"].startswith("[image from some_tool: png,")
    assert "not shown: still over 10 bytes at 64 px" in block["text"]
    assert encoded == [(256, 256), (128, 128), (64, 64)]


def test_undecodable_image_bytes_become_a_note() -> None:
    block = _guarded(b"\x89PNG\r\n\x1a\ngarbage")
    assert "image" not in block
    assert "not shown" in block["text"]


@pytest.mark.parametrize("header", ["P2 2 2 255 ", "P2 "])
def test_a_decoder_failure_note_and_log_line_hold_no_bytes_of_the_input(
    header: str, caplog: pytest.LogCaptureFixture
) -> None:
    block = _guarded((header + "private-text-of-the-file").encode())
    assert "not shown: damaged or unsupported image data (ValueError)]" in block["text"]
    assert "private" not in block["text"] and "private" not in caplog.text
    assert "damaged or unsupported image data" in caplog.text


def test_an_unrecognised_format_note_names_the_declared_format_and_the_reason() -> None:
    block = _guarded(_encode(Image.new("RGB", (2000, 100), (9, 9, 9)), "TGA"))
    assert block["text"].startswith("[image from image_reader: png,")
    assert "not a PNG/JPEG" in block["text"] and "BytesIO" not in block["text"]


def test_other_blocks_keep_their_place_around_a_guarded_image() -> None:
    result = _run(_event([{"text": "before"}, _image(_png(9000, 100)), {"text": "after"}]))
    assert [next(iter(block)) for block in result["content"]] == ["text", "image", "text"]
    assert result["content"][0] == {"text": "before"} and result["content"][2] == {"text": "after"}


def test_extra_result_keys_survive_a_guarded_block() -> None:
    event = _event([_image(_png(9000, 100))])
    event.result["structuredContent"] = {"k": "v"}
    _run(event)
    assert event.result["structuredContent"] == {"k": "v"}
    assert event.result["content"][0]["image"]["format"] == "jpeg"


def test_bmp_bytes_labelled_png_are_re_encoded_to_a_converse_format() -> None:
    block = _guarded(_encode(Image.new("RGB", (16, 16), (1, 2, 3)), "BMP"))
    assert block["image"]["format"] == "jpeg"
    assert _decoded(block).format == "JPEG"


def test_jpeg_bytes_labelled_png_are_relabelled_without_re_encoding() -> None:
    raw = _encode(Image.new("RGB", (16, 16), (1, 2, 3)), "JPEG")
    assert _guarded(raw)["image"] == {"format": "jpeg", "source": {"bytes": raw}}


def test_oversized_16_bit_grayscale_is_downscaled_not_dropped() -> None:
    block = _guarded(_encode(Image.new("I;16", (8100, 100), 40000), "PNG"))
    assert max(_decoded(block).size) <= MAX_EDGE


def test_exif_orientation_is_applied_before_downscaling() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6
    raw = _encode(Image.new("RGB", (6000, 3000), (9, 9, 9)), "JPEG", exif=exif.tobytes())
    width, height = _decoded(_guarded(raw, "jpeg")).size
    assert height > width


def test_tiny_image_with_heavy_metadata_is_re_encoded_once_at_its_own_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(converse_image, "MAX_IMAGE_BYTES", 5000)
    info = PngImagePlugin.PngInfo()
    info.add_text("comment", "x" * 20_000)
    raw = _encode(Image.new("RGB", (32, 32), (7, 7, 7)), "PNG", pnginfo=info)
    assert len(raw) > 5000
    assert _decoded(_guarded(raw)).size == (32, 32)


def test_transparent_palette_image_keeps_its_transparency_when_re_encoded() -> None:
    palette = Image.new("P", (9000, 20))
    palette.putpalette([255, 0, 255] + [0] * 765)
    block = _guarded(_encode(palette, "PNG", transparency=0))
    out = _decoded(block)
    assert block["image"]["format"] == "png" and out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0


def test_rgb_image_with_a_transparent_colour_key_keeps_its_transparency() -> None:
    raw = _encode(Image.new("RGB", (9000, 20), (255, 0, 255)), "PNG", transparency=(255, 0, 255))
    block = _guarded(raw)
    out = _decoded(block)
    assert block["image"]["format"] == "png" and out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0


def test_16_bit_image_with_a_colour_key_keeps_its_transparency() -> None:
    image = Image.new("I;16", (3000, 100), 40000)
    image.paste(Image.new("I;16", (10, 100), 1000), (0, 0))
    block = _guarded(_encode(image, "PNG", transparency=1000))
    out = _decoded(block)
    assert block["image"]["format"] == "png" and out.mode == "LA"
    assert out.getpixel((0, 50))[1] == 0 and out.getpixel((out.size[0] - 1, 50))[1] == 255


_ICC_PROFILE = b"\x00\x00\x02\x00ADBE" + b"\x00" * 500


def test_icc_profile_survives_re_encoding() -> None:
    raw = _encode(Image.new("RGB", (3000, 2000), (9, 9, 9)), "JPEG", icc_profile=_ICC_PROFILE)
    assert _decoded(_guarded(raw, "jpeg")).info.get("icc_profile") == _ICC_PROFILE


def test_icc_profile_is_dropped_when_the_colour_space_changes() -> None:
    cmyk = _encode(Image.new("CMYK", (3000, 100), (0, 0, 0, 0)), "JPEG", icc_profile=_ICC_PROFILE)
    out = _decoded(_guarded(cmyk, "jpeg"))
    assert out.mode == "RGB" and "icc_profile" not in out.info
    keyed_gray = _encode(
        Image.new("L", (9000, 20), 7), "PNG", transparency=7, icc_profile=_ICC_PROFILE
    )
    out = _decoded(_guarded(keyed_gray))
    assert out.mode == "RGBA" and "icc_profile" not in out.info


def test_mode_i_image_is_scaled_to_its_own_range_not_clipped_white() -> None:
    image = Image.new("I", (3000, 100), 10000)
    image.paste(30000, (0, 0, 1500, 100))
    out = _decoded(_guarded(_encode(image, "TIFF"))).convert("L")
    left, right = out.getpixel((10, 50)), out.getpixel((out.size[0] - 10, 50))
    assert (left, right) == (255, 0)


@pytest.mark.parametrize(
    "image,low,high",
    [
        (Image.new("I;16", (3000, 100), 1), 0, 50),
        (Image.new("I;16", (3000, 100), 30000), 90, 150),
        (Image.new("I;16", (3000, 100), 65535), 250, 256),
        (Image.new("I", (3000, 100), 30000), 90, 150),
        (Image.new("F", (3000, 100), 0.5), 100, 160),
        (Image.new("F", (3000, 100), 1.0), 250, 256),
    ],
)
def test_single_value_high_depth_image_is_scaled_by_its_full_range(
    image: Image.Image, low: int, high: int
) -> None:
    fmt = "PNG" if image.mode == "I;16" else "TIFF"
    assert low <= _decoded(_guarded(_encode(image, fmt))).convert("L").getpixel((1, 1)) < high


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("position", [(0, 0), (2999, 99)])
def test_float_image_with_a_non_finite_pixel_keeps_its_contrast(
    bad: float, position: tuple[int, int]
) -> None:
    image = Image.new("F", (3000, 100), 0.5)
    image.paste(1.0, (0, 0, 1500, 100))
    image.putpixel(position, bad)
    out = _decoded(_guarded(_encode(image, "TIFF"))).convert("L")
    assert out.getpixel((10, 20)) > out.getpixel((out.size[0] - 10, 20))


@pytest.mark.parametrize("mode,fmt", [("F", "TIFF"), ("I", "TIFF"), ("I;16", "PNG")])
def test_high_depth_image_is_downscaled_before_its_value_range_is_mapped(
    monkeypatch: pytest.MonkeyPatch, mode: str, fmt: str
) -> None:
    mapped: list[tuple[int, int]] = []
    real_convert = Image.Image.convert

    def recording_convert(self: Image.Image, mode: Any = None, *args: Any, **kwargs: Any) -> Any:
        if mode == "F":
            mapped.append(self.size)
        return real_convert(self, mode, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "convert", recording_convert)
    block = _guarded(_encode(Image.new(mode, (3200, 2000), 7), fmt))
    assert mapped == [(MAX_EDGE, 980)]
    assert _decoded(block).size == (MAX_EDGE, 980)


def test_a_non_finite_pixel_blanks_only_the_output_pixels_that_cover_it() -> None:
    image = Image.new("F", (3000, 100), 1.0)
    image.paste(0.5, (1500, 0, 3000, 100))
    image.putpixel((100, 50), float("nan"))
    out = converse_image._to_grayscale(image, None)
    assert [out.getpixel((x, 26)) for x in (51, 52, 53)] == [255, 0, 255]
    assert out.getpixel((out.size[0] - 1, 26)) == 127


@pytest.mark.parametrize("mode", ["P", "1"])
def test_palette_and_bilevel_diagrams_keep_their_thin_lines_when_downscaled(mode: str) -> None:
    image = Image.new("RGB", (4000, 3000), (255, 255, 255))
    for x in range(20, 4000, 40):
        image.paste((0, 0, 0), (x, 0, x + 1, 3000))
    out = _decoded(_guarded(_encode(image.convert(mode), "PNG"))).convert("L")
    dark = [min(out.getpixel((x, y)) for y in (5, 100)) < 200 for x in range(out.size[0])]
    assert sum(1 for x, is_dark in enumerate(dark) if is_dark and not dark[x - 1]) == 100


def test_image_over_the_decode_pixel_limit_becomes_a_note_without_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _encode(Image.new("1", (2100, 2000), 1), "PNG")
    monkeypatch.setattr(converse_image, "MAX_DECODE_PIXELS", 1_000_000)
    monkeypatch.setattr(ImageFile.ImageFile, "load", Mock(side_effect=AssertionError("decoded")))
    block = _guarded(raw)
    assert "image" not in block
    assert "2100x2000 px exceeds the decode limit" in block["text"]


@pytest.mark.parametrize("size", [(2400, 2400), (6000, 200)])
def test_jpeg_over_the_decode_pixel_limit_is_decoded_at_reduced_scale_not_dropped(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    monkeypatch.setattr(converse_image, "MAX_DECODE_PIXELS", 1_000_000)
    monkeypatch.setattr(converse_image, "MAX_EDGE", 300)
    raw = _encode(Image.new("RGB", size, (9, 9, 9)), "JPEG", comment=b"\xff\xda in a segment")
    block = _guarded(raw, "jpeg")
    assert max(_decoded(block).size) <= 300


def _with_a_second_scan(baseline_jpeg: bytes) -> bytes:
    assert baseline_jpeg.endswith(b"\xff\xd9")
    return baseline_jpeg[:-2] + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\xff\xd9"


@pytest.mark.parametrize("kind", ["progressive", "sequential", "progressive header, one scan"])
def test_jpeg_that_is_not_one_sequential_scan_is_charged_at_full_size_without_decoding(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    image = Image.new("RGB", (2400, 2400), (9, 9, 9))
    raw = _encode(image, "JPEG", progressive=kind == "progressive")
    if kind == "sequential":
        raw = _with_a_second_scan(raw)
    elif kind == "progressive header, one scan":
        assert raw.count(b"\xff\xc0") == 1
        raw = raw.replace(b"\xff\xc0", b"\xff\xc2")
    monkeypatch.setattr(converse_image, "MAX_DECODE_PIXELS", 1_000_000)
    monkeypatch.setattr(converse_image, "MAX_EDGE", 300)
    monkeypatch.setattr(ImageFile.ImageFile, "load", Mock(side_effect=AssertionError("decoded")))
    block = _guarded(raw, "jpeg")
    assert "image" not in block
    assert "2400x2400 px exceeds the decode limit" in block["text"]


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_truncated_bytes_with_an_intact_header_become_a_note(fmt: str) -> None:
    raw = _encode(_noise(), fmt)
    block = _guarded(raw[: len(raw) // 2], fmt.lower())
    assert "image" not in block
    assert "not shown" in block["text"]


@pytest.mark.parametrize("fmt,declared", [("GIF", "gif"), ("PNG", "png"), ("WEBP", "webp")])
def test_an_animation_truncated_after_its_first_frame_becomes_a_note(
    fmt: str, declared: str
) -> None:
    raw = _animation(fmt)
    truncated = raw[: int(len(raw) * 0.8)]
    if fmt != "WEBP":
        assert Image.open(io.BytesIO(truncated)).load() is not None
    block = _guarded(truncated, declared)
    assert "image" not in block
    assert "not shown" in block["text"]


def test_a_many_frame_animation_over_the_frame_budget_keeps_its_first_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [Image.new("RGB", (64, 64), (200, 30, 30))]
    frames += [Image.new("RGB", (64, 64), (0, 5 * index, 200)) for index in range(39)]
    raw = _encode(frames[0], "GIF", save_all=True, append_images=frames[1:])
    assert Image.open(io.BytesIO(raw)).n_frames == 40
    monkeypatch.setattr(converse_image, "MAX_FRAME_PIXELS", 10 * 64 * 64)
    visited: list[int] = []
    real_next = ImageSequence.Iterator.__next__

    def counting_next(self: ImageSequence.Iterator) -> Image.Image:
        visited.append(1)
        return real_next(self)

    monkeypatch.setattr(ImageSequence.Iterator, "__next__", counting_next)
    block = _guarded(raw, "gif")
    assert len(visited) == 11
    assert block["image"]["format"] == "jpeg"
    still = _decoded(block)
    assert still.size == (64, 64) and getattr(still, "n_frames", 1) == 1
    red, green, blue = still.convert("RGB").getpixel((32, 32))
    assert red > 150 and green < 80 and blue < 80


def test_a_gif_frame_over_the_edge_limit_after_the_first_one_is_not_decoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _encode(Image.new("P", (100, 100), 1), "GIF")
    large = _encode(Image.new("P", (2000, 100), 3), "GIF")
    table_bytes = 3 * (2 << (large[10] & 7)) if large[10] & 0x80 else 0
    raw = first[:-1] + large[13 + table_bytes :]
    opened = Image.open(io.BytesIO(raw))
    assert opened.size == (100, 100) and opened.n_frames == 2
    loaded: list[int] = []
    real_load = ImageFile.ImageFile.load

    def recording_load(self: ImageFile.ImageFile) -> Any:
        loaded.append(self.tell())
        return real_load(self)

    monkeypatch.setattr(ImageFile.ImageFile, "load", recording_load)
    block = _guarded(raw, "gif")
    assert loaded and set(loaded) == {0}
    assert getattr(_decoded(block), "n_frames", 1) == 1


def test_an_ico_file_is_not_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _encode(Image.new("RGBA", (64, 64), (1, 2, 3, 4)), "ICO")
    monkeypatch.setattr(ImageFile.ImageFile, "load", Mock(side_effect=AssertionError("decoded")))
    assert "not shown: not a PNG/JPEG/GIF/WEBP/BMP/TIFF/PPM image" in _guarded(raw)["text"]


def test_an_mpo_with_a_damaged_trailing_image_keeps_its_primary_photo() -> None:
    primary = Image.new("RGB", (64, 64), (200, 30, 30))
    second = Image.new("RGB", (64, 64), (30, 200, 30))
    damaged = _encode(primary, "MPO", save_all=True, append_images=[second])[:-40]
    block = _guarded(damaged, "jpeg")
    assert block["image"] == {"format": "jpeg", "source": {"bytes": damaged}}


def test_guard_works_across_separate_event_loops_with_concurrent_results() -> None:
    async def three_at_once() -> list[Block]:
        events = [_event([_image(_png(9000, 100))]) for _ in range(3)]
        hook = ImageBlockGuardHook()
        await asyncio.gather(*(hook._on_after_tool_call(event) for event in events))
        return [event.result["content"][0] for event in events]

    for _ in range(2):
        assert all("image" in block for block in asyncio.run(three_at_once()))


def test_at_most_two_conversions_run_at_a_time_on_their_own_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = threading.Lock()
    running: list[str] = []
    peaks: list[int] = []
    threads: set[str] = set()

    def slow_convert(raw: bytes) -> tuple[bytes, str]:
        name = threading.current_thread().name
        with lock:
            running.append(name)
            peaks.append(len(running))
            threads.add(name)
        time.sleep(0.05)
        with lock:
            running.remove(name)
        return raw, "png"

    monkeypatch.setattr(converse_image, "_convert", slow_convert)
    futures = [converse_image.submit_conversion(b"x") for _ in range(6)]
    assert [future.result(timeout=10) for future in futures] == [(b"x", "png")] * 6
    assert max(peaks) <= 2
    assert all(name.startswith("converse-image") for name in threads)


class _ToolOnceModel(Model):
    """Calls one tool with one input on the first turn, then answers ``done``."""

    def __init__(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.calls = 0

    def update_config(self, **kwargs: Any) -> None:
        pass

    def get_config(self) -> dict[str, Any]:
        return {}

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        if self.calls == 1:
            start = {"toolUse": {"toolUseId": "t1", "name": self.tool_name}}
            yield {"contentBlockStart": {"start": start}}
            delta = {"toolUse": {"input": json.dumps(self.tool_input)}}
            yield {"contentBlockDelta": {"delta": delta}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": "done"}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        usage = {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}
        yield {"metadata": {"usage": usage, "metrics": {"latencyMs": 1}}}

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        if False:
            yield None


def _blobs(obj: Any, found: list[bytes], depth: int = 0) -> list[bytes]:
    """Every bytes value reachable from messages or metrics traces."""
    if depth > 12:
        return found
    if isinstance(obj, (bytes, bytearray)):
        found.append(bytes(obj))
    elif isinstance(obj, dict):
        for value in obj.values():
            _blobs(value, found, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _blobs(value, found, depth + 1)
    elif hasattr(obj, "children") or hasattr(obj, "message"):
        _blobs(getattr(obj, "message", None), found, depth + 1)
        _blobs(getattr(obj, "children", []), found, depth + 1)
    return found


@tool
def raw_image(image_path: str) -> dict[str, Any]:
    """Return the file at image_path as a png image block, whatever its size."""
    with open(image_path, "rb") as file:
        return {"status": "success", "content": [_image(file.read())]}


@pytest.mark.parametrize(
    "tool_name,tools,hooks",
    [
        ("raw_image", [raw_image], [ImageBlockGuardHook()]),
        ("image_reader", [image_reader], []),
    ],
)
def test_an_agent_turn_keeps_only_image_bytes_within_the_limits(
    tmp_path: Any, tool_name: str, tools: list[Any], hooks: list[HookProvider]
) -> None:
    path = tmp_path / "wide.png"
    path.write_bytes(_png(9000, 100))
    agent = Agent(
        model=_ToolOnceModel(tool_name, {"image_path": str(path)}),
        tools=tools,
        hooks=hooks,
        callback_handler=None,
    )
    agent("look at the picture")
    in_traces = _blobs(agent.event_loop_metrics.traces, [])
    in_history = _blobs(agent.messages, [])
    assert in_traces and in_history
    for blob in in_traces + in_history:
        image = Image.open(io.BytesIO(blob))
        assert image.format == "JPEG" and max(image.size) <= MAX_EDGE
