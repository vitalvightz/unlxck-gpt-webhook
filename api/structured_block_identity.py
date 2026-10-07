"""Server-owned identity for the blocks of a structured plan (``block_id``).

Exercise logging records what the athlete actually did against one prescribed
block on one training day, so every loggable block needs an id that cannot be
missing. The Stage 2 converter is told identifiers are optional and usually
emits null, and a log must never be keyed on something the model can drop. This
module fills the gap in code.

A missing id is derived as ``blk-<day>-<exercise>``:

* ``<day>`` is the day's date, or its ``w<week>d<day>`` slot when the card
  carries no valid date (the same rule ``ensure_structured_session_ids`` uses);
* ``<exercise>`` is the planner's ``exercise_key`` when the block has one, else
  its display name;
* a repeat on the same day takes a numeric suffix (``-2``, ``-3``).

The dose is deliberately not part of the id, so changing a block's sets, reps or
load does not change which block it is.

It is a pure function of the stored card, applied in two places that therefore
always agree: the store stamps it when a card is saved, and
``resolve_effective_structured_plan`` derives it on read for cards saved before
that. Do not change the derivation: logs written against a card that predates
persisted ids are keyed on exactly this value.

An id is unique within its day, which is the scope a log needs — an open plan
repeats its weekly template, so a logged occurrence is always
``(plan, training day, block_id)``. Two blocks sharing an id on one day would
overwrite each other's log, so the later one takes a suffix.

Rehab blocks are left exactly as stored. Rehab evidence is keyed on their
identity (``rehab_completion_service.session_rehab_items``): a rehab block with
no id is identified by a hash of its own content, so stamping one would re-key
work the athlete has already been credited for.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

MINTED_BLOCK_ID_PREFIX = "blk-"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_EXERCISE_SLUG_LIMIT = 48
# Identity owned by another contract; see the module docstring.
_UNTOUCHED_BLOCK_TYPES = frozenset({"rehab"})


def _slug(value: Any, limit: int) -> str:
    return _SLUG_RE.sub("-", str(value or "").strip().lower()).strip("-")[:limit].strip("-")


def _block_id(block: Mapping[str, Any]) -> str:
    value = block.get("block_id")
    return "" if value is None else str(value).strip()


def _is_untouched(block: Mapping[str, Any]) -> bool:
    return str(block.get("block_type") or "").strip() in _UNTOUCHED_BLOCK_TYPES


def _day_slot(day: Mapping[str, Any], week_index: int, day_index: int) -> str:
    date_part = str(day.get("date") or "").strip()[:10]
    try:
        date.fromisoformat(date_part)
    except ValueError:
        return f"w{week_index + 1}d{day_index + 1}"
    return date_part


def _exercise_slug(block: Mapping[str, Any]) -> str:
    return (
        _slug(block.get("exercise_key"), _EXERCISE_SLUG_LIMIT)
        or _slug(block.get("display_name"), _EXERCISE_SLUG_LIMIT)
        or _slug(block.get("block_type"), _EXERCISE_SLUG_LIMIT)
        or "block"
    )


def _free_id(base: str, taken: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _day_sessions_with_block_ids(day: Mapping[str, Any], slot: str) -> list[Any] | None:
    """The day's sessions with every block id filled, or None when already complete."""
    sessions = day.get("sessions")
    if not isinstance(sessions, list):
        return None

    def blocks_of(session: Any) -> list[Any]:
        blocks = session.get("blocks") if isinstance(session, Mapping) else None
        return blocks if isinstance(blocks, list) else []

    # Every id already on the day is reserved first, so a derived id can never
    # land on one a later block already carries.
    taken = {
        _block_id(block)
        for session in sessions
        for block in blocks_of(session)
        if isinstance(block, Mapping) and _block_id(block)
    }

    seen: set[str] = set()
    changed = False
    result: list[Any] = []
    for session in sessions:
        blocks = blocks_of(session)
        new_blocks: list[Any] | None = None
        for index, block in enumerate(blocks):
            if not isinstance(block, Mapping):
                continue
            current = _block_id(block)
            if _is_untouched(block):
                seen.add(current)
                continue
            if current and current not in seen:
                seen.add(current)
                continue
            # Missing, or a second block carrying an id already used today.
            assigned = _free_id(current or f"{MINTED_BLOCK_ID_PREFIX}{slot}-{_exercise_slug(block)}", taken)
            seen.add(assigned)
            if new_blocks is None:
                new_blocks = list(blocks)
            new_blocks[index] = {**block, "block_id": assigned}
        if new_blocks is None:
            result.append(session)
        else:
            result.append({**session, "blocks": new_blocks})
            changed = True
    return result if changed else None


def ensure_structured_block_ids(plan: Any) -> Any:
    """Give every block of a structured plan a ``block_id`` unique within its day.

    Existing ids are kept; only a missing id, or the later of two that collide on
    one day, is written. Rehab blocks are never touched. Returns the input object
    itself when there is nothing to do (including anything that is not a plan
    mapping); otherwise a copy of just the week -> day -> session -> block path
    that changed, leaving the input and every other nested value shared and
    unmutated.
    """
    if not isinstance(plan, Mapping):
        return plan
    weeks = plan.get("weeks")
    if not isinstance(weeks, list):
        return plan
    new_weeks: list[Any] | None = None
    for week_index, week in enumerate(weeks):
        days = week.get("days") if isinstance(week, Mapping) else None
        if not isinstance(days, list):
            continue
        new_days: list[Any] | None = None
        for day_index, day in enumerate(days):
            if not isinstance(day, Mapping):
                continue
            sessions = _day_sessions_with_block_ids(day, _day_slot(day, week_index, day_index))
            if sessions is None:
                continue
            if new_days is None:
                new_days = list(days)
            new_days[day_index] = {**day, "sessions": sessions}
        if new_days is not None:
            if new_weeks is None:
                new_weeks = list(weeks)
            new_weeks[week_index] = {**week, "days": new_days}
    if new_weeks is None:
        return plan
    return {**plan, "weeks": new_weeks}


__all__ = ["MINTED_BLOCK_ID_PREFIX", "ensure_structured_block_ids"]
