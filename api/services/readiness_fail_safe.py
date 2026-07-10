"""Fail-safe boundary for Today readiness and session execution.

The deterministic readiness engine remains the authority for normal decisions. This
module only handles UNKNOWN context: a store/schema/classifier failure must never be
misread as healthy history, no injuries, or a safe session.

The public functions intentionally mirror ``api.services.today_service`` so routes can
switch to this boundary without changing API contracts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping

from fastapi import HTTPException, status

from api.contracts.command_view import CommandView, make_risk, sort_risk_watch
from api.contracts.injury_checkin import injury_consequence_tier
from api.contracts.readiness_message import ReadinessAdjustment
from api.services import today_service as _today_service
from api.store import AppStore

logger = logging.getLogger(__name__)

ReadinessContextStatus = Literal["complete", "degraded", "unavailable"]

_FAIL_SAFE_TITLE = "Readiness check limited."
_FAIL_SAFE_REASON = (
    "Some safety context could not be verified, so this session is not cleared "
    "as train-as-planned."
)
_FAIL_SAFE_ACTION = (
    "Use recovery or low-load technical work only. Do not hard spar, sprint, "
    "lift maximally, or add hard conditioning."
)
_FAIL_SAFE_SAFETY = (
    "Stop if pain, instability, swelling, illness, neurological symptoms, "
    "or worsening symptoms appear."
)
_CURRENT_SESSION_EXECUTION_STATUSES = frozenset({"started", "done", "modified"})
_UNAVAILABLE_COMPONENTS = frozenset({"injury_flags", "injury_classification", "schedule"})


@dataclass
class ReadinessContextHealth:
    """Machine-readable health state for safety-critical readiness inputs."""

    failures: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> ReadinessContextStatus:
        if not self.failures:
            return "complete"
        if any(component in _UNAVAILABLE_COMPONENTS for component in self.failures):
            return "unavailable"
        return "degraded"

    @property
    def components(self) -> tuple[str, ...]:
        return tuple(sorted(self.failures))

    def record(self, component: str, exc: BaseException) -> None:
        if component in self.failures:
            return
        self.failures[component] = type(exc).__name__
        logger.error(
            "Readiness context load failed: component=%s error_type=%s",
            component,
            type(exc).__name__,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_tag("readiness_context_component", component)
                scope.set_tag("readiness_context_status", self.status)
                scope.set_level("error")
                sentry_sdk.capture_exception(exc)
        except Exception:
            # Observability must not become another availability dependency.
            logger.debug("Unable to report readiness context failure to Sentry", exc_info=True)


class _ReadinessTrackingStore:
    """Proxy critical reads, preserving failures instead of converting them to health."""

    def __init__(
        self,
        store: AppStore,
        health: ReadinessContextHealth,
        *,
        cache_injury_flags: bool = False,
    ):
        self._store = store
        self.health = health
        self.last_plan: Mapping[str, Any] | None = None
        self._cache_injury_flags = cache_injury_flags
        self._injury_flags_cache: list[dict[str, Any]] | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def _call_list(
        self,
        component: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        method = getattr(self._store, method_name, None)
        if not callable(method):
            self.health.record(
                component,
                RuntimeError(f"required store method {method_name} is unavailable"),
            )
            return []
        try:
            return [dict(row) for row in (method(*args, **kwargs) or [])]
        except Exception as exc:
            self.health.record(component, exc)
            return []

    def list_today_checkins(
        self,
        athlete_id: str,
        *,
        limit: int = 14,
    ) -> list[dict[str, Any]]:
        return self._call_list(
            "recent_checkins",
            "list_today_checkins",
            athlete_id,
            limit=limit,
        )

    def list_session_completions(
        self,
        athlete_id: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        return self._call_list(
            "recent_sessions",
            "list_session_completions",
            athlete_id,
            limit=limit,
        )

    def list_injury_flags(
        self,
        athlete_id: str,
        *,
        statuses: tuple = ("open", "monitoring"),
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self._cache_injury_flags and self._injury_flags_cache is not None:
            return [dict(row) for row in self._injury_flags_cache[:limit]]

        rows = self._call_list(
            "injury_flags",
            "list_injury_flags",
            athlete_id,
            statuses=statuses,
            limit=limit,
        )
        if self._cache_injury_flags and not self.health.failures:
            self._injury_flags_cache = [dict(row) for row in rows]
        for row in rows:
            if str(row.get("status") or "") not in {"open", "monitoring"}:
                continue
            if row.get("consequence") not in (None, ""):
                continue
            try:
                injury_consequence_tier(
                    row.get("body_area"),
                    row.get("description"),
                    severity=row.get("severity"),
                )
            except Exception as exc:
                self.health.record("injury_classification", exc)
                break
        return rows

    def get_intake(self, intake_id: str) -> Mapping[str, Any] | None:
        method = getattr(self._store, "get_intake", None)
        if not callable(method):
            self.health.record(
                "intake",
                RuntimeError("required store method get_intake is unavailable"),
            )
            return None
        try:
            row = method(intake_id)
        except Exception as exc:
            self.health.record("intake", exc)
            return None
        if row is None:
            self.health.record(
                "intake",
                LookupError("active plan references an intake row that was not found"),
            )
        return row

    def get_plan_for_athlete(
        self,
        plan_id: str,
        athlete_id: str,
    ) -> Mapping[str, Any] | None:
        # This is the ownership-authority read, not optional readiness context.
        # Let failures abort the request; returning None would misreport an outage
        # as "plan not found" and could bypass the intended ownership distinction.
        row = self._store.get_plan_for_athlete(plan_id, athlete_id)
        if row:
            self.last_plan = row
        return row


def _legacy_plan_has_schedule_source(plan_row: Mapping[str, Any]) -> bool:
    brief = plan_row.get("planning_brief")
    if not isinstance(brief, Mapping):
        return False
    role_map = brief.get("weekly_role_map")
    return isinstance(role_map, Mapping) and bool(role_map.get("weeks"))


def _probe_schedule(
    plan_row: Mapping[str, Any] | None,
    training_day: str,
    health: ReadinessContextHealth,
) -> None:
    """Record parser/resolver failures without treating a legitimate rest day as failure."""

    if not plan_row:
        return

    try:
        structured_weeks = _today_service._structured_plan_weeks(plan_row)
    except Exception as exc:
        health.record("schedule", exc)
        return

    if structured_weeks:
        try:
            # A clean ``None`` is a legitimate rest day. Only parser failure is UNKNOWN.
            _today_service._structured_today_session_entry(plan_row, training_day)
        except Exception as exc:
            health.record("schedule", exc)
        return

    if not _legacy_plan_has_schedule_source(plan_row):
        return

    try:
        (
            _latest_visible_plan_row,
            parse_iso_date,
            resolve_current_week,
            resolve_today_and_next,
            _weekly_schedule_or_none,
        ) = _today_service._plan_schedule_helpers()
        training_date = parse_iso_date(training_day)
        if training_date is None:
            raise ValueError("training day could not be parsed")
        _week_index, week = resolve_current_week(plan_row, today=training_date)
        resolve_today_and_next(week, today=training_date)
    except Exception as exc:
        health.record("schedule", exc)


def _status_warning(health: ReadinessContextHealth) -> str:
    components = ", ".join(health.components)
    return (
        f"readiness_context_status={health.status}; "
        f"unverified_components={components}"
    )


def _fail_safe_decision(
    *,
    existing_triggers: Any,
    health: ReadinessContextHealth,
) -> ReadinessAdjustment:
    triggers = [str(item) for item in (existing_triggers or []) if str(item)]
    triggers.append(f"readiness_context_status:{health.status}")
    triggers.extend(f"readiness_context_failure:{component}" for component in health.components)
    return ReadinessAdjustment(
        decision="modify",
        title=_FAIL_SAFE_TITLE,
        reason=_FAIL_SAFE_REASON,
        action=_FAIL_SAFE_ACTION,
        safety=_FAIL_SAFE_SAFETY,
        triggers=tuple(dict.fromkeys(triggers)),
        session_risk="unknown",
    )


def _patch_persisted_recommendation(
    store: AppStore,
    *,
    athlete_id: str,
    row: Mapping[str, Any],
    health: ReadinessContextHealth,
) -> dict[str, Any]:
    current_state = str(row.get("recommendation_state") or "")
    patched = dict(row)
    warnings = [str(item) for item in (patched.get("warnings") or [])]
    if not health.failures:
        patched["warnings"] = warnings
        return patched

    warning = _status_warning(health)
    if warning not in warnings:
        warnings.append(warning)
    patched["warnings"] = warnings

    if current_state == "train_as_planned":
        decision = _fail_safe_decision(
            existing_triggers=row.get("recommendation_triggers"),
            health=health,
        )
        fields = _today_service._recommendation_fields_from_decision(
            checkin_row=row,
            decision=decision,
        )
    else:
        triggers = [str(item) for item in (row.get("recommendation_triggers") or []) if str(item)]
        triggers.append(f"readiness_context_status:{health.status}")
        triggers.extend(
            f"readiness_context_failure:{component}"
            for component in health.components
        )
        fields = {
            "plan_id": row.get("plan_id"),
            "training_day": row.get("training_day"),
            "athlete_timezone": row.get("athlete_timezone") or "",
            "recommendation_state": current_state,
            "recommendation_reason": row.get("recommendation_reason") or "",
            "recommendation_triggers": list(dict.fromkeys(triggers)),
        }
        defaults = _today_service.ReadinessCheckin()
        for field_name in _today_service._CHECKIN_INPUT_FIELDS:
            fields[field_name] = row.get(field_name, getattr(defaults, field_name))

    persisted = dict(store.upsert_today_checkin(athlete_id, fields))
    persisted["warnings"] = warnings
    return persisted


def submit_today_checkin(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Submit a check-in, but never return green from unverified context."""

    health = ReadinessContextHealth()
    tracked = _ReadinessTrackingStore(store, health)
    row = _today_service.submit_today_checkin(
        tracked,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        payload=payload,
        now=now,
    )
    _probe_schedule(
        tracked.last_plan,
        str(row.get("training_day") or ""),
        health,
    )
    return _patch_persisted_recommendation(
        store,
        athlete_id=athlete_id,
        row=row,
        health=health,
    )


def _apply_fail_safe_to_command_view(
    view: CommandView,
    health: ReadinessContextHealth,
) -> CommandView:
    if not health.failures:
        return view

    warning = _status_warning(health)
    if warning not in view.today.warnings:
        view.today.warnings.append(warning)

    if str(view.today.recommendation_state) != "train_as_planned":
        return view

    decision = _fail_safe_decision(existing_triggers=(), health=health)
    view.today.recommendation_state = "modify"
    view.today.recommendation_reason = decision.message
    view.today.decision_tier = "modify"
    reminder = make_risk(
        "reminder",
        text="Safety context is unavailable, so hard training is not cleared.",
    )
    view.risk_watch = sort_risk_watch([*view.risk_watch, reminder])
    return view


def build_today_command_view(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
) -> CommandView:
    """Build Today while preserving UNKNOWN safety context as a conservative state."""

    health = ReadinessContextHealth()
    tracked = _ReadinessTrackingStore(store, health)
    view = _today_service.build_today_command_view(
        tracked,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        now=now,
    )
    _probe_schedule(
        tracked.last_plan,
        view.today.training_day,
        health,
    )
    return _apply_fail_safe_to_command_view(view, health)


def _raise_execution_unavailable(health: ReadinessContextHealth) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Safety context is temporarily unavailable, so this session cannot be "
            "started or completed. Retry when injury status can be verified."
        ),
        headers={"Retry-After": "30"},
    )


def upsert_session_completion(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Block current-session execution when active injury state cannot be verified."""

    completion_status = str(payload.get("status") or "not_started")
    current_day = _today_service.resolve_training_day(athlete_timezone, now=now)
    requested_day = str(payload.get("training_day") or "").strip()
    is_retro_log = bool(requested_day) and requested_day != current_day

    if completion_status in _CURRENT_SESSION_EXECUTION_STATUSES and not is_retro_log:
        health = ReadinessContextHealth()
        completion_store = _ReadinessTrackingStore(
            store,
            health,
            cache_injury_flags=True,
        )
        completion_store.list_injury_flags(
            athlete_id,
            statuses=("open", "monitoring"),
        )
        if health.failures:
            _raise_execution_unavailable(health)
    else:
        completion_store = store

    return _today_service.upsert_session_completion(
        completion_store,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        payload=payload,
        now=now,
    )


def submit_today_injury_checkin(
    store: AppStore,
    *,
    athlete_id: str,
    payload: Mapping[str, Any],
    athlete_timezone: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconcile injuries and fail-safe any refreshed readiness recommendation."""

    health = ReadinessContextHealth()
    # Deliberately do not cache injury flags here: the underlying service reads
    # once before reconciliation and again after its writes to return fresh state.
    tracked = _ReadinessTrackingStore(store, health)

    # The reconciliation needs the existing flags for identity. Do not allow a
    # failed read to masquerade as an empty set and create duplicate injuries.
    tracked.list_injury_flags(
        athlete_id,
        statuses=("open", "monitoring"),
    )
    if health.failures:
        _raise_execution_unavailable(health)

    result = _today_service.submit_today_injury_checkin(
        tracked,
        athlete_id=athlete_id,
        payload=payload,
        athlete_timezone=athlete_timezone,
        now=now,
    )
    recommendation = result.get("recommendation")
    if isinstance(recommendation, Mapping):
        _probe_schedule(
            tracked.last_plan,
            str(recommendation.get("training_day") or ""),
            health,
        )
        result["recommendation"] = _patch_persisted_recommendation(
            store,
            athlete_id=athlete_id,
            row=recommendation,
            health=health,
        )
    return result


resolve_today_landing = _today_service.resolve_today_landing

__all__ = [
    "ReadinessContextHealth",
    "build_today_command_view",
    "resolve_today_landing",
    "submit_today_checkin",
    "submit_today_injury_checkin",
    "upsert_session_completion",
]
