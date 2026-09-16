"""Single authority for what ``training_frequency`` means as a *physical* session count.

Product contract
----------------
``training_frequency`` is the number of **physical training sessions** the athlete
plans to complete per week. It is not a stress budget, not a role-candidate
budget, and not a count of anything the athlete merely reads or watches.

Three concepts that used to be conflated live apart here:

``physical_session_target``
    How many physical training days should appear in a week. Derived from the
    requested frequency and the *viable* declared training days remaining on the
    calendar (fight day is not a training opportunity), then reduced only by an
    explicit, recorded safety reason.

``meaningful stress exposures``
    How many of those sessions may carry real loading. Owned by the late-fight
    role budget (``max_meaningful_stress_exposures``) and deliberately **not**
    touched here: the taper reduces dose, not occupancy.

``zero-load tactical / education support``
    Tactical Watch, cue cards, visualization, breathing resets. Valuable, freely
    co-located with a real session, and worth exactly ``0`` toward frequency.

Classification is deterministic and role-key first. ``stress_class`` alone is
never sufficient: a Breathing Reset and a programmed mobility session are both
``support``, but only one of them is a training session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .normalization import clean_list


# --- Canonical classification ------------------------------------------------

#: Support/education content that can never satisfy physical frequency on its
#: own, whatever category or stress class it carries.
NON_PHYSICAL_ROLE_KEYS: frozenset[str] = frozenset(
    {
        # Zero-load tactical / education / mindset
        "tactical_watch",
        "tactical_focus",
        "tactical_cue_card",
        "self_review",
        "neural_visualization",
        "mindset_reset",
        "mindset_review",
        "video_review",
        # Passive micro-resets: a 3-minute breathing insert is not a session.
        "breathing_reset",
        "sleep_downshift",
        "recovery_reset",
        # Fight day is its own category, never weekly training frequency.
        "fight_day_protocol",
    }
)

#: Categories whose members are informational by construction.
NON_PHYSICAL_CATEGORIES: frozenset[str] = frozenset(
    {
        "tactical",
        "mental",
        "mindset",
        "education",
        "coach_note",
        "fight_day",
        "protocol",
    }
)

#: Low-cost *support inserts* that still prescribe real movement, so they do
#: count as a physical session when they are what a day holds. Mirrors
#: ``gap_fill_inserts.PHYSICAL_INSERTS`` / ``LOW_COST_AEROBIC_INSERTS`` without
#: importing them (that module imports the late-fight payload, which imports
#: this one).
PHYSICAL_SUPPORT_ROLE_KEYS: frozenset[str] = frozenset(
    {
        "mobility_rehab",
        "movement_quality",
        "technical_shadow_rhythm",
        "footwork_walkthrough",
        "joint_prep",
        "walk_flush",
        "aerobic_shadow_flow",
        "aerobic_walk_flush",
        "aerobic_footwork_rhythm",
        "aerobic_skip_flush",
        "aerobic_jog_flush",
    }
)

#: Planner categories that prescribe movement. A ``recovery`` role from the
#: normal planner (``recovery_reset_day``, ``tissue_recovery_day``) is a
#: programmed physical session and counts; the ``recovery_reset`` *insert* is a
#: micro-reset and is denied above. That distinction is deliberate.
PHYSICAL_CATEGORIES: frozenset[str] = frozenset(
    {
        "strength",
        "conditioning",
        "recovery",
        "rehab",
        "sparring",
        "combat",
        "technical",
        "skill",
        "mobility",
        "movement_quality",
    }
)


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def is_physical_session_role(role: Any) -> bool:
    """Whether ``role`` is a physical training session for frequency purposes.

    Order matters: the explicit non-physical vocabulary wins over any category
    or stress-class signal, so a support insert cannot drift into the count by
    being given a physical-sounding category later.
    """
    if not isinstance(role, dict):
        return False
    role_key = _normalize(role.get("role_key"))
    if role_key in NON_PHYSICAL_ROLE_KEYS:
        return False
    if role.get("nonphysical") or role.get("execution_only"):
        return False
    category = _normalize(role.get("category"))
    if category in NON_PHYSICAL_CATEGORIES:
        return False
    if role_key in PHYSICAL_SUPPORT_ROLE_KEYS:
        return True
    return category in PHYSICAL_CATEGORIES


def role_countdown_offset(role: Any) -> int | None:
    """Best-effort countdown offset for a role, tolerating label-only entries."""
    if not isinstance(role, dict):
        return None
    value = role.get("countdown_offset")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    for key in ("scheduled_countdown_label", "countdown_label", "countdown_display_label"):
        label = str(role.get(key) or "").strip().upper()
        if not label.startswith("D-"):
            continue
        digits = ""
        for char in label[2:]:
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            return int(digits)
    return None


def physical_session_offsets(roles: Iterable[Any]) -> set[int]:
    """Countdown offsets carrying at least one physical session."""
    offsets: set[int] = set()
    for role in roles or []:
        if not is_physical_session_role(role):
            continue
        offset = role_countdown_offset(role)
        if offset is None or offset <= 0:
            continue
        offsets.add(offset)
    return offsets


def count_physical_sessions(roles: Iterable[Any]) -> int:
    """Physical sessions in ``roles``, counted as occupied training days.

    One day is one session: a Tactical Focus riding alongside a technical combat
    day adds nothing, and two prescribed blocks on one day are still one
    session.
    """
    return len(physical_session_offsets(roles))


# --- Target resolution -------------------------------------------------------

#: Deterministic reasons a viable declared day may be left without a session.
REASON_FIGHT_DAY = "fight_day"
REASON_NO_LEGAL_PHYSICAL_OPTION = "no_legal_physical_option"
REASON_DAY_NO_LONGER_AVAILABLE = "calendar_day_no_longer_available"
REASON_FREQUENCY_TARGET_MET = "requested_frequency_already_met"

WARNING_FREQUENCY_UNMET = "physical_session_frequency_unmet"


def requested_training_frequency(athlete_model: dict[str, Any] | None) -> int | None:
    """The athlete's requested weekly physical-session count, or ``None``."""
    if not isinstance(athlete_model, dict):
        return None
    raw = athlete_model.get("training_frequency")
    if raw is None:
        raw = athlete_model.get("days_available")
    try:
        frequency = int(raw)
    except (TypeError, ValueError):
        return None
    return frequency if frequency > 0 else None


def viable_declared_days(
    day_slots: Sequence[tuple[int, str]],
    athlete_model: dict[str, Any] | None,
) -> list[int]:
    """Countdown offsets in ``day_slots`` that are real training opportunities.

    ``day_slots`` is ``[(countdown_offset, weekday), ...]`` for one week. Fight
    day (D-0) is excluded: it is a competition day, not a training session, so a
    declared weekday that resolves onto it removes one opportunity rather than
    moving it elsewhere.
    """
    declared = {
        _normalize(day)
        for day in clean_list((athlete_model or {}).get("training_days", []))
        if _normalize(day)
    }
    viable: list[int] = []
    for offset, weekday in day_slots:
        if not isinstance(offset, int) or offset <= 0:
            continue  # D-0 fight day, and anything already past.
        if declared and _normalize(weekday) not in declared:
            continue
        viable.append(offset)
    return sorted(set(viable), reverse=True)


@dataclass
class PhysicalOccupancyPlan:
    """Resolved occupancy arithmetic for one week/window."""

    requested_frequency: int | None
    viable_offsets: list[int]
    occupied_offsets: list[int]
    target: int
    fill_offsets: list[int] = field(default_factory=list)

    @property
    def occupancy(self) -> int:
        return len(self.occupied_offsets)

    @property
    def shortfall(self) -> int:
        return max(0, self.target - self.occupancy)


def plan_physical_occupancy(
    *,
    day_slots: Sequence[tuple[int, str]],
    roles: Iterable[Any],
    athlete_model: dict[str, Any] | None,
) -> PhysicalOccupancyPlan:
    """Resolve the authoritative physical-session target for one week.

    ``physical_session_target = min(requested_frequency, viable_declared_days)``.
    Safety may reduce it further, but only by an explicit decision recorded at
    the point the reduction happens — never silently here.
    """
    viable = viable_declared_days(day_slots, athlete_model)
    occupied = sorted(physical_session_offsets(roles) & set(viable), reverse=True)
    requested = requested_training_frequency(athlete_model)
    target = len(viable) if requested is None else min(requested, len(viable))
    fill = [offset for offset in viable if offset not in set(occupied)]
    return PhysicalOccupancyPlan(
        requested_frequency=requested,
        viable_offsets=viable,
        occupied_offsets=occupied,
        target=target,
        fill_offsets=fill,
    )


def unused_day_record(day: str, offset: int, reason: str) -> dict[str, Any]:
    """The canonical ``intentionally_unused_days`` entry for an empty day."""
    return {
        "day": str(day or "").strip().title(),
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "role": "off_day",
        "reason_code": reason,
        "reason": reason.replace("_", " "),
        "physical_session_target_authority": True,
    }


# --- Deterministic QA --------------------------------------------------------


def _week_day_slots(week: dict[str, Any]) -> list[tuple[int, str]]:
    slots: list[tuple[int, str]] = []
    for entry in week.get("calendar_days") or []:
        if isinstance(entry, dict) and isinstance(entry.get("d_day"), int):
            slots.append((int(entry["d_day"]), str(entry.get("weekday") or "")))
    return slots


def _explained_offsets(week: dict[str, Any]) -> set[int]:
    """Offsets a week has explicitly accounted for as intentionally unused."""
    explained: set[int] = set()
    weekday_to_offset = {
        _normalize(weekday): offset for offset, weekday in _week_day_slots(week)
    }
    for entry in week.get("intentionally_unused_days") or []:
        if not isinstance(entry, dict):
            continue
        if not (entry.get("reason_code") or entry.get("reason") or entry.get("role")):
            continue
        offset = entry.get("countdown_offset")
        if not isinstance(offset, int):
            offset = weekday_to_offset.get(_normalize(entry.get("day")))
        if isinstance(offset, int):
            explained.add(offset)
    return explained


def audit_physical_session_frequency(
    weekly_role_map: dict[str, Any] | None,
    athlete_model: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Report weeks whose physical occupancy falls short with nothing to show for it.

    A shortfall is only a finding when a *viable declared* day is both empty and
    unexplained. Zero-load tactical support never closes the gap: occupancy is
    counted with ``is_physical_session_role``, which denies it by construction.
    """
    findings: list[dict[str, Any]] = []
    if not isinstance(weekly_role_map, dict):
        return findings
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        day_slots = _week_day_slots(week)
        if not day_slots:
            continue
        roles = [role for role in week.get("session_roles") or [] if isinstance(role, dict)]
        # The week's own declared days are the authoritative availability for that
        # window (a partial/leading week can legitimately hold fewer instances of a
        # declared weekday than the athlete model implies).
        week_model = dict(athlete_model or {})
        week_declared = clean_list(week.get("declared_training_days"))
        if week_declared:
            week_model["training_days"] = week_declared
        plan = plan_physical_occupancy(
            day_slots=day_slots,
            roles=roles,
            athlete_model=week_model,
        )
        if plan.shortfall <= 0:
            continue
        explained = _explained_offsets(week)
        unexplained = [
            offset
            for offset in plan.fill_offsets
            if offset not in explained
        ]
        if not unexplained:
            continue
        findings.append(
            {
                "reason_code": WARNING_FREQUENCY_UNMET,
                "week_index": week.get("week_index"),
                "phase": week.get("phase"),
                "requested_physical_target": plan.target,
                "viable_declared_days": list(plan.viable_offsets),
                "actual_physical_sessions": plan.occupancy,
                "unexplained_empty_days": sorted(unexplained, reverse=True),
            }
        )
    return findings
