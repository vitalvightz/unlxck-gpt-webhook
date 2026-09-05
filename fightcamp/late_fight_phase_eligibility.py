from __future__ import annotations

from functools import wraps
from typing import Any

from .planner_context import planner_athlete_model_context


_CANONICAL_PHASES = {"GPP", "SPP", "TAPER"}
# Backward-compatible alias for focused tests/debug tooling that may still refer
# to the old late-fight-specific context name.
_PHASE_CONTEXT = planner_athlete_model_context


def _canonical_phase(value: object) -> str:
    phase = str(value or "").strip().upper()
    return phase if phase in _CANONICAL_PHASES else ""


def _countdown_offset(role: dict[str, Any]) -> int | None:
    for key in ("countdown_offset", "scheduled_countdown_label", "countdown_label"):
        value = role.get(key)
        if isinstance(value, int):
            return value if value >= 0 else None
        text = str(value or "").strip().upper()
        if text.startswith("D-"):
            try:
                return int(text[2:])
            except ValueError:
                continue
    return None


def _stage1_phase_for_offset(athlete_model: dict[str, Any], offset: int) -> str:
    """Map D-day using only Stage 1's existing ``phase_weeks.days`` allocation."""
    phase_weeks = athlete_model.get("phase_weeks")
    if not isinstance(phase_weeks, dict):
        return ""
    phase_days = phase_weeks.get("days")
    if not isinstance(phase_days, dict):
        return ""

    normalized_days: dict[str, int] = {}
    for phase in _CANONICAL_PHASES:
        try:
            normalized_days[phase] = max(0, int(phase_days.get(phase, 0) or 0))
        except (TypeError, ValueError):
            return ""
    if not any(normalized_days.values()):
        return ""

    remaining = max(1, int(offset))
    for phase in ("TAPER", "SPP", "GPP"):
        days = normalized_days[phase]
        if days <= 0:
            continue
        if remaining <= days:
            return phase
        remaining -= days
    return ""


def scheduled_phase_for_role(
    role: dict[str, Any],
    *,
    athlete_model: dict[str, Any] | None = None,
    spec_phase: object = None,
) -> str:
    """Return the Stage 1 phase that owns this scheduled late-fight role."""
    offset = _countdown_offset(role)
    if offset is not None and isinstance(athlete_model, dict):
        return _stage1_phase_for_offset(athlete_model, offset)
    if offset is not None:
        return _canonical_phase(spec_phase)
    if phase := _canonical_phase(spec_phase):
        return phase
    for key in ("camp_phase", "scheduled_phase", "phase"):
        if phase := _canonical_phase(role.get(key)):
            return phase
    return ""


def phase_scoped_candidate_pools(
    candidate_pools: dict[str, dict],
    phase: object,
) -> dict[str, dict]:
    """Expose only the Stage 1 pool whose phase owns the scheduled role."""
    canonical = _canonical_phase(phase)
    if not canonical:
        return {}
    pool = (candidate_pools or {}).get(canonical)
    return {canonical: pool} if isinstance(pool, dict) else {}


def install() -> None:
    """Make late-tail exercise selection obey Stage 1 phase eligibility.

    The build wrapper also exposes the same athlete model through a shared
    ContextVar while deterministic planning is executing. Normal strength
    composition consumes that context to apply fatigue/cut/injury pressure
    without duplicating athlete-state derivation or changing Stage 2 authority.
    """
    from . import stage2_payload as payload

    if getattr(payload, "_LATE_FIGHT_PHASE_ELIGIBILITY_INSTALLED", False):
        return

    original_build = payload.build_planning_brief
    original_allocate = payload._build_late_fight_allowed_exercises_by_day

    @wraps(original_build)
    def build_planning_brief(*, athlete_model: dict, **kwargs):
        token = planner_athlete_model_context.set(
            athlete_model if isinstance(athlete_model, dict) else None
        )
        try:
            return original_build(athlete_model=athlete_model, **kwargs)
        finally:
            planner_athlete_model_context.reset(token)

    @wraps(original_allocate)
    def _build_late_fight_allowed_exercises_by_day(
        *,
        spec: dict[str, Any],
        candidate_pools: dict[str, dict],
    ):
        roles = spec.get("visible_session_sequence") or spec.get("session_sequence") or []
        roles = [role for role in roles if isinstance(role, dict)]
        if not roles:
            return original_allocate(spec=spec, candidate_pools=candidate_pools)

        athlete_model = planner_athlete_model_context.get()
        if athlete_model is None and isinstance(spec.get("athlete_model"), dict):
            athlete_model = spec["athlete_model"]
        spec_phase = spec.get("phase")

        grouped: list[tuple[str, list[dict[str, Any]]]] = []
        group_index: dict[str, int] = {}
        for role in roles:
            phase = scheduled_phase_for_role(
                role,
                athlete_model=athlete_model,
                spec_phase=spec_phase,
            )
            group_key = phase or "__unresolved__"
            if group_key not in group_index:
                group_index[group_key] = len(grouped)
                grouped.append((group_key, []))
            grouped[group_index[group_key]][1].append(role)

        allowed_by_day: dict[str, list[str]] = {}
        assignments_by_day: dict[str, list[dict[str, Any]]] = {}
        for group_key, group_roles in grouped:
            group_spec = {
                **spec,
                "visible_session_sequence": group_roles,
                "session_sequence": group_roles,
            }
            scoped_pools = phase_scoped_candidate_pools(candidate_pools, group_key)
            group_allowed, group_assignments = original_allocate(
                spec=group_spec,
                candidate_pools=scoped_pools,
            )
            for day, names in group_allowed.items():
                bucket = allowed_by_day.setdefault(day, [])
                for name in names:
                    if name not in bucket:
                        bucket.append(name)
            for day, assignments in group_assignments.items():
                assignments_by_day.setdefault(day, []).extend(assignments)

        return allowed_by_day, assignments_by_day

    payload.build_planning_brief = build_planning_brief
    payload._build_late_fight_allowed_exercises_by_day = _build_late_fight_allowed_exercises_by_day
    payload._LATE_FIGHT_PHASE_ELIGIBILITY_INSTALLED = True
