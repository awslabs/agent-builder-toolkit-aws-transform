# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Image bytes in the form the Bedrock Converse API accepts."""

import io
import re
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Literal, cast, get_args

from PIL import Image, ImageMath, ImageOps, ImageSequence, UnidentifiedImageError

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
# Pixels of the one frame that is decoded to be encoded again, checked against the header before
# any pixel is decoded. Pillow and the codecs hold up to about 17 bytes a pixel (measured for
# WebP), which is about 350 MB for one image at this limit.
MAX_DECODE_PIXELS = 20_000_000
# Pixels decoded to check an image that is passed on as it is, summed over its frames. Each
# frame is within MAX_EDGE, so this bounds the time of the check, not its memory.
MAX_FRAME_PIXELS = 50_000_000
# Frames decoded in that check. A frame costs a seek whatever its size, so the pixel budget
# alone does not bound the time.
MAX_FRAMES = 1_000

# Untrusted bytes reach only these Pillow decoders (the JPEG decoder also opens MPO). Two are
# left out because the header size does not bound their memory: ICO is decoded on open at the
# size its payload states, and TIFF takes memory by its tile size and its count of strips.
_OPEN_FORMATS = ("PNG", "JPEG", "GIF", "WEBP", "BMP", "PPM")
# Finite float32 bound: a pixel beyond it, or NaN, is zeroed before the value range is measured.
_FLOAT_LIMIT = 3.0e38
# A marker in JPEG scan data: not a stuffed 0xFF, a restart marker or a fill byte.
_JPEG_MARKER = re.compile(rb"\xff[^\x00\xd0-\xd7\xff]")
# Two workers cap the memory of concurrent decodes at twice that of one image, and keep the
# queue of waiting images off the event loop and off the default executor that the rest of the
# agent shares.
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="converse-image")


class ImageConversionError(ValueError):
    """The bytes are not an image that can be brought within MAX_IMAGE_BYTES and MAX_EDGE."""


def submit_conversion(raw: bytes) -> Future[tuple[bytes, ImageFormat]]:
    """Start the conversion of ``raw`` to image bytes and a format that Converse accepts.

    The result is ``raw`` itself, with its real format, when it is a complete png, jpeg, gif or
    webp of at most MAX_IMAGE_BYTES and MAX_EDGE px per side (every frame) with at most
    MAX_FRAMES frames that hold at most MAX_FRAME_PIXELS. Any other image is decoded (first
    frame only), downscaled until it fits and encoded again: png when it has transparency,
    jpeg otherwise.

    At most two conversions run at a time; the others wait in a queue. The future raises
    ImageConversionError when the bytes are not a readable image of a supported format, when
    the frame to encode again is over MAX_DECODE_PIXELS, or when the image is still over
    MAX_IMAGE_BYTES at MIN_EDGE px. The message never quotes the bytes.
    """
    return _POOL.submit(_convert_or_raise, raw)


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
    with Image.open(io.BytesIO(raw), formats=_OPEN_FORMATS) as image:
        pil_format = (image.format or "").lower()
        # An MPO file is a JPEG with further images appended, and Converse reads it as that JPEG.
        fmt = "jpeg" if pil_format == "mpo" else pil_format
        fits = len(raw) <= MAX_IMAGE_BYTES and max(image.size) <= MAX_EDGE
        if fits and fmt in _CONVERSE_FORMATS:
            if _decode_frames(image, first_only=pil_format == "mpo"):
                return raw, cast(ImageFormat, fmt)
            image.seek(0)
        return _reencode(image, raw)


def _decode_frames(image: Image.Image, first_only: bool) -> bool:
    """Decode the frames, so that a damaged or truncated frame raises.

    False, with the later frames not decoded, when there are more than MAX_FRAMES frames, when
    they hold more than MAX_FRAME_PIXELS, or when one of them is over MAX_EDGE (a GIF frame
    can be larger than the first one).
    """
    if first_only:
        image.load()
        return True
    decoded = 0
    for index, frame in enumerate(ImageSequence.Iterator(image)):
        decoded += frame.width * frame.height
        if index >= MAX_FRAMES or decoded > MAX_FRAME_PIXELS or max(frame.size) > MAX_EDGE:
            return False
        frame.load()
    return True


def _reencode(image: Image.Image, raw: bytes) -> tuple[bytes, ImageFormat]:
    """The first frame within MAX_EDGE and MAX_IMAGE_BYTES: png with transparency, else jpeg."""
    width, height = image.size
    if image.format in ("JPEG", "MPO"):
        # A JPEG decodes at 1/2, 1/4 or 1/8 scale, which keeps a large photo inside the budget.
        long_side = max(width, height)
        image.draft(
            "RGB",
            (max(1, MAX_EDGE * width // long_side), max(1, MAX_EDGE * height // long_side)),
        )
        # The decoder holds the coefficients of a JPEG at full size, at any scale, when it is
        # progressive or when its first scan does not code every component.
        if not image.info.get("progressive") and _has_one_scan(raw, len(image.getbands())):
            width, height = image.size
    if width * height > MAX_DECODE_PIXELS:
        raise ImageConversionError(f"{width}x{height} px exceeds the decode limit")
    image.load()
    ImageOps.exif_transpose(image, in_place=True)
    # A profile describes the colour space it was written for, so it is kept only when the
    # encoded image stays in that space.
    keeps_colour_space = image.mode in ("RGB", "RGBA", "P", "PA")
    icc_profile = image.info.get("icc_profile") if keeps_colour_space else None
    colour_key = image.info.get("transparency")
    if image.mode.startswith("I;16") or image.mode in ("I", "F"):
        image = _to_grayscale(image, colour_key)
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
            raise ImageConversionError(f"still over {MAX_IMAGE_BYTES:,} bytes at {MIN_EDGE} px")


def _has_one_scan(raw: bytes, components: int) -> bool:
    """Whether one scan codes all ``components`` of a JPEG file's first image; False if unsure."""
    position = 2
    while position + 4 < len(raw) and raw[position] == 0xFF:
        marker, in_scan = raw[position + 1], raw[position + 4]
        position += 2 + int.from_bytes(raw[position + 2 : position + 4], "big")
        if marker == 0xDA:
            following = _JPEG_MARKER.search(raw, position)
            last = following is None or following.group()[1] == 0xD9
            return last and in_scan == components
    return False


def _to_grayscale(image: Image.Image, colour_key: object) -> Image.Image:
    """Map a 16-bit, 32-bit or float image onto 0-255 over its own value range, as L or LA.

    The image is brought within MAX_EDGE first, so that the mapping works on a small image
    whatever the size of the source. An integer colour key becomes the alpha channel.
    """
    mode = image.mode
    values = image if mode in ("I", "F") else image.convert("I")
    box = (MAX_EDGE, MAX_EDGE)
    alpha = None
    if isinstance(colour_key, int):
        opaque_but_key = [255] * 0x10000
        opaque_but_key[colour_key] = 0
        alpha = values.point(opaque_but_key, "L")
        alpha.thumbnail(box, Image.Resampling.BOX)
    # A box filter has no negative weight, so a NaN or infinite pixel reaches only the output
    # pixels that cover it.
    values.thumbnail(box, Image.Resampling.BOX)
    floats = values.convert("F")
    if mode == "F":
        floats = _finite(floats)
    low, high = cast(tuple[float, float], floats.getextrema())
    if high <= low:
        full = _full_scale(mode, high)
        gray = Image.new("L", floats.size, round(min(max(high, 0.0), full) / full * 255))
    else:
        scale = 255 / (high - low)
        gray = floats.point(lambda value: (value - low) * scale).convert("L")
    return gray if alpha is None else Image.merge("LA", (gray, alpha))


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
