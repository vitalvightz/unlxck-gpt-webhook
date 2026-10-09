"""Shared immutable review contracts and compiled criterion bindings.

These are internal contracts, not API requests. Authority comes from the
separate service-only admin capture boundary; registration does not activate work.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Generic, Literal, Mapping, Protocol, TypeVar

from pydantic import AwareDatetime, Field, model_validator

from .reviewed_prescription import (
    Digest, Identifier, ReviewModel, ReviewTransition, ReviewedPrescriptionOption,
    ReviewedPrescriptionSelection, Version,
)
from .achilles_restore_load_pilot import achilles_review_definition

if TYPE_CHECKING:
    from .clinical_review_validity import ReviewValidityContext


class ReviewDecision(str, Enum):
    APPROVED = "approved"
    NOT_APPROVED = "not_approved"
    DEFERRED = "deferred"


class ReviewLifecycleState(str, Enum):
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class ReviewSource(str, Enum):
    ATHLETE_REPORTED = "athlete_reported"
    INDEPENDENT_CONFIRMATION = "independently_confirmed_clinician_statement"
    CLINICIAN_DIRECT = "clinician_direct_submission"
    PROVIDER_INTEGRATION = "verified_provider_integration"
    DOCUMENT_VERIFICATION = "manual_document_verification"


class ClinicalAuthor(ReviewModel):
    author_id: Identifier
    display_name: Identifier
    qualification_reference: Identifier
    clinical_scopes: tuple[Identifier, ...] = Field(min_length=1)


class OperationalActor(ReviewModel):
    actor_id: Identifier
    role: Literal["operational_recorder", "clinical_author", "provider_service", "athlete"]


class ReviewProvenance(ReviewModel):
    source: ReviewSource
    recorder: OperationalActor
    verifier: OperationalActor | None = None
    confirmed_at: AwareDatetime | None = None
    confirmation_reference: Identifier | None = None
    statement_hash: Digest | None = None


class ReviewedEvidenceReference(ReviewModel):
    event_id: Identifier
    protocol_id: Identifier
    protocol_version: Version
    content_hash: Digest
    observed_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def chronology(self):
        if self.observed_at > self.recorded_at:
            raise ValueError("evidence observation must precede recording")
        return self


class ReviewedEvidencePacket(ReviewModel):
    evidence_cutoff: AwareDatetime
    packet_revision: Digest
    safety_revision: Digest
    references: tuple[ReviewedEvidenceReference, ...] = ()
    clearance_event_id: Identifier | None = None

    @model_validator(mode="after")
    def complete_references(self):
        if len({r.event_id for r in self.references}) != len(self.references):
            raise ValueError("duplicate evidence reference")
        if any(r.recorded_at > self.evidence_cutoff for r in self.references):
            raise ValueError("evidence cannot follow the packet cutoff")
        return self


PayloadT = TypeVar("PayloadT", bound=ReviewModel)


class ClinicalProgressionReview(ReviewModel, Generic[PayloadT]):
    schema_version: Version = 1
    review_id: Identifier
    criterion_id: Identifier
    criterion_version: Version
    profile_id: Identifier
    policy_version: Version
    policy_hash: Digest
    athlete_id: Identifier
    injury_id: Identifier
    injury_episode_id: Identifier
    side: Literal["left", "right", "bilateral"]
    transition: ReviewTransition
    reviewed_at: AwareDatetime
    recorded_at: AwareDatetime
    evidence: ReviewedEvidencePacket
    clinical_author: ClinicalAuthor
    provenance: ReviewProvenance
    decision: ReviewDecision
    interpretation: PayloadT
    selected_prescription: ReviewedPrescriptionSelection | None = None
    rationale: Identifier
    structured_reasons: tuple[Identifier, ...] = Field(min_length=1)
    supersedes_review_id: Identifier | None = None
    valid_until: AwareDatetime | None = None
    expiry_reason: Identifier | None = None

    @model_validator(mode="after")
    def lifecycle(self):
        if self.supersedes_review_id == self.review_id:
            raise ValueError("a review cannot supersede itself")
        if bool(self.valid_until) != bool(self.expiry_reason):
            raise ValueError("expiry needs an explicit clinical/evidence reason")
        if self.valid_until and self.valid_until <= self.reviewed_at:
            raise ValueError("expiry must follow the clinical review")
        return self


class ReviewLifecycleChange(ReviewModel):
    schema_version: Version = 1
    lifecycle_id: Identifier
    review_id: Identifier
    state: ReviewLifecycleState
    effective_at: AwareDatetime
    recorded_at: AwareDatetime
    provenance: ReviewProvenance
    replacement_review_id: Identifier | None = None
    reason: Identifier

    @model_validator(mode="after")
    def replacement(self):
        if (self.state == ReviewLifecycleState.SUPERSEDED) != (self.replacement_review_id is not None):
            raise ValueError("only supersession identifies a replacement")
        if self.replacement_review_id == self.review_id:
            raise ValueError("self supersession is invalid")
        return self


class CriterionStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class ClinicalCriterionResult(ReviewModel):
    status: CriterionStatus
    reason_codes: tuple[Identifier, ...] = Field(min_length=1)


@dataclass(frozen=True)
class CriterionReviewDefinition(Generic[PayloadT]):
    criterion_id: str
    version: int
    profile_ids: frozenset[str]
    transition: ReviewTransition
    payload_type: type[PayloadT]
    clinical_scope: str
    options: tuple[ReviewedPrescriptionOption, ...]
    evaluate: Callable[[PayloadT], ClinicalCriterionResult]
    requires_prescription: bool = True
    evaluate_review: Callable[[ClinicalProgressionReview, ReviewValidityContext], ClinicalCriterionResult] | None = None

    def __post_init__(self):
        if (not self.criterion_id or type(self.version) is not int or self.version < 1
                or not self.profile_ids or not self.clinical_scope
                or not issubclass(self.payload_type, ReviewModel) or self.payload_type is ReviewModel
                or not callable(self.evaluate)
                or (self.evaluate_review is not None and not callable(self.evaluate_review))):
            raise ValueError("criterion needs a strict typed payload and compiled evaluator")
        if len({o.option_id for o in self.options}) != len(self.options):
            raise ValueError("duplicate reviewed option identity")
        if any((o.criterion_id, o.criterion_version, o.transition) != (self.criterion_id, self.version, self.transition)
               or o.profile_id not in self.profile_ids for o in self.options):
            raise ValueError("option must belong to its compiled criterion binding")


class CriterionReviewRegistry:
    """Immutable, code-owned definitions. Historical versions may coexist."""
    def __init__(self, definitions: tuple[CriterionReviewDefinition, ...] = ()):
        by_key = {(d.criterion_id, d.version): d for d in definitions}
        if len(by_key) != len(definitions):
            raise ValueError("duplicate criterion/version binding")
        self._definitions = MappingProxyType(by_key)

    def get(self, criterion_id: str, version: int) -> CriterionReviewDefinition | None:
        return self._definitions.get((criterion_id, version))

    def current(self, criterion_id: str) -> CriterionReviewDefinition | None:
        """Highest compiled version for current capture; older versions remain replayable."""
        return max((d for d in self._definitions.values() if d.criterion_id == criterion_id),
                   key=lambda d: d.version, default=None)

    def parse(self, raw: Mapping | ClinicalProgressionReview) -> ClinicalProgressionReview:
        value = raw.model_dump(mode="python") if isinstance(raw, ClinicalProgressionReview) else raw
        definition = self.get(value.get("criterion_id"), value.get("criterion_version"))
        if definition is None:
            raise ValueError("unregistered clinical criterion/version")
        return ClinicalProgressionReview[definition.payload_type].model_validate(value)


class ReviewTrustPolicy(Protocol):
    """Server-side policy over exact bytes/identity, never deserialised from a review."""
    def review_trusted(self, review: ClinicalProgressionReview, *, as_of: datetime) -> bool: ...

    def lifecycle_trusted(self, change: ReviewLifecycleChange, *, as_of: datetime) -> bool: ...


class UnsupportedReviewTrust:
    def review_trusted(self, review: ClinicalProgressionReview, *, as_of: datetime) -> bool:
        return False

    def lifecycle_trusted(self, change: ReviewLifecycleChange, *, as_of: datetime) -> bool:
        return False


# Pure callers still default to unsupported trust. This compiled shadow binding
# cannot activate a closed transition or create a live prescription.
CLINICAL_REVIEW_REGISTRY = CriterionReviewRegistry((achilles_review_definition(),))
UNSUPPORTED_REVIEW_TRUST = UnsupportedReviewTrust()
