"""Reported clinician observations for one hand-weight lateral elbow option.

Not a diagnosis, verified review or grip-strength estimate. No universal pain,
ROM or force cutoff is inferred from the evidence.
"""
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL = "lateral_elbow_progression_v1"
INPUT = "lateral_elbow_function_assessed_v1"
CRITERION = "lateral_elbow_restore_load_v1"
VERSION = 1
Judgment = Literal["acceptable", "not_acceptable", "unknown"]


class LateralElbowProgressionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    subtype: Literal["lateral", "medial", "posterior", "unknown"] = "unknown"
    course: Literal["subacute", "chronic", "acute_traumatic", "unknown"] = "unknown"
    safety_screen: Literal["clear", "concern", "unknown"] = "unknown"
    # All judgments are the athlete's report of their clinician's assessment.
    # Recording a test does not make any of these judgments acceptable.
    pain_irritability: Judgment = "unknown"
    elbow_wrist_motion: Judgment = "unknown"
    grip_task: Literal["daily_grip_task", "clinician_grip_test", "unknown"] = "unknown"
    grip_function: Judgment = "unknown"
    wrist_extension_task: Literal["supported_hand_weight", "unknown"] = "unknown"
    wrist_extension_tolerance: Judgment = "unknown"
    option_recommended: bool | None = Field(default=None, strict=True)

    @property
    def safety_concern(self):
        return self.safety_screen == "concern" or self.course == "acute_traumatic"


def read_elbow_input(identifier, envelope):
    p = envelope.payload
    known = (envelope.assessor == "clinician_physio" and p.subtype != "unknown"
             and p.course != "unknown" and p.safety_screen != "unknown"
             and p.grip_task != "unknown" and p.wrist_extension_task != "unknown"
             and all(getattr(p, k) != "unknown" for k in
                     ("pain_irritability", "elbow_wrist_motion", "grip_function", "wrist_extension_tolerance"))
             and p.option_recommended is not None)
    return {"status": "pass" if known else "unknown",
            "reason_code": "elbow_observations_recorded" if known else "elbow_function_assessment_incomplete"}


def evaluate_elbow_entry(context):
    # Shared reader owns exact episode/side/provenance, timestamp, setback and
    # history checks. Its PASS means data is present, never clinical readiness.
    from .rehab_assessment import read_assessment_input, instant
    from .clinician_clearance import permits_rehabilitation_loading
    from fightcamp.injury_negation import remove_negated_phrases
    available = read_assessment_input(INPUT, context)
    if available["status"] != "pass":
        return available
    event = context.latest(PROTOCOL)
    assessment = context.parsed(event)
    p = assessment.payload
    def result(status, reason):
        return {"status": status, "reason_code": reason, "observation_id": str(event["id"])}
    if context.injury.get("consequence") in {"structural", "neuro"}:
        return result("fail", "injury_loading_safety_hold")
    for previous in context.observations:
        prior = context.parsed(previous)
        recorded = instant(previous.get("created_at"))
        if (prior and recorded and recorded <= context.as_of and prior.assessed_at <= recorded
                and prior.assessment_kind == PROTOCOL and prior.assessed_at > assessment.assessed_at
                and any(getattr(prior.payload, key) == "not_acceptable" for key in
                        ("pain_irritability", "elbow_wrist_motion", "grip_function", "wrist_extension_tolerance"))):
            return result("fail", "elbow_later_unsatisfactory_function")
    if p.safety_concern or any(getattr(p, k) == "not_acceptable" for k in
                              ("pain_irritability", "elbow_wrist_motion", "grip_function", "wrist_extension_tolerance")):
        return result("fail", "elbow_function_or_safety_not_acceptable")
    if p.subtype != "lateral" or p.course not in {"subacute", "chronic"} or assessment.side not in {"left", "right"}:
        return result("unknown", "elbow_lateral_applicability_not_confirmed")
    description = remove_negated_phrases(" ".join(str(context.injury.get(k) or "") for k in ("body_area", "description"))).lower()
    if re.search(r"\b(medial|posterior|golfer|trauma|fracture|rupture|ligament|nerve|numbness|tingling)\b", description):
        return result("fail", "elbow_conflicting_or_unsupported_presentation")
    if context.injury.get("severity") not in {"mild", "moderate", "low", "medium"}:
        return result("unknown", "elbow_loading_severity_not_supported")
    if not permits_rehabilitation_loading(context.injury):
        return result("unknown", "rehabilitation_loading_not_reported")
    if any(context.injury.get(k) for k in ("medical_hold", "restriction_hold", "progression_assessment_medical_hold")):
        return result("fail", "injury_loading_safety_hold")
    if p.option_recommended is not True:
        return result("fail", "elbow_hand_weight_option_not_recommended")
    return result("pass", "elbow_reported_clinician_function_supports_hand_weight_option")
