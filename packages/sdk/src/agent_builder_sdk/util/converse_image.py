# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Image bytes in the form the Bedrock Converse API accepts."""

import io
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Literal, cast, get_args

from PIL import Image, ImageMath, ImageOps, ImageSequence, UnidentifiedImageError

ImageFormat = Literal["png", "jpeg", "gif", "webp"]
_CONVERSE_FORMATS: frozenset[str] = frozenset(get_args(ImageFormat))

# Converse rejects an image over 3.75 MB, and a rejected image that stays in history fails every
# later model call of the conversation.
MAX_IMAGE_BYTES = 3_750_000
# Longest edge in px. Anthropic's vision guidance gives 1568 px as the edge above which a Claude
# model resizes an image before it reads it, so more pixels only add latency.
MAX_EDGE = 1568
# Shortest long edge, in px, tried before an image that is still over MAX_IMAGE_BYTES is given up.
MIN_EDGE = 64
# Pixels decoded for one image, summed over its frames. Checked against the header before any
# pixel is decoded, so the memory and time one image can take do not depend on its content.
MAX_DECODE_PIXELS = 50_000_000

# Untrusted bytes reach only these Pillow decoders (the JPEG decoder also opens MPO).
_OPEN_FORMATS = ("PNG", "JPEG", "GIF", "WEBP", "BMP", "TIFF", "ICO", "PPM")
# Finite float32 bound: a pixel beyond it, or NaN, is zeroed before the value range is measured.
_FLOAT_LIMIT = 3.0e38
# Two workers bound the memory of concurrent decodes, and keep the queue of waiting images off
# the event loop and off the default executor that the rest of the agent shares.
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="converse-image")


class ImageConversionError(ValueError):
    """The bytes are not an image that can be brought within the Converse limits."""


def submit_conversion(raw: bytes) -> Future[tuple[bytes, ImageFormat]]:
    """Start the conversion of ``raw`` to image bytes and a format that Converse accepts.

    The result is ``raw`` itself, with its real format, when it is a complete png, jpeg, gif or
    webp of at most MAX_IMAGE_BYTES and MAX_EDGE px per side. Any other image is decoded (first
    frame only), downscaled until it fits and encoded again: png when it has transparency, jpeg
    otherwise.

    At most two conversions run at a time; the others wait in a queue. The future raises
    ImageConversionError when the bytes are not a readable image of a supported format, when a
    decode would exceed MAX_DECODE_PIXELS, or when the image is still over MAX_IMAGE_BYTES at
    MIN_EDGE px.
    """
    return _POOL.submit(_convert_or_raise, raw)


def _convert_or_raise(raw: bytes) -> tuple[bytes, ImageFormat]:
    try:
        return _convert(raw)
    except UnidentifiedImageError as error:
        raise ImageConversionError("not a " + "/".join(_OPEN_FORMATS) + " image") from error
    except Exception as error:
        # Pillow decoders raise OSError, ValueError, SyntaxError, struct.error and more on
        # damaged input; callers get one type, with the cause chained.
        raise ImageConversionError(str(error) or type(error).__name__) from error


def _convert(raw: bytes) -> tuple[bytes, ImageFormat]:
    with Image.open(io.BytesIO(raw), formats=_OPEN_FORMATS) as image:
        pil_format = (image.format or "").lower()
        # An MPO file is a JPEG with further images appended, and Converse reads it as that JPEG.
        fmt = "jpeg" if pil_format == "mpo" else pil_format
        fits = len(raw) <= MAX_IMAGE_BYTES and max(image.size) <= MAX_EDGE
        if fits and fmt in _CONVERSE_FORMATS:
            _decode_frames(image, first_only=pil_format == "mpo")
            return raw, cast(ImageFormat, fmt)
        return _reencode(image)


def _decode_frames(image: Image.Image, first_only: bool) -> None:
    """Decode the frames within the pixel budget, so that a damaged or truncated frame raises."""
    if first_only:
        image.load()
        return
    decoded = 0
    for index, frame in enumerate(ImageSequence.Iterator(image)):
        decoded += frame.width * frame.height
        if decoded > MAX_DECODE_PIXELS:
            raise ValueError(f"frames exceed the decode budget at frame {index}")
        frame.load()


def _reencode(image: Image.Image) -> tuple[bytes, ImageFormat]:
    """The first frame within MAX_EDGE and MAX_IMAGE_BYTES: png with transparency, else jpeg."""
    width, height = image.size
    if image.format in ("JPEG", "MPO"):
        # A JPEG decodes at 1/2, 1/4 or 1/8 scale, which keeps a large photo inside the budget.
        long_side = max(width, height)
        image.draft(
            "RGB",
            (max(1, MAX_EDGE * width // long_side), max(1, MAX_EDGE * height // long_side)),
        )
        width, height = image.size
    if width * height > MAX_DECODE_PIXELS:
        raise ValueError(f"{width}x{height} px exceeds the decode limit")
    image.load()
    ImageOps.exif_transpose(image, in_place=True)
    # A profile describes the colour space it was written for, so it is kept only when the
    # encoded image stays in that space.
    keeps_colour_space = image.mode in ("RGB", "RGBA", "P", "PA")
    icc_profile = image.info.get("icc_profile") if keeps_colour_space else None
    colour_key = image.info.get("transparency")
    if image.mode.startswith("I;16") or image.mode in ("I", "F"):
        gray = _to_grayscale(image)
        if isinstance(colour_key, int):
            gray = _with_colour_key_alpha(gray, image, colour_key)
        image = gray
    elif colour_key is not None or image.mode in ("PA", "La", "RGBa"):
        image = image.convert("RGBA")
    has_alpha = image.mode in ("RGBA", "LA")
    if not has_alpha and image.mode != "RGB":
        image = image.convert("RGB")
    # Pillow writes the entries of ``info`` (text chunks, a colour key) into the encoded file.
    image.info = {}
    options: dict[str, Any] = {"format": "PNG"} if has_alpha else {"format": "JPEG", "quality": 85}
    if icc_profile:
        options["icc_profile"] = icc_profile
    edge = min(MAX_EDGE, max(image.size))
    while True:
        image.thumbnail((edge, edge))
        buffer = io.BytesIO()
        image.save(buffer, **options)
        data = buffer.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            return data, "png" if has_alpha else "jpeg"
        edge //= 2
        if edge < MIN_EDGE:
            raise ValueError(f"still over {MAX_IMAGE_BYTES:,} bytes at {MIN_EDGE} px")


def _to_grayscale(image: Image.Image) -> Image.Image:
    """Map a 16-bit, 32-bit or float image onto 0-255 over its own value range."""
    floats = image.convert("F")
    if image.mode == "F":
        floats = _finite(floats)
    low, high = cast(tuple[float, float], floats.getextrema())
    if high <= low:
        full = _full_scale(image.mode, high)
        return Image.new("L", image.size, round(min(max(high, 0.0), full) / full * 255))
    scale = 255 / (high - low)
    return floats.point(lambda value: (value - low) * scale).convert("L")


def _full_scale(mode: str, value: float) -> float:
    """The range a single-value image is measured against: 16-bit, unit float or 8-bit."""
    if mode.startswith("I;16") or (mode == "I" and value > 255):
        return 65535.0
    if mode == "F" and value <= 1.0:
        return 1.0
    return 255.0


def _finite(floats: Image.Image) -> Image.Image:
    """Zero the NaN and infinite pixels of a float image.

    ``Image.point`` cannot test for them. The two clamps differ only in operand order, which
    gives different results for NaN alone, and an infinity clamps to exactly the limit.
    """
    limit = _FLOAT_LIMIT
    upper_first = ImageMath.lambda_eval(
        lambda e: e["max"](e["min"](e["x"], limit), -limit), x=floats
    )
    lower_first = ImageMath.lambda_eval(
        lambda e: e["min"](e["max"](e["x"], -limit), limit), x=floats
    )
    return cast(
        Image.Image,
        ImageMath.lambda_eval(
            lambda e: e["a"] * (e["a"] == e["b"]) * (abs(e["a"]) < limit),
            a=upper_first,
            b=lower_first,
        ),
    )


def _with_colour_key_alpha(gray: Image.Image, source: Image.Image, key: int) -> Image.Image:
    """Carry the transparent colour key of a high-bit-depth image over as an alpha channel."""
    alpha = ImageMath.lambda_eval(lambda e: (e["x"] != key) * 255, x=source.convert("I"))
    return Image.merge("LA", (gray, alpha.convert("L")))
