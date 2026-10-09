"""Exact episode assessment transport/context; protocol interpretation stays typed."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Callable, Generic, Literal, Mapping, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from fightcamp.injury_formatting import parse_injury_entry
from fightcamp.rehab_clinical import load_pathway_catalog

from .achilles_progression import AchillesProgressionInput, read_achilles_input
from .lateral_elbow_progression import LateralElbowProgressionInput, read_elbow_input, PROTOCOL

ASSESSMENT_EVENT = "rehab_progression_assessment"
PayloadT = TypeVar("PayloadT", bound=BaseModel)


class AssessmentHistory(list):
    """Append-only episode history plus an explicit completeness contract."""
    def __init__(self, rows, *, history_complete: bool):
        super().__init__(rows)
        self.history_complete = history_complete


def instant(value):
    if isinstance(value, datetime):
        return value if value.tzinfo and value.utcoffset() is not None else None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def assessment_identity(injury: Mapping):
    parsed = parse_injury_entry(" ".join(str(injury.get(k) or "") for k in ("body_area", "description"))) or {}
    return (injury.get("canonical_location") or parsed.get("canonical_location") or injury.get("body_region"),
            injury.get("injury_type") or injury.get("rehab_type") or parsed.get("injury_type"))


class RehabProgressionAssessment(BaseModel, Generic[PayloadT]):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    assessment_kind: str
    protocol_version: int = Field(strict=True, ge=1)
    side: Literal["left", "right", "bilateral", "unknown"]
    assessed_at: AwareDatetime
    assessor: Literal["self_reported", "clinician_physio", "coach_observed", "unknown"]
    payload: PayloadT

    @model_validator(mode="before")
    @classmethod
    def strict_versions(cls, value):
        if isinstance(value, Mapping) and any(k in value and type(value[k]) is not int for k in ("schema_version", "protocol_version")):
            raise ValueError("assessment versions must be integer identifiers")
        return value

    @model_validator(mode="after")
    def registered_protocol(self):
        definition = ASSESSMENT_PROTOCOLS.get(self.assessment_kind)
        if definition is None or definition.version != self.protocol_version:
            raise ValueError("unknown progression assessment protocol/version")
        if not isinstance(self.payload, definition.payload_type):
            raise ValueError("assessment payload does not match its registered protocol")
        return self


class AchillesProgressionAssessment(RehabProgressionAssessment[AchillesProgressionInput]):
    assessment_kind: Literal["achilles_tendon_progression_v1"] = "achilles_tendon_progression_v1"
    protocol_version: Literal[1] = 1

    @model_validator(mode="after")
    def loading_precedes_assessment(self):
        if self.payload.loading_performed_at and self.payload.loading_performed_at > self.assessed_at:
            raise ValueError("Loading must precede assessment")
        return self


class LateralElbowProgressionAssessment(RehabProgressionAssessment[LateralElbowProgressionInput]):
    assessment_kind: Literal["lateral_elbow_progression_v1"] = "lateral_elbow_progression_v1"
    protocol_version: Literal[1] = 1


@dataclass(frozen=True)
class AssessmentProtocol:
    envelope_type: type[RehabProgressionAssessment]
    payload_type: type[BaseModel]
    version: int
    region: str
    injury_type: str
    profile_id: str
    read_input: Callable
    observation_times: Callable
    safety_concern: Callable

    def applies(self, injury: Mapping) -> bool:
        return assessment_identity(injury) == (self.region, self.injury_type)


# Production-supported typed protocols. Test registrations are isolated.
ASSESSMENT_PROTOCOLS = {
    PROTOCOL: AssessmentProtocol(
        LateralElbowProgressionAssessment, LateralElbowProgressionInput, 1, "elbow", "tendonitis", "elbow_tendonitis",
        read_elbow_input, lambda payload: (), lambda payload: payload.safety_concern,
    ),
    "achilles_tendon_progression_v1": AssessmentProtocol(
        AchillesProgressionAssessment, AchillesProgressionInput, 1, "achilles", "tendonitis", "achilles_tendonitis",
        read_achilles_input,
        lambda payload: (payload.loading_performed_at, payload.delayed_response_at),
        lambda payload: payload.safety_concern,
    ),
}


def validate_assessment(value) -> RehabProgressionAssessment:
    if isinstance(value, RehabProgressionAssessment):
        value = value.model_dump(mode="json")
    definition = ASSESSMENT_PROTOCOLS.get(value.get("assessment_kind")) if isinstance(value, Mapping) else None
    if definition is None:
        raise ValueError("unknown progression assessment protocol")
    return definition.envelope_type.model_validate(value)


def assessment_payload(assessment: RehabProgressionAssessment, injury: Mapping, *, as_of: datetime) -> dict:
    """Server-owned applicability/provenance; never accept a client verification claim."""
    assessment = validate_assessment(assessment)
    definition = ASSESSMENT_PROTOCOLS[assessment.assessment_kind]
    if not definition.applies(injury) or injury.get("status") not in {"open", "monitoring"}:
        raise ValueError("assessment requires an active applicable injury episode")
    if assessment.side != (injury.get("side") or "unknown"):
        raise ValueError("assessment side must match the injury episode")
    dates = (assessment.assessed_at, *definition.observation_times(assessment.payload))
    start = instant(injury.get("created_at"))
    if instant(as_of) is None or not start or any(d and (d > as_of or d < start) for d in dates):
        raise ValueError("assessment timestamps must belong to this episode and cannot be in the future")
    return {"assessment": assessment.model_dump(mode="json"), "region": definition.region,
            "injury_type": definition.injury_type, "profile_id": definition.profile_id,
            "source": "athlete_reported", "externally_verified": False,
            "observation_times": [d.isoformat() for d in dates if d is not None],
            "medical_concern": bool(definition.safety_concern(assessment.payload)),
            "injury_context": {k: injury.get(k) for k in ("body_area", "description")}}


def exact_episode_events(injury: Mapping, observations):
    return [e for e in observations if all(injury.get(v) is not None and str(e.get(k)) == str(injury[v])
            for k, v in (("athlete_id", "athlete_id"), ("injury_id", "id"), ("injury_episode_id", "episode_id")))]


@dataclass(frozen=True)
class AssessmentContext:
    injury: Mapping
    observations: tuple
    as_of: datetime
    episode_start: datetime | None
    setback_at: datetime | None
    history_complete: bool

    @classmethod
    def from_injury(cls, injury: Mapping, *, as_of: datetime, setback_at=None, history_truncated=False):
        if instant(as_of) is None:
            raise ValueError("assessment replay requires an aware as_of")
        setbacks = [d for d in (instant(setback_at), instant(injury.get("assessment_setback_at"))) if d]
        return cls(injury, tuple(exact_episode_events(injury, injury.get("progression_assessments", ()))), as_of,
                   instant(injury.get("assessment_episode_started_at")) or instant(injury.get("created_at")),
                   max(setbacks, default=None), not history_truncated and injury.get("assessment_history_complete", True) is True)

    def parsed(self, event):
        try:
            payload = event.get("payload") or {}
            if not isinstance(payload, Mapping):
                return None
            assessment = validate_assessment(payload.get("assessment"))
            definition = ASSESSMENT_PROTOCOLS[assessment.assessment_kind]
            if (event.get("event_type") != ASSESSMENT_EVENT or not definition.applies(self.injury)
                    or (payload.get("region"), payload.get("injury_type"), payload.get("profile_id")) !=
                    (definition.region, definition.injury_type, definition.profile_id)
                    or assessment.side != self.injury.get("side")
                    or payload.get("source") != "athlete_reported" or payload.get("externally_verified") is not False):
                return None
            return assessment
        except (ValueError, TypeError):
            return None

    @property
    def reported_medical_concern(self):
        # All exact, valid concerns persist through reassuring snapshots/clearance.
        # Freshness/setbacks may invalidate readiness data, never erase a concern.
        return any(
            ASSESSMENT_PROTOCOLS[a.assessment_kind].safety_concern(a.payload)
            for e in self.observations if instant(e.get("created_at")) and instant(e.get("created_at")) <= self.as_of
            and (a := self.parsed(e)) is not None)

    @property
    def medical_hold(self):
        return bool(self.injury.get("rehab_medical_gate")) or self.reported_medical_concern

    def latest(self, kind):
        candidates = [e for e in self.observations if e.get("event_type") == ASSESSMENT_EVENT
                      and isinstance(e.get("payload"), Mapping)
                      and isinstance((e.get("payload") or {}).get("assessment"), Mapping)
                      and e["payload"]["assessment"].get("assessment_kind") == kind
                      and (not instant(e.get("created_at")) or instant(e.get("created_at")) <= self.as_of)]
        return max(candidates, key=lambda e: (instant(e.get("created_at")) or datetime.max.replace(tzinfo=timezone.utc),
                                              str(e.get("id") or "")), default=None)


@lru_cache(maxsize=1)
def _input_declarations():
    return tuple(load_pathway_catalog().functional_checkpoints)


def input_definitions():
    """Catalog owns stable IDs/bases/protocols; code binds a typed registered reader."""
    definitions = {}
    for declaration in _input_declarations():
        if declaration.assessment_kind:
            protocol = ASSESSMENT_PROTOCOLS.get(declaration.assessment_kind)
            if protocol is None or protocol.version != declaration.protocol_version or declaration.basis != "data_sufficiency":
                raise ValueError("invalid assessment input registration")
            definitions[declaration.checkpoint_id] = (declaration, protocol)
    return definitions


def read_assessment_input(identifier: str, context: AssessmentContext):
    result = {"status": "unknown", "reason_code": "assessment_observation_missing", "observation_id": None,
              "assessor": "unknown", "externally_verified": False, "usable_for_clinical_promotion": False}
    def answer(reason, status="unknown"):
        return {**result, "status": status, "reason_code": reason}
    registered = input_definitions().get(identifier)
    if registered is None:
        return answer("assessment_input_not_registered")
    declaration, definition = registered
    if not definition.applies(context.injury):
        return answer("assessment_identity_mismatch")
    if context.medical_hold or context.injury.get("latest_reported_status") == "worse":
        return answer("assessment_medical_or_setback_hold", "fail")
    if not context.history_complete:
        return answer("assessment_history_incomplete")
    event = context.latest(declaration.assessment_kind)
    if event is None:
        return result
    assessment = context.parsed(event)
    if assessment is None or assessment.side == "unknown":
        return answer("assessment_invalid_attribution_or_provenance")
    result.update(observation_id=str(event.get("id")), assessor=assessment.assessor)
    recorded = instant(event.get("created_at"))
    dates = (assessment.assessed_at, *definition.observation_times(assessment.payload))
    if (not recorded or not context.episode_start or recorded > context.as_of
            or any(d and (d > recorded or d < context.episode_start or (context.setback_at and d <= context.setback_at)) for d in dates)):
        return answer("assessment_observation_stale_or_future")
    return {**result, **definition.read_input(identifier, assessment),
            "usable_for_clinical_promotion": False, "externally_verified": False}
