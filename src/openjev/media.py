"""Bounded, local-only image decoding. No URL fetching or file reads."""

import base64
import binascii
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Settings
from .errors import APIError


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
                picture = ImageOps.exif_transpose(source).convert("RGB")
                picture.thumbnail((settings.image_max_edge, settings.image_max_edge))
                output = io.BytesIO()
                picture.save(output, format="PNG")
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
