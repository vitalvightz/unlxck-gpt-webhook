from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE_SOURCE = (REPO_ROOT / "Caddyfile").read_text(encoding="utf-8")


def test_production_caddyfile_preserves_api_proxy_and_security_headers():
    required_headers = (
        'Strict-Transport-Security "max-age=31536000; includeSubDomains"',
        'X-Content-Type-Options "nosniff"',
        'X-Frame-Options "DENY"',
        'Referrer-Policy "no-referrer"',
        'Permissions-Policy "camera=(), microphone=(), geolocation=()"',
        'Content-Security-Policy "default-src \'none\'; frame-ancestors \'none\'"',
    )

    assert "header {" in CADDYFILE_SOURCE
    for header in required_headers:
        assert header in CADDYFILE_SOURCE

    for preserved_directive in (
        "encode zstd gzip",
        "reverse_proxy api:8000",
        "dial_timeout 10s",
        "response_header_timeout 180s",
        "output stdout",
        "format json",
    ):
        assert preserved_directive in CADDYFILE_SOURCE
