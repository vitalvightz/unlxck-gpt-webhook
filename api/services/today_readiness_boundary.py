"""Canonical Today/readiness boundary.

The original fail-safe implementation lives in ``today_readiness_boundary_core``.
This module owns intake-injury synchronization so every caller—HTTP routes,
notifications and XP calculations—uses the same path.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterator

from api.contracts.training_day import resolve_training_day_str
from api.store import AppStore
from .active_plan import ActivePlanResolution, resolve_active_plan
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


class _BuildReadCache:
    """Successful reads shared within one Today build, never across requests.

    The intake-injury sync and the view each read the plan's intake row and the
    athlete's injury flags. Within one build those reads return the same rows,
    so the second is served from the first. Only successful reads are kept: a
    failed read is repeated by the next caller, so the view's readiness tracking
    still sees (and reports) its own failure. Any other store call may write an
    injury flag, so it clears cached flags and history. History keys include the
    requested limit; a smaller window never stands in for a larger one. Today
    never writes an intake row. Every caller gets its own copy of the rows.
    """

    def __init__(self, store: AppStore):
        self._store = store
        self._intakes: dict[str, Any] = {}
        self._flags: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        self._reads: dict[tuple[Any, ...], Any] = {}

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._store, name)
        if callable(attr) and name in {"get_latest_intake", "list_today_checkins", "list_session_completions"}:
            def read(*args: Any, **kwargs: Any) -> Any:
                key = (name, args, tuple(sorted(kwargs.items())))
                if key not in self._reads:
                    # Failed reads are never cached; the next safety consumer
                    # still performs its own read and records any failure.
                    self._reads[key] = deepcopy(attr(*args, **kwargs))
                return deepcopy(self._reads[key])
            return read
        if not callable(attr) or name.startswith(("get_", "list_")):
            return attr

        def write(*args: Any, **kwargs: Any) -> Any:
            self._flags.clear()
            self._reads.clear()
            return attr(*args, **kwargs)

        return write

    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> Any:
        return self._store.get_training_plan_for_athlete(plan_id, athlete_id)

    def get_intake(self, intake_id: str) -> Any:
        if intake_id not in self._intakes:
            self._intakes[intake_id] = self._store.get_intake(intake_id)
        return deepcopy(self._intakes[intake_id])

    def list_injury_flags(self, athlete_id: str, *, statuses: tuple = ("open", "monitoring"), limit: int = 20) -> Any:
        key = (athlete_id, tuple(statuses), limit)
        if key not in self._flags:
            self._flags[key] = [dict(row) for row in (self._store.list_injury_flags(athlete_id, statuses=statuses, limit=limit) or [])]
        return deepcopy(self._flags[key])


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


# The view resolves these again itself: a failed read is retried rather than
# shown as "no plan", and the view's schedule probe checks an unusable plan's row.
_VIEW_RESOLVES_AGAIN = frozenset({"read_failure", "unusable"})


def _resolve_active_plan_once(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime,
) -> ActivePlanResolution | None:
    """The active plan, resolved once for the intake sync and the Today view.

    None when resolution raised; each step then resolves and handles the error
    on its own, as before.
    """
    training_day = resolve_training_day_str(now, athlete_timezone=athlete_timezone)
    try:
        return resolve_active_plan(store, athlete_id, current_training_day=training_day)
    except Exception:
        return None


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
    # One instant for the whole build, so the sync and the view agree on the
    # training day the shared plan resolution was made for.
    now = now or datetime.now(timezone.utc)
    build_store = store
    store = _BuildReadCache(store)
    active_plan = _resolve_active_plan_once(
        store, athlete_id=athlete_id, athlete_timezone=athlete_timezone, now=now
    )
    sync_active_plan_intake_injuries(
        store,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
        active_plan=active_plan,
    )
    view = _build_core(
        _NoLegacyBootstrapStore(store),
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
        active_plan=(
            None if active_plan is None or active_plan.source in _VIEW_RESOLVES_AGAIN else active_plan
        ),
    )
    if views is not None:
        views[key] = (build_store, view.model_copy(deep=True))
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
