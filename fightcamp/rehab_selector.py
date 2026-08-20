"""Deterministic, stage-aware rehabilitation drill selection.

This module selects bank content only.  It deliberately knows nothing about
session cards or rehabilitation-stage progression.  Callers must pass the
already-resolved live stage; shadow LOAD eligibility is not an input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


SELECTOR_VERSION = "1"
CANONICAL_STAGES = ("calm", "restore", "load", "dynamic", "return")
_STAGE_INDEX = {stage: index for index, stage in enumerate(CANONICAL_STAGES)}
_LIVE_STAGES = frozenset({"calm", "restore"})
_NEGATIVE_RESPONSE_VALUES = frozenset({"worse"})


@dataclass(frozen=True)
class RejectedCandidate:
    drill_id: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RankingFactor:
    factor: str
    result: str


@dataclass(frozen=True)
class RehabSelectionResult:
    injury_id: str
    injury_episode_id: str
    rehab_stage: str
    selected_drill_id: str | None
    selection_reason: str
    candidate_count: int
    eligible_candidate_count: int
    ranking_factors: tuple[RankingFactor, ...] = ()
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    selector_version: str = SELECTOR_VERSION
    selected_drill: Mapping[str, object] | None = field(default=None, repr=False, compare=False)


def _clean(value: object) -> str:
    return str(value or "").strip().lower()


def _values(value: object) -> set[str]:
    if isinstance(value, str):
        return {_clean(value)} if _clean(value) else set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {_clean(item) for item in value if _clean(item)}
    return set()


def _negative_drill_ids(
    exposures: Iterable[Mapping[str, object]], injury: Mapping[str, object]
) -> set[str]:
    """Return negative drill ids attributable to this exact injury episode."""
    wanted = (
        _clean(injury.get("athlete_id")),
        _clean(injury.get("id")),
        _clean(injury.get("episode_id")),
    )
    negative: set[str] = set()
    for exposure in exposures:
        event = exposure.get("event_json") if isinstance(exposure.get("event_json"), Mapping) else exposure
        assert isinstance(event, Mapping)
        provenance = event.get("provenance") if isinstance(event.get("provenance"), Mapping) else {}
        identity = (
            _clean(event.get("athlete_id") or provenance.get("athlete_id")),
            _clean(event.get("injury_id")),
            _clean(event.get("injury_episode_id")),
        )
        # Athlete identity is required only when supplied on the injury.  The
        # injury and episode identities are always required.
        if identity[1:] != wanted[1:] or (wanted[0] and identity[0] != wanted[0]):
            continue
        response = event.get("response") if isinstance(event.get("response"), Mapping) else {}
        is_negative = bool(response.get("stopped_due_to_symptoms") or response.get("worsening_reported"))
        is_negative = is_negative or any(
            _clean(response.get(key)) in _NEGATIVE_RESPONSE_VALUES
            for key in ("during_response", "next_day_response")
        )
        if is_negative and _clean(event.get("drill_id")):
            negative.add(_clean(event.get("drill_id")))
    return negative


def filter_rehab_candidates(
    *,
    injury: Mapping[str, object],
    rehab_stage: str,
    candidates: Sequence[Mapping[str, object]],
    available_equipment: Iterable[str] | None = None,
    exposures: Iterable[Mapping[str, object]] = (),
) -> tuple[list[Mapping[str, object]], list[RejectedCandidate]]:
    """Apply non-tradeable compatibility rules before any ranking."""
    stage = _clean(rehab_stage)
    region = _clean(injury.get("body_region") or injury.get("canonical_location") or injury.get("location"))
    family = _clean(injury.get("injury_type") or injury.get("rehab_type"))
    side = _clean(injury.get("side") or injury.get("laterality"))
    severity = _clean(injury.get("severity"))
    equipment = {_clean(item) for item in available_equipment or ()}
    negative = _negative_drill_ids(exposures, injury)
    eligible: list[Mapping[str, object]] = []
    rejected: list[RejectedCandidate] = []

    for candidate in candidates:
        drill_id = _clean(candidate.get("id"))
        reasons: list[str] = []
        candidate_stage = _clean(candidate.get("rehab_stage"))
        candidate_pathway = _clean(candidate.get("care_pathway") or "msk")
        candidate_regions = _values(candidate.get("target_regions"))
        candidate_family = _clean(candidate.get("injury_type") or candidate.get("type"))
        candidate_side = _clean(candidate.get("laterality_applicability"))

        if not drill_id:
            reasons.append("REJECT_INVALID_DRILL_ID")
        if candidate_pathway != "msk":
            reasons.append("REJECT_SURFACE_PATHWAY")
        if stage not in _LIVE_STAGES:
            reasons.append("REJECT_STAGE_NOT_LIVE")
        if candidate_stage not in _STAGE_INDEX:
            reasons.append("REJECT_UNKNOWN_REQUIRED_STAGE")
        elif stage in _STAGE_INDEX and _STAGE_INDEX[candidate_stage] > _STAGE_INDEX[stage]:
            reasons.append("REJECT_STAGE_TOO_ADVANCED")
        elif (
            candidate_stage != stage
            and not bool(candidate.get("allow_conservative_stage_fallback"))
        ):
            reasons.append("REJECT_STAGE_MISMATCH")
        if not region or not candidate_regions:
            reasons.append("REJECT_UNKNOWN_REQUIRED_REGION")
        elif region not in candidate_regions and "generic" not in candidate_regions and "unspecified" not in candidate_regions:
            reasons.append("REJECT_REGION_MISMATCH")
        if candidate_family and candidate_family not in {family, "unspecified"}:
            reasons.append("REJECT_INJURY_FAMILY")
        allowed_severities = _values(candidate.get("allowed_severities"))
        if allowed_severities and (not severity or severity not in allowed_severities):
            reasons.append("REJECT_SEVERITY")
        if candidate_side not in {"", "unknown", "any", "bilateral", "unilateral"} and side != candidate_side:
            reasons.append("REJECT_LATERALITY_MISMATCH")
        if candidate_side in {"left", "right"} and side in {"", "unknown"}:
            reasons.append("REJECT_UNKNOWN_REQUIRED_LATERALITY")
        required = _values(candidate.get("required_equipment") or candidate.get("equipment"))
        if available_equipment is not None and required - equipment:
            reasons.append("REJECT_EQUIPMENT_UNAVAILABLE")
        if drill_id in negative:
            reasons.append("REJECT_RECENT_NEGATIVE_EXPOSURE")
        if reasons:
            rejected.append(RejectedCandidate(drill_id, tuple(dict.fromkeys(reasons))))
        else:
            eligible.append(candidate)
    return eligible, rejected


def _known_demand(candidate: Mapping[str, object]) -> int:
    return sum(_clean(candidate.get(field)) not in {"", "unknown"} for field in ("load", "impact", "velocity"))


def rank_rehab_candidates(
    candidates: Sequence[Mapping[str, object]], *, injury: Mapping[str, object], rehab_stage: str
) -> list[Mapping[str, object]]:
    """Return candidates in a documented lexicographic clinical order."""
    region = _clean(injury.get("body_region") or injury.get("canonical_location") or injury.get("location"))
    family = _clean(injury.get("injury_type") or injury.get("rehab_type"))
    side = _clean(injury.get("side") or injury.get("laterality"))
    severity = _clean(injury.get("severity"))
    stage = _clean(rehab_stage)

    def key(candidate: Mapping[str, object]) -> tuple[object, ...]:
        regions = _values(candidate.get("target_regions"))
        allowed = _values(candidate.get("allowed_severities"))
        return (
            -int(_clean(candidate.get("rehab_stage")) == stage),
            -int(_clean(candidate.get("injury_type") or candidate.get("type")) == family),
            -int(region in regions),
            -int(_clean(candidate.get("laterality_applicability")) == side),
            -int(bool(severity and severity in allowed)),
            -_known_demand(candidate),
            _clean(candidate.get("id")),
        )

    return sorted(candidates, key=key)


def select_rehab_candidate(
    *,
    injury: Mapping[str, object],
    rehab_stage: str,
    candidates: Sequence[Mapping[str, object]],
    available_equipment: Iterable[str] | None = None,
    exposures: Iterable[Mapping[str, object]] = (),
) -> RehabSelectionResult:
    eligible, rejected = filter_rehab_candidates(
        injury=injury,
        rehab_stage=rehab_stage,
        candidates=candidates,
        available_equipment=available_equipment,
        exposures=exposures,
    )
    ranked = rank_rehab_candidates(eligible, injury=injury, rehab_stage=rehab_stage)
    selected = ranked[0] if ranked else None
    selected_id = _clean(selected.get("id")) if selected else None
    factors = ()
    if selected:
        factors = (
            RankingFactor("stage_match", "exact" if _clean(selected.get("rehab_stage")) == _clean(rehab_stage) else "conservative_fallback"),
            RankingFactor("region_match", "exact"),
            RankingFactor("injury_family_match", "exact" if _clean(selected.get("injury_type") or selected.get("type")) == _clean(injury.get("injury_type") or injury.get("rehab_type")) else "regional_fallback"),
        )
    return RehabSelectionResult(
        injury_id=str(injury.get("id") or ""),
        injury_episode_id=str(injury.get("episode_id") or ""),
        rehab_stage=_clean(rehab_stage),
        selected_drill_id=selected_id,
        selection_reason="SELECT_DETERMINISTIC_BEST" if selected else "NO_SUPPORTED_CANDIDATE",
        candidate_count=len(candidates),
        eligible_candidate_count=len(eligible),
        ranking_factors=factors,
        rejected_candidates=tuple(rejected),
        selected_drill=selected,
    )


__all__ = [
    "CANONICAL_STAGES", "SELECTOR_VERSION", "RankingFactor", "RejectedCandidate",
    "RehabSelectionResult", "filter_rehab_candidates", "rank_rehab_candidates",
    "select_rehab_candidate",
]
