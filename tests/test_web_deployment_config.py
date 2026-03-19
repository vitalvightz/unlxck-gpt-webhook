from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NEXT_CONFIG = REPO_ROOT / "web" / "next.config.ts"


def test_vercel_frontend_rewrite_uses_backend_base_url_env_for_render_deployments():
    source = NEXT_CONFIG.read_text()

    assert 'process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"' in source
    assert 'source: "/api/:path*"' in source
    assert 'destination: `${backendUrl}/api/:path*`' in source
