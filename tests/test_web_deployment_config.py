from __future__ import annotations

from pathlib import Path

from conftest import RENDER_BACKEND_URL


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
NEXT_CONFIG_SOURCE = (WEB_ROOT / "next.config.ts").read_text()


def _expected_destination(api_base_url: str | None = None) -> str:
    backend_url = api_base_url or "http://127.0.0.1:8000"
    return f"{backend_url}/api/:path*"


def test_vercel_frontend_rewrite_defaults_to_local_backend():
    assert 'source: "/api/:path*"' in NEXT_CONFIG_SOURCE
    assert 'process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"' in NEXT_CONFIG_SOURCE
    assert '`/api/:path*`' not in NEXT_CONFIG_SOURCE
    assert _expected_destination() == "http://127.0.0.1:8000/api/:path*"


def test_vercel_frontend_rewrite_uses_configured_backend_destination():
    assert _expected_destination(RENDER_BACKEND_URL) == f"{RENDER_BACKEND_URL}/api/:path*"


def test_browser_fetches_use_same_origin_api_paths():
    api_client_source = (WEB_ROOT / "lib" / "api.ts").read_text()

    assert 'if (typeof window !== "undefined") {' in api_client_source
    assert 'return "";' in api_client_source
