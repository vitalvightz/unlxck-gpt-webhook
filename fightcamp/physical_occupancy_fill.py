"""Fill declared training days the planner left empty with low-cost physical work.

This is the *occupancy* half of the frequency contract in
``fightcamp.physical_session_frequency``. The role allocators decide how much
meaningful stress a window may carry; this pass decides whether a day the
athlete declared as a training day ends up with a session on it at all.

It never adds meaningful stress. Every candidate comes from the existing
deterministic gap-fill insert banks, filtered to options that count as physical
work and legal at that countdown position. When no legal physical option exists
the day is recorded in ``intentionally_unused_days`` with a deterministic
reason instead of being padded with filler.
"""

from __future__ import annotations

from typing import Any, Sequence

from .calendar_context import sequence_legality
from .gap_fill_inserts import (
    _record_insert_usage,
    _usage_ledger_from_sequence,
    select_physical_occupancy_insert,
)
from .physical_session_frequency import (
    REASON_FREQUENCY_TARGET_MET,
    REASON_NO_LEGAL_PHYSICAL_OPTION,
    plan_physical_occupancy,
    unused_day_record,
)


def _decorate(role: dict[str, Any], offset: int, weekday: str) -> dict[str, Any]:
    weekday_title = str(weekday or "").strip().title()
    role["countdown_offset"] = offset
    role["countdown_label"] = f"D-{offset}"
    role["scheduled_countdown_label"] = f"D-{offset}"
    if weekday_title:
        role["scheduled_day_hint"] = weekday_title
        role["real_weekday"] = weekday_title
        role["countdown_display_label"] = f"D-{offset} ({weekday_title})"
    return role


def fill_physical_occupancy(
    *,
    day_slots: Sequence[tuple[int, str]],
    roles: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    resolved_contacts: list[dict[str, Any]] | None = None,
    usage_ledger: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(added_roles, intentionally_unused_records)`` for one week.

    ``day_slots`` is ``[(countdown_offset, weekday), ...]`` for the week being
    completed. ``roles`` is the week's already-placed sequence and is not
    mutated.
    """
    plan = plan_physical_occupancy(
        day_slots=day_slots,
        roles=roles,
        athlete_model=athlete_model,
    )
    if plan.requested_frequency is None:
        # No requested frequency, no occupancy authority. Without a stated weekly
        # session count there is no target to hold the calendar to, and filling
        # every declared day would be this pass inventing a contract.
        return [], []
    weekday_by_offset = {
        offset: weekday for offset, weekday in day_slots if isinstance(offset, int)
    }
    added: list[dict[str, Any]] = []
    unused: list[dict[str, Any]] = []
    if not plan.fill_offsets:
        return added, unused

    ledger = usage_ledger if usage_ledger is not None else _usage_ledger_from_sequence(roles)
    remaining = plan.shortfall
    # Earliest days first: a session belongs where the athlete planned to train,
    # and front-loading keeps the cheapest work furthest from fight day.
    for offset in plan.fill_offsets:
        weekday = weekday_by_offset.get(offset, "")
        if remaining <= 0:
            unused.append(unused_day_record(weekday, offset, REASON_FREQUENCY_TARGET_MET))
            continue
        legality = sequence_legality(
            list(roles) + added,
            resolved_contacts=list(resolved_contacts or []),
        )
        insert = select_physical_occupancy_insert(
            athlete_model,
            offset,
            usage_ledger=ledger,
            legality=legality,
            scheduled_roles=list(roles) + added,
        )
        if insert is None:
            unused.append(
                unused_day_record(weekday, offset, REASON_NO_LEGAL_PHYSICAL_OPTION)
            )
            continue
        added.append(_decorate(insert, offset, weekday))
        _record_insert_usage(ledger, str(insert.get("role_key") or ""), offset)
        remaining -= 1
    return added, unused


def _countdown_day_slots(countdown_weekday_map: dict[str, Any] | None) -> list[tuple[int, str]]:
    slots: list[tuple[int, str]] = []
    for label, weekday in (countdown_weekday_map or {}).items():
        text = str(label or "").strip().upper()
        if not text.startswith("D-"):
            continue
        digits = ""
        for char in text[2:]:
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            slots.append((int(digits), str(weekday or "")))
    return sorted(set(slots), reverse=True)


def complete_late_fight_sequence_occupancy(
    session_sequence: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    *,
    countdown_weekday_map: dict[str, Any] | None,
    resolved_contacts: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Occupancy completion for a directly generated late-fight sequence.

    A plan generated inside D-13 has no normal weekly role map to hang this off,
    so the countdown window is bucketed into calendar weeks (``offset // 7``) and
    each bucket gets its own physical-session target. Returns
    ``(sequence, intentionally_unused_days)``; the sequence keeps countdown order.
    """
    slots = _countdown_day_slots(countdown_weekday_map)
    if not slots:
        return list(session_sequence), []

    buckets: dict[int, list[tuple[int, str]]] = {}
    for offset, weekday in slots:
        buckets.setdefault(offset // 7, []).append((offset, weekday))

    combined = list(session_sequence)
    unused: list[dict[str, Any]] = []
    for _bucket, bucket_slots in sorted(buckets.items(), reverse=True):
        added, bucket_unused = fill_physical_occupancy(
            day_slots=bucket_slots,
            roles=combined,
            athlete_model=athlete_model,
            resolved_contacts=resolved_contacts,
        )
        combined.extend(added)
        unused.extend(bucket_unused)

    combined.sort(key=lambda role: int(role.get("countdown_offset") or 0), reverse=True)
    for index, role in enumerate(combined, start=1):
        role["session_index"] = index
    return combined, unused
