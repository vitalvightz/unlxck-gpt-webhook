"""Canonical within-day execution order.

Every other planner owner decides *whether* work exists and *which day* it
belongs on. Nothing decided the order in which a day's work is performed: same
-day sessions kept whatever order they happened to enter ``session_roles``, and
server-owned cards (Tactical Focus, Fight Visualisation) were appended after
conversion. A calming ``Breathing Reset`` could therefore land in front of the
``Technical Shadow Rhythm`` it exists to wind down from.

This module owns that one question and nothing else:

    Given everything already scheduled on one day, in what order should it be
    performed?

It never adds, removes, renames or moves work to another day, and it never
touches ``session_index`` (planning identity). It orders by *intent*, not by
title or category, using a small vocabulary that follows how a coach assembles
a day::

    PREPARE -> PRIME -> LEARN -> PERFORM -> DEVELOP -> FATIGUE -> RESTORE -> REFLECT

The same policy runs one level lower, over the blocks inside a session
(movement prep -> plyometric -> main strength -> accessory -> conditioning ->
cooldown).

Rules the ordering follows:

* **Stable.** Items with the same intent keep their input order, so the engine
  only ever moves something when the intents genuinely disagree.
* **Unclassified work is anchored, never guessed.** An item whose intent cannot
  be resolved travels with the item it was written after (or before, when it
  leads the day) instead of being assigned an invented position.
* **Explicit exceptions win.** A role, session or block carrying
  ``sequence_override`` (``"first"``, ``"last"``, ``"before_<intent>"``,
  ``"after_<intent>"``, e.g. ``"after_conditioning"`` for deliberate
  technical-work-under-fatigue) or ``sequence_intent`` is placed where it says,
  so an unusual order is intentional rather than accidental.

Stage 1 stamps the result on each scheduled role as ``execution_order``
(:func:`stamp_role_execution_order`) so the handoff carries it; the structured
card is re-sequenced after every deterministic and server-owned session has been
merged (:func:`sequence_structured_plan`), because that is the only point at
which the day's full membership is known.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar

from .calendar_context import role_d_day
from .gap_fill_inserts import _INSERT_META
from .role_labels import ROLE_LABELS

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SequenceIntent(IntEnum):
    """Why a piece of work sits where it does in the day.

    Values are spaced by ten so a registry entry can refine its position inside
    its intent (a walk flush before a breathing reset, both ``RESTORE``) without
    ever crossing into the next intent.
    """

    PREPARE = 10
    PRIME = 20
    LEARN = 30
    PERFORM = 40
    DEVELOP = 50
    FATIGUE = 60
    RESTORE = 70
    REFLECT = 80


@dataclass(frozen=True)
class SequenceSlot:
    """A resolved position: its intent, a refinement inside it, and an anchor.

    ``anchor`` is ``"first"`` / ``"last"`` for an item pinned to either end of
    the day regardless of intent.
    """

    intent: SequenceIntent
    offset: int = 0
    anchor: str | None = None

    @property
    def rank(self) -> float:
        if self.anchor == "first":
            return 0.0
        if self.anchor == "last":
            return 1000.0
        return float(int(self.intent) + self.offset)


_INTENT_SPAN = 10  # the rank width owned by one intent

# ---------------------------------------------------------------------------
# Role intent registry.
#
# Keyed by the planner's own role_key. Support inserts use their bank key
# (fightcamp.gap_fill_inserts._INSERT_META) as role_key, so they resolve here
# first; the insert/category tables below only catch keys this registry has not
# learned yet.
# ---------------------------------------------------------------------------

_P, _PR, _L, _PF, _D, _F, _R, _RF = (
    SequenceIntent.PREPARE,
    SequenceIntent.PRIME,
    SequenceIntent.LEARN,
    SequenceIntent.PERFORM,
    SequenceIntent.DEVELOP,
    SequenceIntent.FATIGUE,
    SequenceIntent.RESTORE,
    SequenceIntent.REFLECT,
)

ROLE_SEQUENCE: dict[str, SequenceSlot] = {
    # --- Prepare: joint prep, movement quality, targeted mobility/rehab ------
    "joint_prep": SequenceSlot(_P, 0),
    "movement_quality": SequenceSlot(_P, 2),
    "mobility_rehab": SequenceSlot(_P, 4),
    "converted_mobility_support_day": SequenceSlot(_P, 4),
    "converted_rehab_friendly_support_day": SequenceSlot(_P, 4),
    # --- Prime: neural/mental priming, then physical primers ------------------
    "neural_visualization": SequenceSlot(_PR, 0),
    "fight_visualization": SequenceSlot(_PR, 0),
    "tactical_cue_card": SequenceSlot(_PR, 2),
    "fight_week_freshness_day": SequenceSlot(_PR, 5),
    "alactic_sharpness_day": SequenceSlot(_PR, 5),
    "alactic_speed_day": SequenceSlot(_PR, 5),
    "alactic_support_day": SequenceSlot(_PR, 5),
    "alactic_coordination_day": SequenceSlot(_PR, 5),
    "strength_touch_day": SequenceSlot(_PR, 7),
    "small_strength_touch_day": SequenceSlot(_PR, 7),
    "neural_primer_day": SequenceSlot(_PR, 7),
    # --- Learn: skill before fatigue --------------------------------------------
    "tactical_watch": SequenceSlot(_L, 0),
    "technical_touch_day": SequenceSlot(_L, 3),
    "technical_shadow_rhythm": SequenceSlot(_L, 3),
    "footwork_walkthrough": SequenceSlot(_L, 3),
    "coordination_support": SequenceSlot(_L, 5),
    # --- Perform: contact / competition --------------------------------------------
    "light_combat_day": SequenceSlot(_PF, 0),
    "hard_sparring_day": SequenceSlot(_PF, 0),
    "fight_day_protocol": SequenceSlot(_PF, 0),
    # --- Develop: strength before conditioning ---------------------------------
    "primary_strength_day": SequenceSlot(_D, 0),
    "structural_strength_day": SequenceSlot(_D, 0),
    "neural_plus_strength_day": SequenceSlot(_D, 0),
    "transfer_strength_day": SequenceSlot(_D, 2),
    "secondary_strength_day": SequenceSlot(_D, 2),
    # --- Fatigue: hard conditioning, then easier aerobic support ---------------
    "highest_glycolytic_day": SequenceSlot(_F, 0),
    "main_fight_pace_day": SequenceSlot(_F, 0),
    "fight_pace_repeatability_day": SequenceSlot(_F, 0),
    "controlled_repeatability_day": SequenceSlot(_F, 1),
    "repeatability_support_day": SequenceSlot(_F, 2),
    "aerobic_base_day": SequenceSlot(_F, 4),
    "aerobic_support_day": SequenceSlot(_F, 4),
    "aerobic_coordination_day": SequenceSlot(_F, 4),
    "converted_low_aerobic_gas_tank_day": SequenceSlot(_F, 6),
    "recovery_aerobic_gas_tank_day": SequenceSlot(_F, 6),
    "aerobic_shadow_flow": SequenceSlot(_F, 6),
    "aerobic_footwork_rhythm": SequenceSlot(_F, 6),
    "aerobic_skip_flush": SequenceSlot(_F, 7),
    "aerobic_jog_flush": SequenceSlot(_F, 7),
    "aerobic_walk_flush": SequenceSlot(_F, 7),
    # --- Restore: active flush -> reset -> breathing ----------------------------
    "aerobic_flush_day": SequenceSlot(_R, 0),
    "light_fight_pace_touch_day": SequenceSlot(_R, 0),
    "walk_flush": SequenceSlot(_R, 0),
    "converted_recovery_flush_day": SequenceSlot(_R, 0),
    "recovery_reset_day": SequenceSlot(_R, 3),
    "recovery_only_day": SequenceSlot(_R, 3),
    "tissue_recovery_day": SequenceSlot(_R, 3),
    "recovery_reset": SequenceSlot(_R, 3),
    "breathing_reset": SequenceSlot(_R, 5),
    # Sleep downshift is the last thing in the athlete's day by definition
    # ("lights down, phone away"), after any review.
    "sleep_downshift": SequenceSlot(_R, 8, anchor="last"),
    # --- Reflect ----------------------------------------------------------------
    "self_review": SequenceSlot(_RF, 0),
}

# Insert semantics (gap_fill_inserts._INSERT_META ``insert_category`` / the role's
# ``support_insert_category``) for a support insert this registry has not
# learned by key.
_SUPPORT_CATEGORY_SEQUENCE: dict[str, SequenceSlot] = {
    "mobility": SequenceSlot(_P, 4),
    "movement_quality": SequenceSlot(_P, 2),
    "mental": SequenceSlot(_PR, 0),
    "tactical": SequenceSlot(_L, 0),
    "technical": SequenceSlot(_L, 3),
    "technical_footwork": SequenceSlot(_L, 3),
    "footwork": SequenceSlot(_L, 3),
    "coordination": SequenceSlot(_L, 5),
    "conditioning_maintenance": SequenceSlot(_F, 6),
    "low_cost_aerobic": SequenceSlot(_F, 6),
    "recovery": SequenceSlot(_R, 3),
    "recovery_walk": SequenceSlot(_R, 0),
    "low_cost_recovery": SequenceSlot(_R, 3),
}

# The planner's role ``category`` for anything neither table knows.
_CATEGORY_SEQUENCE: dict[str, SequenceSlot] = {
    "strength": SequenceSlot(_D, 0),
    "conditioning": SequenceSlot(_F, 0),
    "recovery": SequenceSlot(_R, 3),
    "rehab": SequenceSlot(_P, 4),
    "technical": SequenceSlot(_L, 3),
    "skill": SequenceSlot(_L, 3),
    "sparring": SequenceSlot(_PF, 0),
}

# Structured-card vocabulary (api/structured_plan_models.SessionType).
_SESSION_TYPE_SEQUENCE: dict[str, SequenceSlot] = {
    "primer": SequenceSlot(_PR, 5),
    "skill": SequenceSlot(_L, 3),
    "sparring": SequenceSlot(_PF, 0),
    "fight_or_match": SequenceSlot(_PF, 0),
    "strength_power": SequenceSlot(_D, 0),
    "conditioning": SequenceSlot(_F, 0),
    "recovery": SequenceSlot(_R, 3),
}

# Structured-card vocabulary (api/structured_plan_models.BlockType). ``rehab``,
# ``mindset`` and ``nutrition`` are resolved by purpose or anchored instead: a
# mindset block may prime or review, and a rehab block may prepare or restore.
_BLOCK_TYPE_SEQUENCE: dict[str, SequenceSlot] = {
    "preparation": SequenceSlot(_P, 0),
    "mobility_activation": SequenceSlot(_P, 2),
    "speed": SequenceSlot(_PR, 2),
    "plyometric_power": SequenceSlot(_PR, 4),
    "strength_speed": SequenceSlot(_PR, 6),
    "skill": SequenceSlot(_L, 3),
    "sparring": SequenceSlot(_PF, 0),
    "strength": SequenceSlot(_D, 0),
    "accessory": SequenceSlot(_D, 5),
    "conditioning": SequenceSlot(_F, 0),
    "cooldown_recovery": SequenceSlot(_R, 3),
}

# Purpose words that say which end of the day a rehab/mobility item serves.
_RESTORE_PURPOSE_RE = re.compile(
    r"\b(?:downshift|down-regulat\w*|downregulat\w*|cool[\s-]?down|restor\w*|"
    r"recover\w*|flush|calm\w*|decompress\w*|wind[\s-]?down)\b",
    re.IGNORECASE,
)
_PREPARE_PURPOSE_RE = re.compile(
    r"\b(?:activat\w*|warm[\s-]?up|prep\w*|prime|priming|isometric\w*|"
    r"before\s+(?:training|the\s+session|lifting|sparring))\b",
    re.IGNORECASE,
)

# Friendly names accepted in ``sequence_override`` / ``sequence_intent``.
_INTENT_ALIASES: dict[str, SequenceIntent] = {
    **{intent.name.lower(): intent for intent in SequenceIntent},
    "prep": _P,
    "warmup": _P,
    "warm_up": _P,
    "mobility": _P,
    "primer": _PR,
    "skill": _L,
    "technical": _L,
    "sparring": _PF,
    "contact": _PF,
    "strength": _D,
    "conditioning": _F,
    "recovery": _R,
    "review": _RF,
}


def _clean(value: Any) -> str:
    return str(value or "").strip().lower()


def _intent_from_name(value: Any) -> SequenceIntent | None:
    return _INTENT_ALIASES.get(_clean(value).replace("-", "_").replace(" ", "_"))


def parse_sequence_override(value: Any) -> SequenceSlot | None:
    """Explicit placement: ``first``, ``last``, ``before_<x>`` or ``after_<x>``.

    ``before_<x>`` sits ahead of every item of intent ``x``; ``after_<x>`` sits
    behind all of them. Unknown values return ``None`` (ignored, never guessed).
    """
    text = _clean(value).replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in {"first", "last"}:
        return SequenceSlot(_P, 0, anchor=text)
    # Registry refinements stay inside 0..8, so -1 lands just ahead of the whole
    # intent band and span-1 just behind it, never inside another intent's band.
    for prefix, offset in (("before_", -1), ("after_", _INTENT_SPAN - 1)):
        if text.startswith(prefix):
            intent = _intent_from_name(text[len(prefix) :])
            return SequenceSlot(intent, offset) if intent is not None else None
    return None


def _explicit_slot(item: Mapping[str, Any]) -> SequenceSlot | None:
    override = parse_sequence_override(item.get("sequence_override"))
    if override is not None:
        return override
    intent = _intent_from_name(item.get("sequence_intent"))
    return SequenceSlot(intent) if intent is not None else None


def _purpose_slot(text: str, *, default: SequenceSlot | None) -> SequenceSlot | None:
    if _RESTORE_PURPOSE_RE.search(text):
        return SequenceSlot(_R, 2)
    if _PREPARE_PURPOSE_RE.search(text):
        return SequenceSlot(_P, 4)
    return default


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def role_sequence_slot(role: Mapping[str, Any]) -> SequenceSlot | None:
    """Where a Stage 1 session role sits in its day, or ``None`` if unknown."""
    if not isinstance(role, Mapping):
        return None
    explicit = _explicit_slot(role)
    if explicit is not None:
        return explicit
    role_key = _clean(role.get("role_key"))
    if role_key in ROLE_SEQUENCE:
        return ROLE_SEQUENCE[role_key]
    for key in ("support_insert_category", "support_insert_cost_category"):
        slot = _SUPPORT_CATEGORY_SEQUENCE.get(_clean(role.get(key)))
        if slot is not None:
            return slot
    insert_category = _clean((_INSERT_META.get(role_key) or {}).get("insert_category"))
    if insert_category in _SUPPORT_CATEGORY_SEQUENCE:
        return _SUPPORT_CATEGORY_SEQUENCE[insert_category]
    category = _clean(role.get("category"))
    if category == "rehab":
        return _purpose_slot(
            " ".join(str(role.get(k) or "") for k in ("display_text", "athlete_facing_label")),
            default=_CATEGORY_SEQUENCE["rehab"],
        )
    return _CATEGORY_SEQUENCE.get(category)


def _normalise_label(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _label_table() -> dict[str, SequenceSlot]:
    """Planner-owned athlete-facing labels whose roles all share one position.

    A structured session keeps the planner's label as its title (the
    deterministic builder, the locked merge and the converter prompt all use
    it), so an exact label is identity, not a keyword guess. A label shared by
    roles in different positions is left out rather than resolved arbitrarily.
    """
    candidates: dict[str, set[SequenceSlot]] = {}
    for role_key, label in ROLE_LABELS.items():
        slot = ROLE_SEQUENCE.get(role_key)
        if slot is not None:
            candidates.setdefault(_normalise_label(label), set()).add(slot)
    for role_key, meta in _INSERT_META.items():
        slot = ROLE_SEQUENCE.get(role_key)
        label = meta.get("label")
        if slot is not None and label:
            candidates.setdefault(_normalise_label(label), set()).add(slot)
    # Server-owned locked cards (api/structured_plan_locked_merge).
    candidates.setdefault("tactical focus", set()).add(ROLE_SEQUENCE["tactical_watch"])
    candidates.setdefault("fight visualisation", set()).add(ROLE_SEQUENCE["fight_visualization"])
    candidates.setdefault("fight visualization", set()).add(ROLE_SEQUENCE["fight_visualization"])
    return {label: next(iter(slots)) for label, slots in candidates.items() if len(slots) == 1}


_LABEL_SEQUENCE = _label_table()

# Session ids the deterministic assemblers write:
#   deterministic-<d_day>-<role_key>-<session_index>   (fallback / spine restore)
#   locked-<day slug>-tactical-watch | -fight-visualization   (locked merge)
_DETERMINISTIC_SESSION_ID_RE = re.compile(
    r"^deterministic-(?P<d_day>\d+)-(?P<role_key>[a-z0-9_]+)-(?P<index>[^-]+)$"
)
_LOCKED_SESSION_ID_RE = re.compile(r"^locked-.*-(?P<slug>tactical-watch|fight-visualization)$")


def session_role_key(session: Mapping[str, Any]) -> str | None:
    """The planner role_key a deterministic/locked ``session_id`` encodes."""
    session_id = _clean(session.get("session_id"))
    match = _DETERMINISTIC_SESSION_ID_RE.match(session_id)
    if match:
        return match.group("role_key")
    match = _LOCKED_SESSION_ID_RE.match(session_id)
    if match:
        return match.group("slug").replace("-", "_")
    return None


def block_sequence_slot(block: Mapping[str, Any]) -> SequenceSlot | None:
    """Where a block sits inside its session, or ``None`` if unknown."""
    if not isinstance(block, Mapping):
        return None
    explicit = _explicit_slot(block)
    if explicit is not None:
        return explicit
    block_type = _clean(block.get("block_type"))
    if block_type in _BLOCK_TYPE_SEQUENCE:
        return _BLOCK_TYPE_SEQUENCE[block_type]
    if block_type == "rehab":
        text = " ".join(
            str(block.get(key) or "") for key in ("display_name", "purpose", "why_today")
        )
        # A rehab block only moves when its own purpose says which end of the
        # session it serves; otherwise it stays where it was written.
        return _purpose_slot(text, default=None)
    return None


def session_sequence_slot(
    session: Mapping[str, Any], role: Mapping[str, Any] | None = None
) -> SequenceSlot | None:
    """Where a structured-card session sits in its day, or ``None`` if unknown.

    Identity is resolved from the strongest signal available: an explicit
    override, the planner role it represents (``role``, when the caller matched
    one), the role_key encoded in a deterministic/locked ``session_id``, the
    planner's own label as its title, then its session type and blocks.
    """
    if not isinstance(session, Mapping):
        return None
    explicit = _explicit_slot(session)
    if explicit is not None:
        return explicit
    if role is not None:
        slot = role_sequence_slot(role)
        if slot is not None:
            return slot
    role_key = session_role_key(session)
    if role_key and role_key in ROLE_SEQUENCE:
        return ROLE_SEQUENCE[role_key]
    label_slot = _LABEL_SEQUENCE.get(_normalise_label(session.get("title")))
    if label_slot is not None:
        return label_slot
    session_type = _clean(session.get("session_type"))
    if session_type in _SESSION_TYPE_SEQUENCE:
        return _SESSION_TYPE_SEQUENCE[session_type]
    if session_type == "rehab":
        return _purpose_slot(
            " ".join(str(session.get(k) or "") for k in ("title", "objective")),
            default=SequenceSlot(_P, 4),
        )
    return _slot_from_blocks(session.get("blocks"))


_WRAPPER_INTENTS = frozenset({_P, _R, _RF})


def _slot_from_blocks(blocks: Any) -> SequenceSlot | None:
    """A mixed session's position is that of its main work.

    Warm-up and cooldown blocks wrap almost every session, so they only decide
    the position when the session holds nothing else. Among main blocks the
    latest intent wins: a session that ends in conditioning leaves the athlete
    fatigued whatever it started with.
    """
    slots = [
        slot
        for block in blocks or []
        if isinstance(block, Mapping) and (slot := block_sequence_slot(block)) is not None
    ]
    main = [slot for slot in slots if slot.anchor is None and slot.intent not in _WRAPPER_INTENTS]
    if main:
        return max(main, key=lambda slot: slot.rank)
    return slots[0] if slots else None


# Session types and block types that wrap or support a day's main work rather
# than being it. Structural on purpose: the web client mirrors this rule
# (web/lib/camp-map.ts primarySessionOf) and has no access to the registry.
SUPPORT_SESSION_TYPES = frozenset({"recovery", "rehab"})
SUPPORT_BLOCK_TYPES = frozenset(
    {"preparation", "mobility_activation", "cooldown_recovery", "mindset", "nutrition", "rehab"}
)


def is_support_session(session: Mapping[str, Any]) -> bool:
    """Whether a card session is prep/recovery/mindset support, not main work.

    Execution order puts support work around the main work (joint prep first, a
    breathing reset last), so "the first session of the day" no longer means
    "the day's main session". Callers that summarise one session per day use
    this to skip support work when real training exists.
    """
    if not isinstance(session, Mapping):
        return False
    if _clean(session.get("session_type")) in SUPPORT_SESSION_TYPES:
        return True
    blocks = [block for block in session.get("blocks") or [] if isinstance(block, Mapping)]
    return bool(blocks) and all(_clean(block.get("block_type")) in SUPPORT_BLOCK_TYPES for block in blocks)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def sequence_items(
    items: Sequence[T], slot_for: Callable[[T], SequenceSlot | None]
) -> list[T]:
    """``items`` in execution order. Stable; unknown items stay anchored.

    An item with no resolvable slot borrows the rank of the nearest resolved
    item written before it (or after it, when nothing precedes it), so it keeps
    its place beside that neighbour instead of being given a position nobody
    decided. A list with nothing resolvable is returned unchanged.
    """
    ranks: list[float | None] = []
    for item in items:
        slot = slot_for(item)
        ranks.append(slot.rank if slot is not None else None)
    if all(rank is None for rank in ranks):
        return list(items)
    resolved: list[float] = []
    previous: float | None = None
    for rank in ranks:
        previous = rank if rank is not None else previous
        resolved.append(previous if previous is not None else float("nan"))
    following: float | None = None
    for index in range(len(resolved) - 1, -1, -1):
        if ranks[index] is not None:
            following = ranks[index]
        if resolved[index] != resolved[index]:  # NaN: nothing before it
            resolved[index] = following  # type: ignore[assignment]
    order = sorted(range(len(items)), key=lambda index: (resolved[index], index))
    return [items[index] for index in order]


def sequence_day_roles(roles: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """One day's Stage 1 roles in execution order."""
    return sequence_items([role for role in roles if isinstance(role, Mapping)], role_sequence_slot)


def sequence_session_blocks(blocks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One session's blocks in execution order."""
    return sequence_items([block for block in blocks if isinstance(block, dict)], block_sequence_slot)


def sequence_day_sessions(
    sessions: Iterable[dict[str, Any]],
    role_for: Callable[[dict[str, Any]], Mapping[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    """One day's structured sessions in execution order."""
    items = [session for session in sessions if isinstance(session, dict)]
    return sequence_items(
        items, lambda session: session_sequence_slot(session, role_for(session) if role_for else None)
    )


# ---------------------------------------------------------------------------
# Stage 1: stamp execution_order on scheduled roles
# ---------------------------------------------------------------------------


# Every countdown-sequence list the late-fight renderer and finalizer packet read.
_BRIEF_SEQUENCE_KEYS = ("late_fight_session_sequence", "session_sequence", "countdown_sessions")
_SPEC_SEQUENCE_KEYS = ("visible_session_sequence", "session_sequence", "countdown_sessions", "sessions")


def _stamp(groups: dict[Any, list[dict[str, Any]]]) -> None:
    for roles in groups.values():
        for position, role in enumerate(sequence_day_roles(roles), start=1):
            role["execution_order"] = position  # type: ignore[index]


def stamp_role_execution_order(planning_brief: Any) -> Any:
    """Stamp ``execution_order`` (1-based, per day) on every scheduled role.

    Reads the finished calendar and writes only ``execution_order``: role
    membership, day ownership, list order and ``session_index`` are untouched.
    Covers the normal weekly role map and the late-fight countdown sequence.
    Mutates in place and returns ``planning_brief``.
    """
    if not isinstance(planning_brief, dict):
        return planning_brief

    role_map = planning_brief.get("weekly_role_map")
    if isinstance(role_map, dict):
        groups: dict[Any, list[dict[str, Any]]] = {}
        for week_position, week in enumerate(role_map.get("weeks") or []):
            if not isinstance(week, dict):
                continue
            for role in week.get("session_roles") or []:
                if not isinstance(role, dict):
                    continue
                d_day = role_d_day(week, role)
                if isinstance(d_day, int):
                    key: Any = ("d_day", d_day)
                else:
                    weekday = _clean(role.get("scheduled_day_hint") or role.get("real_weekday"))
                    if not weekday:
                        continue
                    key = ("week_day", week_position, weekday)
                groups.setdefault(key, []).append(role)
        _stamp(groups)

    spec = planning_brief.get("late_fight_plan_spec")
    sequences = [planning_brief.get(key) for key in _BRIEF_SEQUENCE_KEYS]
    if isinstance(spec, dict):
        sequences.extend(spec.get(key) for key in _SPEC_SEQUENCE_KEYS)
    for sequence in sequences:
        if not isinstance(sequence, list):
            continue
        groups = {}
        for role in sequence:
            if not isinstance(role, dict):
                continue
            d_day = role_d_day({}, role)
            if isinstance(d_day, int):
                groups.setdefault(d_day, []).append(role)
        _stamp(groups)
    return planning_brief


def in_stamped_execution_order(
    roles: Sequence[dict[str, Any]], day_key: Callable[[dict[str, Any]], Any]
) -> list[dict[str, Any]]:
    """``roles`` with each day's roles in their stamped ``execution_order``.

    Read-only helper for renderers: days keep the order in which they first
    appear, roles without a stamp keep their relative position, and nothing is
    re-derived here.
    """
    first_seen: dict[Any, int] = {}
    for role in roles:
        first_seen.setdefault(day_key(role), len(first_seen))

    def key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, role = item
        stamped = role.get("execution_order")
        return (first_seen[day_key(role)], stamped if isinstance(stamped, int) else 0, index)

    return [role for _, role in sorted(enumerate(roles), key=key)]


# ---------------------------------------------------------------------------
# Structured card: order sessions and blocks after every merge
# ---------------------------------------------------------------------------


def _countdown_dday(label: Any) -> int | None:
    text = str(label or "").strip().upper().replace(" ", "")
    if not text.startswith("D-"):
        return 0 if text == "D0" else None
    try:
        return int(text[2:])
    except ValueError:
        return None


def _brief_roles_by_dday(planning_brief: Any) -> dict[int, list[dict[str, Any]]]:
    by_dday: dict[int, list[dict[str, Any]]] = {}
    if not isinstance(planning_brief, dict):
        return by_dday
    role_map = planning_brief.get("weekly_role_map")
    if isinstance(role_map, dict):
        for week in role_map.get("weeks") or []:
            if not isinstance(week, dict):
                continue
            for role in week.get("session_roles") or []:
                if isinstance(role, dict) and isinstance(d_day := role_d_day(week, role), int):
                    by_dday.setdefault(d_day, []).append(role)
    for role in planning_brief.get("late_fight_session_sequence") or []:
        if isinstance(role, dict) and isinstance(d_day := role_d_day({}, role), int):
            if role not in by_dday.get(d_day, []):
                by_dday.setdefault(d_day, []).append(role)
    return by_dday


def _role_matcher(
    roles: list[dict[str, Any]],
) -> Callable[[dict[str, Any]], Mapping[str, Any] | None]:
    """Match a card session to the one planner role it represents, if any.

    Exact identity only: the ``(role_key, session_index)`` a deterministic
    session id encodes, else the role's athlete-facing label equal to the
    session title and held by exactly one role that day.
    """

    def match(session: dict[str, Any]) -> Mapping[str, Any] | None:
        session_id = _clean(session.get("session_id"))
        found = _DETERMINISTIC_SESSION_ID_RE.match(session_id)
        if found:
            for role in roles:
                index = role.get("session_index")
                if _clean(role.get("role_key")) == found.group("role_key") and str(
                    index if isinstance(index, int) else 0
                ) == found.group("index"):
                    return role
        title = _normalise_label(session.get("title"))
        if not title:
            return None
        labelled = [
            role for role in roles if _normalise_label(role.get("athlete_facing_label")) == title
        ]
        return labelled[0] if len(labelled) == 1 else None

    return match


def sequence_structured_plan(structured_plan: Any, planning_brief: Any = None) -> Any:
    """Put every day's sessions, and every session's blocks, in execution order.

    Run after the card's membership is final (converter output, deterministic
    fallback, spine restore and locked merge all applied). Sets each session's
    ``execution_order`` (1-based within its day) and, where blocks already carry
    ``order_index``, renumbers it to the new order. Nothing is added, removed or
    moved across days. Mutates in place and returns ``structured_plan``.

    Never raises: ordering is presentation of an already-valid card, so an
    unexpected shape leaves the card as it was rather than losing it.
    """
    if not isinstance(structured_plan, dict):
        return structured_plan
    try:
        _sequence_plan_days(structured_plan, planning_brief)
    except Exception:  # noqa: BLE001 - a card must never be lost to ordering
        logger.exception("[session_sequencing] structured plan left in source order")
    return structured_plan


def _sequence_plan_days(structured_plan: dict[str, Any], planning_brief: Any) -> None:
    roles_by_dday = _brief_roles_by_dday(planning_brief)
    for week in structured_plan.get("weeks") or []:
        if not isinstance(week, dict):
            continue
        for day in week.get("days") or []:
            if not isinstance(day, dict) or not isinstance(day.get("sessions"), list):
                continue
            d_day = _countdown_dday(day.get("countdown_label"))
            matcher = _role_matcher(roles_by_dday.get(d_day, [])) if d_day is not None else None
            non_sessions = [item for item in day["sessions"] if not isinstance(item, dict)]
            ordered = sequence_day_sessions(day["sessions"], matcher)
            for position, session in enumerate(ordered, start=1):
                session["execution_order"] = position
                blocks = session.get("blocks")
                if isinstance(blocks, list) and blocks:
                    _sequence_blocks_in_place(session, blocks)
            day["sessions"] = [*ordered, *non_sessions]


def _sequence_blocks_in_place(session: dict[str, Any], blocks: list[Any]) -> None:
    others = [block for block in blocks if not isinstance(block, dict)]
    ordered = sequence_session_blocks(blocks)
    if any(block.get("order_index") is not None for block in ordered):
        for index, block in enumerate(ordered):
            block["order_index"] = index
    session["blocks"] = [*ordered, *others]


__all__ = [
    "ROLE_SEQUENCE",
    "SequenceIntent",
    "SequenceSlot",
    "block_sequence_slot",
    "in_stamped_execution_order",
    "is_support_session",
    "parse_sequence_override",
    "role_sequence_slot",
    "sequence_day_roles",
    "sequence_day_sessions",
    "sequence_items",
    "sequence_session_blocks",
    "sequence_structured_plan",
    "session_role_key",
    "session_sequence_slot",
    "stamp_role_execution_order",
]
