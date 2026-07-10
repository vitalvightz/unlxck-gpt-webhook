from api.models import PlanDetail, PlanOutputs, PlanSafetyState
from api.services.plan_safety_copy import clarify_restricted_training_hold


def _plan(safety_state: PlanSafetyState) -> PlanDetail:
    return PlanDetail(
        plan_id="plan-1",
        athlete_id="athlete-1",
        full_name="Test Athlete",
        created_at="2026-07-10T00:00:00+00:00",
        outputs=PlanOutputs(plan_text=""),
        safety_state=safety_state,
    )


def test_restricted_rehab_internal_token_is_presented_as_training_hold():
    original = _plan(
        PlanSafetyState(
            state="restricted_rehab_only",
            status_chip="RESTRICTED REHAB ONLY",
            header="Planning paused",
            subtext="Legacy copy",
            stage2_skipped=True,
            clinician_clearance_required=True,
            matched_high_risk_categories=["acl_tear"],
            red_flags=["cannot_bear_weight"],
            sparring_risk_band="red",
            next_steps=["Legacy step"],
        )
    )

    clarified = clarify_restricted_training_hold(original)

    assert clarified is not original
    assert clarified.safety_state.state == "restricted_rehab_only"
    assert clarified.safety_state.status_chip == "TRAINING HOLD"
    assert clarified.safety_state.header == "Training hold: clinician clearance required"
    assert "No rehabilitation programme was generated" in clarified.safety_state.subtext
    assert clarified.safety_state.next_steps == [
        "Do not treat this screen as a rehabilitation programme.",
        "Follow clinician-directed rehabilitation outside UNLXCK.",
        "Update the injury intake after clearance, then regenerate the fight-camp plan.",
    ]
    assert clarified.safety_state.stage2_skipped is True
    assert clarified.safety_state.clinician_clearance_required is True
    assert clarified.safety_state.matched_high_risk_categories == ["acl_tear"]
    assert clarified.safety_state.red_flags == ["cannot_bear_weight"]
    assert clarified.safety_state.sparring_risk_band == "red"
    assert original.safety_state.status_chip == "RESTRICTED REHAB ONLY"


def test_non_restricted_safety_state_is_unchanged():
    plan = _plan(
        PlanSafetyState(
            state="medical_hold",
            status_chip="MEDICAL HOLD",
            header="Medical hold",
            subtext="Urgent review required.",
            clinician_clearance_required=True,
        )
    )

    assert clarify_restricted_training_hold(plan) is plan
