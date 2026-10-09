"""Pure review replay, invalidation and future frozen-work safety decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Mapping

from pydantic import AwareDatetime, Field

from .clinical_progression_review import (
    CLINICAL_REVIEW_REGISTRY, UNSUPPORTED_REVIEW_TRUST, ClinicalProgressionReview,
    CriterionReviewRegistry, CriterionStatus, ReviewDecision, ReviewedEvidencePacket,
    ReviewLifecycleChange, ReviewLifecycleState, ReviewSource, ReviewTrustPolicy,
)
from .rehab_assessment import instant
from .reviewed_prescription import (
    Digest, Identifier, PrescriptionReason, ReviewModel, ReviewTransition, Version,
    validate_prescription_selection,
)


class ReviewReason(str, Enum):
    MISSING = "clinical_review_missing"
    MALFORMED = "clinical_review_malformed"
    ATHLETE = "review_athlete_mismatch"
    INJURY = "review_injury_mismatch"
    EPISODE = "review_episode_mismatch"
    SIDE = "review_side_mismatch"
    PROFILE = "review_profile_mismatch"
    CRITERION = "review_criterion_mismatch"
    CRITERION_VERSION = "review_criterion_version_mismatch"
    SCHEMA_VERSION = "review_schema_version_unsupported"
    TRANSITION = "review_transition_mismatch"
    POLICY = "review_policy_version_or_hash_mismatch"
    NOT_REGISTERED = "review_criterion_not_registered"
    EPISODE_CLOSED = "review_episode_not_current"
    HISTORY = "review_history_incomplete"
    FUTURE = "review_future_timestamp"
    CHRONOLOGY = "review_chronology_invalid"
    BEFORE_EPISODE = "review_before_episode"
    PACKET = "review_evidence_packet_mismatch"
    SETBACK = "review_invalidated_by_setback"
    MEDICAL_HOLD = "review_invalidated_by_medical_hold"
    RESTRICTION = "review_invalidated_by_restriction"
    ASSESSMENT = "review_invalidated_by_new_assessment"
    CLEARANCE = "review_invalidated_by_clearance_change"
    PROVENANCE = "review_provenance_incomplete_or_malformed"
    ACTORS = "review_actor_separation_invalid"
    QUALIFICATION = "review_author_scope_mismatch"
    TRUST = "review_trust_channel_unsupported_or_unconfirmed"
    DUPLICATE = "review_duplicate_or_conflicting_identity"
    CONFLICT = "review_supersession_history_conflict"
    REVOKED = "review_revoked"
    SUPERSEDED = "review_superseded"
    LIFECYCLE = "review_lifecycle_malformed_or_untrusted"
    EXPIRED = "review_expired"
    PRESCRIPTION = "review_required_prescription_missing"
    ENGINE_CONTEXT = "review_engine_context_mismatch"


class ReviewSafetyEvent(ReviewModel):
    event_id: Identifier
    athlete_id: Identifier
    injury_id: Identifier
    injury_episode_id: Identifier
    side: Literal["left", "right", "bilateral"]
    kind: Literal["setback", "medical_hold", "restriction", "assessment", "clearance_change"]
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime


class ReviewBankSnapshot(ReviewModel):
    drill_id: Identifier
    bank_hash: Digest


class ReviewValidityContext(ReviewModel):
    athlete_id: Identifier
    injury_id: Identifier
    injury_episode_id: Identifier
    side: Literal["left", "right", "bilateral", "unknown"]
    profile_id: Identifier
    policy_version: Version
    policy_hash: Digest
    criterion_id: Identifier
    criterion_version: Version
    transition: ReviewTransition
    episode_started_at: AwareDatetime
    episode_current: bool = Field(strict=True)
    history_complete: bool = Field(strict=True)
    current_packet: ReviewedEvidencePacket
    bank: tuple[ReviewBankSnapshot, ...]
    safety_history: tuple[ReviewSafetyEvent, ...] = ()
    medical_hold: bool = Field(default=False, strict=True)
    restriction_hold: bool = Field(default=False, strict=True)
    # Complete server-owned assessment event bytes, using the existing protocol
    # readers. Never populated from a clinician capture request.
    assessment_events: tuple[dict, ...] = ()


class FrozenClinicalReviewPin(ReviewModel):
    review_id: Identifier
    criterion_id: Identifier
    criterion_version: Version
    option_id: Identifier
    option_version: Version
    selection_version: Version
    materialised_prescription_hash: Digest


class ReviewEvaluation(ReviewModel):
    evaluated_at: AwareDatetime
    review_id: Identifier | None = None
    validity: Literal["valid", "invalid"]
    trusted: bool
    clinical_decision: ReviewDecision | None = None
    criterion_status: CriterionStatus
    prescription_valid: bool | None = None
    reason_codes: tuple[ReviewReason | PrescriptionReason | Identifier, ...] = Field(min_length=1)
    pin: FrozenClinicalReviewPin | None = None


def _actor_reasons(review: ClinicalProgressionReview, definition) -> list[ReviewReason]:
    author, provenance = review.clinical_author, review.provenance
    actors = (provenance.recorder, provenance.verifier)
    reasons = []
    if (author.author_id == review.athlete_id
            or any(a and (a.role == "athlete" or a.actor_id == review.athlete_id) for a in actors)
            or any(a and a.role == "operational_recorder" and a.actor_id == author.author_id for a in actors)
            or (provenance.verifier and (provenance.verifier.actor_id == author.author_id
                                        or provenance.verifier.role == "clinical_author"))
            or (provenance.recorder.role == "provider_service" and provenance.recorder.actor_id == author.author_id)
            or (provenance.recorder.role == "clinical_author" and
                (provenance.recorder.actor_id != author.author_id or provenance.source != ReviewSource.CLINICIAN_DIRECT))):
        reasons.append(ReviewReason.ACTORS)
    if definition and definition.clinical_scope not in author.clinical_scopes:
        reasons.append(ReviewReason.QUALIFICATION)
    if (provenance.source == ReviewSource.ATHLETE_REPORTED or provenance.verifier is None
            or not provenance.confirmed_at or not provenance.confirmation_reference or not provenance.statement_hash
            or (provenance.source in {ReviewSource.INDEPENDENT_CONFIRMATION, ReviewSource.DOCUMENT_VERIFICATION}
                and provenance.verifier.role != "operational_recorder")):
        reasons.append(ReviewReason.PROVENANCE)
    return reasons


def _raw(value):
    return value.model_dump(mode="python") if isinstance(value, ClinicalProgressionReview) else value


def evaluate_clinical_review(context: ReviewValidityContext, reviews: tuple[Mapping | ClinicalProgressionReview, ...], *,
                             as_of: datetime, lifecycle: tuple[ReviewLifecycleChange, ...] = (),
                             registry: CriterionReviewRegistry = CLINICAL_REVIEW_REGISTRY,
                             trust: ReviewTrustPolicy = UNSUPPORTED_REVIEW_TRUST) -> ReviewEvaluation:
    """Use the latest whole record, never an older best approval.

    Caller supplies exact scoped history and the policy/packet/bank snapshot for
    replay. Unknown newest bytes, conflicts or unknown lifecycle fail closed.
    No current clock, database, injury mutation or stage decision is involved.
    """
    if instant(as_of) is None:
        raise ValueError("review replay requires an aware explicit as_of")
    reasons = []

    def invalid(review=None, *, trusted=False, prescription_valid=None, pin=None):
        return ReviewEvaluation(evaluated_at=as_of, review_id=review.review_id if review else None,
            validity="invalid", trusted=trusted, clinical_decision=review.decision if review else None,
            criterion_status=CriterionStatus.UNKNOWN, prescription_valid=prescription_valid,
            reason_codes=tuple(dict.fromkeys(reasons)), pin=pin)

    if not context.history_complete:
        reasons.append(ReviewReason.HISTORY)
    if not context.episode_current:
        reasons.append(ReviewReason.EPISODE_CLOSED)
    if context.episode_started_at > as_of or context.current_packet.evidence_cutoff > as_of:
        reasons.append(ReviewReason.FUTURE)
    if context.medical_hold:
        reasons.append(ReviewReason.MEDICAL_HOLD)
    if context.restriction_hold:
        reasons.append(ReviewReason.RESTRICTION)
    definition = registry.get(context.criterion_id, context.criterion_version)
    if definition is None:
        reasons.append(ReviewReason.NOT_REGISTERED)
    candidates = []
    for value in reviews:
        raw = _raw(value)
        if not isinstance(raw, Mapping) or instant(raw.get("recorded_at")) is None:
            reasons.append(ReviewReason.MALFORMED)
            return invalid()
        if instant(raw["recorded_at"]) <= as_of:
            candidates.append(raw)
    if not candidates:
        reasons.append(ReviewReason.FUTURE if reviews else ReviewReason.MISSING)
        return invalid()
    if any(not isinstance(r.get("review_id"), str) or not r["review_id"].strip() for r in candidates):
        reasons.append(ReviewReason.MALFORMED)
        return invalid()
    if len({r.get("review_id") for r in candidates}) != len(candidates):
        reasons.append(ReviewReason.DUPLICATE)
        return invalid()
    candidates.sort(key=lambda r: instant(r["recorded_at"]))
    if any(instant(a["recorded_at"]) == instant(b["recorded_at"]) for a, b in zip(candidates, candidates[1:])):
        reasons.append(ReviewReason.CONFLICT)
        return invalid()
    raw = candidates[-1]
    for field, reason in (("athlete_id", ReviewReason.ATHLETE), ("injury_id", ReviewReason.INJURY),
                         ("injury_episode_id", ReviewReason.EPISODE), ("side", ReviewReason.SIDE),
                         ("profile_id", ReviewReason.PROFILE), ("criterion_id", ReviewReason.CRITERION),
                         ("criterion_version", ReviewReason.CRITERION_VERSION), ("policy_version", ReviewReason.POLICY),
                         ("policy_hash", ReviewReason.POLICY)):
        if raw.get(field) != getattr(context, field):
            reasons.append(reason)
    if raw.get("schema_version", 1) != 1:
        reasons.append(ReviewReason.SCHEMA_VERSION)
    try:
        review = registry.parse(raw)
    except (ValueError, TypeError, KeyError):
        reasons.append(ReviewReason.MALFORMED)
        return invalid()
    if review.transition != context.transition or (definition and (
            context.profile_id not in definition.profile_ids or definition.transition != context.transition)):
        reasons.append(ReviewReason.TRANSITION)
    if review.evidence != context.current_packet:
        reasons.append(ReviewReason.PACKET)
    confirmed = review.provenance.confirmed_at
    if review.reviewed_at > as_of or (confirmed and confirmed > as_of):
        reasons.append(ReviewReason.FUTURE)
    if (not review.evidence.evidence_cutoff <= review.reviewed_at <= review.recorded_at
            or (confirmed and not review.reviewed_at <= confirmed <= review.recorded_at)):
        reasons.append(ReviewReason.CHRONOLOGY)
    if (review.reviewed_at < context.episode_started_at or review.evidence.evidence_cutoff < context.episode_started_at
            or any(r.observed_at < context.episode_started_at for r in review.evidence.references)):
        reasons.append(ReviewReason.BEFORE_EPISODE)
    if review.valid_until and as_of >= review.valid_until:
        reasons.append(ReviewReason.EXPIRED)
    if candidates[0].get("supersedes_review_id"):
        reasons.append(ReviewReason.CONFLICT)
    if len(candidates) > 1:
        if any(current.get("supersedes_review_id") != previous.get("review_id")
               for previous, current in zip(candidates, candidates[1:])):
            reasons.append(ReviewReason.CONFLICT)
        # A replacement cannot inherit a foreign review chain.
        scope_fields = ("athlete_id", "injury_id", "injury_episode_id", "side", "profile_id", "criterion_id", "transition")
        if any(any(c.get(k) != raw.get(k) for k in scope_fields) for c in candidates[:-1]):
            reasons.append(ReviewReason.CONFLICT)
    elif review.supersedes_review_id:
        reasons.append(ReviewReason.CONFLICT)
    reasons.extend(_actor_reasons(review, definition))
    trusted = trust.review_trusted(review, as_of=as_of) is True
    if not trusted:
        reasons.append(ReviewReason.TRUST)
    safety_reasons = {"setback": ReviewReason.SETBACK, "medical_hold": ReviewReason.MEDICAL_HOLD,
                      "restriction": ReviewReason.RESTRICTION, "assessment": ReviewReason.ASSESSMENT,
                      "clearance_change": ReviewReason.CLEARANCE}
    for event in context.safety_history:
        if event.recorded_at > as_of:
            continue
        if (event.athlete_id, event.injury_id, event.injury_episode_id, event.side) != (
                context.athlete_id, context.injury_id, context.injury_episode_id, context.side):
            reasons.append(ReviewReason.HISTORY)
        elif event.occurred_at > event.recorded_at:
            reasons.append(ReviewReason.CHRONOLOGY)
        elif event.kind in {"setback", "medical_hold", "restriction"}:
            # Later recording cannot freshen an old clinical judgment. Both
            # clinical time and complete packet chronology are significant.
            if event.occurred_at >= review.reviewed_at or event.recorded_at > review.evidence.evidence_cutoff:
                reasons.append(safety_reasons[event.kind])
            elif event.kind == "setback" and any(r.observed_at <= event.occurred_at for r in review.evidence.references):
                reasons.append(ReviewReason.SETBACK)
        elif event.recorded_at > review.evidence.evidence_cutoff:
            reasons.append(safety_reasons[event.kind])
    seen_lifecycle = set()
    for value in lifecycle:
        # Revalidate even typed inputs: model_copy must not bypass validation.
        try:
            change = ReviewLifecycleChange.model_validate(value.model_dump(mode="python"))
        except (ValueError, TypeError, AttributeError):
            reasons.append(ReviewReason.LIFECYCLE)
            continue
        if change.recorded_at > as_of:
            continue
        target = next((r for r in candidates if r.get("review_id") == change.review_id), None)
        provenance = change.provenance
        malformed_provenance = (provenance.source == ReviewSource.ATHLETE_REPORTED
            or not provenance.confirmed_at or not provenance.confirmation_reference or not provenance.statement_hash
            or provenance.verifier is None
            or any(a and (a.role == "athlete" or a.actor_id == context.athlete_id)
                   for a in (provenance.recorder, provenance.verifier))
            or (provenance.confirmed_at and not change.effective_at <= provenance.confirmed_at <= change.recorded_at))
        if (change.schema_version != 1 or change.lifecycle_id in seen_lifecycle or target is None
                or change.effective_at > change.recorded_at
                or (target and change.effective_at < instant(target["recorded_at"]))
                or malformed_provenance or trust.lifecycle_trusted(change, as_of=as_of) is not True):
            reasons.append(ReviewReason.LIFECYCLE)
        seen_lifecycle.add(change.lifecycle_id)
        if change.review_id == review.review_id:
            reasons.append(ReviewReason.REVOKED if change.state == ReviewLifecycleState.REVOKED else ReviewReason.SUPERSEDED)
        elif change.state == ReviewLifecycleState.SUPERSEDED:
            replacement = next((r for r in candidates if r.get("review_id") == change.replacement_review_id), None)
            if (replacement is None or replacement.get("supersedes_review_id") != change.review_id
                    or instant(replacement["recorded_at"]) < change.effective_at):
                reasons.append(ReviewReason.CONFLICT)
    prescription_valid, pin = None, None
    selection = review.selected_prescription
    if selection:
        bank = {b.drill_id: b.bank_hash for b in context.bank}
        if len(bank) != len(context.bank):
            reasons.append(ReviewReason.HISTORY)
        option = next((o for o in definition.options if o.option_id == selection.option_id), None) if definition else None
        validated = validate_prescription_selection(selection, option, profile_id=context.profile_id,
            criterion_id=context.criterion_id, criterion_version=context.criterion_version,
            transition=context.transition, current_bank_hash=bank.get(selection.drill_id))
        prescription_valid = validated.valid
        reasons.extend(validated.reason_codes)
        pin = FrozenClinicalReviewPin(review_id=review.review_id, criterion_id=review.criterion_id,
            criterion_version=review.criterion_version, option_id=selection.option_id,
            option_version=selection.option_version, selection_version=selection.selection_version,
            materialised_prescription_hash=selection.materialised_prescription_hash)
    elif definition and definition.requires_prescription and review.decision == ReviewDecision.APPROVED:
        prescription_valid = False
        reasons.append(ReviewReason.PRESCRIPTION)
    if reasons:
        return invalid(review, trusted=trusted, prescription_valid=prescription_valid, pin=pin)
    if review.decision == ReviewDecision.DEFERRED:
        status, codes = CriterionStatus.UNKNOWN, ("clinical_decision_deferred",)
    elif review.decision == ReviewDecision.NOT_APPROVED:
        status, codes = CriterionStatus.FAIL, ("clinical_decision_not_approved",)
    else:
        clinical = definition.evaluate(review.interpretation)
        if clinical.status == CriterionStatus.PASS and definition.evaluate_review is not None:
            clinical = definition.evaluate_review(review, context)
        status, codes = clinical.status, clinical.reason_codes
    return ReviewEvaluation(evaluated_at=as_of, review_id=review.review_id, validity="valid", trusted=trusted,
        clinical_decision=review.decision, criterion_status=status, prescription_valid=prescription_valid,
        reason_codes=codes, pin=pin)


@dataclass(frozen=True)
class ClinicalReviewInput:
    context: ReviewValidityContext
    reviews: tuple[Mapping | ClinicalProgressionReview, ...]
    lifecycle: tuple[ReviewLifecycleChange, ...] = ()
    registry: CriterionReviewRegistry = CLINICAL_REVIEW_REGISTRY
    trust: ReviewTrustPolicy = UNSUPPORTED_REVIEW_TRUST


class FrozenReviewSafety(ReviewModel):
    evaluated_at: AwareDatetime
    history_immutable: bool
    can_accept: bool
    safety_hold: bool
    reason_code: str


def evaluate_frozen_review(pin: FrozenClinicalReviewPin, evaluation: ReviewEvaluation, *,
                           work_state: Literal["unstarted", "started", "completed"], as_of: datetime) -> FrozenReviewSafety:
    """Prospective pure overlay. Never returns replacement content/exposure history."""
    if instant(as_of) is None or evaluation.evaluated_at != as_of:
        raise ValueError("frozen replay must use the same explicit aware as_of")
    if work_state not in {"unstarted", "started", "completed"}:
        raise ValueError("unknown frozen work state")
    usable = (evaluation.validity == "valid" and evaluation.trusted
              and evaluation.clinical_decision == ReviewDecision.APPROVED
              and evaluation.criterion_status == CriterionStatus.PASS
              and evaluation.prescription_valid is True and evaluation.pin == pin)
    return FrozenReviewSafety(evaluated_at=as_of, history_immutable=work_state != "unstarted",
        can_accept=work_state == "unstarted" and usable, safety_hold=work_state != "completed" and not usable,
        reason_code="completed_history_preserved" if work_state == "completed" else
                    "review_pin_current" if usable else "review_pin_invalidated_hold")
