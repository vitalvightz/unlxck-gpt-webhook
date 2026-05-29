"""Time helpers shared across the generation runtime modules.

Kept dependency-free (only the stdlib ``datetime``) so any generation module
can import it without risking a circular import back into the runtime shim.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
