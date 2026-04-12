from __future__ import annotations

from pathlib import Path

from conftest import RENDER_BACKEND_URL


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
NEXT_CONFIG_SOURCE = (WEB_ROOT / "next.config.ts").read_text()


def _expected_destination(api_base_url: str) -> str:
    return f"{api_base_url}/api/:path*"


def test_vercel_frontend_rewrite_fails_production_build_without_backend_url():
    assert 'source: "/api/:path*"' in NEXT_CONFIG_SOURCE
    assert "NEXT_PUBLIC_API_BASE_URL must be set for production builds so /api rewrites are always configured." in NEXT_CONFIG_SOURCE
    assert 'process.env.NODE_ENV !== "production"' in NEXT_CONFIG_SOURCE
    assert "return null;" in NEXT_CONFIG_SOURCE
    assert "throw new Error(MISSING_PRODUCTION_REWRITE_ERROR);" in NEXT_CONFIG_SOURCE
    assert 'http://127.0.0.1:8000' in NEXT_CONFIG_SOURCE
    assert '`/api/:path*`' not in NEXT_CONFIG_SOURCE


def test_vercel_frontend_rewrite_uses_configured_backend_destination():
    assert _expected_destination(RENDER_BACKEND_URL) == f"{RENDER_BACKEND_URL}/api/:path*"


def test_browser_fetches_use_same_origin_api_paths():
    api_client_source = (WEB_ROOT / "lib" / "api.ts").read_text()

    assert 'if (typeof window !== "undefined") {' in api_client_source
    assert 'return "";' in api_client_source


def test_server_side_api_client_requires_backend_url_in_production():
    api_client_source = (WEB_ROOT / "lib" / "api.ts").read_text()

    assert "NEXT_PUBLIC_API_BASE_URL must be set for server-side API calls in production." in api_client_source
    assert 'process.env.NODE_ENV !== "production"' in api_client_source
    assert 'http://127.0.0.1:8000' in api_client_source
