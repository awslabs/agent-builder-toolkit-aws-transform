# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Image bytes in the form the Bedrock Converse API accepts."""

import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, cast, get_args

from PIL import Image, UnidentifiedImageError

ImageFormat = Literal["png", "jpeg", "gif", "webp"]
_CONVERSE_FORMATS: frozenset[str] = frozenset(get_args(ImageFormat))

# Converse rejects an image over 3.75 MB, and a rejected image that stays in history fails every
# later model call of the conversation.
MAX_IMAGE_BYTES = 3_750_000
# Longest edge in px. Not a Converse limit (that is 8000 px): Anthropic's vision guidance gives
# 1568 px as the edge above which a Claude model resizes an image before it reads it. A model
# that reads larger images gets less detail than the source holds.
MAX_EDGE = 1568
# Shortest long edge, in px, tried before an image that is still over MAX_IMAGE_BYTES is given up.
MIN_EDGE = 64
# Pixels of an image to encode again, from its header, checked before any pixel is decoded.
# Pillow and the codecs hold up to about 17 bytes a pixel (measured for WebP): about 370 MB.
MAX_DECODE_PIXELS = 20_000_000
# The same for a JPEG, at its full size. It decodes at 1/2 to 1/8 scale, but libjpeg holds the
# coefficients of a progressive or multi-scan JPEG at full size: up to 8 bytes a pixel (CMYK, no
# chroma subsampling), about 340 MB at this limit.
MAX_JPEG_PIXELS = 40_000_000
# Bytes of an image to convert. The metadata that Pillow parses on open (EXIF, text chunks)
# takes memory by its size, which the pixel limits do not bound.
MAX_INPUT_BYTES = 20 * 1024 * 1024
# Seconds a caller waits for a conversion, queue time included. A conversion that is still
# running then keeps its worker until Pillow returns.
CONVERSION_TIMEOUT_SECONDS = 30.0

# Untrusted bytes reach only these Pillow decoders (the JPEG decoder also opens MPO).
_OPEN_FORMATS = ("PNG", "JPEG", "GIF", "WEBP", "BMP")
# Two workers cap the memory of concurrent decodes at twice that of one image.
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="converse-image")


class ImageConversionError(ValueError):
    """The bytes are not an image that can be brought within MAX_IMAGE_BYTES and MAX_EDGE."""


async def convert_image(raw: bytes) -> tuple[bytes, ImageFormat]:
    """``raw`` as image bytes and a format that Converse accepts.

    The result is ``raw`` itself, with its real format, when it is a png, jpeg, gif or webp of
    at most MAX_IMAGE_BYTES and MAX_EDGE px per side whose first frame decodes. Later frames of
    an animation are not checked. Any other image is decoded (first frame only), downscaled
    until it fits and encoded again: png when it has transparency, jpeg otherwise. The EXIF
    orientation is not applied.

    At most two conversions run at a time, on their own threads; the others wait in a queue.
    Raises ImageConversionError when the bytes are over MAX_INPUT_BYTES or are not a readable
    png, jpeg, gif, webp or bmp image, when the image to encode again is over MAX_DECODE_PIXELS
    (MAX_JPEG_PIXELS for a JPEG), when it is still over MAX_IMAGE_BYTES at MIN_EDGE px, or when
    no result came within CONVERSION_TIMEOUT_SECONDS. The message never quotes the bytes.
    """
    try:
        return await asyncio.wait_for(
            asyncio.wrap_future(_POOL.submit(_convert_or_raise, raw)),
            CONVERSION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise ImageConversionError(
            f"not converted within {CONVERSION_TIMEOUT_SECONDS:g} s"
        ) from None


def _convert_or_raise(raw: bytes) -> tuple[bytes, ImageFormat]:
    try:
        return _convert(raw)
    except ImageConversionError:
        raise
    except UnidentifiedImageError as error:
        raise ImageConversionError("not a " + "/".join(_OPEN_FORMATS) + " image") from error
    except Exception as error:
        # Pillow decoders raise OSError, ValueError, SyntaxError, struct.error and more on
        # damaged input, and some of their messages quote bytes of the input. Callers get one
        # type and the name of the cause only, with the cause chained.
        raise ImageConversionError(
            f"damaged or unsupported image data ({type(error).__name__})"
        ) from error


def _convert(raw: bytes) -> tuple[bytes, ImageFormat]:
    if len(raw) > MAX_INPUT_BYTES:
        raise ImageConversionError(f"over the {MAX_INPUT_BYTES:,}-byte input limit")
    with Image.open(io.BytesIO(raw), formats=_OPEN_FORMATS) as image:
        # An MPO file is a JPEG with further images appended, and Converse reads it as that JPEG.
        fmt = "jpeg" if image.format == "MPO" else (image.format or "").lower()
        if fmt in _CONVERSE_FORMATS and len(raw) <= MAX_IMAGE_BYTES and max(image.size) <= MAX_EDGE:
            image.load()
            return raw, cast(ImageFormat, fmt)
        return _reencode(image)


def _reencode(image: Image.Image) -> tuple[bytes, ImageFormat]:
    """The first frame within MAX_EDGE and MAX_IMAGE_BYTES: png with transparency, else jpeg."""
    width, height = image.size
    is_jpeg = image.format in ("JPEG", "MPO")
    if width * height > (MAX_JPEG_PIXELS if is_jpeg else MAX_DECODE_PIXELS):
        raise ImageConversionError(f"{width}x{height} px exceeds the decode limit")
    if is_jpeg:
        long_side = max(width, height)
        image.draft(
            "RGB",
            (max(1, MAX_EDGE * width // long_side), max(1, MAX_EDGE * height // long_side)),
        )
    image.load()
    # A profile describes the colour space it was written for, so it is kept only when the
    # encoded image stays in that space.
    icc_profile = image.info.get("icc_profile") if image.mode in ("RGB", "RGBA", "P") else None
    if image.mode.startswith("I"):
        # A 16-bit PNG: convert() clips every value over 255 to white.
        image = image.point(lambda value: value / 257).convert("L")
    has_alpha = "transparency" in image.info or image.mode in ("RGBA", "LA", "PA")
    mode = "RGBA" if has_alpha else "RGB"
    if image.mode != mode:
        # Not called for the same mode: convert() then copies the whole image.
        image = image.convert(mode)
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
            raise ImageConversionError(f"still over {MAX_IMAGE_BYTES:,} bytes at {MIN_EDGE} px")
