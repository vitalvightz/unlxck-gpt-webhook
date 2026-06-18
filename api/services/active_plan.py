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
rule. Deleted or unavailable active plans are treated the same. Overlapping camp
or fight dates are allowed and never block selection. When several ready plans
exist, ordering is deterministic: explicit active first, otherwise latest
eligible by ``created_at`` then id. Eligible statuses are ``ready`` and
``publishable_with_flags``. Generated, review, hold, failed, archived, missing,
and deleted plans are never active. Overview and Today both call this resolver;
UI code must not guess with “latest visible plan” logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, status

ELIGIBLE_ACTIVE_PLAN_STATUSES = {"ready", "publishable_with_flags"}
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


def resolve_active_plan(store: ActivePlanStore, athlete_id: str) -> ActivePlanResolution:
    explicit_id = _explicit_active_plan_id(store, athlete_id)
    if explicit_id:
        explicit = store.get_plan_for_athlete(explicit_id, athlete_id)
        if is_active_plan_eligible(explicit):
            return ActivePlanResolution(plan=explicit, source="explicit")

    eligible = [row for row in store.list_user_plans(athlete_id) if is_active_plan_eligible(row)]
    if not eligible:
        return ActivePlanResolution(plan=None, source="none")
    return ActivePlanResolution(plan=sorted(eligible, key=_created_sort_key, reverse=True)[0], source="auto_latest_eligible")


def set_active_plan(store: ActivePlanStore, athlete_id: str, plan_id: str) -> dict[str, Any]:
    plan = store.get_plan_for_athlete(plan_id, athlete_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    if not is_active_plan_eligible(plan):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan is not eligible to become active")
    setter = getattr(store, "set_active_plan_id", None)
    if not callable(setter):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="explicit active plan storage is unavailable")
    setter(athlete_id, plan_id)
    return plan
