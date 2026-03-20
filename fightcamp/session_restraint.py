"""Session restraint pass.

Applies three small post-selection rules after the main planner has assembled
strength exercises, without touching scoring or planner architecture:

1. context_density_cap  — tighter per-session exercise limit in taper /
                          short-notice / high-fatigue contexts.
2. tie_break_sort       — deterministic secondary sort by fatigue cost when
                          scores are near-equal.
3. pruning_pass         — in restrictive contexts, removes the lowest-necessity
                          non-anchor item if the session retains its purpose.
"""

from __future__ import annotations

from .strength_session_quality import classify_strength_item

# ---------------------------------------------------------------------------
# Fatigue-cost estimation from tags
# ---------------------------------------------------------------------------

# Tags that indicate high recovery cost (soreness risk, neural demand, or
# coordination complexity).
_HIGH_COST_TAGS: frozenset[str] = frozenset(
    {
        "mech_cns_high",
        "mech_systemic_fatigue",
        "high_cns",
        "eccentric",
        "mech_landing_impact",
        "mech_ballistic",
        "plyometric",
        "rate_of_force",
        "mech_max_velocity",
        "triphasic",
    }
)

# Tags that indicate low recovery cost (joint-friendly, rehab-level load).
_LOW_COST_TAGS: frozenset[str] = frozenset(
    {
        "isometric",
        "rehab_friendly",
        "stability",
        "core",
        "zero_impact",
        "cns_freshness",
        "mobility",
        "anti_rotation",
    }
)


def fatigue_cost(exercise: dict) -> int:
    """Return an integer recovery-cost estimate for a single exercise.

    Higher values = more demanding (more soreness, higher neural complexity,
    higher aggravation risk).  Used as a deterministic tie-breaker when two
    candidates score within the near-equal margin.
    """
    tags = set(exercise.get("tags") or [])
    cost = 0
    for t in tags:
        if t in _HIGH_COST_TAGS:
            cost += 2
    for t in tags:
        if t in _LOW_COST_TAGS:
            cost -= 1
    return cost


# ---------------------------------------------------------------------------
# Rule 1 — Context-sensitive density cap
# ---------------------------------------------------------------------------

# Base per-session exercise maximums (matches STRENGTH_PER_DAY in config).
_BASE_CAP_PER_SESSION: dict[str, int] = {"GPP": 7, "SPP": 6, "TAPER": 4}

# Fatigue-driven per-session reduction (subtracted from the base cap).
_FATIGUE_REDUCTION: dict[str, int] = {"high": 2, "moderate": 1, "low": 0}

# Days-until-fight threshold that defines "short notice".
SHORT_NOTICE_DAYS = 14


def _is_short_notice(days_until_fight: int | None) -> bool:
    return isinstance(days_until_fight, int) and 0 <= days_until_fight <= SHORT_NOTICE_DAYS


def context_density_cap(
    *,
    phase: str,
    fatigue: str,
    days_until_fight: int | None,
    num_sessions: int,
) -> int:
    """Return the maximum total exercises to include across all strength sessions.

    The per-session limit tightens in taper, short-notice, or high-fatigue
    contexts and is multiplied by *num_sessions* for the full-week total.
    """
    phase = phase.upper()
    per_session = _BASE_CAP_PER_SESSION.get(phase, 6)
    per_session -= _FATIGUE_REDUCTION.get(fatigue, 0)
    if _is_short_notice(days_until_fight) and phase != "GPP":
        per_session -= 1
    per_session = max(2, per_session)
    return per_session * max(1, num_sessions)


# ---------------------------------------------------------------------------
# Rule 2 — Deterministic tie-breaking sort
# ---------------------------------------------------------------------------


def tie_break_sort(
    weighted: list[tuple[dict, float, dict]],
) -> list[tuple[dict, float, dict]]:
    """Sort scored exercise triples deterministically.

    Primary key : score (descending).
    Secondary key: fatigue_cost (ascending) — resolves near-equal scores in
                   favour of lower recovery cost.
    Tertiary key : exercise name (ascending) — ensures identical-score items
                   always land in the same order regardless of dict insertion
                   order or bank loading sequence.

    This does not change which exercises are *eligible* — it only resolves
    ordering for near-equal candidates so the final top-N slice is consistent
    across identical inputs.
    """
    if not weighted:
        return weighted
    weighted.sort(
        key=lambda item: (
            -item[1],
            fatigue_cost(item[0]),
            item[0].get("name", ""),
        )
    )
    return weighted


# ---------------------------------------------------------------------------
# Rule 3 — Final pruning pass
# ---------------------------------------------------------------------------


def _restrictive_context(phase: str, fatigue: str, days_until_fight: int | None) -> bool:
    """Return True when the session context warrants aggressive pruning."""
    phase = phase.upper()
    return phase == "TAPER" or fatigue == "high" or _is_short_notice(days_until_fight)


def pruning_pass(
    exercises: list[dict],
    *,
    phase: str,
    fatigue: str,
    days_until_fight: int | None,
    score_lookup: dict[str, float],
) -> tuple[list[dict], dict | None]:
    """Remove the lowest-necessity item in restrictive contexts.

    Eligible for removal: a non-anchor-capable item whose base categories are
    already covered by at least one other item in the list.

    Safety check: the remaining list must still contain at least one
    anchor-capable item.  Anchor items and sole base-category representatives
    are never removed.

    Returns ``(updated_exercises, removed_item_or_None)``.  When nothing was
    removed *removed_item_or_None* is ``None``.
    """
    if not _restrictive_context(phase, fatigue, days_until_fight):
        return exercises, None

    # Need at least 3 items before pruning makes sense.
    if len(exercises) <= 2:
        return exercises, None

    # Count how many items cover each base category.
    category_coverage: dict[str, int] = {}
    for ex in exercises:
        profile = classify_strength_item(ex)
        for cat in profile.get("base_categories", []):
            category_coverage[cat] = category_coverage.get(cat, 0) + 1

    # Build the candidate-removal list: support-only items that are not the
    # sole representative of any base category.
    candidates: list[tuple[int, dict, float]] = []
    for idx, ex in enumerate(exercises):
        profile = classify_strength_item(ex)
        if profile["anchor_capable"]:
            continue
        sole = any(
            category_coverage.get(cat, 0) <= 1
            for cat in profile.get("base_categories", [])
        )
        if sole:
            continue
        score = score_lookup.get(ex.get("name", ""), 0.0)
        candidates.append((idx, ex, score))

    if not candidates:
        return exercises, None

    # Choose the lowest-scoring candidate as the target for removal.
    worst_idx, worst_ex, _ = min(candidates, key=lambda c: c[2])

    # Verify the remaining list still has an anchor.
    remaining = [ex for i, ex in enumerate(exercises) if i != worst_idx]
    if not any(classify_strength_item(ex)["anchor_capable"] for ex in remaining):
        return exercises, None

    return remaining, worst_ex
