"""Normal-camp strength management immediately before effective hard contact.

This module is a subordinate implementation helper for the normal role-budget
owner in :mod:`stage2_role_map`.  It does not invent contact state or calendar
legality: both come from the resolved hard-sparring plan and the shared
``combat_load_policy`` through ``calendar_context``.

The policy is deliberately narrow:

* only the canonical ``pre_hard_contact_managed_stress`` decision triggers it;
* there is no two-days-before rule;
* when triggered, the week keeps one meaningful strength exposure only;
* the highest-priority existing strength role survives; extra strength roles are
  suppressed rather than silently deleted;
* the surviving pre-hard-contact role is marked for the downstream effective
  prescription resolver, which owns the actual dose reduction.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .calendar_context import (
    CalendarLegalityView,
    build_events,
    classify_role,
    role_d_day,
    week_scope,
)
from .normalization import clean_list, ordered_weekdays


PRE_HARD_CONTACT_REASON = "pre_hard_contact_managed_stress"
PRE_HARD_CONTACT_STRENGTH_CAP_REASON = "pre_hard_contact_strength_exposure_cap"
_PRE_HARD_CONTACT_SUPPRESSION = (
    "Pre-hard-contact week allows one meaningful strength exposure; extra strength "
    "roles are suppressed to protect hard-sparring quality."
)


def _int_or_large(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10_000


def _strength_priority(role: dict[str, Any]) -> tuple[int, int]:
    """Existing planner strength order: strength-session index, then role index."""
    return (
        _int_or_large(role.get("strength_session_index")),
        _int_or_large(role.get("session_index")),
    )


def _decision_for_role(
    weekly_role_map: dict[str, Any],
    week: dict[str, Any],
    ordinal: int,
    role: dict[str, Any],
):
    profile = classify_role(role)
    d_day = role_d_day(week, role)
    if profile is None or d_day is None:
        return None
    # Exclude the candidate itself so the policy sees the surrounding calendar,
    # not a synthetic same-day collision with the role being evaluated. Building
    # from the whole map also preserves cross-week nearest-contact adjacency.
    view = CalendarLegalityView(
        events=tuple(build_events(weekly_role_map, exclude_role=role)),
        scope=week_scope(week, ordinal),
    )
    return view.decision_for_profile(profile, d_day)


def _suppression_record(role: dict[str, Any]) -> dict[str, Any]:
    governance = deepcopy(role.get("governance") or {})
    hard_reasons = [
        str(reason).strip()
        for reason in clean_list(governance.get("hard_suppression_reasons"))
        if str(reason).strip()
    ]
    if _PRE_HARD_CONTACT_SUPPRESSION not in hard_reasons:
        hard_reasons.append(_PRE_HARD_CONTACT_SUPPRESSION)
    governance["hard_suppression_reasons"] = hard_reasons
    return {
        "category": role.get("category"),
        "role_key": role.get("role_key"),
        "preferred_system": role.get("preferred_system", ""),
        "strength_session_index": role.get("strength_session_index"),
        "scheduled_day_hint": role.get("scheduled_day_hint"),
        "reasons": [_PRE_HARD_CONTACT_SUPPRESSION],
        "governance": governance,
        "intentional_compression": True,
        "compression_reason_codes": [PRE_HARD_CONTACT_STRENGTH_CAP_REASON],
        "compression_summary": _PRE_HARD_CONTACT_SUPPRESSION,
    }


def _merge_compression(week: dict[str, Any]) -> None:
    compression = dict(week.get("intentional_compression") or {})
    codes = [
        str(code).strip()
        for code in clean_list(compression.get("reason_codes"))
        if str(code).strip()
    ]
    if PRE_HARD_CONTACT_STRENGTH_CAP_REASON not in codes:
        codes.append(PRE_HARD_CONTACT_STRENGTH_CAP_REASON)
    existing_summary = str(compression.get("summary") or "").strip()
    summary = (
        f"{existing_summary} {_PRE_HARD_CONTACT_SUPPRESSION}".strip()
        if existing_summary and _PRE_HARD_CONTACT_SUPPRESSION not in existing_summary
        else (existing_summary or _PRE_HARD_CONTACT_SUPPRESSION)
    )
    compression.update(
        {
            "active": True,
            "reason_codes": codes,
            "reason": ", ".join(codes),
            "summary": summary,
        }
    )
    week["intentional_compression"] = compression


def _refresh_unused_days(week: dict[str, Any], athlete_model: dict[str, Any]) -> None:
    """Keep the role-budget owner's unused-day state truthful after suppression."""
    training_days = ordered_weekdays(
        clean_list(week.get("declared_training_days") or athlete_model.get("training_days"))
    )
    if not training_days:
        return
    roles = [role for role in (week.get("session_roles") or []) if isinstance(role, dict)]
    used = {
        str(role.get("scheduled_day_hint") or "").strip().lower()
        for role in roles
        if str(role.get("scheduled_day_hint") or "").strip()
    }
    has_recovery = any(role.get("category") == "recovery" for role in roles)
    week["intentionally_unused_days"] = [
        {
            "day": day,
            "role": "off_day" if has_recovery else "recovery_only_day",
        }
        for day in training_days
        if str(day).strip().lower() not in used
    ]


def apply_pre_hard_contact_strength_exposure_cap(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cap a pre-hard-contact week to one meaningful strength exposure.

    The shared collision policy remains the authority for *whether* a scheduled
    strength role is immediately before effective hard contact. This helper only
    owns the normal role-budget consequence after placement has finished.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    athlete_model = athlete_model or {}

    for ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
        if not isinstance(week, dict):
            continue
        roles = [role for role in (week.get("session_roles") or []) if isinstance(role, dict)]
        strength_roles = [role for role in roles if str(role.get("category") or "").strip().lower() == "strength"]
        if not strength_roles:
            continue

        affected: list[dict[str, Any]] = []
        for role in strength_roles:
            decision = _decision_for_role(weekly_role_map, week, ordinal, role)
            if decision is not None and decision.reason_code == PRE_HARD_CONTACT_REASON:
                affected.append(role)

        if not affected:
            continue

        # Preserve the planner's highest-priority strength exposure. A lower
        # priority role does not replace it merely because that lower role happens
        # to occupy a cleaner day.
        keeper = min(strength_roles, key=_strength_priority)
        if keeper in affected:
            keeper["pre_hard_contact_managed_stress"] = True
            keeper["pre_hard_contact_effective_hard_distance"] = 1
            keeper["pre_hard_contact_reason_code"] = PRE_HARD_CONTACT_REASON

        dropped = [role for role in strength_roles if role is not keeper]
        if dropped:
            dropped_ids = {id(role) for role in dropped}
            week["session_roles"] = [role for role in roles if id(role) not in dropped_ids]
            suppressed = list(week.get("suppressed_roles") or [])
            suppressed.extend(_suppression_record(role) for role in dropped)
            week["suppressed_roles"] = suppressed
            _merge_compression(week)
            for index, role in enumerate(week["session_roles"], start=1):
                role["session_index"] = index
            _refresh_unused_days(week, athlete_model)

        week["pre_hard_contact_strength_policy"] = {
            "active": True,
            "trigger_reason": PRE_HARD_CONTACT_REASON,
            "max_meaningful_strength_exposures": 1,
            "keeper_role_key": keeper.get("role_key"),
            "keeper_strength_session_index": keeper.get("strength_session_index"),
            "keeper_is_pre_hard_contact": keeper in affected,
            "suppressed_strength_roles": len(dropped),
        }

    return weekly_role_map
