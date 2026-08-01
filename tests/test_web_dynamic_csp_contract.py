from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_dynamic_rendering_remains_explicit_while_nonce_csp_is_used() -> None:
    """A per-request CSP nonce requires request-time rendering.

    This contract prevents a future performance cleanup from silently removing
    dynamic rendering while the root layout still reads the nonce from request
    headers, which would either break scripts or encourage weakening the CSP.
    """
    layout = _read("web/app/layout.tsx")
    proxy = _read("web/proxy.ts")

    assert 'export const dynamic = "force-dynamic"' in layout
    assert "await headers()" in layout
    assert 'requestHeaders.set("x-nonce", nonce)' in proxy
    assert "'strict-dynamic'" in proxy


def test_nonce_proxy_skips_static_assets_and_backend_rewrites() -> None:
    """Keep middleware work off static assets and API proxy traffic."""
    proxy = _read("web/proxy.ts")

    assert "api|_next/static|_next/image" in proxy
    assert "manifest.webmanifest" in proxy
    assert "next-router-prefetch" in proxy
