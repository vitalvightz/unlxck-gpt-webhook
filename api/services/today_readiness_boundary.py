"""Canonical Today/readiness boundary.

The original fail-safe implementation lives in ``today_readiness_boundary_core``.
This module owns intake-injury synchronization so every caller—HTTP routes,
notifications and XP calculations—uses the same path.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Iterator

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


_REUSABLE_VIEWS: ContextVar[dict[tuple[Any, ...], tuple[AppStore, Any]] | None] = ContextVar(
    "today_command_view_reuse", default=None
)


@contextmanager
def reuse_today_command_views() -> Iterator[None]:
    """Build each athlete's Today view once per (timezone, instant) in this scope.

    For callers that evaluate the same athlete several times at one fixed
    instant, such as the push sweep, whose dispatchers each used to rebuild the
    full view. Only builds with an explicit ``now`` are reused, and every caller
    gets its own deep copy, so one consumer cannot change what the next reads.
    """
    token = _REUSABLE_VIEWS.set({})
    try:
        yield
    finally:
        _REUSABLE_VIEWS.reset(token)


def build_today_command_view(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
):
    """Synchronize intake injuries before every canonical Today build."""
    views = _REUSABLE_VIEWS.get() if now is not None else None
    key = (id(store), athlete_id, athlete_timezone, now)
    if views is not None:
        cached = views.get(key)
        if cached is not None and cached[0] is store:
            return cached[1].model_copy(deep=True)
    sync_active_plan_intake_injuries(
        store,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
    )
    view = _build_core(
        _NoLegacyBootstrapStore(store),
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
    )
    if views is not None:
        views[key] = (store, view.model_copy(deep=True))
    return view


__all__ = [
    "ReadinessContextHealth",
    "build_today_command_view",
    "resolve_today_landing",
    "reuse_today_command_views",
    "submit_today_checkin",
    "submit_today_injury_checkin",
    "upsert_session_completion",
]
