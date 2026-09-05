from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any

from .gap_fill_inserts import _watch_phase_for_offset


_CANONICAL_PHASES = {"GPP", "SPP", "TAPER"}
_PHASE_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "late_fight_phase_eligibility_context",
    default=None,
)


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


def scheduled_phase_for_role(
    role: dict[str, Any],
    *,
    athlete_model: dict[str, Any] | None = None,
    spec_phase: object = None,
) -> str:
    """Return the Stage 1 phase that owns this scheduled late-fight role.

    Prefer phase already stamped on the role. Otherwise use Stage 1's dynamic
    phase allocation carried on the athlete model and map the role's D-day back
    to GPP/SPP/TAPER. ``spec_phase`` is only a compatibility fallback for direct
    callers that do not carry the phase allocation.
    """
    for key in ("camp_phase", "scheduled_phase", "phase"):
        if phase := _canonical_phase(role.get(key)):
            return phase

    offset = _countdown_offset(role)
    if offset is not None and isinstance(athlete_model, dict):
        try:
            phase = _canonical_phase(_watch_phase_for_offset(athlete_model, offset))
        except (KeyError, TypeError, ValueError):
            phase = ""
        if phase:
            return phase

    return _canonical_phase(spec_phase)


def phase_scoped_candidate_pools(
    candidate_pools: dict[str, dict],
    phase: object,
) -> dict[str, dict]:
    """Expose only the Stage 1 pool whose phase owns the scheduled role."""
    canonical = _canonical_phase(phase)
    if not canonical:
        return candidate_pools
    pool = (candidate_pools or {}).get(canonical)
    return {canonical: pool} if isinstance(pool, dict) else {}


def install() -> None:
    """Make late-tail exercise selection obey Stage 1 phase eligibility.

    The legacy selector iterates every candidate pool for every late role. This
    runtime policy keeps the existing role matcher/ranking but scopes its input
    to the phase that owns each scheduled D-day. A GPP-only exercise therefore
    cannot be transplanted into an SPP/TAPER late role simply because its name
    semantically matches the role.
    """
    from . import stage2_payload as payload

    if getattr(payload, "_LATE_FIGHT_PHASE_ELIGIBILITY_INSTALLED", False):
        return

    original_build = payload.build_planning_brief
    original_allocate = payload._build_late_fight_allowed_exercises_by_day

    @wraps(original_build)
    def build_planning_brief(*, athlete_model: dict, **kwargs):
        token = _PHASE_CONTEXT.set(athlete_model if isinstance(athlete_model, dict) else None)
        try:
            return original_build(athlete_model=athlete_model, **kwargs)
        finally:
            _PHASE_CONTEXT.reset(token)

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

        athlete_model = _PHASE_CONTEXT.get()
        spec_phase = spec.get("phase")

        # Preserve original role order while grouping by authoritative phase so
        # the allocator still shares its consumed-slot ledger across all roles
        # inside the same Stage 1 phase.
        grouped: list[tuple[str, list[dict[str, Any]]]] = []
        group_index: dict[str, int] = {}
        for role in roles:
            phase = scheduled_phase_for_role(
                role,
                athlete_model=athlete_model,
                spec_phase=spec_phase,
            )
            group_key = phase or "__legacy__"
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
            scoped_pools = (
                candidate_pools
                if group_key == "__legacy__"
                else phase_scoped_candidate_pools(candidate_pools, group_key)
            )
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
