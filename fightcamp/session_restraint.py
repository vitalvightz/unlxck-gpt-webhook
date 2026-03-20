"""Session restraint pass.

Applies three small post-selection rules after the main planner has assembled
strength exercises, without touching scoring or planner architecture:

1. context_density_cap  — tighter per-session exercise limit in taper /
                          short-notice / high-fatigue contexts.
2. tie_break_sort       — near-equal score band comparator: within the band,
                          resolve in favour of lower recovery cost; outside it,
                          higher score wins as normal.
3. pruning_pass         — in restrictive contexts, removes the lowest-necessity
                          non-anchor item only when the session retains both
                          base-category coverage *and* quality/support-function
                          coverage already recognised by the planner.
"""

from __future__ import annotations

import functools

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
# Rule 2 — Near-equal score band comparator
# ---------------------------------------------------------------------------

# Scores within this range are treated as genuinely near-equal.  This equals
# the single-sided noise magnitude used by the strength scorer (±0.15), so any
# two scores within the band may differ only because of randomness, not because
# one exercise is meaningfully better.
NEAR_EQUAL_SCORE_BAND: float = 0.15


def _compare_weighted(
    a: tuple[dict, float, dict],
    b: tuple[dict, float, dict],
) -> int:
    """Three-level comparator for scored exercise triples.

    Outside the near-equal band : higher score wins.
    Inside  the near-equal band : lower fatigue cost wins.
    Equal fatigue cost           : alphabetical name (stable fallback).
    """
    score_a, score_b = a[1], b[1]
    if abs(score_a - score_b) > NEAR_EQUAL_SCORE_BAND:
        # Scores are genuinely different — rank by score only.
        return -1 if score_a > score_b else 1
    # Near-equal: prefer the less costly option.
    cost_a, cost_b = fatigue_cost(a[0]), fatigue_cost(b[0])
    if cost_a != cost_b:
        return -1 if cost_a < cost_b else 1
    # Same cost: stable alphabetical fallback.
    name_a = a[0].get("name", "")
    name_b = b[0].get("name", "")
    return -1 if name_a < name_b else (1 if name_a > name_b else 0)


def tie_break_sort(
    weighted: list[tuple[dict, float, dict]],
) -> list[tuple[dict, float, dict]]:
    """Sort scored exercise triples using the near-equal band comparator.

    Scores separated by more than *NEAR_EQUAL_SCORE_BAND* are ordered purely
    by score.  Scores within the band are resolved in favour of lower recovery
    cost (fatigue_cost), with a stable alphabetical fallback.

    This is a real near-equal comparator, not just a secondary sort key, so
    borderline candidates with slightly different scores are also influenced by
    recovery cost — not only exact ties.
    """
    if not weighted:
        return weighted
    weighted.sort(key=functools.cmp_to_key(_compare_weighted))
    return weighted


# ---------------------------------------------------------------------------
# Rule 3 — Final pruning pass
# ---------------------------------------------------------------------------


def _restrictive_context(phase: str, fatigue: str, days_until_fight: int | None) -> bool:
    """Return True when the session context warrants aggressive pruning."""
    phase = phase.upper()
    return phase == "TAPER" or fatigue == "high" or _is_short_notice(days_until_fight)


def _describe_context(phase: str, fatigue: str, days_until_fight: int | None) -> str:
    """Return a short human-readable description of why the context is restrictive."""
    reasons = []
    if phase.upper() == "TAPER":
        reasons.append("TAPER phase")
    if fatigue == "high":
        reasons.append("high fatigue")
    if _is_short_notice(days_until_fight):
        reasons.append(f"short notice ({days_until_fight}d until fight)")
    return ", ".join(reasons) if reasons else "restrictive context"


def pruning_pass(
    exercises: list[dict],
    *,
    phase: str,
    fatigue: str,
    days_until_fight: int | None,
    score_lookup: dict[str, float],
) -> tuple[list[dict], dict | None, str]:
    """Remove the lowest-necessity item in restrictive contexts.

    Eligible for removal: a non-anchor-capable item whose base categories *and*
    quality/support function (``quality_class``) are each already covered by at
    least one other item in the list.

    Safety checks (all must pass before any removal):
    - The remaining list retains at least one anchor-capable item.
    - No base-category (``lower_body_loaded``, ``upper_body_push_pull``,
      ``unilateral``) loses its sole representative.
    - No quality/support function recognised by the planner (``quality_class``)
      loses its sole representative — this preserves rehab-support items,
      unique isometric anchors, etc.

    Returns ``(updated_exercises, removed_item_or_None, safety_note)``.
    *safety_note* is a human-readable string explaining why removal was (or was
    not) carried out; it is always non-empty so callers can log it directly.
    """
    if not _restrictive_context(phase, fatigue, days_until_fight):
        return exercises, None, "non-restrictive context — no pruning"

    # Need at least 3 items before pruning makes sense.
    if len(exercises) <= 2:
        return exercises, None, "session too small to prune (≤2 items)"

    # Count how many items cover each base category and quality class.
    category_coverage: dict[str, int] = {}
    quality_coverage: dict[str, int] = {}
    for ex in exercises:
        profile = classify_strength_item(ex)
        for cat in profile.get("base_categories", []):
            category_coverage[cat] = category_coverage.get(cat, 0) + 1
        qc = profile["quality_class"]
        quality_coverage[qc] = quality_coverage.get(qc, 0) + 1

    # Build the candidate-removal list: non-anchor items that are not the sole
    # representative of any base category *or* quality class.
    candidates: list[tuple[int, dict, float]] = []
    for idx, ex in enumerate(exercises):
        profile = classify_strength_item(ex)
        if profile["anchor_capable"]:
            continue
        # Sole representative of any base category?
        if any(
            category_coverage.get(cat, 0) <= 1
            for cat in profile.get("base_categories", [])
        ):
            continue
        # Sole representative of its quality/support function?
        if quality_coverage.get(profile["quality_class"], 0) <= 1:
            continue
        score = score_lookup.get(ex.get("name", ""), 0.0)
        candidates.append((idx, ex, score))

    if not candidates:
        return exercises, None, "no removable candidate (all items are sole representatives)"

    # Choose the lowest-scoring candidate as the target for removal.
    worst_idx, worst_ex, _ = min(candidates, key=lambda c: c[2])

    # Verify the remaining list still has an anchor.
    remaining = [ex for i, ex in enumerate(exercises) if i != worst_idx]
    if not any(classify_strength_item(ex)["anchor_capable"] for ex in remaining):
        return exercises, None, "removal would leave no anchor — skipped"

    # Build the safety note explaining why removal was safe.
    context_desc = _describe_context(phase, fatigue, days_until_fight)
    anchor_names = [
        ex.get("name", "?")
        for ex in remaining
        if classify_strength_item(ex)["anchor_capable"]
    ]
    worst_profile = classify_strength_item(worst_ex)
    safety_note = (
        f"context={context_desc}; "
        f"removed '{worst_ex.get('name', '?')}' (quality_class={worst_profile['quality_class']}); "
        f"anchor retained ({', '.join(anchor_names)}); "
        f"base-category coverage preserved; "
        f"quality-class '{worst_profile['quality_class']}' has ≥2 representatives"
    )

    return remaining, worst_ex, safety_note
