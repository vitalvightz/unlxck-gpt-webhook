from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from .injury_scoring import score_injury_phrase
from .input_parsing import PlanInput
from .sparring_advisories import _highest_risk_entry, _sparring_injury_entries

FULL_PLAN = "full_plan"
RESTRICTED_REHAB_ONLY = "restricted_rehab_only"
MEDICAL_HOLD = "medical_hold"

# Explicit hard-routing map for severe injury classes.
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

_MEDICAL_HOLD_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bconcussion\b", "concussion"),
    (r"\bsuspected\s+concussion\b", "suspected_concussion"),
    (r"\bloss\s+of\s+consciousness\b|\bpassed\s+out\b|\bknocked\s+out\b", "loss_of_consciousness"),
    (r"\bopen\s+fracture\b", "open_fracture"),
    (r"\bdeformit(?:y|ies)\b", "deformity"),
    (r"\bshort(?:ness)?\s+of\s+breath\b", "shortness_of_breath"),
    (r"\bcough(?:ing)?\s+blood\b|\bhemoptysis\b", "coughing_blood"),
    (r"\b(chest\s+pain|chest\s+pressure)\b", "chest_symptoms"),
    (r"\b(severe\s+)?neurolog(?:ic|ical)\s+(symptom|deficit|issue)s?\b", "neurological_red_flag"),
)

_RESTRICTED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bfracture\b", "fracture"),
    (r"\bstress\s+fracture\b", "stress_fracture"),
    (r"\bbroken\s+rib\b|\brib\s+fracture\b", "broken_rib"),
    (r"\bdislocation\b", "dislocation"),
    (r"\bcan(?:not|'t)?\s+bear\s+weight\b|\bunable\s+to\s+bear\s+weight\b", "cannot_bear_weight"),
    (r"\brapid(?:ly)?\s+worsening\s+swelling\b", "rapid_worsening_swelling"),
    (r"\bsevere\s+.*\bpain\b", "severe_unresolved_pain"),
    (r"\binstability\b|\bgiving\s+way\b|\bbuckled\b", "acute_instability"),
)

_RED_FLAG_SYMPTOM_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnumb(?:ness)?\b", "numbness"),
    (r"\btingl(?:e|ing)\b", "tingling"),
    (r"\bweak(?:ness)?\b", "weakness"),
    (r"\bcan(?:not|'t)?\s+bear\s+weight\b|\bunable\s+to\s+bear\s+weight\b", "cannot_bear_weight"),
    (r"\brapid(?:ly)?\s+worsening\s+swelling\b", "rapid_swelling"),
    (r"\bdeformit(?:y|ies)\b", "deformity"),
    (r"\bshort(?:ness)?\s+of\s+breath\b", "shortness_of_breath"),
    (r"\bchest\s+pain\b", "chest_pain"),
    (r"\bcough(?:ing)?\s+blood\b|\bhemoptysis\b", "coughing_blood"),
    (r"\bloss\s+of\s+consciousness\b|\bpassed\s+out\b|\bknocked\s+out\b", "loss_of_consciousness"),
)


@dataclass(frozen=True)
class InjuryTriageResult:
    mode: str
    reasons: list[str] = field(default_factory=list)
    clinician_clearance_required: bool = False
    red_flags: list[str] = field(default_factory=list)
    matched_high_risk_categories: list[str] = field(default_factory=list)
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


def triage_injuries(plan_input: PlanInput) -> InjuryTriageResult:
    injury_texts: list[str] = []
    if plan_input.injuries:
        injury_texts.extend([chunk.strip() for chunk in plan_input.injuries.split(",") if chunk.strip()])
    injury_texts.extend(
        str(item.get("original_phrase") or "").strip()
        for item in (plan_input.parsed_injuries or [])
        if isinstance(item, dict)
    )
    injury_texts = [text for text in injury_texts if text]

    combined_text = " | ".join(injury_texts)

    urgent_flags: set[str] = set()
    for text in injury_texts:
        scored = score_injury_phrase(text)
        for flag in scored.get("flags", []):
            if str(flag).startswith("urgent"):
                urgent_flags.add(str(flag))

    red_flags = _collect_matches(combined_text, _RED_FLAG_SYMPTOM_PATTERNS)
    medical_hold_matches = _collect_matches(combined_text, _MEDICAL_HOLD_PATTERNS)
    restricted_matches = _collect_matches(combined_text, _RESTRICTED_PATTERNS)

    routed_categories: set[str] = set()
    lowered = combined_text.lower()
    for category, route in _HIGH_RISK_CATEGORY_ROUTE.items():
        if category.replace("_", " ") in lowered:
            routed_categories.add(category)
            if route == MEDICAL_HOLD:
                medical_hold_matches.add(category)
            elif route == RESTRICTED_REHAB_ONLY:
                restricted_matches.add(category)

    if "urgent_fracture" in urgent_flags:
        restricted_matches.add("fracture")
    if "urgent_dislocation" in urgent_flags:
        restricted_matches.add("dislocation")
    if "urgent_nerve" in urgent_flags:
        medical_hold_matches.add("neurological_red_flag")

    sparring_entries = _sparring_injury_entries({"injuries": injury_texts})
    highest_sparring = _highest_risk_entry(sparring_entries)
    highest_band = str((highest_sparring or {}).get("risk_band") or "green")

    if highest_band == "black":
        medical_hold_matches.add("sparring_black_risk")
    elif highest_band == "red" and restricted_matches:
        restricted_matches.add("sparring_red_risk")

    matched_categories = sorted(
        {
            *medical_hold_matches,
            *restricted_matches,
            *[flag.replace("urgent_", "") for flag in urgent_flags if flag != "urgent"],
            *routed_categories,
        }
    )

    if medical_hold_matches:
        return InjuryTriageResult(
            mode=MEDICAL_HOLD,
            reasons=[
                "Urgent or medically disqualifying injury signals were detected before planning.",
                "Training guidance is blocked pending immediate medical review.",
            ],
            clinician_clearance_required=True,
            red_flags=sorted({*red_flags, *medical_hold_matches}),
            matched_high_risk_categories=matched_categories,
            should_block_stage2=True,
            urgent_flags=sorted(urgent_flags),
            sparring_risk_band=highest_band,
        )

    if restricted_matches:
        return InjuryTriageResult(
            mode=RESTRICTED_REHAB_ONLY,
            reasons=[
                "Serious structural injury signals were detected before planning.",
                "Normal fight-camp loading/sparring generation is suspended until clinician clearance.",
            ],
            clinician_clearance_required=True,
            red_flags=sorted(red_flags),
            matched_high_risk_categories=matched_categories,
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
        "injury_triage": triage.to_dict(),
    }
