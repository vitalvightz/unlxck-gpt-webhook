"""Midportion-only clinical interpretation and bounded, dormant LOAD option.

No pain/count readiness threshold or automated diagnosis. A trusted clinician
must interpret the exact observation and selected work; shared validity owns
authority, lifecycle, safety and prescription integrity. This never schedules.
"""
from __future__ import annotations

from typing import Literal

from fightcamp.rehab_clinical import content_hash

from .achilles_restore_load import REQUIRED_INPUTS, SOURCES
from .rehab_assessment import AssessmentContext, read_assessment_input
from .reviewed_prescription import (
    Digest, Identifier, ResistanceRule, ReviewModel, ReviewedCadence, ReviewedDose,
    ReviewedPrescriptionOption, ReviewTransition, Version,
)

CRITERION_ID = "achilles_restore_load_clinical_review_v1"
CRITERION_VERSION = 1
OPTION_ID = "achilles_midportion_floor_lowering_bodyweight_v1"
OPTION_VERSION = 1
CLINICAL_SCOPE = "qualified_msk_clinician_achilles_tendinopathy"
DOSE_SOURCE = "https://www.dynamichealth.nhs.uk/help-and-advice/foot-or-ankle-pain/ankle-tendon-pain/"
PILOT_SOURCES = (*SOURCES[:2], DOSE_SOURCE)
JUDGMENTS = (
    "diagnosis_applicable", "no_presumed_structural_frailty", "function_adequate",
    "loading_task_appropriate", "during_response_acceptable", "delayed_response_acceptable",
    "range_appropriate", "resistance_appropriate", "dose_appropriate", "cadence_appropriate",
    "no_incompatible_pathology", "no_preventing_restriction",
)
Judgment = Literal["supported", "not_supported", "unknown"]


class AchillesRestoreLoadInterpretationV1(ReviewModel):
    schema_version: Version = 1
    subtype: Literal["midportion", "insertional", "unknown"] = "unknown"
    assessment_event_id: Identifier | None = None
    assessment_content_hash: Digest | None = None
    selected_prescription_hash: Digest | None = None
    diagnosis_applicable: Judgment = "unknown"
    no_presumed_structural_frailty: Judgment = "unknown"
    function_adequate: Judgment = "unknown"
    loading_task_appropriate: Judgment = "unknown"
    during_response_acceptable: Judgment = "unknown"
    delayed_response_acceptable: Judgment = "unknown"
    range_appropriate: Judgment = "unknown"
    resistance_appropriate: Judgment = "unknown"
    dose_appropriate: Judgment = "unknown"
    cadence_appropriate: Judgment = "unknown"
    no_incompatible_pathology: Judgment = "unknown"
    no_preventing_restriction: Judgment = "unknown"


RESTRICTIONS = (
    "bodyweight_only_no_added_resistance",
    "floor_only_no_step_or_below_floor_dorsiflexion",
    "follow_clinician_restrictions_no_training_or_contact_clearance",
    "no_speed_bouncing_hopping_or_automatic_progression",
    "stable_support_controlled_lowering",
    "stop_for_worsening_during_or_delayed_symptoms_seek_review",
    "stop_seek_assessment_for_snap_sudden_pain_or_loss_of_function",
)

ACHILLES_LOAD_OPTION = ReviewedPrescriptionOption(
    option_id=OPTION_ID, option_version=OPTION_VERSION, profile_id="achilles_tendonitis",
    criterion_id=CRITERION_ID, criterion_version=CRITERION_VERSION,
    transition=ReviewTransition(from_stage="restore", to_stage="load"),
    drill_id="achilles_tendonitis_eccentric_calf_drops_on_step",
    bank_hash="557056e938e245ccf7bda3621958820389212034a4eb47c3fb4d04d3e58bad2f",
    instructions="Beside stable support on firm level ground, raise both heels, then transfer weight to the affected leg and slowly lower its heel only to the floor. Do not use a step, lower into deep dorsiflexion, increase depth or add speed or weight. Stop if symptoms worsen during or after the work.",
    range_choices=("floor_level",), resistance_rules=(ResistanceRule(mode="bodyweight"),),
    # NHS phase 1 B: symptom-selected repetitions up to ten, once daily.
    # This first option covers only people whose clinician selects all ten;
    # it is not a mandatory minimum or the source's complete programme.
    dose_choices=(ReviewedDose(sets=1, reps=10),),
    cadence_choices=(ReviewedCadence(frequency="daily", minimum_gap_days=1),),
    mandatory_restrictions=RESTRICTIONS, allowed_restrictions=RESTRICTIONS,
)


def _result(status, *reasons):
    from .clinical_progression_review import ClinicalCriterionResult
    return ClinicalCriterionResult(status=status, reason_codes=reasons)


def evaluate_achilles_interpretation(payload: AchillesRestoreLoadInterpretationV1):
    """Pure typed judgment checks; PASS still needs exact evidence/selection checks."""
    try:
        payload = AchillesRestoreLoadInterpretationV1.model_validate(payload.model_dump(mode="python"))
    except (ValueError, TypeError, AttributeError):
        return _result("unknown", "achilles_interpretation_malformed")
    if payload.schema_version != 1:
        return _result("unknown", "achilles_interpretation_version_unsupported")
    negative = tuple(f"achilles_{key}_not_supported" for key in JUDGMENTS
                     if getattr(payload, key) == "not_supported")
    if negative:
        return _result("fail", *negative)
    if payload.subtype != "midportion":
        return _result("unknown", "achilles_subtype_not_supported_by_option")
    incomplete = tuple(f"achilles_{key}_unknown" for key in JUDGMENTS if getattr(payload, key) != "supported")
    if incomplete:
        return _result("unknown", *incomplete)
    if not all((payload.assessment_event_id, payload.assessment_content_hash, payload.selected_prescription_hash)):
        return _result("unknown", "achilles_interpretation_binding_incomplete")
    return _result("pass", "achilles_clinical_judgments_supported")


def evaluate_achilles_review(review, context):
    """Interpret actual latest protocol values, bound to the reviewed packet.

    Called only after shared trust/validity/selection and typed judgments pass.
    The server context contains existing assessment events, never client copies.
    """
    payload = review.interpretation
    selection = review.selected_prescription
    if selection is None or payload.selected_prescription_hash != selection.materialised_prescription_hash:
        return _result("unknown", "achilles_interpretation_prescription_mismatch")
    injury = dict(athlete_id=context.athlete_id, id=context.injury_id, episode_id=context.injury_episode_id,
        side=context.side, canonical_location="achilles", injury_type="tendonitis", status="monitoring",
        created_at=context.episode_started_at, progression_assessments=context.assessment_events,
        rehab_medical_gate=context.medical_hold)
    setbacks = [e.occurred_at for e in context.safety_history if e.kind == "setback"]
    assessed = AssessmentContext.from_injury(injury, as_of=review.reviewed_at,
        setback_at=max(setbacks, default=None), history_truncated=not context.history_complete)
    event = assessed.latest("achilles_tendon_progression_v1")
    reference = next((r for r in context.current_packet.references if r.event_id == payload.assessment_event_id), None)
    if (event is None or event.get("id") != payload.assessment_event_id or reference is None
            or reference.protocol_id != "achilles_tendon_progression_v1" or reference.protocol_version != 1
            or content_hash(event.get("payload")) != payload.assessment_content_hash
            or reference.content_hash != payload.assessment_content_hash):
        return _result("unknown", "achilles_interpretation_assessment_mismatch")
    inputs = [read_assessment_input(key, assessed) for key in REQUIRED_INPUTS]
    insufficient = tuple(dict.fromkeys(v["reason_code"] for v in inputs if v["status"] != "pass"))
    if insufficient:
        return _result("fail" if any(v["status"] == "fail" for v in inputs) else "unknown", *insufficient)
    observation = assessed.parsed(event).payload
    if observation.site != "midportion" or observation.site != payload.subtype or context.side == "bilateral":
        return _result("unknown", "achilles_observed_subtype_or_side_not_supported")
    if any(getattr(observation, k) is not False for k in (
            "suspected_rupture", "marked_weakness", "traumatic_loss_of_function", "clinician_restriction")):
        return _result("unknown", "achilles_safety_exclusions_incomplete")
    if observation.heel_rise_repetitions is None:
        return _result("unknown", "achilles_heel_rise_count_not_observed")
    if (observation.permitted_range != selection.range_choice or observation.resistance != "bodyweight"
            or observation.resistance_kg is not None):
        return _result("unknown", "achilles_observed_range_or_resistance_not_supported")
    return _result("pass", "achilles_exact_assessment_and_prescription_supported")


def achilles_review_definition():
    from .clinical_progression_review import CriterionReviewDefinition
    return CriterionReviewDefinition(criterion_id=CRITERION_ID, version=CRITERION_VERSION,
        profile_ids=frozenset({"achilles_tendonitis"}), transition=ACHILLES_LOAD_OPTION.transition,
        payload_type=AchillesRestoreLoadInterpretationV1, clinical_scope=CLINICAL_SCOPE,
        options=(ACHILLES_LOAD_OPTION,), evaluate=evaluate_achilles_interpretation,
        evaluate_review=evaluate_achilles_review)
