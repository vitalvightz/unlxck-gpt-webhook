"""Strict, metadata-free screenshot decoding for beta feedback uploads."""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
MAX_SCREENSHOT_DIMENSION = 4096
MAX_SCREENSHOT_PIXELS = 12_000_000
_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
_FORMAT_DETAILS = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}

# Pillow checks this limit while decoding, before our post-decode dimension
# checks can run. The application never needs to decode larger images.
Image.MAX_IMAGE_PIXELS = MAX_SCREENSHOT_PIXELS


class ScreenshotValidationError(ValueError):
    """Raised for a stable, client-safe invalid screenshot response."""


@dataclass(frozen=True)
class SanitisedScreenshot:
    data: bytes
    mime: str
    extension: str
    width: int
    height: int


def _validate_geometry(width: int, height: int) -> None:
    if width < 1 or height < 1:
        raise ScreenshotValidationError("Screenshot dimensions are invalid.")
    if width > MAX_SCREENSHOT_DIMENSION or height > MAX_SCREENSHOT_DIMENSION:
        raise ScreenshotValidationError("Screenshot dimensions exceed 4096 x 4096 pixels.")
    if width * height > MAX_SCREENSHOT_PIXELS:
        raise ScreenshotValidationError("Screenshot exceeds the 12,000,000 pixel limit.")


def _open_and_verify(data: bytes) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image_format = str(image.format or "").upper()
                if image_format not in _ALLOWED_FORMATS:
                    raise ScreenshotValidationError("Use a PNG, JPEG, or WebP screenshot.")
                if int(getattr(image, "n_frames", 1)) != 1:
                    raise ScreenshotValidationError("Animated or multi-frame screenshots are not supported.")
                _validate_geometry(*image.size)
                image.verify()
                return image_format
    except ScreenshotValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ScreenshotValidationError("Screenshot dimensions are unsafe.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ScreenshotValidationError("The screenshot could not be decoded.") from None


def sanitise_screenshot(data: bytes) -> SanitisedScreenshot:
    """Decode, orient, copy pixels into a fresh image, and re-encode.

    The returned bytes contain no source metadata. Validation intentionally
    ignores the caller-provided MIME type and filename.
    """

    if not data:
        raise ScreenshotValidationError("The screenshot is empty.")
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise ScreenshotValidationError("Screenshot must be 5 MB or smaller.")

    image_format = _open_and_verify(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if int(getattr(source, "n_frames", 1)) != 1:
                    raise ScreenshotValidationError("Animated or multi-frame screenshots are not supported.")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                _validate_geometry(*oriented.size)
                has_alpha = "A" in oriented.getbands() or "transparency" in source.info
                target_mode = "RGBA" if has_alpha and image_format != "JPEG" else "RGB"
                converted = oriented.convert(target_mode)
                # frombytes creates a pixel-only image with an empty info dict.
                clean = Image.frombytes(target_mode, converted.size, converted.tobytes())

        output = io.BytesIO()
        if image_format == "JPEG":
            clean.save(output, format="JPEG", quality=90, optimize=True, progressive=False)
        elif image_format == "PNG":
            clean.save(output, format="PNG", optimize=True)
        else:
            clean.save(output, format="WEBP", lossless=True, method=4)
        encoded = output.getvalue()
    except ScreenshotValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ScreenshotValidationError("Screenshot dimensions are unsafe.") from None
    except (OSError, ValueError):
        raise ScreenshotValidationError("The screenshot could not be sanitised.") from None

    if len(encoded) > MAX_SCREENSHOT_BYTES:
        raise ScreenshotValidationError("Sanitised screenshot must be 5 MB or smaller.")

    # Validate the exact object that will be uploaded, including a full decode.
    verified_format = _open_and_verify(encoded)
    try:
        with Image.open(io.BytesIO(encoded)) as verified:
            verified.load()
            forbidden_metadata = {
                "exif", "xmp", "icc_profile", "comment", "comments", "text", "xml", "photoshop"
            }
            if forbidden_metadata.intersection(key.lower() for key in verified.info):
                raise ScreenshotValidationError("Sanitised screenshot retained auxiliary metadata.")
            width, height = verified.size
    except ScreenshotValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ScreenshotValidationError("Sanitised screenshot validation failed.") from None

    if verified_format != image_format:
        raise ScreenshotValidationError("Sanitised screenshot format changed unexpectedly.")
    mime, extension = _FORMAT_DETAILS[image_format]
    return SanitisedScreenshot(
        data=encoded,
        mime=mime,
        extension=extension,
        width=width,
        height=height,
    )
