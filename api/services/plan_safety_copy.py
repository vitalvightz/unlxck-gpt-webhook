from __future__ import annotations

from api.models import PlanDetail, PlanSafetyState


_RESTRICTED_HOLD_STATUS_CHIP = "TRAINING HOLD"
_RESTRICTED_HOLD_HEADER = "Training hold: clinician clearance required"
_RESTRICTED_HOLD_SUBTEXT = (
    "No rehabilitation programme was generated. Normal fight-camp loading and "
    "sparring remain blocked until the athlete updates the injury intake after "
    "clinician clearance."
)
_RESTRICTED_HOLD_NEXT_STEPS = [
    "Do not treat this screen as a rehabilitation programme.",
    "Follow clinician-directed rehabilitation outside UNLXCK.",
    "Update the injury intake after clearance, then regenerate the fight-camp plan.",
]


def clarify_restricted_training_hold(plan: PlanDetail) -> PlanDetail:
    """Make the athlete-facing contract truthful for restricted injury triage.

    ``restricted_rehab_only`` remains the stable internal compatibility token, but
    the current product does not generate or prescribe a rehabilitation programme.
    It blocks normal fight-camp loading until clearance. This adapter keeps stored
    data and admin workflows compatible while preventing the API from presenting a
    safety hold as if it were a rehab plan.
    """

    safety = plan.safety_state
    if safety.state != "restricted_rehab_only":
        return plan

    clarified = PlanSafetyState(
        state=safety.state,
        status_chip=_RESTRICTED_HOLD_STATUS_CHIP,
        header=_RESTRICTED_HOLD_HEADER,
        subtext=_RESTRICTED_HOLD_SUBTEXT,
        stage2_skipped=safety.stage2_skipped,
        clinician_clearance_required=safety.clinician_clearance_required,
        matched_high_risk_categories=list(safety.matched_high_risk_categories),
        red_flags=list(safety.red_flags),
        sparring_risk_band=safety.sparring_risk_band,
        next_steps=list(_RESTRICTED_HOLD_NEXT_STEPS),
    )
    return plan.model_copy(update={"safety_state": clarified})
