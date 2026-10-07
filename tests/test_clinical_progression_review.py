"""Shared envelope, actors, versions and independent production trust boundary."""
from dataclasses import replace

import pytest
from pydantic import ValidationError

from api.contracts.clinical_progression_review import (
    CLINICAL_REVIEW_REGISTRY, UNSUPPORTED_REVIEW_TRUST, ClinicalProgressionReview, CriterionReviewRegistry,
    ReviewSource,
)
from api.contracts.clinical_review_validity import ReviewReason, evaluate_clinical_review
from tests.clinical_review_fixtures import (
    NOW, REGISTRY, SyntheticAttestations, SyntheticControlInterpretation, bundle, changed_review, evaluate, protocol,
)


@pytest.mark.parametrize("second", [False, True])
def test_two_protocols_share_envelope_and_validity(second):
    supplied = bundle(second)
    review = supplied.reviews[0]
    result = evaluate(supplied)
    assert result.validity == "valid" and result.trusted
    assert result.clinical_decision == "approved" and result.criterion_status == "pass"
    assert result.prescription_valid and result.pin.review_id == review.review_id
    assert REGISTRY.parse(review.model_dump(mode="json")) == review
    assert set(type(review).model_fields) == set(type(bundle(not second).reviews[0]).model_fields)
    assert result == evaluate(supplied)  # Explicit deterministic replay.


@pytest.mark.parametrize("decision,status", [("approved", "pass"), ("not_approved", "fail"), ("deferred", "unknown")])
def test_validity_is_distinct_from_decision_and_criterion(decision, status):
    supplied = changed_review(bundle(), decision=decision,
                              selected_prescription=bundle().reviews[0].selected_prescription if decision == "approved" else None)
    result = evaluate(supplied)
    assert result.validity == "valid" and result.trusted and result.clinical_decision == decision
    assert result.criterion_status == status


@pytest.mark.parametrize("adequacy,status", [("inadequate", "fail"), ("unknown", "unknown")])
def test_valid_trusted_approval_can_fail_clinical_interpretation(adequacy, status):
    supplied = changed_review(bundle(), interpretation=dict(applicability="applicable", selected_task_adequacy=adequacy))
    result = evaluate(supplied)
    assert result.validity == "valid" and result.clinical_decision == "approved"
    assert result.criterion_status == status


@pytest.mark.parametrize("source", list(ReviewSource))
def test_all_production_channels_are_currently_unsupported(source):
    supplied = bundle()
    supplied = changed_review(supplied, provenance=supplied.reviews[0].provenance.model_dump() | {"source": source})
    result = evaluate(replace(supplied, trust=UNSUPPORTED_REVIEW_TRUST))
    assert result.validity == "invalid" and not result.trusted and result.criterion_status != "pass"
    assert ReviewReason.TRUST in result.reason_codes
    assert CLINICAL_REVIEW_REGISTRY.get(supplied.context.criterion_id, 1) is None


@pytest.mark.parametrize("field,value", [("externally_verified", True), ("trusted", True), ("approved_stage", "load")])
def test_client_authority_flags_are_rejected(field, value):
    raw = bundle().reviews[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        REGISTRY.parse(raw | {field: value})
    with pytest.raises(ValidationError):
        REGISTRY.parse(raw | {"provenance": raw["provenance"] | {field: value}})


@pytest.mark.parametrize("field,value", [("schema_version", True), ("criterion_version", "1"), ("policy_version", 1.0),
                                          ("side", "unknown"), ("rationale", " ")])
def test_strict_envelope_rejects_malformed_identifiers(field, value):
    raw = bundle().reviews[0].model_dump(mode="json")
    with pytest.raises((ValueError, TypeError)):
        REGISTRY.parse(raw | {field: value})


def test_profile_specific_payload_must_match_registered_type():
    raw = bundle().reviews[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        REGISTRY.parse(raw | {"interpretation": {"arbitrary": {"clinically_passed": True}}})
    with pytest.raises(ValidationError):
        REGISTRY.parse(raw | {"interpretation": bundle(True).reviews[0].interpretation.model_dump()})
    with pytest.raises(ValidationError):
        SyntheticControlInterpretation(applicability="applicable", selected_task_adequacy="adequate", free_text_dose="anything")


@pytest.mark.parametrize("actor", ["athlete_author", "athlete_recorder", "athlete_verifier", "admin_author", "forged_author"])
def test_actor_separation_and_byte_bound_attestation(actor):
    supplied = bundle()
    review = supplied.reviews[0]
    author = review.clinical_author.model_dump()
    provenance = review.provenance.model_dump()
    if actor == "athlete_author":
        author["author_id"] = review.athlete_id
    elif actor == "athlete_recorder":
        provenance["recorder"] = dict(actor_id=review.athlete_id, role="athlete")
    elif actor == "athlete_verifier":
        provenance["verifier"] = dict(actor_id=review.athlete_id, role="operational_recorder")
    elif actor == "admin_author":
        author["author_id"] = provenance["recorder"]["actor_id"]
    else:
        author["author_id"] = "client-forged-clinician"
    supplied = changed_review(supplied, attest=False, clinical_author=author, provenance=provenance)
    result = evaluate(supplied)
    assert result.validity == "invalid" and result.criterion_status != "pass"
    assert ReviewReason.TRUST in result.reason_codes
    if actor != "forged_author":
        assert ReviewReason.ACTORS in result.reason_codes


def test_admin_cannot_become_clinical_author_even_with_synthetic_trust():
    supplied = bundle()
    author = supplied.reviews[0].clinical_author.model_dump() | {"author_id": "test-admin"}
    result = evaluate(changed_review(supplied, clinical_author=author))
    assert result.trusted and result.validity == "invalid" and ReviewReason.ACTORS in result.reason_codes


@pytest.mark.parametrize("missing", ["confirmed_at", "confirmation_reference", "statement_hash", "verifier"])
def test_incomplete_provenance_fails_closed(missing):
    supplied = bundle()
    provenance = supplied.reviews[0].provenance.model_dump() | {missing: None}
    assert ReviewReason.PROVENANCE in evaluate(changed_review(supplied, provenance=provenance)).reason_codes


def test_author_scope_is_not_admin_status():
    supplied = bundle()
    author = supplied.reviews[0].clinical_author.model_dump() | {"clinical_scopes": ("unrelated_scope",)}
    assert ReviewReason.QUALIFICATION in evaluate(changed_review(supplied, clinical_author=author)).reason_codes


def test_clinical_author_cannot_independently_verify_their_own_review():
    supplied = bundle()
    provenance = supplied.reviews[0].provenance.model_dump() | {
        "verifier": dict(actor_id="test-clinician", role="clinical_author")}
    assert ReviewReason.ACTORS in evaluate(changed_review(supplied, provenance=provenance)).reason_codes


def test_prescription_requirement_is_optional_per_compiled_criterion():
    supplied = bundle()
    registry = CriterionReviewRegistry((replace(protocol(), requires_prescription=False, options=()),))
    result = evaluate(changed_review(replace(supplied, registry=registry), selected_prescription=None))
    assert result.validity == "valid" and result.criterion_status == "pass" and result.prescription_valid is None


def test_registry_rejects_duplicate_and_mismatched_option_bindings():
    definition = protocol()
    with pytest.raises(ValueError, match="duplicate criterion"):
        CriterionReviewRegistry((definition, definition))
    with pytest.raises(ValueError, match="duplicate reviewed option"):
        replace(definition, options=definition.options * 2)
    with pytest.raises(ValueError, match="option must belong"):
        replace(definition, options=protocol(True).options)


def test_missing_registry_or_attestation_never_approves():
    supplied = bundle()
    assert ReviewReason.NOT_REGISTERED in evaluate(replace(supplied, registry=CLINICAL_REVIEW_REGISTRY)).reason_codes
    assert ReviewReason.TRUST in evaluate(replace(supplied, trust=SyntheticAttestations())).reason_codes
    # No default context/registry function silently trusts even a valid fixture.
    result = evaluate_clinical_review(supplied.context, supplied.reviews, as_of=NOW, registry=REGISTRY)
    assert result.validity == "invalid" and not result.trusted


def test_envelope_and_nested_selection_are_immutable():
    review = bundle().reviews[0]
    with pytest.raises(ValidationError):
        review.decision = "approved"
    with pytest.raises(ValidationError):
        review.selected_prescription.dose.reps = 100
    with pytest.raises(ValidationError):
        ClinicalProgressionReview[SyntheticControlInterpretation].model_validate(review.model_dump() | {"schema_version": "1"})


@pytest.mark.parametrize("field", ["schema_version", "criterion_version", "policy_version"])
def test_typed_review_model_copy_cannot_normalise_invalid_version(field):
    supplied = bundle()
    forged = supplied.reviews[0].model_copy(update={field: True})
    with pytest.raises(ValidationError):
        REGISTRY.parse(forged)
    result = evaluate(replace(supplied, reviews=(forged,)))
    assert result.validity == "invalid" and ReviewReason.MALFORMED in result.reason_codes
