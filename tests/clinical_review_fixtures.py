"""Two invented test protocols and byte-bound trust; never production content."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal

from api.contracts.clinical_progression_review import (
    ClinicalCriterionResult, ClinicalProgressionReview, CriterionReviewDefinition, CriterionReviewRegistry,
    ReviewLifecycleChange,
)
from api.contracts.clinical_review_validity import ClinicalReviewInput, ReviewValidityContext, evaluate_clinical_review
from api.contracts.reviewed_prescription import (
    ReviewModel, ReviewedPrescriptionOption, ReviewedPrescriptionSelection, ReviewTransition, materialised_selection_hash,
)
from fightcamp.rehab_clinical import content_hash

START = datetime(2026, 10, 1, tzinfo=timezone.utc)
CUTOFF = START + timedelta(days=1)
REVIEWED = CUTOFF + timedelta(hours=1)
RECORDED = REVIEWED + timedelta(hours=1)
NOW = RECORDED + timedelta(hours=1)
TRANSITION = ReviewTransition(from_stage="restore", to_stage="load")


class SyntheticControlInterpretation(ReviewModel):
    applicability: Literal["applicable", "not_applicable", "unknown"]
    selected_task_adequacy: Literal["adequate", "inadequate", "unknown"]


class SyntheticTendonInterpretation(ReviewModel):
    subtype: Literal["invented_tendon_a", "invented_tendon_b", "unknown"]
    reviewed_response: Literal["adequate", "inadequate", "unknown"]


def control_criterion(payload: SyntheticControlInterpretation) -> ClinicalCriterionResult:
    status = "unknown" if "unknown" in (payload.applicability, payload.selected_task_adequacy) else (
        "pass" if payload.applicability == "applicable" and payload.selected_task_adequacy == "adequate" else "fail")
    return ClinicalCriterionResult(status=status, reason_codes=("synthetic_control_interpretation",))


def tendon_criterion(payload: SyntheticTendonInterpretation) -> ClinicalCriterionResult:
    status = "unknown" if "unknown" in (payload.subtype, payload.reviewed_response) else (
        "pass" if payload.subtype == "invented_tendon_a" and payload.reviewed_response == "adequate" else "fail")
    return ClinicalCriterionResult(status=status, reason_codes=("synthetic_tendon_interpretation",))


@dataclass(frozen=True)
class SyntheticAttestations:
    """Exact bytes separately attested in memory. Nothing in a review grants trust."""
    review_hashes: frozenset[str] = frozenset()
    lifecycle_hashes: frozenset[str] = frozenset()

    def review_trusted(self, review, *, as_of):
        return review.recorded_at <= as_of and content_hash(review.model_dump(mode="json")) in self.review_hashes

    def lifecycle_trusted(self, change, *, as_of):
        return change.recorded_at <= as_of and content_hash(change.model_dump(mode="json")) in self.lifecycle_hashes

    @classmethod
    def attest(cls, reviews=(), lifecycle=()):
        return cls(frozenset(content_hash(r.model_dump(mode="json")) for r in reviews),
                   frozenset(content_hash(c.model_dump(mode="json")) for c in lifecycle))


def provenance(stamp=REVIEWED):
    return dict(source="independently_confirmed_clinician_statement",
                recorder=dict(actor_id="test-admin", role="operational_recorder"),
                verifier=dict(actor_id="test-verifier", role="operational_recorder"),
                confirmed_at=stamp, confirmation_reference="opaque-test-confirmation",
                statement_hash=content_hash("test-only-clinician-statement"))


def selection_for(option):
    # All numeric choices are invented fixture values, not clinical guidance.
    selection = ReviewedPrescriptionSelection(option_id=option.option_id, option_version=option.option_version,
        option_hash=option.option_hash, drill_id=option.drill_id, bank_hash=option.bank_hash,
        range_choice=option.range_choices[0], resistance=dict(mode="bodyweight"),
        dose=option.dose_choices[0], cadence=option.cadence_choices[0],
        restrictions=tuple(sorted(option.mandatory_restrictions)), materialised_prescription_hash="0" * 64)
    return selection.model_copy(update={"materialised_prescription_hash": materialised_selection_hash(option, selection)})


def protocol(second=False):
    profile = "test_tendon_profile" if second else "test_control_profile"
    criterion = "test_tendon_criterion" if second else "test_control_criterion"
    option = ReviewedPrescriptionOption(option_id=f"{profile}_option", option_version=1,
        profile_id=profile, criterion_id=criterion, criterion_version=1, transition=TRANSITION,
        drill_id=f"{profile}_drill", bank_hash=content_hash(dict(id=f"{profile}_drill", mechanics="test-only")),
        instructions="Invented test mechanics.", range_choices=("test_range_a", "test_range_b"),
        resistance_rules=(dict(mode="bodyweight"), dict(mode="external_kg", minimum_kg=1.0, maximum_kg=2.0)),
        dose_choices=(dict(sets=1, reps=3), dict(sets=1, reps=4)),
        cadence_choices=(dict(frequency="daily", minimum_gap_days=1),),
        mandatory_restrictions=("test_stop_rule",), allowed_restrictions=("test_stop_rule", "test_extra_limit"))
    definition = CriterionReviewDefinition(criterion_id=criterion, version=1, profile_ids=frozenset({profile}),
        transition=TRANSITION, payload_type=SyntheticTendonInterpretation if second else SyntheticControlInterpretation,
        clinical_scope="test_tendon_scope" if second else "test_control_scope", options=(option,),
        evaluate=tendon_criterion if second else control_criterion)
    return definition


REGISTRY = CriterionReviewRegistry((protocol(), protocol(True)))


def bundle(second=False):
    definition = protocol(second)
    option = definition.options[0]
    context = ReviewValidityContext(athlete_id="test-athlete", injury_id="test-injury", injury_episode_id="test-episode",
        side="left", profile_id=option.profile_id, policy_version=1, policy_hash=content_hash("test-policy"),
        criterion_id=definition.criterion_id, criterion_version=1, transition=TRANSITION, episode_started_at=START,
        episode_current=True, history_complete=True,
        current_packet=dict(evidence_cutoff=CUTOFF, packet_revision=content_hash("test-packet"),
            safety_revision=content_hash("test-safety"), references=(dict(event_id="test-observation", protocol_id="test-protocol",
                protocol_version=1, content_hash=content_hash("test-evidence"), observed_at=CUTOFF, recorded_at=CUTOFF),)),
        bank=(dict(drill_id=option.drill_id, bank_hash=option.bank_hash),))
    interpretation = (dict(subtype="invented_tendon_a", reviewed_response="adequate") if second else
                      dict(applicability="applicable", selected_task_adequacy="adequate"))
    review = ClinicalProgressionReview[definition.payload_type](schema_version=1, review_id="test-review",
        **{k: getattr(context, k) for k in ("athlete_id", "injury_id", "injury_episode_id", "side", "profile_id",
            "policy_version", "policy_hash", "criterion_id", "criterion_version", "transition")},
        reviewed_at=REVIEWED, recorded_at=RECORDED, evidence=context.current_packet,
        clinical_author=dict(author_id="test-clinician", display_name="Synthetic qualified author",
            qualification_reference="test-only-registration", clinical_scopes=(definition.clinical_scope,)),
        provenance=provenance(), decision="approved", interpretation=interpretation,
        selected_prescription=selection_for(option), rationale="Invented test decision.", structured_reasons=("test_reason",))
    return ClinicalReviewInput(context, (review,), registry=REGISTRY, trust=SyntheticAttestations.attest((review,)))


def evaluate(supplied=None, *, as_of=NOW):
    supplied = supplied or bundle()
    return evaluate_clinical_review(supplied.context, supplied.reviews, as_of=as_of, lifecycle=supplied.lifecycle,
                                   registry=supplied.registry, trust=supplied.trust)


def changed_review(supplied, *, attest=True, **changes):
    old = supplied.reviews[-1]
    raw = old.model_dump(mode="python") | changes
    definition = supplied.registry.get(old.criterion_id, old.criterion_version)
    review = ClinicalProgressionReview[definition.payload_type].model_validate(raw)
    return replace(supplied, reviews=(review,), trust=SyntheticAttestations.attest((review,)) if attest else supplied.trust)


def lifecycle_change(supplied, state="revoked", stamp=NOW):
    return ReviewLifecycleChange(lifecycle_id="test-change", review_id=supplied.reviews[0].review_id,
        state=state, effective_at=stamp, recorded_at=stamp, provenance=provenance(stamp),
        replacement_review_id="test-next-replacement" if state == "superseded" else None, reason="Test-only withdrawal.")
