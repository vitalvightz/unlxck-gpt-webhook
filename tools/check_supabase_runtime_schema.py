#!/usr/bin/env python3
"""Verify the *live* Supabase database matches the schema the backend requires.

This is a deployment gate: run it after applying migrations and before deploying
(or starting) the backend. It connects to the real Supabase project using the
same environment variables the app uses, asks the database to introspect its own
catalog, and diffs the result against the centralized requirements in
``api/schema_requirements.py``.

Design notes / safety:
* Uses the existing Supabase service-role integration (``SUPABASE_URL`` +
  ``SUPABASE_SERVICE_ROLE_KEY``). No new credential pattern is introduced.
* Introspection runs through the ``public.runtime_schema_introspection`` RPC,
  which returns catalog metadata only (object names + per-table RLS flags). It
  never reads application/user row data.
* Secrets are never printed. Errors are summarized, not dumped verbatim.
* Exits non-zero on any missing/incorrect schema piece so it can fail a deploy.

Usage:
    python tools/check_supabase_runtime_schema.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Allow running as a standalone script (``python tools/...``) from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.schema_requirements import (  # noqa: E402  (after sys.path setup)
    SchemaCheckResult,
    SchemaIntrospectionError,
    evaluate_payload,
)

INTROSPECTION_RPC = "runtime_schema_introspection"

# Defense in depth: redact long token-like strings (service-role keys, JWTs)
# from any exception text we surface, mirroring api/store.py's secret scrubbing.
_LONG_SECRET_PATTERN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")

_MISSING_RPC_HINT = (
    f"The '{INTROSPECTION_RPC}' RPC was not found in the database. Apply the "
    "latest Supabase migrations first "
    "(supabase/migrations/20260602000000_add_runtime_schema_introspection_rpc.sql), "
    "then re-run this check."
)


class RuntimeSchemaCheckError(RuntimeError):
    """Operational failure that prevents the check from running (not a schema gap)."""


def _require_env() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    missing = [
        name
        for name, value in (("SUPABASE_URL", url), ("SUPABASE_SERVICE_ROLE_KEY", key))
        if not value
    ]
    if missing:
        # Names only — never echo the values.
        raise RuntimeSchemaCheckError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )
    return url, key


def _build_client(url: str, key: str):
    try:
        import httpx
        from supabase import Client, ClientOptions, create_client
    except ImportError as exc:  # pragma: no cover - dependency wiring
        raise RuntimeSchemaCheckError(
            "supabase client libraries are not installed; run "
            "`pip install -r requirements.txt`"
        ) from exc

    # Match api/store.py: HTTP/1.1 only to avoid GOAWAY-frame RemoteProtocolErrors.
    try:
        http_client = httpx.Client(http2=False)
        client: Client = create_client(
            url, key, options=ClientOptions(httpx_client=http_client)
        )
    except Exception as exc:  # noqa: BLE001 - normalize into a clean operator message
        raise RuntimeSchemaCheckError(
            f"Failed to initialize the Supabase client. {_summarize_exc(exc)}"
        ) from exc
    return client


def fetch_introspection(client) -> dict:
    """Call the introspection RPC and return its payload as a plain dict."""
    try:
        response = client.rpc(INTROSPECTION_RPC).execute()
    except Exception as exc:  # noqa: BLE001 - normalize into a clean operator message
        text = str(exc).lower()
        if INTROSPECTION_RPC in text and (
            "could not find" in text
            or "does not exist" in text
            or "not found" in text
            or "404" in text
            or "pgrst202" in text
        ):
            raise RuntimeSchemaCheckError(_MISSING_RPC_HINT) from exc
        raise RuntimeSchemaCheckError(
            f"Failed to call '{INTROSPECTION_RPC}'. {_summarize_exc(exc)}"
        ) from exc

    payload = getattr(response, "data", None)
    if payload is None:
        raise RuntimeSchemaCheckError(
            f"'{INTROSPECTION_RPC}' returned no data. {_MISSING_RPC_HINT}"
        )
    if not isinstance(payload, dict):
        raise RuntimeSchemaCheckError(
            f"'{INTROSPECTION_RPC}' returned an unexpected payload type: "
            f"{type(payload).__name__}"
        )
    return payload


def _summarize_exc(exc: Exception) -> str:
    """Short, secret-free one-liner describing an exception."""
    summary = " ".join(str(exc).split())
    # Redact long token-like strings (e.g. the service-role key) before logging.
    summary = _LONG_SECRET_PATTERN.sub("[redacted_secret]", summary)
    if len(summary) > 200:
        summary = summary[:200] + "…"
    return f"{type(exc).__name__}: {summary}" if summary else type(exc).__name__


def run_check() -> SchemaCheckResult:
    """Connect, introspect, and evaluate. Raises RuntimeSchemaCheckError on I/O issues."""
    url, key = _require_env()
    client = _build_client(url, key)
    payload = fetch_introspection(client)
    try:
        return evaluate_payload(payload)
    except SchemaIntrospectionError as exc:
        raise RuntimeSchemaCheckError(
            f"Could not interpret the introspection payload: {exc}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_check()
    except RuntimeSchemaCheckError as exc:
        print("❌ Supabase runtime schema check could not run.")
        print(f"- {exc}")
        return 2

    print(result.format_report())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
