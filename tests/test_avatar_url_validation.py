import base64

import pytest
from pydantic import ValidationError

from api.models import ProfileUpdateRequest


def _data_url(kind: str, raw: bytes) -> str:
    return f"data:image/{kind};base64,{base64.b64encode(raw).decode()}"


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/photo.jpg",
        _data_url("jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 40),
        _data_url("png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40),
        _data_url("gif", b"GIF89a" + b"\x00" * 40),
        _data_url("webp", b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 40),
    ],
)
def test_avatar_url_accepts_https_and_real_raster_images(value):
    assert ProfileUpdateRequest(avatar_url=value).avatar_url == value


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "http://example.com/photo.jpg",
        "https://user:pass@example.com/photo.jpg",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        _data_url("svg+xml", b"<svg onload=alert(1)>"),
        # Declared as JPEG but the bytes are HTML.
        _data_url("jpeg", b"<script>alert(1)</script>" + b"\x00" * 20),
        "data:image/png;base64,not valid",
        "https:///nohost",
    ],
)
def test_avatar_url_rejects_scriptable_or_mislabelled_values(value):
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(avatar_url=value)


def test_avatar_url_blank_clears():
    assert ProfileUpdateRequest(avatar_url="  ").avatar_url == ""
