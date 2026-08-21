"""Deterministic RESTORE -> LOAD eligibility interpretation in shadow mode.

This module interprets immutable :class:`RehabExposureEvent` observations for
one exact athlete/injury/episode.  It never mutates a rehabilitation stage and
is not imported by drill or session selection.

The registry is intentionally empty until the rehab bank or another reviewed
repository source supplies condition-specific progression capabilities with
provenance. A taxonomy label alone is not a LOAD rule. Unsupported types are an
evidence gap, not an invitation to invent a generic day, pain, session-count or
diagnosis rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fightcamp.injury_taxonomy import INJURY_TAXONOMY
from .rehab_exposure import RehabExposureEvent
from .rehab_stage import (
    REASON_RED_FLAG_GATE,
    REASON_URGENT_INJURY_TYPE,
    STAGE_RESTORE,
    RehabStageDecision,
)

LOAD_ELIGIBILITY_ENGINE_VERSION = "1"

EligibilityDecision = Literal[
    "eligible",
    "not_eligible",
    "insufficient_evidence",
    "medically_blocked",
    "not_applicable",
]
CriterionStatus = Literal["pass", "fail", "unknown", "not_applicable"]
EvidenceClassification = Literal[
    "qualifying_positive_candidate",
    "negative_response",
    "neutral_observation",
    "unusable_for_capacity",
    "incomplete_unknown",
]

# Final/result reasons.
ELIGIBLE_LOAD_CRITERIA_MET = "eligible_load_criteria_met"
INSUFFICIENT_NO_EXPOSURES = "insufficient_no_exposures"
INSUFFICIENT_NO_QUALIFYING_DEMAND = "insufficient_no_qualifying_demand"
INSUFFICIENT_DELAYED_RESPONSE = "insufficient_delayed_response"
INSUFFICIENT_UNSUPPORTED_INJURY_TYPE = "insufficient_unsupported_injury_type"
INSUFFICIENT_LATERALITY = "insufficient_laterality"
INSUFFICIENT_INJURY_IDENTITY = "insufficient_injury_identity"
INSUFFICIENT_UNQUANTIFIED_EXPOSURE = "insufficient_unquantified_exposure"
INSUFFICIENT_NO_COMPLETED_DOSE = "insufficient_no_completed_dose"
INSUFFICIENT_RESPONSE = "insufficient_injury_response"
INSUFFICIENT_RESPONSE_GROUP = "insufficient_response_group_identity"
INSUFFICIENT_HISTORY_TRUNCATED = "insufficient_history_truncated"
INSUFFICIENT_UNRESOLVED_NEGATIVE_EVIDENCE = (
    "insufficient_unresolved_historical_negative_evidence"
)
BLOCKED_RED_FLAG = "blocked_red_flag"
BLOCKED_MEDICAL_REVIEW = "blocked_medical_review"
BLOCKED_ACTIVE_WORSENING = "blocked_active_worsening"
FAIL_STOPPED_DUE_TO_SYMPTOMS = "fail_stopped_due_to_symptoms"
FAIL_DURING_RESPONSE_WORSE = "fail_during_response_worse"
FAIL_NEXT_DAY_RESPONSE_WORSE = "fail_next_day_response_worse"
FAIL_WORSENING_REPORTED = "fail_worsening_reported"
NOT_APPLICABLE_SURFACE_PATHWAY = "not_applicable_surface_pathway"
NOT_APPLICABLE_CURRENT_STAGE = "not_applicable_current_stage"

# Evidence-rejection reasons. These are diagnostics, never positive evidence.
IGNORED_INVALID_EVENT = "ignored_invalid_event"
IGNORED_ATHLETE_MISMATCH = "ignored_athlete_mismatch"
IGNORED_INJURY_MISMATCH = "ignored_injury_mismatch"
IGNORED_EPISODE_MISMATCH = "ignored_episode_mismatch"
IGNORED_REGION_MISMATCH = "ignored_region_mismatch"
IGNORED_SIDE_MISMATCH = "ignored_side_mismatch"
IGNORED_DUPLICATE_EXPOSURE = "ignored_duplicate_exposure"


@dataclass(frozen=True)
class LoadCriteria:
    """A condition-specific capability rule with explicit repository provenance.

    A taxonomy family is not itself progression evidence. Each future entry
    must name one exact structured injury type and the reviewed repo source that
    justifies its capabilities. No counts or elapsed-time values belong here.
    """

    injury_type: str
    taxonomy_family: str
    provenance: str
    qualifying_loads: frozenset[str]
    requires_quantified_dose: bool
    allowed_during_responses: frozenset[str]
    requires_delayed_response: bool
    allowed_delayed_responses: frozenset[str]
    historical_negative_resolution_rule: str | None


_NON_WORSENING_RESPONSES = frozenset({"better", "same"})

# No existing rehab-bank or taxonomy record currently supplies a reviewed,
# condition-specific RESTORE -> LOAD capability rule with provenance. In
# particular, the bank's clinical demand metadata (``load``/``impact``/
# ``velocity``) remains pending migration: every drill resolves to ``unknown``
# demand today, so ``RehabExposureEvent.has_unknown_demand`` excludes every
# exposure from LOAD qualification and any criterion added now could never fire.
# An empty registry is therefore the only honest production configuration.
#
# The dependency before this can be populated is: migrate the clinical demand
# taxonomy -> classify each drill's real load/impact/velocity -> land the
# reviewed values in the bank -> validate coverage -> only then enable criteria.
# Future entries must be keyed by an exact structured taxonomy type (not a broad
# family label), cite their reviewed source in ``provenance``, and be backed by
# real bank demand — enforced by
# ``tests/test_load_criteria_registry_coverage.py`` so a rule that can never fire
# cannot be merged.
LOAD_CRITERIA_REGISTRY: Mapping[str, LoadCriteria] = MappingProxyType({})


class CriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion: str
    status: CriterionStatus
    reason_code: str
    evidence_ids: list[str] = Field(default_factory=list)
    response_group_ids: list[str] = Field(default_factory=list)


class ExposureAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exposure_id: str
    response_group_id: str | None = None
    classification: EvidenceClassification
    reason_codes: list[str] = Field(default_factory=list)


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exposure_count: int = 0
    independent_response_group_count: int = 0
    classification_counts: dict[str, int] = Field(default_factory=dict)
    qualifying_exposure_ids: list[str] = Field(default_factory=list)
    qualifying_response_group_ids: list[str] = Field(default_factory=list)
    assessments: list[ExposureAssessment] = Field(default_factory=list)
    ignored_row_count: int = 0
    ignored_reason_counts: dict[str, int] = Field(default_factory=dict)
    history_truncated: bool = False


class LoadEligibilityResult(BaseModel):
    """Canonical shadow result for one exact injury evidence episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    injury_id: str
    injury_episode_id: str
    current_stage: str | None
    injury_type: str
    injury_family: str | None = None
    eligible_for_load: bool
    decision: EligibilityDecision
    reason_codes: list[str]
    evidence_summary: EvidenceSummary = Field(default_factory=EvidenceSummary)
    criteria_results: list[CriterionResult] = Field(default_factory=list)
    evaluated_at: datetime
    engine_version: str = LOAD_ELIGIBILITY_ENGINE_VERSION


@dataclass(frozen=True)
class _GroupEvidence:
    group_id: str | None
    events: tuple[RehabExposureEvent, ...]
    negative_reasons: tuple[str, ...]
    response_consistent: bool


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _canonical_token(value: Any) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def resolve_injury_type(injury: Mapping[str, Any]) -> str:
    """Read a structured taxonomy key used to select progression criteria.

    Free text is deliberately not scored here. A triage/display parser may
    suggest an injury elsewhere, but prose is not progression authority. If no
    exact structured taxonomy field exists, the result is ``unspecified`` and
    LOAD eligibility remains insufficient.
    """

    for field_name in ("triage_category", "injury_type", "rehab_type", "surface_type"):
        candidate = _canonical_token(injury.get(field_name))
        if candidate in INJURY_TAXONOMY:
            return candidate
    return "unspecified"


def criteria_for_injury_type(
    injury_type: str,
    registry: Mapping[str, LoadCriteria] = LOAD_CRITERIA_REGISTRY,
) -> LoadCriteria | None:
    normalized = _canonical_token(injury_type)
    criteria = registry.get(normalized)
    taxonomy = INJURY_TAXONOMY.get(normalized)
    if (
        criteria is None
        or criteria.injury_type != normalized
        or not criteria.provenance
        or criteria.taxonomy_family != _clean((taxonomy or {}).get("category"))
    ):
        return None
    return criteria


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _clean(value)
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _evaluated_at(
    injury: Mapping[str, Any], events: Sequence[RehabExposureEvent]
) -> datetime:
    """Derive a stable watermark from the input state, never wall-clock time."""

    timestamps = [event.occurred_at.astimezone(timezone.utc) for event in events]
    timestamps.extend(
        timestamp
        for timestamp in (
            _parse_timestamp(injury.get("updated_at")),
            _parse_timestamp(injury.get("created_at")),
        )
        if timestamp is not None
    )
    return max(timestamps, default=datetime(1970, 1, 1, tzinfo=timezone.utc))


def _side_matches(injury_side: str, event_side: str) -> bool:
    if injury_side in {"", "unknown"} or event_side == "unknown":
        return False
    return (
        injury_side == event_side
        or injury_side == "bilateral"
        or event_side == "bilateral"
    )


def _read_exact_events(
    *,
    athlete_id: str,
    injury: Mapping[str, Any],
    exposure_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[RehabExposureEvent], Counter[str]]:
    ignored: Counter[str] = Counter()
    events: list[RehabExposureEvent] = []
    seen: set[str] = set()
    injury_id = _clean(injury.get("id"))
    episode_id = _clean(injury.get("episode_id"))
    body_region = _clean(injury.get("body_region"))
    injury_side = _canonical_token(injury.get("side"))

    for row in exposure_rows or ():
        if not isinstance(row, Mapping):
            ignored[IGNORED_INVALID_EVENT] += 1
            continue
        if _clean(row.get("athlete_id")) != athlete_id:
            ignored[IGNORED_ATHLETE_MISMATCH] += 1
            continue
        raw_event = row.get("event_json")
        if not isinstance(raw_event, Mapping):
            ignored[IGNORED_INVALID_EVENT] += 1
            continue
        try:
            event = RehabExposureEvent.model_validate(raw_event)
        except (ValidationError, TypeError, ValueError):
            ignored[IGNORED_INVALID_EVENT] += 1
            continue
        exposure_id = str(event.exposure_id)
        if exposure_id in seen:
            ignored[IGNORED_DUPLICATE_EXPOSURE] += 1
            continue
        seen.add(exposure_id)
        if str(event.injury_id) != injury_id:
            ignored[IGNORED_INJURY_MISMATCH] += 1
            continue
        if str(event.injury_episode_id) != episode_id:
            ignored[IGNORED_EPISODE_MISMATCH] += 1
            continue
        if event.body_region != body_region:
            ignored[IGNORED_REGION_MISMATCH] += 1
            continue
        if not _side_matches(injury_side, event.side):
            ignored[IGNORED_SIDE_MISMATCH] += 1
            continue
        events.append(event)

    events.sort(key=lambda event: (event.occurred_at, str(event.exposure_id)))
    return events, ignored


def _negative_reasons(event: RehabExposureEvent) -> tuple[str, ...]:
    reasons: list[str] = []
    if event.response.stopped_due_to_symptoms is True:
        reasons.append(FAIL_STOPPED_DUE_TO_SYMPTOMS)
    if event.response.during_response == "worse":
        reasons.append(FAIL_DURING_RESPONSE_WORSE)
    if event.response.next_day_response == "worse":
        reasons.append(FAIL_NEXT_DAY_RESPONSE_WORSE)
    if event.response.worsening_reported is True:
        reasons.append(FAIL_WORSENING_REPORTED)
    return tuple(reasons)


def _response_signature(event: RehabExposureEvent) -> tuple[Any, ...]:
    response = event.response
    return (
        response.during_response,
        response.next_day_response,
        response.stopped_due_to_symptoms,
        response.worsening_reported,
    )


def _group_events(events: Sequence[RehabExposureEvent]) -> list[_GroupEvidence]:
    grouped: dict[str, list[RehabExposureEvent]] = {}
    for event in events:
        # A missing group is deliberately isolated to its exposure for
        # chronology/diagnostics, but cannot qualify positively later.
        key = str(event.response_group_id) if event.response_group_id else f"missing:{event.exposure_id}"
        grouped.setdefault(key, []).append(event)
    results: list[_GroupEvidence] = []
    for key, group_events in grouped.items():
        reasons = tuple(
            dict.fromkeys(
                reason
                for event in group_events
                for reason in _negative_reasons(event)
            )
        )
        results.append(
            _GroupEvidence(
                group_id=None if key.startswith("missing:") else key,
                events=tuple(group_events),
                negative_reasons=reasons,
                response_consistent=len({_response_signature(event) for event in group_events}) == 1,
            )
        )
    results.sort(key=lambda group: (group.events[0].occurred_at, str(group.events[0].exposure_id)))
    return results


def _has_positive_completed_amount(event: RehabExposureEvent) -> bool:
    dose = event.dose_completed
    measured = (
        dose.sets,
        dose.reps,
        dose.duration_seconds,
        dose.external_load_kg,
        dose.distance_metres,
        dose.hold_seconds,
        dose.completed_fraction,
    )
    return dose.completion_state == "quantified" and any(
        isinstance(value, (int, float)) and value > 0 for value in measured
    )


def _criterion(
    criterion: str,
    status: CriterionStatus,
    reason_code: str,
    events: Sequence[RehabExposureEvent] = (),
) -> CriterionResult:
    return CriterionResult(
        criterion=criterion,
        status=status,
        reason_code=reason_code,
        evidence_ids=[str(event.exposure_id) for event in events],
        response_group_ids=list(
            dict.fromkeys(str(event.response_group_id) for event in events if event.response_group_id)
        ),
    )


def _summary(
    *,
    events: Sequence[RehabExposureEvent],
    groups: Sequence[_GroupEvidence],
    criteria: LoadCriteria | None,
    qualifying_events: Sequence[RehabExposureEvent] = (),
    ignored: Counter[str] | None = None,
    history_truncated: bool = False,
) -> EvidenceSummary:
    assessments: list[ExposureAssessment] = []
    counts: Counter[str] = Counter()
    group_by_event = {
        str(event.exposure_id): group for group in groups for event in group.events
    }
    qualifying_ids = {str(event.exposure_id) for event in qualifying_events}

    for event in events:
        group = group_by_event[str(event.exposure_id)]
        reasons: list[str] = []
        if group.negative_reasons:
            classification: EvidenceClassification = "negative_response"
            reasons.extend(group.negative_reasons)
        elif group.group_id is None:
            classification = "incomplete_unknown"
            reasons.append(INSUFFICIENT_RESPONSE_GROUP)
        elif not group.response_consistent:
            classification = "incomplete_unknown"
            reasons.append(INSUFFICIENT_RESPONSE)
        elif event.has_unknown_demand:
            classification = "unusable_for_capacity"
            reasons.append(INSUFFICIENT_NO_QUALIFYING_DEMAND)
        elif criteria is not None and event.demand.load not in criteria.qualifying_loads:
            classification = "neutral_observation"
            reasons.append(INSUFFICIENT_NO_QUALIFYING_DEMAND)
        elif (
            (criteria is None or criteria.requires_quantified_dose)
            and event.dose_completed.completion_state != "quantified"
        ):
            classification = "incomplete_unknown"
            reasons.append(INSUFFICIENT_UNQUANTIFIED_EXPOSURE)
        elif (
            (criteria is None or criteria.requires_quantified_dose)
            and not _has_positive_completed_amount(event)
        ):
            classification = "incomplete_unknown"
            reasons.append(INSUFFICIENT_NO_COMPLETED_DOSE)
        elif event.response.during_response not in _NON_WORSENING_RESPONSES:
            classification = "incomplete_unknown"
            reasons.append(INSUFFICIENT_RESPONSE)
        elif str(event.exposure_id) in qualifying_ids:
            classification = "qualifying_positive_candidate"
            reasons.append(ELIGIBLE_LOAD_CRITERIA_MET)
        else:
            classification = "neutral_observation"
        counts[classification] += 1
        assessments.append(
            ExposureAssessment(
                exposure_id=str(event.exposure_id),
                response_group_id=str(event.response_group_id) if event.response_group_id else None,
                classification=classification,
                reason_codes=reasons,
            )
        )

    qualifying_groups = list(
        dict.fromkeys(
            str(event.response_group_id)
            for event in qualifying_events
            if event.response_group_id is not None
        )
    )
    ignored = ignored or Counter()
    return EvidenceSummary(
        exposure_count=len(events),
        independent_response_group_count=sum(group.group_id is not None for group in groups),
        classification_counts=dict(sorted(counts.items())),
        qualifying_exposure_ids=[str(event.exposure_id) for event in qualifying_events],
        qualifying_response_group_ids=qualifying_groups,
        assessments=assessments,
        ignored_row_count=sum(ignored.values()),
        ignored_reason_counts=dict(sorted(ignored.items())),
        history_truncated=history_truncated,
    )


def _result(
    *,
    injury: Mapping[str, Any],
    stage_decision: RehabStageDecision,
    injury_type: str,
    injury_family: str | None,
    decision: EligibilityDecision,
    reasons: Sequence[str],
    criteria_results: Sequence[CriterionResult],
    evidence_summary: EvidenceSummary,
    evaluated_at: datetime,
) -> LoadEligibilityResult:
    return LoadEligibilityResult(
        injury_id=_clean(injury.get("id")),
        injury_episode_id=_clean(injury.get("episode_id")),
        current_stage=stage_decision.stage,
        injury_type=injury_type,
        injury_family=injury_family,
        eligible_for_load=decision == "eligible",
        decision=decision,
        reason_codes=list(dict.fromkeys(reasons)),
        evidence_summary=evidence_summary,
        criteria_results=list(criteria_results),
        evaluated_at=evaluated_at,
    )


def resolve_load_eligibility(
    *,
    athlete_id: str,
    injury: Mapping[str, Any],
    stage_decision: RehabStageDecision,
    exposure_rows: Sequence[Mapping[str, Any]] = (),
    history_truncated: bool = False,
    criteria_registry: Mapping[str, LoadCriteria] | None = None,
) -> LoadEligibilityResult:
    """Compute a shadow LOAD decision without changing stage or programming."""

    injury_type = resolve_injury_type(injury)
    taxonomy_rule = INJURY_TAXONOMY.get(injury_type, INJURY_TAXONOMY["unspecified"])
    injury_family = _clean(taxonomy_rule.get("category")) or None
    events, ignored = _read_exact_events(
        athlete_id=athlete_id,
        injury=injury,
        exposure_rows=exposure_rows,
    )
    groups = _group_events(events)
    evaluated_at = _evaluated_at(injury, events)
    empty_summary = _summary(
        events=events,
        groups=groups,
        criteria=None,
        ignored=ignored,
        history_truncated=history_truncated,
    )

    # Existing authoritative safety routing always precedes positive criteria.
    if stage_decision.is_wound_care or injury_family == "surface":
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="not_applicable",
            reasons=[NOT_APPLICABLE_SURFACE_PATHWAY],
            criteria_results=[
                _criterion(
                    "musculoskeletal_pathway",
                    "not_applicable",
                    NOT_APPLICABLE_SURFACE_PATHWAY,
                )
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )
    if stage_decision.medical_gate:
        gate_reason = (
            BLOCKED_RED_FLAG
            if REASON_RED_FLAG_GATE in stage_decision.reasons
            else BLOCKED_MEDICAL_REVIEW
        )
        # An urgent injury-specific route remains medical review even if a
        # whole-athlete red flag also exists.
        if REASON_URGENT_INJURY_TYPE in stage_decision.reasons:
            gate_reason = BLOCKED_MEDICAL_REVIEW
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="medically_blocked",
            reasons=[gate_reason],
            criteria_results=[_criterion("medical_safety_gate", "fail", gate_reason)],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )
    if _canonical_token(injury.get("latest_reported_status")) == "worse":
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="not_eligible",
            reasons=[BLOCKED_ACTIVE_WORSENING],
            criteria_results=[
                _criterion("current_injury_not_worsening", "fail", BLOCKED_ACTIVE_WORSENING)
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )
    if stage_decision.stage != STAGE_RESTORE:
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="not_applicable",
            reasons=[NOT_APPLICABLE_CURRENT_STAGE],
            criteria_results=[
                _criterion("current_stage_restore", "not_applicable", NOT_APPLICABLE_CURRENT_STAGE)
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )

    criteria = criteria_for_injury_type(
        injury_type,
        LOAD_CRITERIA_REGISTRY if criteria_registry is None else criteria_registry,
    )

    # A negative in the newest independently reported response group is current
    # negative evidence and prevents eligibility. An older negative followed by
    # newer evidence is different: it cannot be a permanent episode-wide veto,
    # but neither may a generic time/count rule clear it. Until this exact injury
    # type has a sourced resolution rule, report the uncertainty explicitly.
    negative_groups = [group for group in groups if group.negative_reasons]
    if negative_groups and groups and groups[-1].negative_reasons:
        latest_negative_events = list(groups[-1].events)
        latest_negative_reasons = list(groups[-1].negative_reasons)
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="not_eligible",
            reasons=latest_negative_reasons,
            criteria_results=[
                _criterion(
                    "latest_injury_response_not_negative",
                    "fail",
                    latest_negative_reasons[0],
                    latest_negative_events,
                )
            ],
            evidence_summary=_summary(
                events=events,
                groups=groups,
                criteria=criteria,
                ignored=ignored,
                history_truncated=history_truncated,
            ),
            evaluated_at=evaluated_at,
        )
    if negative_groups:
        historical_negative_events = [
            event for group in negative_groups for event in group.events
        ]
        historical_reasons = list(
            dict.fromkeys(
                reason for group in negative_groups for reason in group.negative_reasons
            )
        )
        # No current condition-specific rule defines how historical negatives
        # become resolved. Adding a registry entry alone must not silently clear
        # them; a future implementation must explicitly evaluate that entry's
        # sourced resolution rule here.
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_UNRESOLVED_NEGATIVE_EVIDENCE, *historical_reasons],
            criteria_results=[
                _criterion(
                    "historical_negative_evidence_resolved",
                    "unknown",
                    INSUFFICIENT_UNRESOLVED_NEGATIVE_EVIDENCE,
                    historical_negative_events,
                )
            ],
            evidence_summary=_summary(
                events=events,
                groups=groups,
                criteria=criteria,
                ignored=ignored,
                history_truncated=history_truncated,
            ),
            evaluated_at=evaluated_at,
        )

    if history_truncated:
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_HISTORY_TRUNCATED],
            criteria_results=[
                _criterion(
                    "complete_episode_history_available",
                    "unknown",
                    INSUFFICIENT_HISTORY_TRUNCATED,
                )
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )

    if criteria is None:
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=injury_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_UNSUPPORTED_INJURY_TYPE],
            criteria_results=[
                _criterion(
                    "injury_type_criteria_supported",
                    "unknown",
                    INSUFFICIENT_UNSUPPORTED_INJURY_TYPE,
                )
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )

    body_region = _clean(injury.get("body_region"))
    if not body_region:
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=criteria.taxonomy_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_INJURY_IDENTITY],
            criteria_results=[
                _criterion("injury_evidence_identity", "unknown", INSUFFICIENT_INJURY_IDENTITY)
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )
    if _canonical_token(injury.get("side")) in {"", "unknown"}:
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=criteria.taxonomy_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_LATERALITY],
            criteria_results=[
                _criterion("injury_laterality_known", "unknown", INSUFFICIENT_LATERALITY)
            ],
            evidence_summary=empty_summary,
            evaluated_at=evaluated_at,
        )

    criteria_results: list[CriterionResult] = [
        _criterion("current_stage_restore", "pass", "current_stage_restore"),
        _criterion(
            "injury_type_criteria_supported",
            "pass",
            f"supported_{criteria.injury_type}",
        ),
    ]
    if not events:
        criteria_results.append(
            _criterion("injury_specific_exposure_available", "unknown", INSUFFICIENT_NO_EXPOSURES)
        )
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=criteria.taxonomy_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_NO_EXPOSURES],
            criteria_results=criteria_results,
            evidence_summary=_summary(
                events=events,
                groups=groups,
                criteria=criteria,
                ignored=ignored,
                history_truncated=history_truncated,
            ),
            evaluated_at=evaluated_at,
        )

    criteria_results.append(
        _criterion("no_negative_injury_response", "pass", "no_negative_injury_response", events)
    )

    grouped_events = [
        event
        for group in groups
        if group.group_id is not None and group.response_consistent
        for event in group.events
    ]
    known_loading = [
        event
        for event in grouped_events
        if not event.has_unknown_demand and event.demand.load in criteria.qualifying_loads
    ]
    if not known_loading:
        reason = (
            INSUFFICIENT_RESPONSE_GROUP
            if events and not grouped_events
            else INSUFFICIENT_NO_QUALIFYING_DEMAND
        )
        criteria_results.append(_criterion("loading_demand_demonstrated", "unknown", reason))
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=criteria.taxonomy_family,
            decision="insufficient_evidence",
            reasons=[reason],
            criteria_results=criteria_results,
            evidence_summary=_summary(
                events=events,
                groups=groups,
                criteria=criteria,
                ignored=ignored,
                history_truncated=history_truncated,
            ),
            evaluated_at=evaluated_at,
        )
    criteria_results.append(
        _criterion(
            "loading_demand_demonstrated",
            "pass",
            "known_loading_demand_demonstrated",
            known_loading,
        )
    )

    quantified = [event for event in known_loading if _has_positive_completed_amount(event)]
    if criteria.requires_quantified_dose and not quantified:
        reason = (
            INSUFFICIENT_UNQUANTIFIED_EXPOSURE
            if any(event.dose_completed.completion_state != "quantified" for event in known_loading)
            else INSUFFICIENT_NO_COMPLETED_DOSE
        )
        criteria_results.append(_criterion("completed_dose_quantified", "unknown", reason))
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=criteria.taxonomy_family,
            decision="insufficient_evidence",
            reasons=[reason],
            criteria_results=criteria_results,
            evidence_summary=_summary(
                events=events,
                groups=groups,
                criteria=criteria,
                ignored=ignored,
                history_truncated=history_truncated,
            ),
            evaluated_at=evaluated_at,
        )
    if criteria.requires_quantified_dose:
        dose_candidates = quantified
        criteria_results.append(
            _criterion(
                "completed_dose_quantified",
                "pass",
                "completed_dose_quantified",
                quantified,
            )
        )
    else:
        # The condition-specific criterion explicitly says that a quantified
        # amount is not required. Keep the known-loading events as candidates;
        # do not claim or infer a dose that the exposure did not record.
        dose_candidates = known_loading
        criteria_results.append(
            _criterion(
                "completed_dose_quantified",
                "not_applicable",
                "quantified_dose_not_required_for_criterion",
            )
        )

    favourable_during = [
        event
        for event in dose_candidates
        if event.response.during_response in criteria.allowed_during_responses
    ]
    if not favourable_during:
        criteria_results.append(
            _criterion("symptom_response_during_load", "unknown", INSUFFICIENT_RESPONSE)
        )
        return _result(
            injury=injury,
            stage_decision=stage_decision,
            injury_type=injury_type,
            injury_family=criteria.taxonomy_family,
            decision="insufficient_evidence",
            reasons=[INSUFFICIENT_RESPONSE],
            criteria_results=criteria_results,
            evidence_summary=_summary(
                events=events,
                groups=groups,
                criteria=criteria,
                ignored=ignored,
                history_truncated=history_truncated,
            ),
            evaluated_at=evaluated_at,
        )
    criteria_results.append(
        _criterion(
            "symptom_response_during_load",
            "pass",
            "non_worsening_during_response",
            favourable_during,
        )
    )

    qualifying = favourable_during
    if criteria.requires_delayed_response:
        qualifying = [
            event
            for event in favourable_during
            if event.response.next_day_response in criteria.allowed_delayed_responses
        ]
        if not qualifying:
            criteria_results.append(
                _criterion(
                    "delayed_response_when_required",
                    "unknown",
                    INSUFFICIENT_DELAYED_RESPONSE,
                )
            )
            return _result(
                injury=injury,
                stage_decision=stage_decision,
                injury_type=injury_type,
                injury_family=criteria.taxonomy_family,
                decision="insufficient_evidence",
                reasons=[INSUFFICIENT_DELAYED_RESPONSE],
                criteria_results=criteria_results,
                evidence_summary=_summary(
                    events=events,
                    groups=groups,
                    criteria=criteria,
                    ignored=ignored,
                    history_truncated=history_truncated,
                ),
                evaluated_at=evaluated_at,
            )
        criteria_results.append(
            _criterion(
                "delayed_response_when_required",
                "pass",
                "non_worsening_delayed_response",
                qualifying,
            )
        )
    else:
        # not_yet_known/not_sure are not passes; the criterion simply does not
        # apply to a family that has no existing delayed-response rule.
        criteria_results.append(
            _criterion(
                "delayed_response_when_required",
                "not_applicable",
                "delayed_response_not_required_for_family",
            )
        )

    return _result(
        injury=injury,
        stage_decision=stage_decision,
        injury_type=injury_type,
        injury_family=criteria.taxonomy_family,
        decision="eligible",
        reasons=[ELIGIBLE_LOAD_CRITERIA_MET],
        criteria_results=criteria_results,
        evidence_summary=_summary(
            events=events,
            groups=groups,
            criteria=criteria,
            qualifying_events=qualifying,
            ignored=ignored,
            history_truncated=history_truncated,
        ),
        evaluated_at=evaluated_at,
    )


__all__ = [
    "BLOCKED_ACTIVE_WORSENING",
    "BLOCKED_MEDICAL_REVIEW",
    "BLOCKED_RED_FLAG",
    "CriterionResult",
    "ELIGIBLE_LOAD_CRITERIA_MET",
    "EvidenceSummary",
    "FAIL_DURING_RESPONSE_WORSE",
    "FAIL_NEXT_DAY_RESPONSE_WORSE",
    "FAIL_STOPPED_DUE_TO_SYMPTOMS",
    "INSUFFICIENT_HISTORY_TRUNCATED",
    "INSUFFICIENT_NO_EXPOSURES",
    "INSUFFICIENT_NO_QUALIFYING_DEMAND",
    "INSUFFICIENT_UNQUANTIFIED_EXPOSURE",
    "INSUFFICIENT_UNRESOLVED_NEGATIVE_EVIDENCE",
    "INSUFFICIENT_UNSUPPORTED_INJURY_TYPE",
    "LOAD_CRITERIA_REGISTRY",
    "LOAD_ELIGIBILITY_ENGINE_VERSION",
    "LoadCriteria",
    "LoadEligibilityResult",
    "NOT_APPLICABLE_CURRENT_STAGE",
    "NOT_APPLICABLE_SURFACE_PATHWAY",
    "criteria_for_injury_type",
    "resolve_injury_type",
    "resolve_load_eligibility",
]
