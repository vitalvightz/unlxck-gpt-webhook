"""Versioned Achilles LOAD review. Current capture cannot establish clinical PASS.

Sources support individualised loading, not a universal product-stage cutoff.
This review identifies exclusions and missing clinical judgments without making
availability, reported assessor identity or symptom magnitudes into clearance.
It deliberately has no PASS path and is not registered as a captured criterion.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .rehab_assessment import ASSESSMENT_PROTOCOLS, AssessmentContext, read_assessment_input

CRITERION_ID = "achilles_restore_load_review_v1"
REQUIRED_INPUTS = (
    "achilles_site_assessed", "achilles_heel_rise_assessed",
    "achilles_loading_response_assessed", "achilles_range_load_assessed",
)
SOURCES = (
    "https://bjsm.bmj.com/content/55/20/1125",
    "https://www.orthopt.org/uploads/content_files/files/Achilles_Pain_revision_2024.pdf",
    "https://www.kentcht.nhs.uk/leaflet/achilles-insertional-tendinopathy/",
)


class AchillesRestoreLoadReview(BaseModel):
    criterion_id: Literal["achilles_restore_load_review_v1"] = CRITERION_ID
    criterion_version: Literal[1] = 1
    status: Literal["fail", "unknown"]
    reason_codes: list[str]
    subtype: Literal["midportion", "insertional", "unknown"] = "unknown"
    required_input_ids: list[str]
    observation_id: str | None = None
    externally_verified: Literal[False] = False
    promotion_allowed: Literal[False] = False
    sources: list[str]


def review_achilles_restore_load(context: AssessmentContext) -> dict:
    """Use the shared context/readers, including latest snapshot and setbacks.

FAIL is an explicit safety exclusion or reported unusable/not-tolerated input.
    UNKNOWN includes unavailable interpretation/provenance/prescription. Neither
    can open a transition. Future approval must replace this incomplete review with
    a reviewed clinical PASS predicate, not toggle a boolean or trust a client flag.
    """
    result = AchillesRestoreLoadReview(status="unknown", reason_codes=[],
        required_input_ids=list(REQUIRED_INPUTS), sources=list(SOURCES)).model_dump()
    protocol = ASSESSMENT_PROTOCOLS["achilles_tendon_progression_v1"]
    if not protocol.applies(context.injury):
        return {**result, "reason_codes": ["achilles_profile_mismatch"]}
    if context.medical_hold or context.injury.get("latest_reported_status") == "worse":
        return {**result, "status": "fail", "reason_codes": ["achilles_medical_or_setback_hold"]}
    inputs = {key: read_assessment_input(key, context) for key in REQUIRED_INPUTS}
    if any(value["status"] != "pass" for value in inputs.values()):
        return {**result, "status": "fail" if any(v["status"] == "fail" for v in inputs.values()) else "unknown",
                "reason_codes": list(dict.fromkeys(v["reason_code"] for v in inputs.values() if v["status"] != "pass"))}
    # The shared readers established attribution, chronology, complete history,
    # and the latest whole snapshot. Never search for a historical best result.
    assessment = context.parsed(context.latest("achilles_tendon_progression_v1"))
    payload = assessment.payload
    reasons = []
    if any(getattr(payload, key) is not False for key in (
            "suspected_rupture", "marked_weakness", "traumatic_loss_of_function", "clinician_restriction")):
        reasons.append("achilles_safety_exclusions_incomplete")
    # Distinct applicability branches: the midportion CPG is not insertional
    # evidence. The candidate is unilateral; insertional guidance starts with
    # bilateral floor work and clinician-directed progression to single leg.
    if payload.site == "insertional":
        reasons.append("achilles_insertional_unilateral_progression_requires_clinician_review")
    elif payload.site == "midportion":
        reasons.append("achilles_midportion_structural_applicability_requires_clinician_review")
    else:
        reasons.append("achilles_subtype_unknown")
    reasons += [
        "achilles_verified_clinician_review_unavailable",
        "achilles_selected_load_functional_adequacy_not_captured",
        "achilles_acceptable_symptom_response_not_defined",
        "achilles_individual_load_prescription_not_defined",
    ]
    return {**result, "subtype": payload.site, "observation_id": inputs[REQUIRED_INPUTS[0]]["observation_id"],
            "reason_codes": reasons}
