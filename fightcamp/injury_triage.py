from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from .input_parsing import PlanInput
from .sparring_advisories import summarize_sparring_injury_risk
from .triage_features import build_triage_features

FULL_PLAN = "full_plan"
RESTRICTED_REHAB_ONLY = "restricted_rehab_only"
MEDICAL_HOLD = "medical_hold"
NEEDS_REVIEW = "needs_review"

_HIGH_RISK_CATEGORY_ROUTE: dict[str, str] = {
    "fracture": RESTRICTED_REHAB_ONLY,
    "stress_fracture": RESTRICTED_REHAB_ONLY,
    "rib_fracture": RESTRICTED_REHAB_ONLY,
    "broken_rib": RESTRICTED_REHAB_ONLY,
    "dislocation": RESTRICTED_REHAB_ONLY,
    "acl_tear": RESTRICTED_REHAB_ONLY,
    "achilles_rupture": RESTRICTED_REHAB_ONLY,
    "full_thickness_rotator_cuff_tear": RESTRICTED_REHAB_ONLY,
    "tendon_rupture_or_avulsion": RESTRICTED_REHAB_ONLY,
    "complete_ligament_tear": RESTRICTED_REHAB_ONLY,
    "concussion": MEDICAL_HOLD,
    "suspected_concussion": MEDICAL_HOLD,
    "open_fracture": MEDICAL_HOLD,
    "pcl_tear": RESTRICTED_REHAB_ONLY,
    "mcl_grade3_tear": RESTRICTED_REHAB_ONLY,
    "lcl_grade3_tear": RESTRICTED_REHAB_ONLY,
    "meniscus_bucket_handle_tear": RESTRICTED_REHAB_ONLY,
    "patellar_tendon_rupture": RESTRICTED_REHAB_ONLY,
    "quadriceps_tendon_rupture": RESTRICTED_REHAB_ONLY,
    "distal_biceps_tendon_rupture": RESTRICTED_REHAB_ONLY,
    "triceps_tendon_rupture": RESTRICTED_REHAB_ONLY,
    "pec_major_tear": RESTRICTED_REHAB_ONLY,
    "patellar_dislocation": RESTRICTED_REHAB_ONLY,
    "recurrent_shoulder_dislocation": RESTRICTED_REHAB_ONLY,
    "labral_tear_with_instability": RESTRICTED_REHAB_ONLY,
    "hip_labral_tear": RESTRICTED_REHAB_ONLY,
    "syndesmotic_high_ankle_sprain_severe": RESTRICTED_REHAB_ONLY,
    "lisfranc_injury": RESTRICTED_REHAB_ONLY,
    "tibial_plateau_fracture": RESTRICTED_REHAB_ONLY,
    "scaphoid_fracture": RESTRICTED_REHAB_ONLY,
    "jaw_fracture": RESTRICTED_REHAB_ONLY,
    "post_op_reconstruction_active": RESTRICTED_REHAB_ONLY,
    "post_op_tendon_repair_active": RESTRICTED_REHAB_ONLY,
    "post_op_fracture_fixation_active": RESTRICTED_REHAB_ONLY,
    "spinal_fracture": MEDICAL_HOLD,
    "orbital_fracture": MEDICAL_HOLD,
    "facial_fracture": MEDICAL_HOLD,
    "retinal_detachment_or_eye_trauma": MEDICAL_HOLD,
    "pneumothorax": MEDICAL_HOLD,
    "hemothorax": MEDICAL_HOLD,
    "spleen_or_liver_injury": MEDICAL_HOLD,
    "cervical_spine_injury": MEDICAL_HOLD,
    "septic_joint_or_bone_infection": MEDICAL_HOLD,
}

_TRAUMA_CONTEXT_PATTERNS = (
    r"\bhit\b",
    r"\bimpact\b",
    r"\bcollision\b",
    r"\bblow\b",
    r"\bfell\b",
    r"\bfall\b",
)

_NEURO_CONTEXT_PATTERN = r"\bneurolog(?:ic|ical)\b|\bnerve\b"


@dataclass(frozen=True)
class InjuryTriageResult:
    mode: str
    reasons: list[str] = field(default_factory=list)
    clinician_clearance_required: bool = False
    red_flags: list[str] = field(default_factory=list)
    matched_high_risk_categories: list[str] = field(default_factory=list)
    routing_reasons: list[str] = field(default_factory=list)
    should_block_stage2: bool = False
    urgent_flags: list[str] = field(default_factory=list)
    sparring_risk_band: str = "green"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def triage_injuries(plan_input: PlanInput) -> InjuryTriageResult:
    features = build_triage_features(
        injuries=plan_input.injuries,
        parsed_injuries=plan_input.parsed_injuries,
        guided_injury=plan_input.guided_injury,
        restrictions=plan_input.restrictions,
    )

    injury_texts = list(features.raw_evidence.get("all_input") or [])
    combined_text = " | ".join(injury_texts).lower()

    matched_categories = set(features.high_risk_diagnoses)
    red_flags = set(features.red_flags)
    urgent_flags = set(features.urgent_flags)
    routing_reasons: set[str] = set()

    for category in matched_categories:
        route = _HIGH_RISK_CATEGORY_ROUTE.get(category)
        if route:
            routing_reasons.add(f"mapped:{category}:{route}")
    if "urgent_fracture" in urgent_flags:
        matched_categories.add("fracture")
        routing_reasons.add("urgent_flag:urgent_fracture")
    if "urgent_dislocation" in urgent_flags:
        matched_categories.add("dislocation")
        routing_reasons.add("urgent_flag:urgent_dislocation")
    if "urgent_nerve" in urgent_flags:
        red_flags.add("neurological_symptoms")
        routing_reasons.add("urgent_flag:urgent_nerve")

    guided = plan_input.guided_injury
    guided_severity = str((guided.severity if guided else "") or "").strip().lower()
    guided_trend = str((guided.trend if guided else "") or "").strip().lower()
    guided_avoid = str((guided.avoid if guided else "") or "").strip().lower()
    guided_notes = str((guided.notes if guided else "") or "").strip().lower()

    if guided_severity in {"high", "severe"}:
        routing_reasons.add("guided_injury:high_severity")
        if any(
            token in combined_text
            for token in ("rib", "fracture", "dislocation", "instability", "cannot bear weight")
        ):
            matched_categories.add("structural_high_severity")

    if guided_trend in {"worse", "worsening", "regressing", "worsened"}:
        red_flags.add("worsening_course")
        routing_reasons.add("guided_injury:worsening")

    if any(token in guided_avoid for token in ("contact", "spar", "impact", "loaded", "weight bearing")):
        routing_reasons.add("guided_injury:avoid_high_load")

    if "breath" in guided_notes and any(token in combined_text for token in ("rib", "chest", "pain")):
        red_flags.add("breathing_pain")
        routing_reasons.add("guided_injury:breathing_symptoms")
    rib_or_chest_context = any(token in combined_text for token in ("rib", "intercostal", "chest"))

    medical_hold = False
    if any(
        flag in red_flags
        for flag in (
            "loss_of_consciousness",
            "coughing_blood",
            "deformity",
            "vomiting_after_head_impact",
            "severe_headache_after_head_impact",
            "seizure_or_convulsion",
            "amnesia_or_memory_loss",
            "blurred_or_double_vision",
            "unequal_pupils",
            "worsening_drowsiness_or_cannot_wake",
            "slurred_speech",
            "neck_pain_after_trauma",
            "bowel_or_bladder_changes_after_back_injury",
        )
    ):
        medical_hold = True
        routing_reasons.add("critical_red_flag")

    if any(_HIGH_RISK_CATEGORY_ROUTE.get(c) == MEDICAL_HOLD for c in matched_categories):
        medical_hold = True
        routing_reasons.add("mapped_medical_hold_category")

    chest_with_systemic = "chest_pain" in red_flags and (
        "shortness_of_breath" in red_flags
        or "coughing_blood" in red_flags
        or any(re.search(pattern, combined_text) for pattern in _TRAUMA_CONTEXT_PATTERNS)
        or "worsening_course" in red_flags
    )
    if chest_with_systemic:
        medical_hold = True
        routing_reasons.add("chest_red_flag_combination")

    rib_breathing_unsafe = rib_or_chest_context and ("breathing_pain" in red_flags) and (
        any(category in matched_categories for category in ("broken_rib", "fracture", "open_fracture"))
        or any(re.search(pattern, combined_text) for pattern in _TRAUMA_CONTEXT_PATTERNS)
        or "shortness_of_breath" in red_flags
    )
    if rib_breathing_unsafe:
        medical_hold = True
        routing_reasons.add("rib_breathing_red_flag_combination")

    neuro_combo = (
        bool(re.search(_NEURO_CONTEXT_PATTERN, combined_text))
        and any(flag in red_flags for flag in ("loss_of_consciousness", "numbness", "weakness", "confusion"))
    ) or (
        "loss_of_consciousness" in red_flags
        and any(flag in red_flags for flag in ("numbness", "weakness", "tingling", "confusion"))
    )
    if neuro_combo:
        medical_hold = True
        routing_reasons.add("neurological_red_flag_combination")

    restricted_rehab = False
    if any(_HIGH_RISK_CATEGORY_ROUTE.get(c) == RESTRICTED_REHAB_ONLY for c in matched_categories) or "structural_high_severity" in matched_categories:
        restricted_rehab = True
        routing_reasons.add("mapped_restricted_category")

    if any(flag in red_flags for flag in ("cannot_bear_weight", "rapid_swelling")):
        restricted_rehab = True
        routing_reasons.add("structural_function_red_flag")

    if features.structural_severe_signals:
        restricted_rehab = True
        routing_reasons.add("scored_structural_severe_signal")

    if features.clinician_restriction_signals:
        restricted_rehab = True
        routing_reasons.add("clinician_restriction_signal")

    sparring_risk = summarize_sparring_injury_risk(injury_texts=injury_texts)
    highest_band = str(sparring_risk.get("risk_band") or "green")
    if highest_band in {"red", "black"} and guided_severity in {"high", "severe"}:
        restricted_rehab = True
        routing_reasons.add("guided_high_severity_with_elevated_sparring_risk")
    if highest_band == "black":
        routing_reasons.add("sparring_black_risk")
        if any(flag in red_flags for flag in ("loss_of_consciousness", "coughing_blood", "deformity")):
            medical_hold = True
        else:
            restricted_rehab = True
    elif highest_band == "red" and restricted_rehab:
        routing_reasons.add("sparring_red_risk")

    matched_categories_sorted = sorted(matched_categories)
    routing_reasons_sorted = sorted(routing_reasons)

    if medical_hold:
        return InjuryTriageResult(
            mode=MEDICAL_HOLD,
            reasons=[
                "Urgent or medically disqualifying injury signals were detected before planning.",
                "Training guidance is blocked pending immediate medical review.",
            ],
            clinician_clearance_required=True,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories_sorted,
            routing_reasons=routing_reasons_sorted,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    if restricted_rehab:
        return InjuryTriageResult(
            mode=RESTRICTED_REHAB_ONLY,
            reasons=[
                "Serious structural injury signals were detected before planning.",
                "Normal fight-camp loading/sparring generation is suspended until clinician clearance.",
            ],
            clinician_clearance_required=True,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories_sorted,
            routing_reasons=routing_reasons_sorted,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    has_dangerous_red_flags = any(
        flag in red_flags
        for flag in (
            "loss_of_consciousness",
            "coughing_blood",
            "deformity",
            "vomiting_after_head_impact",
            "severe_headache_after_head_impact",
            "seizure_or_convulsion",
            "amnesia_or_memory_loss",
            "blurred_or_double_vision",
            "unequal_pupils",
            "worsening_drowsiness_or_cannot_wake",
            "slurred_speech",
            "neck_pain_after_trauma",
            "bowel_or_bladder_changes_after_back_injury",
            "shortness_of_breath",
            "chest_pain",
            "breathing_pain",
        )
    )
    has_chest_or_neuro_combo = chest_with_systemic or rib_breathing_unsafe or neuro_combo
    has_mapped_medical_hold = any(_HIGH_RISK_CATEGORY_ROUTE.get(category) == MEDICAL_HOLD for category in matched_categories)
    has_mapped_restricted = any(_HIGH_RISK_CATEGORY_ROUTE.get(category) == RESTRICTED_REHAB_ONLY for category in matched_categories)
    has_structural_severe_signal = bool(features.structural_severe_signals)
    has_clinician_restriction_signal = bool(features.clinician_restriction_signals)
    has_function_loss_signal = bool(features.function_loss_signals)
    has_uncertainty_trigger = bool(guided) and not any(
        (
            matched_categories,
            red_flags,
            features.structural_severe_signals,
            features.clinician_restriction_signals,
            features.function_loss_signals,
            urgent_flags,
        )
    ) and len(guided_notes.split()) < 3

    guided_combo = (guided_severity, guided_trend)
    if guided_combo in {("high", "worse"), ("high", "worsening"), ("high", "regressing"), ("high", "worsened"), ("severe", "worse"), ("severe", "worsening"), ("severe", "regressing"), ("severe", "worsened")}:
        routing_reasons.add("combo_gate:high_worsening")
        routing_reasons_sorted = sorted(routing_reasons)
        if has_dangerous_red_flags or has_chest_or_neuro_combo or has_mapped_medical_hold:
            return InjuryTriageResult(
                mode=MEDICAL_HOLD,
                reasons=[
                    "High-severity worsening injury with dangerous escalation signals was detected.",
                    "Training guidance is blocked pending immediate medical review.",
                ],
                clinician_clearance_required=True,
                red_flags=sorted(red_flags),
                matched_high_risk_categories=matched_categories_sorted,
                routing_reasons=routing_reasons_sorted,
                should_block_stage2=True,
                urgent_flags=sorted(urgent_flags),
                sparring_risk_band=highest_band,
            )
        return InjuryTriageResult(
            mode=NEEDS_REVIEW,
            reasons=[
                "High-severity worsening injury requires coach/admin review before any normal plan.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories_sorted,
            routing_reasons=routing_reasons_sorted,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    if guided_combo in {("high", "stable"), ("severe", "stable")}:
        routing_reasons.add("combo_gate:high_stable")
        routing_reasons_sorted = sorted(routing_reasons)
        if (
            has_structural_severe_signal
            or has_mapped_restricted
            or has_clinician_restriction_signal
            or has_function_loss_signal
        ):
            return InjuryTriageResult(
                mode=RESTRICTED_REHAB_ONLY,
                reasons=[
                    "High-severity stable injury still shows structural/restriction risk signals.",
                    "Normal fight-camp loading/sparring generation remains suspended.",
                ],
                clinician_clearance_required=True,
                red_flags=sorted(red_flags),
                matched_high_risk_categories=matched_categories_sorted,
                routing_reasons=routing_reasons_sorted,
                should_block_stage2=True,
                urgent_flags=sorted(urgent_flags),
                sparring_risk_band=highest_band,
            )
        return InjuryTriageResult(
            mode=NEEDS_REVIEW,
            reasons=[
                "High-severity stable injury requires coach/admin review before any normal plan.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories_sorted,
            routing_reasons=routing_reasons_sorted,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    if guided_combo in {("moderate", "worse"), ("moderate", "worsening"), ("moderate", "regressing"), ("moderate", "worsened")}:
        routing_reasons.add("combo_gate:moderate_worsening")
        routing_reasons_sorted = sorted(routing_reasons)
        if has_dangerous_red_flags or has_mapped_medical_hold:
            return InjuryTriageResult(
                mode=MEDICAL_HOLD,
                reasons=[
                    "Moderate worsening injury includes dangerous escalation signals.",
                    "Training guidance is blocked pending immediate medical review.",
                ],
                clinician_clearance_required=True,
                red_flags=sorted(red_flags),
                matched_high_risk_categories=matched_categories_sorted,
                routing_reasons=routing_reasons_sorted,
                should_block_stage2=True,
                urgent_flags=sorted(urgent_flags),
                sparring_risk_band=highest_band,
            )
        return InjuryTriageResult(
            mode=NEEDS_REVIEW,
            reasons=[
                "Moderate worsening injury requires coach/admin review before any normal plan.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories_sorted,
            routing_reasons=routing_reasons_sorted,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    if guided_combo in {("low", "worse"), ("low", "worsening"), ("low", "regressing"), ("low", "worsened")}:
        routing_reasons.add("combo_gate:low_worsening")
        routing_reasons_sorted = sorted(routing_reasons)
        return InjuryTriageResult(
            mode=NEEDS_REVIEW,
            reasons=[
                "Low-severity worsening injury still requires review before normal planning.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories_sorted,
            routing_reasons=routing_reasons_sorted,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    if guided_combo == ("moderate", "stable"):
        routing_reasons.add("combo_gate:moderate_stable_allowlist_check")
        has_mapped_serious_category = has_mapped_medical_hold or has_mapped_restricted
        if (
            has_dangerous_red_flags
            or has_structural_severe_signal
            or has_clinician_restriction_signal
            or has_mapped_serious_category
            or has_uncertainty_trigger
        ):
            routing_reasons.add("combo_gate:moderate_stable_blocked")
            routing_reasons_sorted = sorted(routing_reasons)
            return InjuryTriageResult(
                mode=NEEDS_REVIEW,
                reasons=[
                    "Moderate stable injury did not meet the strict allowlist for automatic full planning.",
                    "Coach/admin review is required before normal plan generation.",
                ],
                clinician_clearance_required=False,
                red_flags=sorted(red_flags),
                matched_high_risk_categories=matched_categories_sorted,
                routing_reasons=routing_reasons_sorted,
                should_block_stage2=True,
                urgent_flags=sorted(urgent_flags),
                sparring_risk_band=highest_band,
            )

    return InjuryTriageResult(
        mode=FULL_PLAN,
        reasons=["No pre-planning medical hold signals detected."],
        clinician_clearance_required=False,
        red_flags=sorted(red_flags),
        matched_high_risk_categories=matched_categories_sorted,
        routing_reasons=routing_reasons_sorted,
        should_block_stage2=False,
        urgent_flags=sorted(urgent_flags),
        sparring_risk_band=highest_band,
    )


def blocked_mode_output(*, triage: InjuryTriageResult) -> dict[str, Any]:
    if triage.mode == NEEDS_REVIEW:
        plan_text = (
            "## Injury Triage: Needs Review\n"
            "Automatic full-plan generation is paused.\n\n"
            "- Coach/admin approval is required before Stage 2 or normal planning can run.\n"
            "- Update injury specifics, restrictions, and progression status before regenerating."
        )
        coach_notes = (
            "needs_review: severity/trend combo safety gate triggered; "
            "stage2 and normal generation blocked pending coach/admin approval."
        )
    elif triage.mode == RESTRICTED_REHAB_ONLY:
        plan_text = (
            "## Injury Triage: Restricted Rehab Only\n"
            "Normal fight-camp planning is intentionally suspended.\n\n"
            "- Clinician clearance is required before return to loading or sparring.\n"
            "- Do not run hard conditioning, hard sparring, or standard S&C sessions from this system.\n"
            "- Follow only already-approved rehab / medical guidance until re-cleared."
        )
        coach_notes = (
            "restricted_rehab_only: serious structural injury gate triggered; "
            "normal camp generation blocked by design."
        )
    else:
        plan_text = (
            "## Injury Triage: Medical Hold\n"
            "No training plan was generated.\n\n"
            "- Urgent medical review is required before any training guidance.\n"
            "- This intake is intentionally blocked from planning and Stage 2 finalization."
        )
        coach_notes = (
            "medical_hold: urgent neurological/medical red-flag gate triggered; "
            "all training generation blocked by design."
        )

    return {
        "status": "triage_blocked",
        "ok": False,
        "pdf_url": None,
        "why_log": {"injury_triage": triage.to_dict()},
        "coach_notes": coach_notes,
        "plan_text": plan_text,
        "stage2_payload": None,
        "planning_brief": None,
        "stage2_handoff_text": "",
        "parsing_metadata": {},
        "stage2_status": "triage_blocked",
        "injury_triage": triage.to_dict(),
    }
