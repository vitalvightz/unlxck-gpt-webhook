"""Deterministic, stage-aware rehabilitation drill selection.

This module selects bank content only. It deliberately knows nothing about
session cards or rehabilitation-stage progression. Callers must pass the
already-resolved live stage; shadow LOAD eligibility is not an input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .rehab_schema import (
    LATERALITY_APPLICABILITY_VALUES,
    REHAB_STAGES,
    SEVERITY_VALUES,
)


SELECTOR_VERSION = "2"
CANONICAL_STAGES = REHAB_STAGES
_STAGE_INDEX = {stage: index for index, stage in enumerate(CANONICAL_STAGES)}
_LIVE_STAGES = frozenset({"calm", "restore"})
_NEGATIVE_RESPONSE_VALUES = frozenset({"worse"})
_EXPLICIT_NON_ADVERSE_RESPONSE_VALUES = frozenset({"better", "same"})
_MSK_PATHWAYS = frozenset({"msk", "musculoskeletal"})


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
    selected_drill: Mapping[str, object] | None = field(
        default=None,
        repr=False,
        compare=False,
    )


def _clean(value: object) -> str:
    return str(value or "").strip().lower()


def _values(value: object) -> set[str]:
    if isinstance(value, str):
        cleaned = _clean(value)
        return {cleaned} if cleaned else set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {_clean(item) for item in value if _clean(item)}
    return set()


def _canonical_severity(value: object) -> str:
    """Collapse accepted intake aliases onto the rehab-bank severity contract."""
    normalized = _clean(value)
    aliases = {
        "mild": "low",
        "low": "low",
        "moderate": "moderate",
        "high": "high",
        "severe": "high",
    }
    return aliases.get(normalized, normalized if normalized in SEVERITY_VALUES else "")


def _canonical_side(value: object) -> str:
    normalized = _clean(value)
    if normalized == "both":
        return "bilateral"
    return normalized


def _event_mapping(exposure: Mapping[str, object]) -> Mapping[str, object]:
    """Flatten a persisted row without losing storage-envelope identity.

    ``RehabExposureEvent`` intentionally does not carry ``athlete_id`` because
    athlete ownership belongs to the database row. Supabase readers therefore
    return an envelope containing athlete/injury identity plus ``event_json``.
    Treat the envelope as authoritative for identity while taking response and
    demand observations from the immutable event payload.
    """
    event_json = exposure.get("event_json")
    if not isinstance(event_json, Mapping):
        return exposure

    event = dict(event_json)
    for key in (
        "athlete_id",
        "injury_id",
        "injury_episode_id",
        "body_region",
        "side",
        "drill_id",
        "occurred_at",
        "id",
    ):
        if exposure.get(key) is not None:
            event[key] = exposure[key]
    return event


def _response_mapping(event: Mapping[str, object]) -> Mapping[str, object]:
    response = event.get("response")
    return response if isinstance(response, Mapping) else {}


def _is_negative_response(response: Mapping[str, object]) -> bool:
    if response.get("stopped_due_to_symptoms") or response.get("worsening_reported"):
        return True
    return any(
        _clean(response.get(key)) in _NEGATIVE_RESPONSE_VALUES
        for key in ("during_response", "next_day_response")
    )


def _is_explicit_non_adverse_response(response: Mapping[str, object]) -> bool:
    """Return True only for an explicit newer non-adverse observation.

    This is not a recovery or tolerance claim. It only prevents one historical
    negative event from becoming a permanent drill blacklist inside the same
    injury episode. Unknown/not-sure responses cannot do this.
    """
    if _is_negative_response(response):
        return False
    return any(
        _clean(response.get(key)) in _EXPLICIT_NON_ADVERSE_RESPONSE_VALUES
        for key in ("during_response", "next_day_response")
    )


def _event_matches_injury(
    event: Mapping[str, object],
    injury: Mapping[str, object],
) -> bool:
    provenance = (
        event.get("provenance")
        if isinstance(event.get("provenance"), Mapping)
        else {}
    )
    wanted_athlete = _clean(injury.get("athlete_id"))
    wanted_injury = _clean(injury.get("id"))
    wanted_episode = _clean(injury.get("episode_id"))
    wanted_region = _clean(
        injury.get("body_region")
        or injury.get("canonical_location")
        or injury.get("location")
    )
    wanted_side = _canonical_side(injury.get("side") or injury.get("laterality"))

    event_athlete = _clean(event.get("athlete_id") or provenance.get("athlete_id"))
    if (
        not wanted_injury
        or not wanted_episode
        or _clean(event.get("injury_id")) != wanted_injury
        or _clean(event.get("injury_episode_id")) != wanted_episode
    ):
        return False
    if wanted_athlete and event_athlete != wanted_athlete:
        return False

    # PR3's evidence contract is region/laterality isolated. Missing or
    # mismatched identity cannot influence selection.
    if wanted_region and _clean(event.get("body_region")) != wanted_region:
        return False
    if not wanted_side or wanted_side == "unknown":
        return False
    if _canonical_side(event.get("side")) != wanted_side:
        return False
    return True


def _negative_exposure_state(
    exposures: Iterable[Mapping[str, object]],
    injury: Mapping[str, object],
) -> tuple[set[str], set[str]]:
    """Return unresolved-negative and historical-uncertainty drill IDs.

    A negative remains a hard selector rejection until a *newer explicit*
    non-adverse observation exists for the exact same injury episode, region
    and side. That later observation does not clinically clear the old event;
    it only changes selector handling from hard rejection to a conservative
    ranking penalty. No time/session threshold is used.
    """
    by_drill: dict[str, list[tuple[int, Mapping[str, object]]]] = {}
    for index, raw_exposure in enumerate(exposures):
        event = _event_mapping(raw_exposure)
        if not _event_matches_injury(event, injury):
            continue
        drill_id = _clean(event.get("drill_id"))
        if drill_id:
            by_drill.setdefault(drill_id, []).append((index, event))

    unresolved: set[str] = set()
    historical_uncertainty: set[str] = set()

    for drill_id, events in by_drill.items():
        def chronology(item: tuple[int, Mapping[str, object]]) -> tuple[object, ...]:
            index, event = item
            occurred_at = _clean(event.get("occurred_at"))
            stable_id = _clean(event.get("exposure_id") or event.get("id"))
            # Canonical stored events are timestamped. If legacy/synthetic rows
            # are not, preserve their supplied order rather than inventing time.
            if not occurred_at:
                return (0, "", "", index)
            return (1, occurred_at, stable_id, index)

        ordered = sorted(events, key=chronology)
        negative_indexes = [
            index
            for index, (_, event) in enumerate(ordered)
            if _is_negative_response(_response_mapping(event))
        ]
        if not negative_indexes:
            continue

        last_negative = negative_indexes[-1]
        newer_non_adverse = any(
            _is_explicit_non_adverse_response(_response_mapping(event))
            for _, event in ordered[last_negative + 1 :]
        )
        if newer_non_adverse:
            historical_uncertainty.add(drill_id)
        else:
            unresolved.add(drill_id)

    return unresolved, historical_uncertainty


def _laterality_rejection(applicability: str, side: str) -> str | None:
    if applicability not in LATERALITY_APPLICABILITY_VALUES:
        return "REJECT_UNKNOWN_REQUIRED_LATERALITY"
    if applicability == "unknown":
        return "REJECT_UNKNOWN_REQUIRED_LATERALITY"
    if applicability == "not_applicable":
        return None
    if not side or side == "unknown":
        return "REJECT_UNKNOWN_REQUIRED_LATERALITY"
    if applicability == "bilateral_only" and side != "bilateral":
        return "REJECT_LATERALITY_MISMATCH"
    if applicability == "side_specific" and side not in {"left", "right", "bilateral"}:
        return "REJECT_LATERALITY_MISMATCH"
    return None


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
    region = _clean(
        injury.get("body_region")
        or injury.get("canonical_location")
        or injury.get("location")
    )
    family = _clean(injury.get("injury_type") or injury.get("rehab_type"))
    side = _canonical_side(injury.get("side") or injury.get("laterality"))
    severity = _canonical_severity(injury.get("severity"))
    equipment = {_clean(item) for item in available_equipment or ()}
    unresolved_negative, _ = _negative_exposure_state(exposures, injury)
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
        if candidate_pathway not in _MSK_PATHWAYS:
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
        elif (
            region not in candidate_regions
            and "generic" not in candidate_regions
            and "unspecified" not in candidate_regions
        ):
            reasons.append("REJECT_REGION_MISMATCH")

        if candidate_family and candidate_family not in {family, "unspecified"}:
            reasons.append("REJECT_INJURY_FAMILY")

        allowed_severities = _values(candidate.get("allowed_severities"))
        if allowed_severities:
            if not severity:
                reasons.append("REJECT_UNKNOWN_REQUIRED_SEVERITY")
            elif severity not in allowed_severities:
                reasons.append("REJECT_SEVERITY")

        laterality_reason = _laterality_rejection(candidate_side, side)
        if laterality_reason:
            reasons.append(laterality_reason)

        required = _values(candidate.get("required_equipment") or candidate.get("equipment"))
        if available_equipment is not None and required - equipment:
            reasons.append("REJECT_EQUIPMENT_UNAVAILABLE")

        if drill_id in unresolved_negative:
            reasons.append("REJECT_UNRESOLVED_NEGATIVE_EXPOSURE")

        if reasons:
            rejected.append(RejectedCandidate(drill_id, tuple(dict.fromkeys(reasons))))
        else:
            eligible.append(candidate)

    return eligible, rejected


def _known_demand(candidate: Mapping[str, object]) -> int:
    return sum(
        _clean(candidate.get(field)) not in {"", "unknown"}
        for field in ("load", "impact", "velocity")
    )


def _laterality_specificity(candidate: Mapping[str, object], side: str) -> int:
    applicability = _clean(candidate.get("laterality_applicability"))
    if applicability == "bilateral_only" and side == "bilateral":
        return 2
    if applicability == "side_specific" and side in {"left", "right", "bilateral"}:
        return 2
    if applicability == "not_applicable":
        return 1
    return 0


def rank_rehab_candidates(
    candidates: Sequence[Mapping[str, object]],
    *,
    injury: Mapping[str, object],
    rehab_stage: str,
    historical_negative_drill_ids: Iterable[str] = (),
) -> list[Mapping[str, object]]:
    """Return candidates in a documented deterministic clinical order."""
    region = _clean(
        injury.get("body_region")
        or injury.get("canonical_location")
        or injury.get("location")
    )
    family = _clean(injury.get("injury_type") or injury.get("rehab_type"))
    side = _canonical_side(injury.get("side") or injury.get("laterality"))
    severity = _canonical_severity(injury.get("severity"))
    stage = _clean(rehab_stage)
    historical = {_clean(value) for value in historical_negative_drill_ids}
    continuity_id = _clean(
        injury.get("current_rehab_drill_id")
        or injury.get("continuity_rehab_drill_id")
    )
    preferred_function = _clean(
        injury.get("session_rehab_function")
        or injury.get("preferred_rehab_function")
        or injury.get("rehab_function")
    )

    def key(candidate: Mapping[str, object]) -> tuple[object, ...]:
        drill_id = _clean(candidate.get("id"))
        regions = _values(candidate.get("target_regions"))
        allowed = _values(candidate.get("allowed_severities"))
        candidate_family = _clean(candidate.get("injury_type") or candidate.get("type"))
        candidate_function = _clean(candidate.get("function"))
        return (
            -int(_clean(candidate.get("rehab_stage")) == stage),
            int(drill_id in historical),
            -int(candidate_family == family),
            -int(region in regions),
            -_laterality_specificity(candidate, side),
            -int(bool(severity and severity in allowed)),
            -int(bool(continuity_id and drill_id == continuity_id)),
            -int(bool(preferred_function and candidate_function == preferred_function)),
            -_known_demand(candidate),
            drill_id,
        )

    return sorted(candidates, key=key)


def _ranking_factors(
    selected: Mapping[str, object],
    *,
    injury: Mapping[str, object],
    rehab_stage: str,
    historical_negative_drill_ids: set[str],
) -> tuple[RankingFactor, ...]:
    selected_id = _clean(selected.get("id"))
    stage = _clean(rehab_stage)
    family = _clean(injury.get("injury_type") or injury.get("rehab_type"))
    side = _canonical_side(injury.get("side") or injury.get("laterality"))
    continuity_id = _clean(
        injury.get("current_rehab_drill_id")
        or injury.get("continuity_rehab_drill_id")
    )
    preferred_function = _clean(
        injury.get("session_rehab_function")
        or injury.get("preferred_rehab_function")
        or injury.get("rehab_function")
    )
    candidate_function = _clean(selected.get("function"))
    demand_known = _known_demand(selected)

    return (
        RankingFactor(
            "stage_match",
            "exact"
            if _clean(selected.get("rehab_stage")) == stage
            else "conservative_fallback",
        ),
        RankingFactor("region_match", "compatible"),
        RankingFactor(
            "injury_family_match",
            "exact"
            if _clean(selected.get("injury_type") or selected.get("type")) == family
            else "regional_fallback",
        ),
        RankingFactor(
            "laterality",
            "specific"
            if _laterality_specificity(selected, side) == 2
            else "not_applicable",
        ),
        RankingFactor(
            "historical_negative",
            "uncertainty" if selected_id in historical_negative_drill_ids else "none",
        ),
        RankingFactor(
            "continuity",
            "match"
            if continuity_id and selected_id == continuity_id
            else ("not_match" if continuity_id else "no_context"),
        ),
        RankingFactor(
            "function",
            "match"
            if preferred_function and candidate_function == preferred_function
            else ("not_match" if preferred_function else "no_context"),
        ),
        RankingFactor(
            "demand_metadata",
            "complete"
            if demand_known == 3
            else ("partial" if demand_known else "unknown"),
        ),
    )


def select_rehab_candidate(
    *,
    injury: Mapping[str, object],
    rehab_stage: str,
    candidates: Sequence[Mapping[str, object]],
    available_equipment: Iterable[str] | None = None,
    exposures: Iterable[Mapping[str, object]] = (),
) -> RehabSelectionResult:
    exposure_rows = tuple(exposures)
    eligible, rejected = filter_rehab_candidates(
        injury=injury,
        rehab_stage=rehab_stage,
        candidates=candidates,
        available_equipment=available_equipment,
        exposures=exposure_rows,
    )
    _, historical_negative = _negative_exposure_state(exposure_rows, injury)
    ranked = rank_rehab_candidates(
        eligible,
        injury=injury,
        rehab_stage=rehab_stage,
        historical_negative_drill_ids=historical_negative,
    )
    selected = ranked[0] if ranked else None
    selected_id = _clean(selected.get("id")) if selected else None
    factors = (
        _ranking_factors(
            selected,
            injury=injury,
            rehab_stage=rehab_stage,
            historical_negative_drill_ids=historical_negative,
        )
        if selected
        else ()
    )
    selection_reason = "NO_SUPPORTED_CANDIDATE"
    if selected:
        selection_reason = (
            "SELECT_DETERMINISTIC_WITH_HISTORICAL_NEGATIVE_UNCERTAINTY"
            if selected_id in historical_negative
            else "SELECT_DETERMINISTIC_BEST"
        )

    return RehabSelectionResult(
        injury_id=str(injury.get("id") or ""),
        injury_episode_id=str(injury.get("episode_id") or ""),
        rehab_stage=_clean(rehab_stage),
        selected_drill_id=selected_id,
        selection_reason=selection_reason,
        candidate_count=len(candidates),
        eligible_candidate_count=len(eligible),
        ranking_factors=factors,
        rejected_candidates=tuple(rejected),
        selected_drill=selected,
    )


__all__ = [
    "CANONICAL_STAGES",
    "SELECTOR_VERSION",
    "RankingFactor",
    "RejectedCandidate",
    "RehabSelectionResult",
    "filter_rehab_candidates",
    "rank_rehab_candidates",
    "select_rehab_candidate",
]
