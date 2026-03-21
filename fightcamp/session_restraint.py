from __future__ import annotations

from typing import Any

# Match the score_exercise noise ceiling (uniform +/-0.15) so Rule 2 only treats
# candidates inside the scorer's normal jitter band as near-equal.
NEAR_EQUAL_SCORE_BAND = 0.15


def _candidate_name(candidate: dict[str, Any]) -> str:
    return str(candidate.get("name") or "")


def _candidate_score(candidate: dict[str, Any]) -> float:
    return float(candidate.get("score", 0.0))


def _candidate_fatigue_cost(candidate: dict[str, Any]) -> float:
    return float(candidate.get("fatigue_cost", 0.0))


def sort_weighted_candidates(
    weighted_candidates: list[dict[str, Any]],
    *,
    near_equal_score_band: float = NEAR_EQUAL_SCORE_BAND,
) -> list[dict[str, Any]]:
    """Return a deterministic Rule 2 ordering for weighted session candidates.

    Candidates are first globally sorted by score descending with a stable
    alphabetical name fallback. Contiguous near-equal groups are then formed from the
    current group leader using ``near_equal_score_band`` as a score floor. Items
    inside each leader-anchored group are locally reordered by lower fatigue cost,
    then name, so lower-fatigue items may intentionally rise above slightly
    higher-scored items within the same group. Cross-group order remains score-driven,
    and the grouping pass avoids non-transitive pairwise comparison logic.
    """
    if len(weighted_candidates) < 2:
        return list(weighted_candidates)

    score_sorted = sorted(
        weighted_candidates,
        key=lambda candidate: (-_candidate_score(candidate), _candidate_name(candidate)),
    )

    ordered: list[dict[str, Any]] = []
    group_start = 0
    while group_start < len(score_sorted):
        group_end = group_start + 1
        group_floor = _candidate_score(score_sorted[group_start]) - near_equal_score_band
        while group_end < len(score_sorted) and _candidate_score(score_sorted[group_end]) >= group_floor:
            group_end += 1

        group = score_sorted[group_start:group_end]
        ordered.extend(
            sorted(group, key=lambda candidate: (_candidate_fatigue_cost(candidate), _candidate_name(candidate)))
        )
        group_start = group_end

    return ordered
