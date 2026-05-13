from __future__ import annotations

from dataclasses import dataclass

from .injury_synonyms import remove_negated_phrases


@dataclass
class ClinicalGate:
    red_flag_level: str
    clearance_required: bool
    training_status: str
    reasons: list[str]
    blocked_modules: list[str]
    source_phrases: list[str]


_EMERGENCY_TERMS = {
    "cold limb": "limb circulation red flag",
    "blue limb": "limb circulation red flag",
    "grey limb": "limb circulation red flag",
    "loss of pulse": "loss of pulse",
    "severe deformity": "severe deformity",
    "suspected fracture with deformity": "suspected fracture with deformity",
    "loss of consciousness": "head injury with loss of consciousness",
    "repeated vomiting": "repeated vomiting after head impact",
    "worsening neurological": "worsening neurological symptoms",
    "cold and blue": "limb circulation red flag",
}

_URGENT_TERMS = {
    "suspected fracture": "suspected fracture",
    "dislocation": "suspected dislocation",
    "tendon rupture": "suspected tendon rupture",
    "ligament tear": "suspected ligament tear",
    "acl tear": "suspected ACL/PCL/MCL/LCL tear",
    "mcl tear": "suspected ACL/PCL/MCL/LCL tear",
    "lcl tear": "suspected ACL/PCL/MCL/LCL tear",
    "pcl tear": "suspected ACL/PCL/MCL/LCL tear",
    "muscle rupture": "suspected muscle rupture",
    "concussion": "head injury/concussion symptoms",
    "head injury": "head injury/concussion symptoms",
    "head impact": "head injury/concussion symptoms",
    "headache": "head injury/concussion symptoms",
    "numbness": "nerve involvement symptoms",
    "tingling": "nerve involvement symptoms",
    "nerve": "nerve involvement symptoms",
    "fever": "possible infection signs",
    "pus": "possible infection signs",
    "red streak": "possible infection signs",
    "hernia": "possible hernia",
    "cannot bear weight": "cannot bear weight",
    "can't bear weight": "cannot bear weight",
    "severe swelling": "severe swelling",
    "giving way": "joint giving way after injury",
    "blacked out": "loss of consciousness / blackout",
    "knocked out": "loss of consciousness / knockout",
    "got rocked": "head impact symptom",
    "snap in achilles": "possible achilles rupture",
    "felt a snap": "possible structural rupture",
}

_CAUTION_TERMS = {
    "open cut": "open skin wound",
    "laceration": "skin wound",
    "graze": "skin wound",
    "blister": "skin friction wound",
    "abrasion": "skin wound",
    "mild swelling": "mild swelling",
    "clicking with pain": "joint mechanical symptoms with pain",
    "instability": "instability symptoms",
    "recurring tendon pain": "recurring tendon pain",
    "catching": "joint mechanical symptoms",
}

_SURFACE_TYPES = {"cut", "laceration", "graze", "abrasion", "blister"}
_CONTACT_WOUND_TERMS = ("open", "bleed", "bleeding", "leaking", "pus", "reopen", "grappl", "spar")


def _contains(text: str, phrase: str) -> bool:
    return phrase in text


def evaluate_clinical_gate(injury_text: str = "", parsed_entries: list[dict] | None = None) -> ClinicalGate:
    entries = [entry for entry in (parsed_entries or []) if isinstance(entry, dict)]
    lowered_text = (injury_text or "").lower()
    normalized_text = remove_negated_phrases(lowered_text)
    source_phrases = [normalized_text] if normalized_text else []
    for entry in entries:
        phrase = str(entry.get("original_phrase") or entry.get("notes") or "").strip().lower()
        if phrase:
            source_phrases.append(phrase)

    haystack = " ; ".join(source_phrases)
    haystack_full = " ; ".join([lowered_text] + [p for p in source_phrases if p != lowered_text])

    emergency_reasons = [reason for term, reason in _EMERGENCY_TERMS.items() if _contains(haystack_full, term)]
    urgent_reasons = [reason for term, reason in _URGENT_TERMS.items() if _contains(haystack_full, term)]
    caution_reasons = [reason for term, reason in _CAUTION_TERMS.items() if _contains(haystack, term)]

    parsed_types = {str(entry.get("injury_type") or entry.get("rehab_type") or "").strip().lower() for entry in entries}
    triage_flags = {str(entry.get("triage_category") or "").strip().lower() for entry in entries}
    flags = {str(flag).strip().lower() for entry in entries for flag in (entry.get("flags") or []) if flag}

    if {"urgent", "structural_red_flag", "suspected_concussion"} & flags or any("tear" in t for t in triage_flags):
        urgent_reasons.append("structured injury triage flagged urgent risk")

    has_surface = bool(parsed_types & _SURFACE_TYPES) or any(t in haystack for t in _SURFACE_TYPES)
    has_open_contact_risk = has_surface and any(token in haystack for token in _CONTACT_WOUND_TERMS)

    if emergency_reasons:
        return ClinicalGate("emergency", True, "emergency_care", sorted(set(emergency_reasons)), ["strength", "conditioning", "sparring", "rehab", "contact"], source_phrases)

    if urgent_reasons:
        status = "no_contact" if has_surface or "concussion" in haystack or "head" in haystack else "no_training"
        blocked = ["sparring", "contact"] if status == "no_contact" else ["strength", "conditioning", "sparring", "rehab", "contact"]
        if "grappl" in haystack and "grappling" not in blocked:
            blocked.append("grappling")
        return ClinicalGate("urgent", True, status, sorted(set(urgent_reasons)), blocked, source_phrases)

    if has_open_contact_risk:
        return ClinicalGate("caution", True, "no_contact", ["open skin wound with contact risk"], ["sparring", "contact", "grappling"], source_phrases)

    if caution_reasons or ("pain" in haystack and not urgent_reasons):
        return ClinicalGate("caution", False, "allow_modified", sorted(set(caution_reasons)) or ["pain above normal training baseline"], [], source_phrases)

    return ClinicalGate("none", False, "allow", [], [], source_phrases)
