from __future__ import annotations
from dataclasses import dataclass
import re

from .injury_negation import remove_negated_phrases
from .injury_synonyms import detect_structural_red_flags, detect_triage_category
from .injury_taxonomy import get_red_flag_message, is_urgent_injury


@dataclass(frozen=True)
class InjurySafetyDecision:
    red_flag_level: str
    training_status: str
    clearance_required: bool
    blocked_modules: list[str]
    reasons: list[str]
    source_phrases: list[str]


def _clean(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){re.escape(phrase)}([^a-z0-9]|$)", text) is not None


def _hits(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if _has(text, p)]


def evaluate_injury_safety(injury_text: str = "", parsed_entries: list[dict] | None = None) -> InjurySafetyDecision:
    parsed_entries = parsed_entries or []
    raw = _clean(injury_text)
    neg_clean = _clean(remove_negated_phrases(raw))

    reasons, sources = [], []

    def add(reason: str, phrases: list[str] | None = None):
        if reason not in reasons:
            reasons.append(reason)
        for p in phrases or []:
            if p not in sources:
                sources.append(p)

    if (_has(neg_clean, "cold limb") or _has(neg_clean, "blue limb") or _has(neg_clean, "grey limb") or
        _has(neg_clean, "loss of pulse") or _has(neg_clean, "no pulse") or _has(neg_clean, "severe deformity") or
        _has(neg_clean, "obvious deformity") or _has(neg_clean, "head injury with loss of consciousness") or
        _has(neg_clean, "repeated vomiting after head impact") or _has(neg_clean, "worsening neurological symptoms") or
        (_has(neg_clean, "cold") and _has(neg_clean, "blue"))):
        add("Emergency training safety flag: immediate care is needed before any training.")
        return InjurySafetyDecision("emergency", "emergency_care", True, ["strength", "conditioning", "sparring", "contact", "grappling", "rehab"], reasons, sources)

    urgent_types = {"acl_tear", "mcl_tear", "lcl_tear", "pcl_tear", "ligament_tear", "tendon_rupture", "muscle_rupture", "fracture", "dislocation", "concussion", "infection", "nerve_involvement", "acute_nerve_issue", "hernia", "post_surgery"}
    urgent_phrase_hits = _hits(neg_clean, ["cannot bear weight", "can't bear weight", "unable to bear weight", "numbness", "numb", "tingling", "nerve pain", "pus", "red streaking", "fever with wound", "infected wound", "blacked out", "knocked out", "got rocked", "headache after sparring", "headache after head impact", "blurred vision after hit", "vomiting after head impact", "severe swelling", "joint gave way after injury", "snap in achilles", "achilles snap", "felt a snap in achilles"])

    flags = set(detect_structural_red_flags(neg_clean))
    triage = detect_triage_category(neg_clean)
    if triage in urgent_types:
        flags.add(triage)
    if _has(raw, "no fracture") or _has(raw, "ruled out fracture"):
        flags.discard("suspected_fracture")
        flags.discard("fracture")
        flags.discard("structural_red_flag")
        flags.discard("urgent")
        urgent_phrase_hits = [h for h in urgent_phrase_hits if h != "fracture"]

    for entry in parsed_entries:
        for key in (entry.get("injury_type"), entry.get("rehab_type"), entry.get("triage_category")):
            norm = str(key or "").strip().lower()
            if norm in urgent_types or is_urgent_injury(norm):
                flags.add(norm)
                msg = get_red_flag_message(norm)
                if msg:
                    add(f"Training safety flag: {msg}", [norm])
        for f in entry.get("flags") or []:
            normf = str(f).strip().lower()
            if normf in {"urgent", "structural_red_flag"}:
                flags.add(normf)

    all_urgent = sorted(flags.union(urgent_phrase_hits))
    if all_urgent:
        user_signals = [str(x).replace("_", " ") for x in all_urgent if x not in {"urgent", "structural_red_flag"} and not str(x).startswith("suspected_")]
        detail = ", ".join(user_signals[:4])
        reason = "Urgent training safety flag: pause training until appropriately cleared."
        if detail:
            reason = f"{reason} Signals: {detail}"
        add(reason, all_urgent)
        head = any(x in all_urgent for x in ["blacked out", "knocked out", "got rocked", "headache after sparring", "headache after head impact", "blurred vision after hit", "vomiting after head impact", "concussion"])
        if head:
            add("No contact or high-CNS work until appropriately cleared.")
            return InjurySafetyDecision("urgent", "no_training", True, ["sparring", "contact", "grappling", "conditioning", "strength"], reasons, sources)
        return InjurySafetyDecision("urgent", "no_training", True, ["strength", "conditioning", "sparring", "contact", "grappling", "rehab"], reasons, sources)

    caution_hits = _hits(neg_clean, ["cut", "laceration", "graze", "abrasion", "blister", "open wound", "open blister", "bleeding blister", "clicking with pain", "catching with pain", "recurring tendon pain", "moderate swelling"])
    if _has(neg_clean, "clicking") and _has(neg_clean, "pain") and _has(neg_clean, "catching"):
        caution_hits.extend(["clicking", "pain", "catching"])

    surface = any(_has(neg_clean, t) for t in ["cut", "laceration", "graze", "abrasion", "blister"])
    wound_risk = _hits(neg_clean, ["open", "bleeding", "leaking", "reopened", "pus", "grappling", "sparring", "contact"])
    if surface and wound_risk:
        add("Training safety flag: avoid contact and sparring while this wound risk is active.", wound_risk)
        if "pus" in wound_risk:
            add("Possible infection safety flag: clearance is required before return.")
            return InjurySafetyDecision("urgent", "no_training", True, ["strength", "conditioning", "sparring", "contact", "grappling", "rehab"], reasons, sources)
        return InjurySafetyDecision("caution", "no_contact", False, ["sparring", "contact", "grappling"], reasons, sources)

    if caution_hits:
        add("Caution training safety flag: train with modifications and monitor symptoms.", caution_hits)
        return InjurySafetyDecision("caution", "allow_modified", False, [], reasons, sources)

    return InjurySafetyDecision("none", "allow", False, [], [], [])
