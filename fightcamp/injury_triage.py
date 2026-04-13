from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from .injury_scoring import score_injury_phrase
from .input_parsing import GuidedInjury, PlanInput
from .sparring_advisories import summarize_sparring_injury_risk

FULL_PLAN = "full_plan"
RESTRICTED_REHAB_ONLY = "restricted_rehab_only"
MEDICAL_HOLD = "medical_hold"

_HIGH_RISK_CATEGORY_ROUTE: dict[str, str] = {
    "fracture": RESTRICTED_REHAB_ONLY,
    "stress_fracture": RESTRICTED_REHAB_ONLY,
    "rib_fracture": RESTRICTED_REHAB_ONLY,
    "broken_rib": RESTRICTED_REHAB_ONLY,
    "dislocation": RESTRICTED_REHAB_ONLY,
    "concussion": MEDICAL_HOLD,
    "suspected_concussion": MEDICAL_HOLD,
    "open_fracture": MEDICAL_HOLD,
}

_RED_FLAG_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnumb(?:ness)?\b", "numbness"),
    (r"\btingl(?:e|ing)\b", "tingling"),
    (r"\bweak(?:ness)?\b", "weakness"),
    (r"\bcan(?:not|'t)?\s+bear\s+weight\b|\bunable\s+to\s+bear\s+weight\b", "cannot_bear_weight"),
    (r"\brapid(?:ly)?\s+worsening\s+swelling\b", "rapid_swelling"),
    (r"\bdeformit(?:y|ies)\b", "deformity"),
    (r"\bshort(?:ness)?\s+of\s+breath\b", "shortness_of_breath"),
    (r"\bcough(?:ing)?\s+blood\b|\bhemoptysis\b", "coughing_blood"),
    (r"\bloss\s+of\s+consciousness\b|\bpassed\s+out\b|\bknocked\s+out\b", "loss_of_consciousness"),
    (r"\bconfus(?:ed|ion)\b", "confusion"),
    (r"\bchest\s+pain\b|\bchest\s+pressure\b", "chest_pain"),
    (r"\bpain\s+(?:when|with)?\s*breath(?:ing)?\b|\bpainful\s+breath(?:ing)?\b", "breathing_pain"),
)

_HIGH_RISK_CATEGORY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bopen\s+fracture\b", "open_fracture"),
    (r"\bstress\s+fracture\b", "stress_fracture"),
    (r"\brib\s+fracture\b|\bbroken\s+rib\b", "broken_rib"),
    (r"\bfracture\b", "fracture"),
    (r"\bdislocation\b", "dislocation"),
    (r"\bsuspected\s+concussion\b", "suspected_concussion"),
    (r"\bconcussion\b", "concussion"),
)

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


def _collect_matches(text: str, patterns: tuple[tuple[str, str], ...]) -> set[str]:
    lowered = str(text or "").lower()
    matches: set[str] = set()
    for pattern, label in patterns:
        if re.search(pattern, lowered):
            matches.add(label)
    return matches


def _guided_injury_text_chunks(guided: GuidedInjury | None) -> list[str]:
    if guided is None:
        return []
    chunks = [
        str(guided.area or "").strip(),
        str(guided.severity or "").strip(),
        str(guided.trend or "").strip(),
        str(guided.avoid or "").strip(),
        str(guided.notes or "").strip(),
    ]
    return [chunk for chunk in chunks if chunk]


def _restriction_text_chunks(restrictions: list[dict[str, Any]]) -> list[str]:
    chunks: list[str] = []
    for item in restrictions or []:
        if not isinstance(item, dict):
            continue
        parts = [
            str(item.get("original_phrase") or "").strip(),
            str(item.get("restriction") or "").replace("_", " ").strip(),
            str(item.get("strength") or "").strip(),
            str(item.get("region") or "").strip(),
        ]
        chunks.extend([part for part in parts if part])
    return chunks


def triage_injuries(plan_input: PlanInput) -> InjuryTriageResult:
    injury_texts: list[str] = []
    if plan_input.injuries:
        injury_texts.extend([chunk.strip() for chunk in plan_input.injuries.split(",") if chunk.strip()])
    injury_texts.extend(
        str(item.get("original_phrase") or "").strip()
        for item in (plan_input.parsed_injuries or [])
        if isinstance(item, dict)
    )
    injury_texts.extend(_guided_injury_text_chunks(plan_input.guided_injury))
    injury_texts.extend(_restriction_text_chunks(plan_input.restrictions))
    injury_texts = [text for text in injury_texts if text]

    combined_text = " | ".join(injury_texts).lower()
    red_flags = _collect_matches(combined_text, _RED_FLAG_PATTERNS)

    urgent_flags: set[str] = set()
    for text in injury_texts:
        scored = score_injury_phrase(text)
        for flag in scored.get("flags", []):
            if str(flag).startswith("urgent"):
                urgent_flags.add(str(flag))

    matched_categories = _collect_matches(combined_text, _HIGH_RISK_CATEGORY_PATTERNS)
    routing_reasons: set[str] = set()

    for category, route in _HIGH_RISK_CATEGORY_ROUTE.items():
        if category.replace("_", " ") in combined_text:
            matched_categories.add(category)
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
        if any(token in combined_text for token in ("rib", "fracture", "dislocation", "instability", "cannot bear weight")):
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

    # Strict medical-hold escalation rules (combination based, not broad single phrases).
    medical_hold = False
    if any(flag in red_flags for flag in ("loss_of_consciousness", "coughing_blood", "deformity")):
        medical_hold = True
        routing_reasons.add("critical_red_flag")

    if any(category in matched_categories for category in ("concussion", "suspected_concussion", "open_fracture")):
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
    if any(category in matched_categories for category in ("fracture", "stress_fracture", "broken_rib", "dislocation", "structural_high_severity")):
        restricted_rehab = True
        routing_reasons.add("mapped_restricted_category")
    if any(flag in red_flags for flag in ("cannot_bear_weight", "rapid_swelling")):
        restricted_rehab = True
        routing_reasons.add("structural_function_red_flag")

    sparring_risk = summarize_sparring_injury_risk(injury_texts=injury_texts)
    highest_band = str(sparring_risk.get("risk_band") or "green")
    if highest_band == "black":
        routing_reasons.add("sparring_black_risk")
        if any(flag in red_flags for flag in ("loss_of_consciousness", "coughing_blood", "deformity")):
            medical_hold = True
        else:
            restricted_rehab = True
    elif highest_band == "red" and restricted_rehab:
        routing_reasons.add("sparring_red_risk")

    matched_categories = sorted(matched_categories)
    routing_reasons = sorted(routing_reasons)

    if medical_hold:
        return InjuryTriageResult(
            mode=MEDICAL_HOLD,
            reasons=[
                "Urgent or medically disqualifying injury signals were detected before planning.",
                "Training guidance is blocked pending immediate medical review.",
            ],
            clinician_clearance_required=True,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories,
            routing_reasons=routing_reasons,
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
            matched_high_risk_categories=matched_categories,
            routing_reasons=routing_reasons,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    return InjuryTriageResult(
        mode=FULL_PLAN,
        reasons=["No pre-planning medical hold signals detected."],
        clinician_clearance_required=False,
        red_flags=sorted(red_flags),
        matched_high_risk_categories=matched_categories,
        routing_reasons=routing_reasons,
        should_block_stage2=False,
        urgent_flags=sorted(urgent_flags),
        sparring_risk_band=highest_band,
    )


def blocked_mode_output(*, triage: InjuryTriageResult) -> dict[str, Any]:
    if triage.mode == RESTRICTED_REHAB_ONLY:
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
