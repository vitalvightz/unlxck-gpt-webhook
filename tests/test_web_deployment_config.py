from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from conftest import RENDER_BACKEND_URL


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"


def _rewrites(api_base_url: str | None = None) -> list[dict[str, str]]:
    env = os.environ.copy()
    if api_base_url is None:
        env.pop("NEXT_PUBLIC_API_BASE_URL", None)
    else:
        env["NEXT_PUBLIC_API_BASE_URL"] = api_base_url

    result = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            "import config from './next.config.ts'; const rewrites = await config.rewrites(); console.log(JSON.stringify(rewrites));",
        ],
        cwd=WEB_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    return json.loads(result.stdout)


def test_vercel_frontend_rewrite_defaults_to_local_backend():
    assert _rewrites() == [
        {
            "source": "/api/:path*",
            "destination": "http://127.0.0.1:8000/api/:path*",
        }
    ]


def test_vercel_frontend_rewrite_uses_configured_backend_destination():
    assert _rewrites(RENDER_BACKEND_URL) == [
        {
            "source": "/api/:path*",
            "destination": f"{RENDER_BACKEND_URL}/api/:path*",
        }
    ]
