"""Fail a production deployment unless the final XP hardening is live."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import Any

from supabase import create_client


EXPECTED_VERSION = "20260803182000"


def _payload(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, Mapping) else None


def validate_xp_hardening_rollout() -> None:
    url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not service_key:
        raise RuntimeError("Supabase service-role configuration is missing")

    response = create_client(url, service_key).rpc(
        "validate_xp_abuse_hardening"
    ).execute()
    value = _payload(getattr(response, "data", None))
    if not value:
        raise RuntimeError("XP hardening validation returned no payload")

    valid = (
        value.get("ok") is True
        and str(value.get("version") or "") == EXPECTED_VERSION
        and value.get("rollout_ready") is True
        and value.get("open_plan_scope_ready") is True
    )
    if not valid:
        raise RuntimeError("XP hardening rollout is incomplete")


if __name__ == "__main__":
    try:
        validate_xp_hardening_rollout()
    except Exception as exc:  # noqa: BLE001 - deployment gate must fail closed
        print(f"XP hardening deployment gate failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("XP hardening deployment gate passed")
