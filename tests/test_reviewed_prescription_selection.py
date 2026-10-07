"""Reviewed options cannot be expanded or substituted by selection bytes."""
from dataclasses import replace
from math import inf, nan

import pytest
from pydantic import ValidationError

from api.contracts.clinical_review_validity import ReviewReason
from api.contracts.reviewed_prescription import (
    PrescriptionReason, ResistanceRule, ReviewedPrescriptionSelection, materialised_selection_hash,
    validate_prescription_selection,
)
from tests.clinical_review_fixtures import bundle, changed_review, evaluate, protocol


@pytest.mark.parametrize("changes,reason", [
    (dict(option_id="out-of-registry"), PrescriptionReason.OPTION_MISSING),
    (dict(option_version=2), PrescriptionReason.OPTION_CHANGED),
    (dict(option_hash="f" * 64), PrescriptionReason.OPTION_CHANGED),
    (dict(drill_id="arbitrary-bank-drill"), PrescriptionReason.DRILL_CHANGED),
    (dict(bank_hash="f" * 64), PrescriptionReason.DRILL_CHANGED),
    (dict(range_choice="unreviewed-depth"), PrescriptionReason.RANGE),
    (dict(resistance=dict(mode="external_kg", kg=3.0)), PrescriptionReason.RESISTANCE),
    (dict(dose=dict(sets=1, reps=999)), PrescriptionReason.DOSE),
    (dict(cadence=dict(frequency="daily", minimum_gap_days=2)), PrescriptionReason.CADENCE),
    (dict(restrictions=("test_extra_limit",)), PrescriptionReason.RESTRICTIONS),
    (dict(restrictions=("arbitrary_clear_contact", "test_stop_rule")), PrescriptionReason.RESTRICTIONS),
    (dict(materialised_prescription_hash="e" * 64), PrescriptionReason.MATERIALISATION),
    (dict(selection_version=2), PrescriptionReason.MATERIALISATION),
])
def test_unreviewed_or_tampered_selection_is_rejected(changes, reason):
    supplied = bundle()
    selected = ReviewedPrescriptionSelection.model_validate(supplied.reviews[0].selected_prescription.model_dump() | changes)
    supplied = changed_review(supplied, selected_prescription=selected)
    result = evaluate(supplied)
    assert result.prescription_valid is False and reason in result.reason_codes
    assert result.criterion_status != "pass"


@pytest.mark.parametrize("kg", [1.0, 1.5, 2.0])
def test_explicit_reviewed_resistance_bounds(kg):
    supplied = bundle()
    option = protocol().options[0]
    selection = ReviewedPrescriptionSelection.model_validate(supplied.reviews[0].selected_prescription.model_dump() |
        dict(resistance=dict(mode="external_kg", kg=kg)))
    selection = selection.model_copy(update={"materialised_prescription_hash": materialised_selection_hash(option, selection)})
    assert evaluate(changed_review(supplied, selected_prescription=selection)).criterion_status == "pass"


def test_allowed_choice_is_still_a_new_selection_hash_and_review():
    supplied = bundle()
    option = protocol().options[0]
    old = supplied.reviews[0].selected_prescription
    changed = old.model_copy(update={"dose": option.dose_choices[1]})
    assert PrescriptionReason.MATERIALISATION in evaluate(changed_review(supplied, selected_prescription=changed)).reason_codes
    changed = changed.model_copy(update={"materialised_prescription_hash": materialised_selection_hash(option, changed)})
    assert changed.materialised_prescription_hash != old.materialised_prescription_hash
    assert evaluate(changed_review(supplied, selected_prescription=changed)).criterion_status == "pass"


@pytest.mark.parametrize("change", ["option_version", "mechanics", "bounds", "bank"])
def test_changed_option_or_bank_does_not_silently_reuse_approval(change):
    supplied = bundle()
    definition = protocol()
    option = definition.options[0]
    context = supplied.context
    if change == "option_version":
        option = option.model_copy(update={"option_version": 2})
    elif change == "mechanics":
        option = option.model_copy(update={"instructions": "Changed unilateral/bilateral mechanics."})
    elif change == "bounds":
        option = option.model_copy(update={"range_choices": ("changed_range",)})
    else:
        context = context.model_copy(update={"bank": (context.bank[0].model_copy(update={"bank_hash": "e" * 64}),)})
    from api.contracts.clinical_progression_review import CriterionReviewRegistry
    registry = CriterionReviewRegistry((replace(definition, options=(option,)),))
    result = evaluate(replace(supplied, context=context, registry=registry))
    assert result.criterion_status != "pass" and result.prescription_valid is False
    assert (PrescriptionReason.DRILL_CHANGED if change == "bank" else PrescriptionReason.OPTION_CHANGED) in result.reason_codes


def test_option_applies_to_exact_criterion_profile_and_transition():
    supplied = bundle()
    option = protocol(True).options[0]
    context = supplied.context
    result = validate_prescription_selection(supplied.reviews[0].selected_prescription, option,
        profile_id=context.profile_id, criterion_id=context.criterion_id, criterion_version=context.criterion_version,
        transition=context.transition, current_bank_hash=option.bank_hash)
    assert not result.valid and PrescriptionReason.OPTION_BINDING in result.reason_codes


def test_no_option_and_no_prescription_approval_remain_closed():
    supplied = bundle()
    assert ReviewReason.PRESCRIPTION in evaluate(changed_review(supplied, selected_prescription=None)).reason_codes
    from api.contracts.clinical_progression_review import CriterionReviewRegistry
    registry = CriterionReviewRegistry((replace(protocol(), options=()),))
    assert PrescriptionReason.OPTION_MISSING in evaluate(replace(supplied, registry=registry)).reason_codes


@pytest.mark.parametrize("kg", [nan, inf, -inf, -1.0, True])
def test_nonfinite_negative_or_boolean_resistance_is_invalid(kg):
    raw = bundle().reviews[0].selected_prescription.model_dump()
    with pytest.raises(ValidationError):
        ReviewedPrescriptionSelection.model_validate(raw | dict(resistance=dict(mode="external_kg", kg=kg)))


@pytest.mark.parametrize("raw", [dict(mode="external_kg"), dict(mode="bodyweight", minimum_kg=1.0),
    dict(mode="external_kg", minimum_kg=2.0, maximum_kg=1.0)])
def test_reviewed_bounds_must_be_explicit_and_coherent(raw):
    with pytest.raises(ValidationError):
        ResistanceRule.model_validate(raw)


def test_no_unrestricted_text_or_hidden_movement_parameters():
    raw = bundle().reviews[0].selected_prescription.model_dump()
    for field in ("instructions", "movement_substitution", "clinical_notes", "contact_clearance"):
        with pytest.raises(ValidationError):
            ReviewedPrescriptionSelection.model_validate(raw | {field: "unreviewed"})


def test_direct_pure_validator_rechecks_model_copy_bypasses():
    supplied = bundle()
    context = supplied.context
    option = protocol().options[0]
    selected = supplied.reviews[0].selected_prescription.model_copy(update={"selection_version": True})
    result = validate_prescription_selection(selected, option, profile_id=context.profile_id,
        criterion_id=context.criterion_id, criterion_version=context.criterion_version,
        transition=context.transition, current_bank_hash=option.bank_hash)
    assert not result.valid and result.reason_codes == (PrescriptionReason.MALFORMED,)
