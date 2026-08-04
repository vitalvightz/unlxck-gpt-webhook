"""Canonical Today/readiness boundary.

The original fail-safe implementation lives in ``today_readiness_boundary_core``.
This module owns intake-injury synchronization so every caller—HTTP routes,
notifications and XP calculations—uses the same path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.store import AppStore
from .intake_injury_sync import sync_active_plan_intake_injuries
from .today_readiness_boundary_core import (
    ReadinessContextHealth,
    resolve_today_landing,
    submit_today_checkin,
    submit_today_injury_checkin,
    upsert_session_completion,
)
from .today_readiness_boundary_core import build_today_command_view as _build_core


class _NoLegacyBootstrapStore:
    """Delegate reads but prevent the superseded lazy intake bootstrap writing."""

    def __init__(self, store: AppStore):
        self._store = store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def create_injury_flag(self, athlete_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("legacy intake injury bootstrap is disabled")


def build_today_command_view(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
):
    """Synchronize intake injuries before every canonical Today build."""
    sync_active_plan_intake_injuries(
        store,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
    )
    return _build_core(
        _NoLegacyBootstrapStore(store),
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
    )


__all__ = [
    "ReadinessContextHealth",
    "build_today_command_view",
    "resolve_today_landing",
    "submit_today_checkin",
    "submit_today_injury_checkin",
    "upsert_session_completion",
]
