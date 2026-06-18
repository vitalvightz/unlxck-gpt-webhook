"""Central active-plan resolver (Block 4 / PR #1800).

This is the single source of truth for "which plan is active for this athlete".
Overview, Today, the active-plan API, and the `/plan` alias all resolve through
here so the same athlete always sees the same active plan everywhere. Do not
re-derive "the latest visible plan" anywhere else.

=============================================================================
IMPLEMENTATION DECISION NOTE
=============================================================================

How is the active plan selected?
    Priority order (see ``resolve_active_plan``):
      1. The athlete's explicit ``active_plan_id`` (persisted on the profile),
         *if* that plan still exists, is owned by the athlete, and is eligible.
      2. Otherwise the latest eligible plan is auto-selected as a temporary
         fallback (``source == "auto_selected"``). This is surfaced explicitly
         via the resolution's ``source`` field, never as ad-hoc UI guessing.
      3. Otherwise there is no active plan (``source is None``).

Where is the active plan stored / derived?
    The explicit choice is stored in ``profiles.active_plan_id`` (added in
    migration 20260618130000). The *resolution* is derived at read time so an
    ineligible/stale pointer can never win.

What happens when a new plan is generated and becomes eligible?
    Nothing is silently switched. Generation does not write ``active_plan_id``.
    - If the athlete has no explicit active plan, the new eligible plan becomes
      active simply because it is now the latest eligible plan (fallback).
    - If the athlete already has an explicit active plan, that explicit plan
      keeps winning, so an unrelated new plan does NOT hijack Today. Making the
      new plan active is an explicit user action ("Set active") — i.e. the
      intended replacement flow is a deliberate set, not an implicit switch.

What happens when a plan is archived?
    Archiving flips the status to ``archived`` (it is not a hard delete).
    Archived plans are never eligible, so they can never be active. When the
    *active* plan is archived, the archive endpoint clears ``active_plan_id``
    (see api/routes/plans.py); even if it were not cleared, the resolver rejects
    the now-ineligible explicit pointer and falls back to the next eligible
    plan, so Overview never keeps showing an archived plan as active.

What happens when the active plan is deleted / unavailable?
    A hard delete clears ``active_plan_id`` via ``ON DELETE SET NULL``. A missing
    or unreadable explicit plan is treated as ineligible and the resolver falls
    back. No dereference of a missing plan ever happens.

What happens with overlapping fight/camp dates?
    Overlap is allowed and never blocks selection — athletes legitimately keep
    drafts, alternates, and updated camps. Overlap has no effect here: exactly
    one plan is active, and only the active plan drives Today/Overview.

What happens when there are multiple ready plans?
    Resolution is deterministic: explicit pointer first, else the latest
    eligible plan by ``created_at`` (the order ``list_user_plans`` already
    returns). Two ready plans therefore resolve predictably to the same one on
    every read.

Which statuses are eligible to become active?
    Only athlete-displayable plans: ``ready`` and ``publishable_with_flags``
    (``api.state_machine.ATHLETE_DISPLAYABLE_PLAN_STATUSES``). Eligibility is
    checked against the NORMALIZED summary status, so a legacy ``review_required``
    row that normalizes to ``ready``/``publishable_with_flags`` is eligible while
    one that normalizes to ``held_for_review`` is not.

Which statuses are never active?
    ``generated``, ``review_required``/``held_for_review``, ``needs_review``,
    ``triage_blocked``, ``medical_hold``, ``restricted_rehab_only``,
    ``failed``, ``archived``, and any deleted/missing plan.

How do Overview and Today resolve the active plan?
    Both call ``resolve_active_plan`` (via api/services/today_service.py). They
    never read ``list_user_plans``/"latest visible plan" directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from api.plan_mappers import _map_plan_summary, _visible_plans_for_athlete
from api.state_machine import ATHLETE_DISPLAYABLE_PLAN_STATUSES
from api.store import AppStore

# The only statuses an athlete-facing active plan may have. Kept in lockstep
# with the state machine's athlete-displayable set so the two never drift.
ELIGIBLE_ACTIVE_STATUSES: frozenset[str] = frozenset(ATHLETE_DISPLAYABLE_PLAN_STATUSES)

ActivePlanSource = Literal["explicit", "auto_selected"]


def plan_is_eligible_for_active(plan_row: Any) -> bool:
    """True only for athlete-displayable plans (ready / publishable_with_flags).

    Checks the *normalized* summary status so a legacy ``review_required`` row
    that resolves to ``ready``/``publishable_with_flags`` is treated correctly,
    while archived/blocked/held/medical/triage statuses are rejected.
    """
    if not isinstance(plan_row, dict):
        return False
    try:
        normalized_status = _map_plan_summary(plan_row).status
    except Exception:
        return False
    return normalized_status in ELIGIBLE_ACTIVE_STATUSES


@dataclass(frozen=True)
class ActivePlanResolution:
    """Outcome of resolving the active plan for an athlete."""

    plan_row: dict[str, Any] | None
    source: ActivePlanSource | None

    @property
    def has_active_plan(self) -> bool:
        return self.plan_row is not None

    @property
    def plan_id(self) -> str | None:
        if not self.plan_row:
            return None
        return str(self.plan_row.get("id") or "") or None


def _latest_eligible_plan(store: AppStore, athlete_id: str) -> dict[str, Any] | None:
    """First eligible plan in newest-first order (the fallback active plan)."""
    for row in _visible_plans_for_athlete(store.list_user_plans(athlete_id)):
        if plan_is_eligible_for_active(row):
            return row
    return None


def resolve_active_plan(store: AppStore, athlete_id: str) -> ActivePlanResolution:
    """Resolve the athlete's single active plan (see module decision note).

    Explicit pointer first (when valid + eligible), else the latest eligible
    plan, else no active plan. The result's ``source`` distinguishes an explicit
    choice from an auto-selected fallback for diagnostics/telemetry.
    """
    getter = getattr(store, "get_active_plan_id", None)
    explicit_id = str((getter(athlete_id) if callable(getter) else "") or "").strip()
    if explicit_id:
        explicit_row = store.get_plan_for_athlete(explicit_id, athlete_id)
        if plan_is_eligible_for_active(explicit_row):
            return ActivePlanResolution(plan_row=explicit_row, source="explicit")

    fallback = _latest_eligible_plan(store, athlete_id)
    if fallback is not None:
        return ActivePlanResolution(plan_row=fallback, source="auto_selected")

    return ActivePlanResolution(plan_row=None, source=None)


def resolve_active_plan_row(store: AppStore, athlete_id: str) -> dict[str, Any] | None:
    """Convenience: just the active plan row (or ``None``)."""
    return resolve_active_plan(store, athlete_id).plan_row
