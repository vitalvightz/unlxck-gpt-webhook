#!/usr/bin/env python3
"""Run the Supabase runtime schema check with CI deploy-gate policy."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

# Allow running as a standalone script (``python tools/...``) from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.check_supabase_runtime_schema import main as run_runtime_schema_check  # noqa: E402

MANDATORY_MISSING_ENV_MESSAGE = (
    "Supabase runtime schema check is mandatory for Main/main deploys. "
    "Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for this workflow."
)
SKIP_MISSING_ENV_MESSAGE = (
    "Skipping live schema check; Supabase credentials are not configured for this "
    "non-Main/main run."
)
# Set by workflows (e.g. the deploy) that must never skip the live check.
REQUIRED_ENV_FLAG = "SUPABASE_SCHEMA_GATE_REQUIRED"


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def is_main_deploy(env: Mapping[str, str]) -> bool:
    """Return whether this run must pass the live check before deploying.

    Any push to Main/main deploys (deploy-hetzner.yml), whether or not the
    branch is protected, so branch protection is not required here: gating on
    it let the check skip silently while migrations were missing in production.
    """
    if _is_truthy(env.get(REQUIRED_ENV_FLAG)):
        return True
    ref_name = str(env.get("GITHUB_REF_NAME") or "").strip()
    return env.get("GITHUB_EVENT_NAME") == "push" and ref_name in {"Main", "main"}


def missing_supabase_credentials(env: Mapping[str, str]) -> list[str]:
    """Return required Supabase env var names that are blank or unset."""
    return [
        name
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        if not env.get(name, "").strip()
    ]


def run_gate(
    env: Mapping[str, str] = os.environ,
    schema_check=run_runtime_schema_check,
) -> int:
    """Run the schema check, allowing credential skips only off Main/main."""
    missing = missing_supabase_credentials(env)
    if missing:
        if is_main_deploy(env):
            print(f"::error::{MANDATORY_MISSING_ENV_MESSAGE}")
            print("Missing required environment variable(s): " + ", ".join(missing))
            return 2
        print(SKIP_MISSING_ENV_MESSAGE)
        print("Missing Supabase environment variable(s): " + ", ".join(missing))
        return 0

    return schema_check([])


def main() -> int:
    return run_gate()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
