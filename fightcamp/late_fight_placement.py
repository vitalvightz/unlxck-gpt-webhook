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

def _target_offset_for_cost(slots: list[str], cost: str, assigned: list[int]) -> int:
    """Return a taper-aware target offset for a role cost bucket."""
    offsets = sorted((countdown_offset(lbl) or 0) for lbl in slots)
    if not offsets:
        return 0

    # Cost-biased quantiles instead of extreme-first picks:
    # high -> early-ish, medium -> middle, low -> late-ish.
    if cost == "high" and not assigned:
        return offsets[-1]

    quantile_index = {
        "high": 0.70,
        "medium": 0.55,
        "low": 0.25,
    }.get(cost, 0.55)
    idx = round((len(offsets) - 1) * quantile_index)
    return offsets[max(0, min(idx, len(offsets) - 1))]


def _pick_slot(slots: list[str], assigned: list[int], *, cost: str) -> str | None:
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

    target = _target_offset_for_cost(slots, cost, assigned)
    best_key: tuple[int, int, int, int] | None = None
    best_label: str | None = None

    for lbl in slots:
        off = countdown_offset(lbl) or 0
        gap = _min_gap(off, assigned)

        # Hard preference: avoid consecutive active days whenever possible.
        spacing_penalty = 0 if gap >= 2 else (1 if gap == 1 else 3)
        target_distance = abs(off - target)

        # Cost-direction tie-breaker preserves shape without forcing extremes.
        if cost == "high":
            direction_penalty = -off
        elif cost == "low":
            direction_penalty = off
        else:
            direction_penalty = abs(off - target)

        key = (spacing_penalty, target_distance, direction_penalty, -off)
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
    assigned: list[int] = [
        countdown_offset(str(r.get("countdown_label") or ""))
        for r in locked
        if countdown_offset(str(r.get("countdown_label") or "")) is not None
    ]

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
        lbl = _pick_slot(pool, assigned, cost=cost)
        if lbl:
            unlocked_pairs.append((role, lbl))
            pool.remove(lbl)
            off = countdown_offset(lbl)
            if off is not None:
                assigned.append(off)

    # ── 6. Place low cost roles ──────────────────────────────────────────────
    for role in low_cost:
        if not pool:
            break
        lbl = _pick_slot(pool, assigned, cost="low")
        if lbl:
            unlocked_pairs.append((role, lbl))
            pool.remove(lbl)
            off = countdown_offset(lbl)
            if off is not None:
                assigned.append(off)

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
