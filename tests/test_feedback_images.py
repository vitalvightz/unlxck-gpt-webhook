from __future__ import annotations

import io

import pytest
from PIL import Image, ImageCms, PngImagePlugin

from api.feedback_images import MAX_SCREENSHOT_BYTES, ScreenshotValidationError, sanitise_screenshot


def _image_bytes(image_format: str, *, size: tuple[int, int] = (40, 30), **save_options) -> bytes:
    image = Image.new("RGB", size, (170, 20, 45))
    output = io.BytesIO()
    image.save(output, format=image_format, **save_options)
    return output.getvalue()


@pytest.mark.parametrize(
    ("image_format", "mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_allowed_formats_are_fully_reencoded(image_format: str, mime: str):
    result = sanitise_screenshot(_image_bytes(image_format))
    assert result.mime == mime
    assert result.width == 40
    assert result.height == 30
    with Image.open(io.BytesIO(result.data)) as clean:
        clean.load()
        assert "exif" not in clean.info
        assert "xmp" not in clean.info
        assert "icc_profile" not in clean.info
        assert "comment" not in clean.info


def test_exif_gps_comment_and_png_text_do_not_survive():
    image = Image.new("RGB", (20, 10), "white")
    exif = Image.Exif()
    exif[0x010E] = "private comment"
    exif[0x0112] = 3
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}
    jpeg = io.BytesIO()
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    image.save(
        jpeg,
        format="JPEG",
        exif=exif,
        comment=b"private",
        xmp=b"private-xmp",
        icc_profile=icc,
    )
    clean_jpeg = sanitise_screenshot(jpeg.getvalue())
    with Image.open(io.BytesIO(clean_jpeg.data)) as clean:
        assert clean.getexif() == {}
        assert "comment" not in clean.info
        assert "xmp" not in clean.info
        assert "icc_profile" not in clean.info

    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("private-message", "secret")
    png = io.BytesIO()
    image.save(png, format="PNG", pnginfo=png_info)
    clean_png = sanitise_screenshot(png.getvalue())
    with Image.open(io.BytesIO(clean_png.data)) as clean:
        assert "private-message" not in clean.info


def test_orientation_is_applied_before_metadata_is_removed():
    image = Image.new("RGB", (20, 10), "white")
    exif = Image.Exif()
    exif[0x0112] = 6
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    result = sanitise_screenshot(output.getvalue())
    assert (result.width, result.height) == (10, 20)


def test_rejects_oversized_dimensions_and_pixel_bombs():
    with pytest.raises(ScreenshotValidationError, match="4096"):
        sanitise_screenshot(_image_bytes("PNG", size=(4097, 1)))
    with pytest.raises(ScreenshotValidationError, match="unsafe|12,000,000"):
        sanitise_screenshot(_image_bytes("PNG", size=(3500, 3500)))


def test_rejects_multiple_frames_unknown_formats_and_file_size():
    frames = [Image.new("RGB", (12, 12), color) for color in ("red", "blue")]
    animated = io.BytesIO()
    frames[0].save(animated, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(ScreenshotValidationError, match="multi-frame"):
        sanitise_screenshot(animated.getvalue())
    with pytest.raises(ScreenshotValidationError, match="PNG, JPEG, or WebP"):
        sanitise_screenshot(_image_bytes("BMP"))
    with pytest.raises(ScreenshotValidationError, match="5 MB"):
        sanitise_screenshot(b"x" * (MAX_SCREENSHOT_BYTES + 1))
