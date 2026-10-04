"""Stamp stable exercise identity (``SessionBlock.exercise_key``) onto plan blocks.

``display_name`` is athlete-facing copy. The markdown→JSON conversion is free to
write it as a prescription ("3 x 2 min easy rounds") or a paraphrase
("Skipping flush (30/30)"), so it cannot identify the movement a demo video
belongs to. This module resolves identity once, from the plan's own planner
data, the same way ``reconcile_rehab_drill_ids`` resolves rehab identity:

* bank-backed exercises: a block whose name is one of the plan's own candidate
  pool exercises takes that bank exercise's normalized name as its key. The
  match is exact after normalization, so qualified variants ("Box Jump (Max
  Height)" vs "Box Jump (Stick Landing)") never collapse onto one key;
* gap-fill support inserts: a session on the insert's own countdown day whose
  title names the insert takes the insert's deterministic identity
  (``fightcamp.support_insert_identity.support_insert_exercise_key``), whatever its
  block happens to be called.

The model is never a source of a key. A key the server did not derive is
cleared unless it is just the block's own normalized name (what a deterministic
bank adapter stamps). Non-physical blocks (mindset, nutrition, coach-led
sparring) never carry a key, so they never receive a video.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

from fightcamp.support_insert_identity import support_insert_exercise_key

from .services.exercise_media import (
    NON_PHYSICAL_BLOCK_TYPES,
    normalize_exercise_key,
    strip_dose_suffix,
)

# Words that describe how an insert is dosed or framed rather than which
# movement it is; a session title is matched to an insert on the rest.
_FRAMING_WORDS = frozenset({
    "a", "aerobic", "and", "easy", "flow", "flush", "light", "long", "low",
    "min", "minute", "minutes", "of", "off", "on", "pace", "recovery", "rest",
    "round", "rounds", "rpe", "sec", "seconds", "short", "solo", "the", "work",
    "x",
})
_WORD_RE = re.compile(r"[a-z]+")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def block_exercise_key_for_name(name: Any) -> str | None:
    """The identity a deterministic adapter stamps for a bank exercise name."""
    key = normalize_exercise_key(strip_dose_suffix(str(name or "")))
    return key or None


def _bank_keys(planning_brief: Mapping[str, Any]) -> set[str]:
    """Normalized names of every bank exercise this plan's planner offered or assigned."""
    pools = planning_brief.get("candidate_pools")
    keys: set[str] = set()
    if not isinstance(pools, Mapping):
        return keys
    for pool in pools.values():
        if not isinstance(pool, Mapping):
            continue
        for group in ("strength_slots", "conditioning_slots"):
            for slot in _as_list(pool.get(group)):
                if not isinstance(slot, Mapping):
                    continue
                for option in [slot.get("selected"), *_as_list(slot.get("alternates"))]:
                    if isinstance(option, Mapping):
                        key = normalize_exercise_key(option.get("name"))
                        if key:
                            keys.add(key)
    for role in _iter_roles(planning_brief.get("weekly_role_map")):
        for assignment in _as_list(role.get("selected_exercise_assignments")):
            if isinstance(assignment, Mapping) and (key := normalize_exercise_key(assignment.get("name"))):
                keys.add(key)
        microdose = role.get("priority_microdose")
        if isinstance(microdose, Mapping) and (key := normalize_exercise_key(microdose.get("name"))):
            keys.add(key)
    return keys


def _countdown(value: Any) -> str | None:
    match = re.search(r"D-\s*(\d+)", str(value or ""), re.IGNORECASE)
    return f"D-{int(match.group(1))}" if match else None


def _identity_words(text: Any) -> set[str]:
    words = set(_WORD_RE.findall(str(text or "").lower()))
    # "skip"/"skipping", "shadow"/"shadowboxing": compare on stems.
    stems = {word[:5] for word in words - _FRAMING_WORDS if len(word) >= 4}
    return stems


def _iter_roles(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if value.get("role_key"):
            yield value
        for child in value.values():
            yield from _iter_roles(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_roles(child)


def _support_inserts_by_day(planning_brief: Mapping[str, Any]) -> dict[str, list[tuple[str, set[str], str]]]:
    """countdown label -> [(normalized label, identity stems, exercise key)]."""
    by_day: dict[str, list[tuple[str, set[str], str]]] = {}
    for role in _iter_roles(planning_brief.get("weekly_role_map")):
        label = role.get("athlete_facing_label")
        key = support_insert_exercise_key(role.get("role_key"), label)
        if not key:
            continue
        day = None
        for field in ("scheduled_countdown_label", "countdown_label", "countdown_display_label"):
            day = _countdown(role.get(field))
            if day:
                break
        if not day:
            continue
        entry = (normalize_exercise_key(label), _identity_words(label), key)
        if entry not in by_day.setdefault(day, []):
            by_day[day].append(entry)
    return by_day


def _insert_for_session(
    session: Mapping[str, Any],
    inserts: list[tuple[str, set[str], str]],
) -> tuple[set[str], str] | None:
    """(stems, key) of the one support insert this session renders, else None."""
    title = session.get("title")
    exact = {
        (frozenset(stems), key) for label, stems, key in inserts
        if label and label == normalize_exercise_key(title)
    }
    if len(exact) != 1:
        title_stems = _identity_words(title)
        exact = {
            (frozenset(stems), key) for _, stems, key in inserts
            if stems and stems <= title_stems
        }
    if len(exact) != 1:
        return None
    stems, key = next(iter(exact))
    return set(stems), key


def _is_physical(block: Mapping[str, Any]) -> bool:
    return str(block.get("block_type") or "").strip() not in NON_PHYSICAL_BLOCK_TYPES


def reconcile_exercise_keys(structured_plan: Any, planning_brief: Any) -> Any:
    """Stamp ``exercise_key`` on every physical block whose identity is known.

    Returns the input object unchanged when nothing changes, else a deep copy.
    """
    if not isinstance(structured_plan, dict):
        return structured_plan
    brief = planning_brief if isinstance(planning_brief, Mapping) else {}
    bank_keys = _bank_keys(brief)
    inserts_by_day = _support_inserts_by_day(brief)

    repaired = copy.deepcopy(structured_plan)
    changed = False
    for week in _as_list(repaired.get("weeks")):
        if not isinstance(week, dict):
            continue
        for day in _as_list(week.get("days")):
            if not isinstance(day, dict):
                continue
            inserts = inserts_by_day.get(_countdown(day.get("countdown_label")) or "", [])
            for session in _as_list(day.get("sessions")):
                if not isinstance(session, dict):
                    continue
                blocks = [block for block in _as_list(session.get("blocks")) if isinstance(block, dict)]
                insert = _insert_for_session(session, inserts) if inserts else None
                resolved_by_block = [_resolve_block_key(block, bank_keys) for block in blocks]
                if insert is not None:
                    insert_stems, insert_key = insert
                    open_blocks = [
                        index for index, block in enumerate(blocks)
                        if resolved_by_block[index] is None and _is_physical(block)
                    ]
                    for index in open_blocks:
                        # The insert session is one movement dosed in rounds, so
                        # a lone block is that movement however it is worded.
                        # Beside other blocks, only a block that is pure dose
                        # copy or names the movement itself takes the identity.
                        if len(open_blocks) == 1 or _identity_words(
                            blocks[index].get("display_name")
                        ) <= insert_stems:
                            resolved_by_block[index] = insert_key
                for block, resolved in zip(blocks, resolved_by_block):
                    if block.get("exercise_key") != resolved:
                        if resolved is None and "exercise_key" not in block:
                            continue
                        block["exercise_key"] = resolved
                        changed = True
    return repaired if changed else structured_plan


def _resolve_block_key(block: Mapping[str, Any], bank_keys: set[str]) -> str | None:
    if not _is_physical(block):
        return None
    own = block_exercise_key_for_name(block.get("display_name"))
    if own and own in bank_keys:
        return own
    existing = normalize_exercise_key(block.get("exercise_key"))
    # Keep a key a deterministic builder stamped only when it names one of this
    # plan's own planner exercises or the block's own name; anything else was
    # not derived from planner data and is dropped.
    if existing and (existing in bank_keys or existing == own):
        return existing
    return None
