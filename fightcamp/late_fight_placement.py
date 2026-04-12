"""
late_fight_placement.py  —  Layer 3 of the late-fight countdown architecture.

Three-layer design
──────────────────
  Layer 1  Permission layer   what session types are legal
           stage2_payload_late_fight._late_fight_permissions / _late_fight_forbidden_blocks

  Layer 2  Budget layer        how many roles exist and which ones
           stage2_payload_late_fight._late_fight_session_roles

  Layer 3  Placement layer     where each role goes in the countdown  ← THIS MODULE

The placement engine accepts an already-built, already-sized role list and assigns
each role to the best available countdown label (D-N … D-1) using:

  • locked-day constraints   declared hard sparring days are never moved
  • role cost class          high-cost → earlier (further from fight)
                             low-cost  → later  (closer to fight, but not D-0)
  • spacing preference       avoid consecutive active days; maximise gaps
  • taper shape              stress first, freshness last

This module knows nothing about phase doctrine, session counts, or athlete
profiles.  Its only inputs are:

  roles               the final role list from the budget layer
  days_until_fight    integer countdown anchor
  countdown_weekday_map  D-N → weekday resolved map (from stage2_payload_late_fight)
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Cost classification
# ---------------------------------------------------------------------------

_ANCHOR_COST: dict[str, str] = {
    "highest_neural_day":     "high",
    "highest_glycolytic_day": "high",   # glycolytic roles are always locked; included for completeness
    "support_day":            "medium",
    "lowest_load_day":        "low",
}

_COST_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
_PRESERVED_ROLE_METADATA_KEYS: tuple[str, ...] = (
    "declared_day_locked",
    "scheduled_day_hint",
    "locked_day",
    "day_assignment_reason",
    "countdown_offset",
    "downgraded_from_hard_sparring",
    "governance",
    "coach_notes",
)


def role_cost(role: dict[str, Any]) -> str:
    """Return 'high', 'medium', or 'low' for a role dict."""
    anchor = str(role.get("anchor") or "").strip()
    return _ANCHOR_COST.get(anchor, "medium")


def _is_preservable_metadata(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def countdown_offset(label: str) -> int | None:
    """Parse 'D-N' → N.  Returns None on bad input."""
    norm = str(label or "").strip().upper()
    if not norm.startswith("D-"):
        return None
    try:
        return int(norm[2:])
    except ValueError:
        return None


def _countdown_display_label(label: str, weekday: str | None) -> str:
    """Render labels in exact athlete-facing form: ``D-N (Weekday)``."""
    if not weekday:
        return label
    return f"{label} ({str(weekday).strip().title()})"


def _min_gap(candidate: int, assigned: list[int]) -> int:
    """Minimum absolute distance from candidate offset to any assigned offset."""
    if not assigned:
        return 999
    return min(abs(candidate - a) for a in assigned)


# ---------------------------------------------------------------------------
# Slot-selection strategies
# ---------------------------------------------------------------------------

_ROLE_TARGET_QUANTILE: dict[str, float] = {
    "strength_touch_day": 0.78,
    "neural_primer_day": 0.85,
    "hard_sparring_day": 0.80,
    "light_fight_pace_touch_day": 0.48,
    "alactic_sharpness_day": 0.42,
    "fight_week_freshness_day": 0.12,
}

_MEANINGFUL_STRESS_ROLE_KEYS: set[str] = {
    "hard_sparring_day",
    "strength_touch_day",
    "neural_primer_day",
    "light_fight_pace_touch_day",
    "alactic_sharpness_day",
}


def _normalize_flag_set(values: Any) -> set[str]:
    if isinstance(values, (list, tuple, set)):
        return {str(v).strip().lower() for v in values if str(v).strip()}
    return set()


def _readiness_severity(context: dict[str, Any]) -> int:
    fatigue = str(context.get("fatigue") or "").strip().lower()
    flags = _normalize_flag_set(context.get("readiness_flags"))
    fatigue_score = 2 if fatigue == "high" else (1 if fatigue == "moderate" else 0)
    injury_flag = any(tok in flag for flag in flags for tok in ("injury", "pain", "flare", "acute"))
    return min(3, fatigue_score + (1 if injury_flag else 0))


def _role_target_quantile(role: dict[str, Any], cost: str) -> float:
    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key in _ROLE_TARGET_QUANTILE:
        return _ROLE_TARGET_QUANTILE[role_key]
    return {
        "high": 0.70,
        "medium": 0.55,
        "low": 0.25,
    }.get(cost, 0.55)


def _target_offset_for_role(
    slots: list[str],
    role: dict[str, Any],
    cost: str,
    assigned_offsets: list[int],
    context: dict[str, Any],
) -> int:
    """Return a taper-aware target offset for the exact role and context."""
    offsets = sorted((countdown_offset(lbl) or 0) for lbl in slots)
    if not offsets:
        return 0

    # High-cost first anchor can still use the earliest slot when useful.
    if cost == "high" and not assigned_offsets:
        return offsets[-1]

    role_key = str(role.get("role_key") or "").strip().lower()
    if role.get("downgraded_from_hard_sparring"):
        declared_off = role.get("countdown_offset")
        if isinstance(declared_off, int) and declared_off in offsets:
            return declared_off
    if role_key in {"technical_touch_day", "light_fight_pace_touch_day"}:
        declared_tech = {int(v) for v in context.get("declared_technical_offsets", []) if isinstance(v, int)}
        matching = [off for off in offsets if off in declared_tech]
        if matching:
            return max(matching)

    quantile_index = _role_target_quantile(role, cost)
    idx = round((len(offsets) - 1) * float(quantile_index))
    return offsets[max(0, min(idx, len(offsets) - 1))]


def _collision_penalty(off: int, declared_hard: set[int]) -> int:
    if not declared_hard:
        return 0
    penalty = 0
    if off in declared_hard:
        penalty += 4
    if (off - 1) in declared_hard:
        penalty += 2
    if (off + 1) in declared_hard:
        penalty += 2
    if (off - 1) in declared_hard and (off + 1) in declared_hard:
        penalty += 3
    return penalty


def _pick_slot(
    slots: list[str],
    assigned_offsets: list[int],
    assigned_stress_offsets: list[int],
    *,
    role: dict[str, Any],
    cost: str,
    context: dict[str, Any],
) -> str | None:
    """
    Pick the best slot using taper-aware target proximity plus spacing quality.

    This avoids blanket early-slot bias while still preserving taper intent:
      • high   tends earlier
      • medium tends central/early
      • low    tends later

    Same-day (D-N) placement is allowed, but only when it wins this score.
    """
    if not slots:
        return None

    if role.get("downgraded_from_hard_sparring"):
        declared_off = role.get("countdown_offset")
        if isinstance(declared_off, int):
            declared_label = f"D-{declared_off}"
            if declared_label in slots:
                return declared_label

    target = _target_offset_for_role(slots, role, cost, assigned_offsets, context)
    role_key = str(role.get("role_key") or "").strip().lower()
    today_offset = int(context.get("today_offset") or 0)
    declared_hard = {int(v) for v in context.get("declared_hard_spar_offsets", []) if isinstance(v, int)}
    readiness = _readiness_severity(context)
    is_meaningful_stress = role_key in _MEANINGFUL_STRESS_ROLE_KEYS

    best_key: tuple[int, int, int, int, int, int, int] | None = None
    best_label: str | None = None

    slot_offsets = [(lbl, countdown_offset(lbl) or 0) for lbl in slots]

    def _base_score_components(off: int) -> tuple[int, int, int, int, int]:
        gap = _min_gap(off, assigned_offsets)

        # Hard preference: avoid consecutive active days whenever possible.
        spacing_penalty = 0 if gap >= 2 else (1 if gap == 1 else 3)
        if role_key == "fight_week_freshness_day":
            spacing_penalty = 0 if gap >= 1 else 2
        if readiness >= 2 and gap < 2:
            spacing_penalty += readiness

        stress_penalty = 0
        if is_meaningful_stress and assigned_stress_offsets:
            stress_gap = _min_gap(off, assigned_stress_offsets)
            stress_penalty = 0 if stress_gap >= 2 else (2 if stress_gap == 1 else 4)

        collision_penalty = _collision_penalty(off, declared_hard)
        readiness_penalty = readiness if (readiness > 0 and cost in {"medium", "low"} and gap < 3) else 0
        target_distance = abs(off - target)
        return spacing_penalty, stress_penalty, collision_penalty, readiness_penalty, target_distance

    for lbl in slots:
        off = countdown_offset(lbl) or 0
        spacing_penalty, stress_penalty, collision_penalty, readiness_penalty, target_distance = _base_score_components(off)

        same_day_penalty = 0
        if today_offset and off == today_offset and cost in {"medium", "low"}:
            non_today_base = [
                _base_score_components(o)
                for _, o in slot_offsets
                if o != today_offset
            ]
            if non_today_base:
                current_base = _base_score_components(off)
                if min(non_today_base) <= current_base:
                    same_day_penalty = 1 + readiness

        # Cost-direction tie-breaker preserves shape without forcing extremes.
        if cost == "high":
            direction_penalty = -off
        elif cost == "low":
            direction_penalty = off
        else:
            direction_penalty = abs(off - target)

        key = (
            spacing_penalty,
            stress_penalty,
            collision_penalty,
            same_day_penalty,
            readiness_penalty,
            target_distance,
            direction_penalty,
        )
        if best_key is None or key < best_key:
            best_key = key
            best_label = lbl

    return best_label


# ---------------------------------------------------------------------------
# Core placement engine
# ---------------------------------------------------------------------------

def place_roles_in_countdown(
    *,
    roles: list[dict[str, Any]],
    days_until_fight: int,
    countdown_weekday_map: dict[str, str],
    placement_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Assign each role to a countdown label using cost-aware, spacing-maximising
    placement.  Returns the sequence sorted earliest-first (highest D-offset
    first, i.e. furthest from the fight first).

    Locked roles (declared_day_locked=True with a countdown_label set by the
    budget layer) keep their fixed label unconditionally.

    Unlocked roles are placed into the remaining legal labels (D-N to D-1,
    D-0 is always blocked as fight day):
      • high / medium cost  → placed in earlier slots (higher D-offset)
                               with gap-maximising spacing
      • low cost            → placed in later slots  (lower D-offset,
                               closer to fight) with at least 1-day gap
    """

    # ── 1. Separate locked from unlocked ────────────────────────────────────
    locked: list[dict[str, Any]] = []
    unlocked: list[dict[str, Any]] = []

    for role in roles:
        label = str(role.get("countdown_label") or "").strip()
        if role.get("declared_day_locked") and label.startswith("D-"):
            locked.append(role)
        else:
            unlocked.append(role)

    locked_labels: set[str] = {
        str(r.get("countdown_label") or "").strip()
        for r in locked
    }

    # ── 2. Build available slot pool (D-N to D-1; D-0 always blocked) ──────
    all_labels = [f"D-{off}" for off in range(days_until_fight, 0, -1)]
    available: list[str] = [lbl for lbl in all_labels if lbl not in locked_labels]

    # ── 3. Seed assigned offsets from locked roles ───────────────────────────
    assigned_offsets: list[int] = [
        countdown_offset(str(r.get("countdown_label") or ""))
        for r in locked
        if countdown_offset(str(r.get("countdown_label") or "")) is not None
    ]
    assigned_stress_offsets: list[int] = [
        off for r in locked
        if str(r.get("role_key") or "").strip().lower() in _MEANINGFUL_STRESS_ROLE_KEYS
        for off in [countdown_offset(str(r.get("countdown_label") or ""))]
        if off is not None
    ]
    context = dict(placement_context or {})

    # ── 4. Split unlocked by cost bucket ────────────────────────────────────
    #      Sort high/medium by cost rank so high comes before medium
    high_medium = sorted(
        [r for r in unlocked if role_cost(r) in {"high", "medium"}],
        key=lambda r: _COST_RANK.get(role_cost(r), 1),
    )
    low_cost = [r for r in unlocked if role_cost(r) == "low"]

    unlocked_pairs: list[tuple[dict[str, Any], str]] = []
    pool = list(available)  # mutable working pool

    # ── 5. Place high / medium cost roles ────────────────────────────────────
    for role in high_medium:
        if not pool:
            break
        cost = role_cost(role)
        lbl = _pick_slot(
            pool,
            assigned_offsets,
            assigned_stress_offsets,
            role=role,
            cost=cost,
            context=context,
        )
        if lbl:
            unlocked_pairs.append((role, lbl))
            pool.remove(lbl)
            off = countdown_offset(lbl)
            if off is not None:
                assigned_offsets.append(off)
                if str(role.get("role_key") or "").strip().lower() in _MEANINGFUL_STRESS_ROLE_KEYS:
                    assigned_stress_offsets.append(off)

    # ── 6. Place low cost roles ──────────────────────────────────────────────
    for role in low_cost:
        if not pool:
            break
        lbl = _pick_slot(
            pool,
            assigned_offsets,
            assigned_stress_offsets,
            role=role,
            cost="low",
            context=context,
        )
        if lbl:
            unlocked_pairs.append((role, lbl))
            pool.remove(lbl)
            off = countdown_offset(lbl)
            if off is not None:
                assigned_offsets.append(off)
                if str(role.get("role_key") or "").strip().lower() in _MEANINGFUL_STRESS_ROLE_KEYS:
                    assigned_stress_offsets.append(off)

    # ── 7. Combine and sort: earliest-first (highest D-offset first) ─────────
    locked_pairs: list[tuple[dict[str, Any], str]] = [
        (r, str(r.get("countdown_label") or "").strip())
        for r in locked
    ]
    all_pairs = locked_pairs + unlocked_pairs
    all_pairs.sort(key=lambda pair: -(countdown_offset(pair[1]) or 0))

    # ── 8. Build result entries ──────────────────────────────────────────────
    locked_role_ids = {id(r) for r in locked}
    result: list[dict[str, Any]] = []

    for idx, (role, lbl) in enumerate(all_pairs, start=1):
        weekday = countdown_weekday_map.get(lbl)
        is_locked = id(role) in locked_role_ids

        entry: dict[str, Any] = {
            "session_index": idx,
            "category": role.get("category"),
            "role_key": role.get("role_key"),
            "preferred_pool": role.get("preferred_pool"),
            "preferred_system": role.get("preferred_system"),
            "selection_rule": role.get("selection_rule"),
            "placement_rule": role.get("placement_rule"),
            "anchor": role.get("anchor"),
            "countdown_label": lbl,
            "countdown_display_label": _countdown_display_label(lbl, weekday),
            "placement_basis": "locked" if is_locked else role_cost(role),
        }
        if weekday:
            entry["real_weekday"] = weekday
        # Preserve meaningful role semantics from the budget layer.
        for key in _PRESERVED_ROLE_METADATA_KEYS:
            value = role.get(key)
            if _is_preservable_metadata(value):
                entry[key] = value

        result.append(entry)

    return result
