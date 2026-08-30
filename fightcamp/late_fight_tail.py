"""Shared finished D-13 -> D-0 late-fight tail construction.

Long camps must not splice raw allocator roles into their future fight week. This
module reproduces the same completed late-fight path used by a plan generated
inside D-13: build the existing late-fight plan spec, preserve coach-owned combat
spine, apply the existing gap/support inserts, then carry the existing late-fight
segment metadata alongside the finished session sequence.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .gap_fill_inserts import apply_gap_fill_inserts
from . import stage2_payload_late_fight as late_fight


def _role_countdown_offset(role: dict[str, Any]) -> int | None:
    value = role.get("countdown_offset")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if not label.startswith("D-"):
            continue
        digits: list[str] = []
        for char in label[2:]:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if digits:
            return int("".join(digits))
    return None


def _segment_span(segment: dict[str, Any]) -> tuple[int, int] | None:
    span = segment.get("countdown_span")
    if not isinstance(span, dict):
        return None
    try:
        start_day = int(span.get("start_day"))
        end_day = int(span.get("end_day"))
    except (TypeError, ValueError):
        return None
    if start_day < end_day:
        start_day, end_day = end_day, start_day
    return start_day, end_day


def build_finished_late_fight_tail(
    source_days_until_fight: Any,
    athlete_model: dict[str, Any],
    *,
    start_day: int = 13,
) -> dict[str, Any]:
    """Return the completed existing late-fight tail for a longer camp.

    ``source_days_until_fight`` is the long-camp generation day (for example
    D-30). The athlete snapshot is shifted to ``start_day`` so calendar weekday
    context is identical to a plan generated directly at that countdown point.

    The returned ``session_sequence`` is intentionally the *finished* sequence:
    it has already passed through the same coach-spine and gap/support finishing
    steps as the direct late-fight Stage 2 path. ``segments`` and
    ``day_metadata`` preserve the existing late-fight allocator's window-level
    compression, role-budget, sparring, suppression, and payload-mode context.
    """
    try:
        source_days = int(source_days_until_fight)
        start = int(start_day)
    except (TypeError, ValueError):
        return {}
    if source_days < start or start < 1:
        return {}

    tail_athlete = late_fight._shifted_segment_athlete_model(
        source_days,
        start,
        athlete_model,
    )

    base_spec = late_fight._build_late_fight_plan_spec(start, tail_athlete)
    pre_gap_sequence = late_fight.ensure_declared_coach_combat_spine(
        [
            deepcopy(role)
            for role in (
                base_spec.get("session_sequence")
                or base_spec.get("visible_session_sequence")
                or []
            )
            if isinstance(role, dict)
        ],
        tail_athlete,
        dict(base_spec.get("countdown_weekday_map") or {}),
    )
    finished_sequence = late_fight._visible_calendar_session_sequence(
        apply_gap_fill_inserts(pre_gap_sequence, tail_athlete)
    )

    late_role_map = late_fight._build_late_fight_weekly_role_map(
        start,
        tail_athlete,
    )
    finished_segments: list[dict[str, Any]] = []
    day_metadata: dict[int, dict[str, Any]] = {}

    for raw_segment in late_role_map.get("weeks", []) or []:
        if not isinstance(raw_segment, dict):
            continue
        span = _segment_span(raw_segment)
        if span is None:
            continue
        segment_start, segment_end = span
        segment = deepcopy(raw_segment)
        segment_roles = [
            deepcopy(role)
            for role in finished_sequence
            if isinstance(role, dict)
            and (offset := _role_countdown_offset(role)) is not None
            and segment_end <= offset <= segment_start
        ]
        segment["session_roles"] = segment_roles
        segment["finished_late_fight_path"] = True
        finished_segments.append(segment)

        metadata = {
            "stage_key": segment.get("stage_key"),
            "payload_mode": segment.get("payload_mode"),
            "countdown_span": deepcopy(segment.get("countdown_span") or {}),
            "intentional_compression": deepcopy(segment.get("intentional_compression") or {}),
            "role_budget": deepcopy(segment.get("role_budget") or {}),
            "suppressed_roles": deepcopy(segment.get("suppressed_roles") or []),
            "hard_sparring_plan": deepcopy(segment.get("hard_sparring_plan") or []),
            "effective_hard_sparring_days": deepcopy(
                segment.get("effective_hard_sparring_days") or []
            ),
        }
        for offset in range(segment_end, segment_start + 1):
            day_metadata[offset] = deepcopy(metadata)

    return {
        "source_days_until_fight": source_days,
        "start_day": start,
        "athlete_model": tail_athlete,
        "plan_spec": base_spec,
        "session_sequence": [
            deepcopy(role) for role in finished_sequence if isinstance(role, dict)
        ],
        "segments": finished_segments,
        "day_metadata": day_metadata,
    }
