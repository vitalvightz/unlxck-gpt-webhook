"""Active-plan resolution for Block 4.

Implementation note (PR #1800): active plan selection is centralized here.
If ``profiles.active_plan_id`` exists, that explicit plan wins only when it
belongs to the athlete and has an athlete-displayable status. This PR also
supports a temporary derived fallback: when no valid explicit active plan is
stored, the latest eligible saved plan is auto-selected by created time. New
eligible plans therefore become active only when the athlete has no valid active
plan; unrelated ready plans do not silently replace an existing explicit active
plan. Archiving makes a plan ineligible; the resolver will not return it, and it
falls back to the next eligible plan only through the same explicit fallback
rule. Deleted or unavailable active plans are treated the same. Overlapping saved
or draft plans are allowed, but activating an overlapping second plan requires an
explicit pause or replacement choice. ``pause`` preserves the previous plan row
unchanged and switches the single active pointer to the selected plan, allowing
the previous plan to be reactivated later. ``replace`` switches the pointer and
archives the previous plan. When several ready plans exist, ordering is
deterministic: explicit active first, otherwise latest eligible by ``created_at``
then id. Eligible statuses are ``ready`` and
``publishable_with_flags``. Generated, review, hold, failed, archived, missing,
and deleted plans are never active. Overview and Today both call this resolver;
UI code must not guess with “latest visible plan” logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from typing import Any, Mapping, Protocol

from fastapi import HTTPException, status

ELIGIBLE_ACTIVE_PLAN_STATUSES = {"ready", "publishable_with_flags"}
ACTIVE_PLAN_OVERLAP_ACTIONS = {"pause", "replace"}
ACTIVE_PLAN_OVERLAP_CONFLICT_MESSAGE = (
    "This overlaps with your current active plan. Do you want to replace the current plan, pause it, or choose a new start date?"
)
ACTIVE_PLAN_OVERLAP_CONFLICT_CODE = "active_plan_overlap"
ACTIVE_PLAN_REPLACE_FAILED_MESSAGE = "Unable to replace the current active plan. The original active plan was restored."
NEVER_ACTIVE_PLAN_STATUSES = {
    "generated",
    "review_required",
    "held_for_review",
    "triage_blocked",
    "medical_hold",
    "restricted_rehab_only",
    "needs_review",
    "failed",
    "archived",
}


class ActivePlanStore(Protocol):
    def list_user_plans(self, athlete_id: str) -> list[dict[str, Any]]: ...
    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ActivePlanResolution:
    plan: dict[str, Any] | None
    source: str

    @property
    def plan_id(self) -> str | None:
        return str(self.plan.get("id")) if self.plan and self.plan.get("id") else None


@dataclass(frozen=True)
class PlanDateRange:
    start: date
    end: date


def normalize_plan_status(row: dict[str, Any] | None) -> str:
    return str((row or {}).get("status") or "").strip().lower()


def is_active_plan_eligible(row: dict[str, Any] | None) -> bool:
    return normalize_plan_status(row) in ELIGIBLE_ACTIVE_PLAN_STATUSES


def _created_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("created_at") or ""), str(row.get("id") or ""))


def _explicit_active_plan_id(store: ActivePlanStore, athlete_id: str) -> str | None:
    getter = getattr(store, "get_active_plan_id", None)
    if not callable(getter):
        return None
    value = getter(athlete_id)
    return str(value).strip() or None if value is not None else None


def _decode_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, Mapping) else {}
    return {}


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _collect_structured_dates(row: dict[str, Any]) -> list[date]:
    structured_plan = _decode_mapping(row.get("structured_plan"))
    weeks = structured_plan.get("weeks")
    if not isinstance(weeks, list):
        return []
    dates: list[date] = []
    for week in weeks:
        if not isinstance(week, Mapping):
            continue
        for key in ("start_date", "end_date"):
            parsed = _parse_date(week.get(key))
            if parsed:
                dates.append(parsed)
        days = week.get("days")
        if isinstance(days, list):
            for day in days:
                if isinstance(day, Mapping):
                    parsed = _parse_date(day.get("date"))
                    if parsed:
                        dates.append(parsed)
    return dates


def _collect_planning_brief_dates(row: dict[str, Any]) -> list[date]:
    planning_brief = _decode_mapping(row.get("planning_brief"))
    role_map = planning_brief.get("weekly_role_map")
    weeks = role_map.get("weeks") if isinstance(role_map, Mapping) else None
    if not isinstance(weeks, list):
        return []
    dates: list[date] = []
    for week in weeks:
        if not isinstance(week, Mapping):
            continue
        calendar_days = week.get("calendar_days")
        if isinstance(calendar_days, list):
            for day in calendar_days:
                if isinstance(day, Mapping):
                    parsed = _parse_date(day.get("calendar_date"))
                    if parsed:
                        dates.append(parsed)
    return dates


def _camp_length_weeks(row: dict[str, Any]) -> int | None:
    planning_brief = _decode_mapping(row.get("planning_brief"))
    for container in (
        planning_brief.get("fight_demands"),
        planning_brief.get("athlete_snapshot"),
        planning_brief.get("athlete_model"),
    ):
        if isinstance(container, Mapping):
            parsed = _int_or_none(container.get("camp_length_weeks"))
            if parsed:
                return parsed
    return None


def plan_date_range(row: dict[str, Any] | None) -> PlanDateRange | None:
    if not row:
        return None

    dates = _collect_structured_dates(row) or _collect_planning_brief_dates(row)
    if dates:
        return PlanDateRange(start=min(dates), end=max(dates))

    fight_date = _parse_date(row.get("fight_date"))
    camp_length_weeks = _camp_length_weeks(row)
    if fight_date and camp_length_weeks:
        return PlanDateRange(
            start=fight_date - timedelta(days=(camp_length_weeks * 7) - 1),
            end=fight_date,
        )

    return None


def _ranges_overlap(left: PlanDateRange, right: PlanDateRange) -> bool:
    return left.start <= right.end and right.start <= left.end


def _active_plan_overlap(
    store: ActivePlanStore,
    athlete_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    current = resolve_active_plan(store, athlete_id).plan
    if not current or str(current.get("id") or "") == str(candidate.get("id") or ""):
        return None
    if not is_active_plan_eligible(current):
        return None

    # The resolver may have selected from a summary projection. Re-read the row
    # before comparing dates so planning_brief / structured_plan can be used.
    current_id = str(current.get("id") or "")
    if current_id:
        full_current = store.get_plan_for_athlete(current_id, athlete_id)
        if full_current:
            current = full_current

    current_range = plan_date_range(current)
    candidate_range = plan_date_range(candidate)
    if not current_range or not candidate_range:
        return None
    return current if _ranges_overlap(current_range, candidate_range) else None


def resolve_active_plan(store: ActivePlanStore, athlete_id: str) -> ActivePlanResolution:
    explicit_id = _explicit_active_plan_id(store, athlete_id)
    if explicit_id:
        explicit = store.get_plan_for_athlete(explicit_id, athlete_id)
        if is_active_plan_eligible(explicit):
            return ActivePlanResolution(plan=explicit, source="explicit")

    eligible = [row for row in store.list_user_plans(athlete_id) if is_active_plan_eligible(row)]
    if not eligible:
        return ActivePlanResolution(plan=None, source="none")
    return ActivePlanResolution(plan=max(eligible, key=_created_sort_key), source="auto_latest_eligible")


def set_active_plan(
    store: ActivePlanStore,
    athlete_id: str,
    plan_id: str,
    *,
    overlap_action: str | None = None,
) -> dict[str, Any]:
    plan = store.get_plan_for_athlete(plan_id, athlete_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    if not is_active_plan_eligible(plan):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan is not eligible to become active")
    normalized_action = str(overlap_action or "").strip().lower() or None
    if normalized_action is not None and normalized_action not in ACTIVE_PLAN_OVERLAP_ACTIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid overlap action")
    overlapping_active = _active_plan_overlap(store, athlete_id, plan)
    if overlapping_active and normalized_action is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": ACTIVE_PLAN_OVERLAP_CONFLICT_CODE,
                "message": ACTIVE_PLAN_OVERLAP_CONFLICT_MESSAGE,
            },
        )
    setter = getattr(store, "set_active_plan_id", None)
    if not callable(setter):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="explicit active plan storage is unavailable")
    if overlapping_active and normalized_action == "pause":
        # The active pointer is the pause state. Preserve the previous plan row
        # unchanged so it remains available for deliberate reactivation later.
        setter(athlete_id, plan_id)
        return plan
    if overlapping_active and normalized_action == "replace":
        archiver = getattr(store, "archive_plan_for_athlete", None)
        if not callable(archiver):
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="plan replacement is unavailable")
        current_plan_id = str(overlapping_active.get("id") or "")
        setter(athlete_id, plan_id)
        try:
            archiver(current_plan_id, athlete_id)
        except Exception as exc:
            setter(athlete_id, current_plan_id)
            if isinstance(exc, HTTPException):
                raise HTTPException(
                    status_code=exc.status_code,
                    detail=ACTIVE_PLAN_REPLACE_FAILED_MESSAGE,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ACTIVE_PLAN_REPLACE_FAILED_MESSAGE,
            ) from exc
        return plan
    setter(athlete_id, plan_id)
    return plan
