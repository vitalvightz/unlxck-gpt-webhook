"""Short-lived reuse of the Today command view for read-only consumers.

``GET /api/today`` always builds a fresh command view. Every Today refresh in
the web app is immediately followed by an XP progress refresh, which used to
rebuild the whole command view (active plan, check-in, completions, schedule,
injuries, rehab state) a second time just to derive its "next action" list.

``/api/today`` now remembers the view it just built; XP progress reuses it when
it is recent and was built for the same athlete and timezone, and builds its own
otherwise. Any mutating request by the athlete drops the entry (see the
``invalidate_athlete_read_caches`` middleware in ``api.app``), so a check-in or
completion is never answered from a pre-write view. Only derived read models
use this; Today itself is never served from it.
"""

from __future__ import annotations

import os
import time
from threading import Lock
from typing import Any

from api.store import AppStore

DEFAULT_TODAY_COMMAND_CACHE_TTL_SECONDS = 30.0
_MAX_ENTRIES = 2000
_REGISTRY_ATTR = "_unlxck_today_command_cache"
_LOCK = Lock()


def _ttl_seconds() -> float:
    raw_value = os.getenv("TODAY_COMMAND_CACHE_TTL_SECONDS")
    if raw_value is None or not raw_value.strip():
        return DEFAULT_TODAY_COMMAND_CACHE_TTL_SECONDS
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        return DEFAULT_TODAY_COMMAND_CACHE_TTL_SECONDS
    return parsed if parsed >= 0 else DEFAULT_TODAY_COMMAND_CACHE_TTL_SECONDS


def _registry(store: AppStore) -> dict[str, tuple[str, Any, float]] | None:
    registry = getattr(store, _REGISTRY_ATTR, None)
    if isinstance(registry, dict):
        return registry
    with _LOCK:
        registry = getattr(store, _REGISTRY_ATTR, None)
        if isinstance(registry, dict):
            return registry
        registry = {}
        try:
            setattr(store, _REGISTRY_ATTR, registry)
        except Exception:  # noqa: BLE001 - an uncacheable store just rebuilds
            return None
        return registry


def remember_today_command(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    view: Any,
) -> None:
    ttl = _ttl_seconds()
    if ttl <= 0 or not athlete_id or view is None:
        return
    registry = _registry(store)
    if registry is None:
        return
    now = time.monotonic()
    with _LOCK:
        if athlete_id not in registry and len(registry) >= _MAX_ENTRIES:
            for key in [key for key, entry in registry.items() if entry[2] <= now]:
                registry.pop(key, None)
            if len(registry) >= _MAX_ENTRIES:
                registry.clear()
        registry[athlete_id] = (str(athlete_timezone or ""), view, now + ttl)


def recent_today_command(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
) -> Any | None:
    if not athlete_id or _ttl_seconds() <= 0:
        return None
    registry = _registry(store)
    if registry is None:
        return None
    with _LOCK:
        entry = registry.get(athlete_id)
        if entry is None:
            return None
        timezone_key, view, expires_at = entry
        if expires_at <= time.monotonic():
            registry.pop(athlete_id, None)
            return None
        if timezone_key != str(athlete_timezone or ""):
            return None
        return view


def forget_today_command(store: AppStore, athlete_id: str | None) -> None:
    if not athlete_id:
        return
    registry = getattr(store, _REGISTRY_ATTR, None)
    if not isinstance(registry, dict):
        return
    with _LOCK:
        registry.pop(athlete_id, None)


__all__ = [
    "forget_today_command",
    "recent_today_command",
    "remember_today_command",
]
