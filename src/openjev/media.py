"""Bounded, local-only image decoding. No URL fetching or file reads."""

import base64
import binascii
import io
import math
import struct
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Settings
from .errors import APIError

_ORIENTATION = 0x0112
_TRANSPOSED = {5, 6, 7, 8}  # EXIF orientations that swap width and height
MIN_IMAGE_TOKENS = 8  # llama.cpp's floor for Qwen-VL images (clip.cpp)


def _f32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def smart_size(width: int, height: int, align: int, min_pixels: int, max_pixels: int):
    """llama.cpp's Qwen-VL `smart_resize` (mtmd-image.cpp), float32 rounding included."""

    def by_factor(value: float, rounding) -> int:
        return int(rounding(_f32(_f32(value) / align))) * align

    def nearest(x: float) -> float:  # std::round: halves away from zero
        return math.floor(x + 0.5)

    h_bar = max(align, by_factor(height, nearest))
    w_bar = max(align, by_factor(width, nearest))
    if h_bar * w_bar > max_pixels:
        beta = _f32(math.sqrt(_f32(width * height / max_pixels)))
        h_bar = max(align, by_factor(_f32(height / beta), math.floor))
        w_bar = max(align, by_factor(_f32(width / beta), math.floor))
    elif h_bar * w_bar < min_pixels:
        beta = _f32(math.sqrt(_f32(min_pixels / (width * height))))
        h_bar = by_factor(_f32(height * beta), math.ceil)
        w_bar = by_factor(_f32(width * beta), math.ceil)
    return w_bar, h_bar


def encoder_size(width: int, height: int, grid: int, token_budget: int) -> tuple[int, int]:
    """The size a Qwen-VL vision encoder resizes an image to: aligned to `grid` pixels
    (patch x spatial merge) and within `token_budget` visual tokens."""
    return smart_size(
        width, height, grid, MIN_IMAGE_TOKENS * grid * grid, token_budget * grid * grid
    )


def output_size(width: int, height: int, settings: Settings) -> tuple[int, int]:
    """Size sent to the backend.

    Images that need shrinking are resized once, straight to the size the vision encoder
    will use, so llama.cpp does not resample them a second time. Smaller images keep their
    size; the backend aligns them to its token grid itself, as before.
    """
    scale = min(1.0, settings.image_max_edge / max(width, height))
    capped = (max(1, round(width * scale)), max(1, round(height * scale)))
    if not settings.image_align:
        return capped
    target = encoder_size(*capped, settings.image_align, settings.image_token_budget)
    if scale == 1.0 and target[0] * target[1] >= width * height:
        return width, height
    return target


def sanitize_image(value: str, settings: Settings) -> str:
    if not isinstance(value, str) or not value.startswith("data:image/"):
        raise APIError("Images must be inline data URLs (PNG, JPEG or WebP).")
    header, separator, encoded = value.partition(",")
    if not separator or header not in {
        "data:image/png;base64",
        "data:image/jpeg;base64",
        "data:image/webp;base64",
    }:
        raise APIError("Unsupported image format; use base64 PNG, JPEG or WebP.")
    if len(encoded) > settings.max_body_bytes:
        raise APIError("Image exceeds the request size limit.", 413)
    try:
        raw = base64.b64decode(encoded, validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise APIError("Image bytes are not PNG, JPEG or WebP.")
                if source.width * source.height > settings.image_max_pixels:
                    raise APIError("Decoded image exceeds the pixel limit.", 413)
                if getattr(source, "n_frames", 1) != 1:
                    raise APIError("Animated images are unsupported; send individual frames.")
                swapped = source.getexif().get(_ORIENTATION) in _TRANSPOSED
                upright = (source.height, source.width) if swapped else source.size
                target = output_size(*upright, settings)
                if source.format == "JPEG" and target != upright:
                    # Let libjpeg decode at the smallest DCT scale that still covers the target.
                    source.draft("RGB", target[::-1] if swapped else target)
                picture = ImageOps.exif_transpose(source).convert("RGB")
                if picture.size != target:
                    picture = picture.resize(target, Image.Resampling.BICUBIC, reducing_gap=2.0)
                output = io.BytesIO()
                picture.save(output, format="PNG", compress_level=1)
        return base64.b64encode(output.getvalue()).decode("ascii")
    except APIError:
        raise
    except (
        ValueError,
        OSError,
        binascii.Error,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise APIError("Invalid or unsafe image data.") from exc
