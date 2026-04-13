from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .injury_scoring import score_injury_phrase
from .injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
from .input_parsing import GuidedInjury


@dataclass(frozen=True)
class TriageFeatures:
    high_risk_diagnoses: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    structural_severe_signals: list[str] = field(default_factory=list)
    function_loss_signals: list[str] = field(default_factory=list)
    clinician_restriction_signals: list[str] = field(default_factory=list)
    urgent_flags: list[str] = field(default_factory=list)
    raw_evidence: dict[str, list[str]] = field(default_factory=dict)


_TEAR_SYNONYM_PATTERN = r"(?:tear|tears?|torn)"
_RUPTURE_OR_TEAR_PATTERN = rf"(?:rupture|ruptured|{_TEAR_SYNONYM_PATTERN})"

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
    (r"\bvomit(?:ing|ed)?\b[\w\s-]{0,40}\b(?:head|concussion|impact|hit)\b|\b(?:head|concussion|impact|hit)\b[\w\s-]{0,40}\bvomit(?:ing|ed)?\b", "vomiting_after_head_impact"),
    (r"\bsevere\s+headache\b[\w\s-]{0,40}\b(?:head|concussion|impact|hit)\b|\b(?:head|concussion|impact|hit)\b[\w\s-]{0,40}\bsevere\s+headache\b", "severe_headache_after_head_impact"),
    (r"\bseizure(?:s)?\b|\bconvulsion(?:s)?\b", "seizure_or_convulsion"),
    (r"\bamnesi(?:a|c)\b|\bmemory\s+loss\b", "amnesia_or_memory_loss"),
    (r"\bblurred\s+vision\b|\bdouble\s+vision\b|\bdiplopia\b", "blurred_or_double_vision"),
    (r"\bunequal\s+pupil(?:s)?\b|\bone\s+pupil\s+(?:larger|bigger)\b", "unequal_pupils"),
    (r"\bworsening\s+drows(?:y|iness)\b|\bcannot\s+wake\b|\bcan(?:not|'t)\s+wake(?:\s+up)?\b|\bhard\s+to\s+wake\b", "worsening_drowsiness_or_cannot_wake"),
    (r"\bslurred\s+speech\b", "slurred_speech"),
    (r"\bneck\s+pain\b[\w\s-]{0,40}\b(?:after|from)\s+(?:trauma|fall|impact|collision|hit)\b|\b(?:trauma|fall|impact|collision|hit)\b[\w\s-]{0,40}\bneck\s+pain\b", "neck_pain_after_trauma"),
    (r"\b(?:bowel|bladder)\s+(?:changes?|issues?|dysfunction|incontinence)\b[\w\s-]{0,40}\b(?:back|spine|spinal)\b|\b(?:back|spine|spinal)\b[\w\s-]{0,40}\b(?:bowel|bladder)\s+(?:changes?|issues?|dysfunction|incontinence)\b", "bowel_or_bladder_changes_after_back_injury"),
)

_HIGH_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bopen\s+fracture\b", "open_fracture"),
    (r"\bstress\s+fracture\b", "stress_fracture"),
    (r"\brib\s+fracture\b|\bbroken\s+rib\b", "broken_rib"),
    (r"\bfracture\b", "fracture"),
    (r"\bdislocat(?:ion|e|ed|es|ing)\b|\bsublux(?:ation|ing|ed)?\b|\bpartial\s+dislocation\b", "dislocation"),
    (r"\bsuspected\s+concussion\b", "suspected_concussion"),
    (r"\bconcussion\b", "concussion"),
    (
        rf"\bachilles\b[\w\s-]{{0,30}}\b(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion)\b"
        rf"|\b(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion)\b[\w\s-]{{0,30}}\bachilles\b",
        "achilles_rupture",
    ),
    (rf"\bfull[-\s]?thickness\s+rotator\s+cuff\s+{_TEAR_SYNONYM_PATTERN}\b", "full_thickness_rotator_cuff_tear"),
    (
        rf"\btendon\s+(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion|pop|snap|failure)\b"
        rf"|\b(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion|pop|snap|failure)\s+tendon\b",
        "tendon_rupture_or_avulsion",
    ),
    (
        rf"\bcomplete\s+ligament\s+{_TEAR_SYNONYM_PATTERN}\b|\bligament\s+{_TEAR_SYNONYM_PATTERN}\s+complete\b"
        r"|\b(?:ruptured|torn|blown)\s+ligament\b"
        rf"|\bgrade\s*(?:3|iii)\b[\w\s-]{{0,20}}\b(?:ligament|mcl|lcl|acl|pcl|ucl)\b[\w\s-]{{0,20}}\b(?:{_RUPTURE_OR_TEAR_PATTERN}|sprain|injury)?\b"
        r"|\b(?:ligament|mcl|lcl|acl|pcl|ucl)\b[\w\s-]{0,20}\bgrade\s*(?:3|iii)\b",
        "complete_ligament_tear",
    ),
    (r"\bacl\b", "acl_mention"),
    (
        rf"\bacl\b[\w\s-]{{0,30}}\b(?:{_RUPTURE_OR_TEAR_PATTERN}|reconstruction|injury|surgery)\b"
        rf"|\b(?:{_RUPTURE_OR_TEAR_PATTERN}|injury)\b[\w\s-]{{0,30}}\bacl\b",
        "acl_tear",
    ),
    (rf"\bpcl\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b|\b{_RUPTURE_OR_TEAR_PATTERN}\b[\w\s-]{{0,30}}\bpcl\b", "pcl_tear"),
    (rf"\bmcl\b[\w\s-]{{0,30}}\b(?:grade\s*(?:3|iii)|complete)\b[\w\s-]{{0,20}}\b{_RUPTURE_OR_TEAR_PATTERN}\b|\b(?:grade\s*(?:3|iii)|complete)\s+mcl\s+{_TEAR_SYNONYM_PATTERN}\b", "mcl_grade3_tear"),
    (rf"\blcl\b[\w\s-]{{0,30}}\b(?:grade\s*(?:3|iii)|complete)\b[\w\s-]{{0,20}}\b{_RUPTURE_OR_TEAR_PATTERN}\b|\b(?:grade\s*(?:3|iii)|complete)\s+lcl\s+{_TEAR_SYNONYM_PATTERN}\b", "lcl_grade3_tear"),
    (rf"\bbucket[\s-]?handle\s+{_TEAR_SYNONYM_PATTERN}\b[\w\s-]{{0,20}}\bmeniscus\b|\bmeniscus\b[\w\s-]{{0,30}}\bbucket[\s-]?handle\s+{_TEAR_SYNONYM_PATTERN}\b", "meniscus_bucket_handle_tear"),
    (rf"\bpatellar\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b|\bjumper'?s\s+knee\s+rupture\b", "patellar_tendon_rupture"),
    (rf"\bquadriceps\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b", "quadriceps_tendon_rupture"),
    (rf"\bdistal\s+biceps\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b|\bdistal\s+biceps\s+rupture\b", "distal_biceps_tendon_rupture"),
    (rf"\btriceps\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b|\btriceps\s+rupture\b", "triceps_tendon_rupture"),
    (rf"\bpec(?:toralis)?\s+major\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b", "pec_major_tear"),
    (r"\bpatellar\s+dislocation\b|\bdislocated\s+patella\b", "patellar_dislocation"),
    (r"\brecurrent\s+shoulder\s+dislocation\b|\bshoulder\s+dislocat(?:ion|ed)\b[\w\s-]{0,20}\brecurrent\b", "recurrent_shoulder_dislocation"),
    (rf"\blabral\s+{_TEAR_SYNONYM_PATTERN}\b[\w\s-]{{0,40}}\binstability\b|\binstability\b[\w\s-]{{0,40}}\blabral\s+{_TEAR_SYNONYM_PATTERN}\b", "labral_tear_with_instability"),
    (rf"\bhip\s+labral\s+{_TEAR_SYNONYM_PATTERN}\b", "hip_labral_tear"),
    (r"\bsyndesmotic\s+high\s+ankle\s+sprain\b|\bhigh\s+ankle\s+sprain\b[\w\s-]{0,20}\b(?:grade\s*(?:3|iii)|severe)\b", "syndesmotic_high_ankle_sprain_severe"),
    (r"\blisfranc\s+(?:injury|fracture|sprain)\b", "lisfranc_injury"),
    (r"\btibial\s+plateau\s+fracture\b", "tibial_plateau_fracture"),
    (r"\bscaphoid\s+fracture\b", "scaphoid_fracture"),
    (r"\bspinal\s+fracture\b|\bvertebral\s+fracture\b", "spinal_fracture"),
    (r"\borbital\s+fracture\b", "orbital_fracture"),
    (r"\bjaw\s+fracture\b|\bmandib(?:le|ular)\s+fracture\b", "jaw_fracture"),
    (r"\bfacial\s+fracture\b|\bzygoma(?:tic)?\s+fracture\b|\bmaxillary\s+fracture\b", "facial_fracture"),
    (r"\bretinal\s+detach(?:ment|ed)\b|\beye\s+trauma\b|\bocular\s+trauma\b", "retinal_detachment_or_eye_trauma"),
    (r"\bpneumothorax\b|\bcollapsed\s+lung\b", "pneumothorax"),
    (r"\bhemothorax\b|\bhaemothorax\b", "hemothorax"),
    (r"\b(?:spleen|splenic|liver|hepatic)\s+(?:injury|laceration|rupture)\b", "spleen_or_liver_injury"),
    (r"\bcervical\s+spine\s+injury\b|\bc[-\s]?spine\s+injury\b|\bneck\s+fracture\b", "cervical_spine_injury"),
    (r"\bpost[-\s]?op\b[\w\s-]{0,40}\b(?:acl|pcl|mcl|lcl|labral|meniscus|reconstruction)\b|\brecent\s+reconstruction\b", "post_op_reconstruction_active"),
    (r"\bpost[-\s]?op\b[\w\s-]{0,40}\b(?:tendon|repair)\b|\brecent\s+tendon\s+repair\b", "post_op_tendon_repair_active"),
    (r"\bpost[-\s]?op\b[\w\s-]{0,40}\b(?:orif|fixation|fracture\s+repair)\b|\brecent\s+fracture\s+fixation\b", "post_op_fracture_fixation_active"),
    (r"\bseptic\s+(?:joint|arthritis|bursitis|bone)\b|\bosteomyelitis\b", "septic_joint_or_bone_infection"),
)

_STRUCTURAL_SEVERE_TERMS = (
    "tear",
    "torn",
    "rupture",
    "full thickness",
    "full-thickness",
    "grade 3",
    "grade iii",
    "reconstruction",
    "post-op",
    "post op",
    "postoperative",
    "snapped",
    "complete",
    "avulsion",
)

_STRUCTURAL_TISSUE_TERMS = (
    "ligament",
    "tendon",
    "acl",
    "pcl",
    "mcl",
    "lcl",
    "meniscus",
    "labrum",
    "rotator cuff",
    "achilles",
    "hamstring",
    "patellar tendon",
    "bicep tendon",
    "quadriceps tendon",
    "triceps tendon",
    "pec major",
    "lisfranc",
    "syndesmotic",
)

_NEGATED_SEVERE_PATTERNS = (
    rf"\b(?:no|not|without|denies?|denied)\s+(?:an?\s+)?(?:fracture|stress\s+fracture|dislocation|concussion|acl\s+{_TEAR_SYNONYM_PATTERN}|pcl\s+{_TEAR_SYNONYM_PATTERN}|{_TEAR_SYNONYM_PATTERN}|{_RUPTURE_OR_TEAR_PATTERN}|pneumothorax|hemothorax|vomit(?:ing)?)\b",
    rf"\bruled\s+out\s+(?:an?\s+)?(?:fracture|dislocation|concussion|{_TEAR_SYNONYM_PATTERN}|{_RUPTURE_OR_TEAR_PATTERN}|pneumothorax|hemothorax)\b",
    r"\b(?:acl|pcl)\s+intact\b",
    r"\bno\s+fracture\s+seen\b",
)

_ACL_HISTORY_TERMS = (
    "history of",
    "hx of",
    "old acl",
    "prior acl",
    "previous acl",
    "post acl",
    "status post acl",
    "s/p acl",
    "acl rehab history",
    "now cleared",
    "cleared",
)

_ACL_CURRENT_CONCERN_TERMS = (
    "reinjur",
    "new injury",
    "fresh",
    "acute",
    "swelling",
    "instability",
    "giving way",
    "buckl",
    "popped",
    "pop",
    "pain",
)

_HISTORY_TERMS = (
    "history of",
    "hx of",
    "old",
    "prior",
    "previous",
    "years ago",
    "status post",
    "s/p",
    "rehab history",
    "now cleared",
    "cleared",
    "healed",
    "resolved",
    "fully recovered",
    "recovered",
    "past injury",
)

_CURRENT_CONCERN_TERMS = (
    "reinjur",
    "new injury",
    "fresh",
    "acute",
    "current",
    "currently",
    "today",
    "ongoing",
    "worse",
    "worsening",
    "swelling",
    "instability",
    "giving way",
    "buckl",
    "popped",
    "pop",
    "pain",
    "cannot",
    "unable",
)

_RESOLUTION_TERMS = (
    "now cleared",
    "cleared",
    "healed",
    "resolved",
    "fully recovered",
    "recovered",
    "asymptomatic",
    "no symptoms",
    "pain free",
)

_HISTORY_SUPPRESSIBLE_LABELS = {
    "acl_tear",
    "complete_ligament_tear",
    "tendon_rupture_or_avulsion",
    "dislocation",
}

_FUNCTION_LOSS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bcan(?:not|'t)?\s+bear\s+weight\b|\bunable\s+to\s+bear\s+weight\b", "cannot_bear_weight"),
    (r"\bcannot\s+lift\s+arm\b|\bunable\s+to\s+lift\s+arm\b", "cannot_lift_arm"),
    (r"\bgiving\s+way\b|\bbuckled\b", "instability_event"),
    (r"\bcan(?:not|'t)\s+(?:fully\s+)?straighten\s+(?:my\s+)?knee\b|\bunable\s+to\s+straighten\s+knee\b", "cannot_straighten_knee"),
    (r"\bcan(?:not|'t)\s+(?:raise|lift)\s+(?:my\s+)?arm\b|\bunable\s+to\s+raise\s+arm\b", "cannot_raise_arm"),
    (r"\bcan(?:not|'t)\s+push\s+off\s+(?:my\s+)?foot\b|\bunable\s+to\s+push\s+off\b", "cannot_push_off_foot"),
    (r"\bcan(?:not|'t)\s+(?:grip|hold)\b|\bunable\s+to\s+(?:grip|hold)\b", "cannot_grip_or_hold"),
    (r"\blocked\s+knee\b|\bknee\s+is\s+locked\b", "locked_knee"),
    (r"\bjoint\s+gives\s+way\b|\bgives\s+way\s+repeatedly\b|\brecurrent\s+giving\s+way\b", "joint_gives_way_repeatedly"),
)

_CLINICIAN_RESTRICTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bavoid\s+(?:contact|spar|impact|loaded|weight\s*bearing)\b", "avoid_high_load"),
    (r"\bno\s+spar(?:ring)?\b", "no_sparring"),
    (r"\bpost[-\s]?op\b|\breconstruction\b|\bsurgery\b", "post_op_or_reconstruction"),
    (r"\bnon[-\s]?weight\s*bearing\b|\bnwb\b", "non_weight_bearing"),
    (r"\bin\s+(?:a\s+)?(?:walking\s+)?(?:boot|cast)\b|\bwearing\s+(?:a\s+)?(?:boot|cast)\b", "in_a_boot_or_cast"),
    (r"\bon\s+crutches\b|\busing\s+crutches\b", "on_crutches"),
    (r"\b(?:doctor|dr\.?|physio|physical\s+therap(?:ist|y))\b[\w\s-]{0,40}\b(?:no\s+contact|no\s+spar(?:ring)?)\b", "doctor_or_physio_said_no_contact_or_no_sparring"),
)


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


def _injury_text_chunks(injuries: str) -> list[str]:
    text = str(injuries or "").strip()
    if not text:
        return []
    chunks: list[str] = [text]
    chunks = [chunk.strip() for chunk in split_injury_text(text) if chunk.strip()]
    if chunks:
        return list(dict.fromkeys([text, *chunks]))
    comma_chunks = [chunk.strip() for chunk in text.split(",") if chunk.strip()]
    return list(dict.fromkeys([text, *comma_chunks]))


def _parsed_injury_chunks(parsed_injuries: list[dict[str, Any]] | None) -> list[str]:
    chunks: list[str] = []
    for item in parsed_injuries or []:
        if not isinstance(item, dict):
            continue
        original_phrase = str(item.get("original_phrase") or "").strip()
        if original_phrase:
            chunks.append(original_phrase)
        injury_type = str(item.get("injury_type") or "").strip()
        canonical_location = str(item.get("canonical_location") or item.get("region") or "").strip()
        normalized = " ".join(part for part in (canonical_location, injury_type) if part)
        if normalized:
            chunks.append(normalized)
    return chunks


def _collect_matches(text: str, patterns: tuple[tuple[str, str], ...]) -> set[str]:
    lowered = str(text or "").lower()
    matches: set[str] = set()
    for pattern, label in patterns:
        if re.search(pattern, lowered):
            matches.add(label)
    return matches


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    if not terms:
        return False
    pattern = rf"(?<!\w)(?:{'|'.join(re.escape(t) for t in terms)})(?!\w)"
    return bool(re.search(pattern, text))


def _is_structural_severe_signal(*, text: str, scored_injury_type: str) -> bool:
    lowered = str(text or "").lower()
    injury_type = str(scored_injury_type or "").lower()
    has_severe_term = any(term in lowered for term in _STRUCTURAL_SEVERE_TERMS)
    if not has_severe_term:
        return False
    if injury_type in {"sprain", "strain", "instability"}:
        return True
    return any(term in lowered for term in _STRUCTURAL_TISSUE_TERMS)


def _is_negated_severe_chunk(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(re.search(pattern, lowered) for pattern in _NEGATED_SEVERE_PATTERNS)


def _is_acl_history_only_chunk(text: str) -> bool:
    lowered = str(text or "").lower()
    if "acl" not in lowered:
        return False
    has_history = _contains_any_term(lowered, _ACL_HISTORY_TERMS)
    has_current_concern = _contains_any_term(lowered, _ACL_CURRENT_CONCERN_TERMS)
    return has_history and not has_current_concern


def _is_history_only_chunk(text: str) -> bool:
    lowered = str(text or "").lower()
    has_history = _contains_any_term(lowered, _HISTORY_TERMS)
    has_current_concern = _contains_any_term(lowered, _CURRENT_CONCERN_TERMS)
    return has_history and not has_current_concern


def build_triage_features(
    *,
    injuries: str,
    parsed_injuries: list[dict[str, Any]] | None,
    guided_injury: GuidedInjury | None,
    restrictions: list[dict[str, Any]] | None,
) -> TriageFeatures:
    raw_chunks: list[str] = []
    raw_chunks.extend(_injury_text_chunks(injuries))
    raw_chunks.extend(_parsed_injury_chunks(parsed_injuries))
    raw_chunks.extend(_guided_injury_text_chunks(guided_injury))
    raw_chunks.extend(_restriction_text_chunks(restrictions or []))
    raw_chunks = [chunk for chunk in raw_chunks if chunk]

    cleaned_chunks: list[str] = []
    high_risk_diagnoses: set[str] = set()
    red_flags: set[str] = set()
    structural_severe_signals: set[str] = set()
    function_loss_signals: set[str] = set()
    clinician_restriction_signals: set[str] = set()
    urgent_flags: set[str] = set()

    high_risk_evidence: set[str] = set()
    red_flag_evidence: set[str] = set()
    structural_evidence: set[str] = set()
    function_loss_evidence: set[str] = set()
    clinician_evidence: set[str] = set()
    urgent_evidence: set[str] = set()

    for raw_chunk in raw_chunks:
        cleaned_chunk = remove_negated_phrases(raw_chunk).strip().lower()
        if not cleaned_chunk:
            continue
        parsed_type, parsed_location = parse_injury_phrase(cleaned_chunk)
        canonical_chunk = " ".join(
            piece for piece in (str(parsed_location or "").strip(), str(parsed_type or "").strip()) if piece
        ).strip()
        enriched_chunk = " ".join(piece for piece in (cleaned_chunk, canonical_chunk) if piece)
        cleaned_chunks.append(cleaned_chunk)
        history_only_chunk = _is_history_only_chunk(cleaned_chunk)

        chunk_red_flags = _collect_matches(enriched_chunk, _RED_FLAG_PATTERNS)
        if chunk_red_flags:
            red_flags.update(chunk_red_flags)
            red_flag_evidence.add(raw_chunk)

        chunk_function_loss = _collect_matches(enriched_chunk, _FUNCTION_LOSS_PATTERNS)
        if chunk_function_loss:
            function_loss_signals.update(chunk_function_loss)
            function_loss_evidence.add(raw_chunk)

        chunk_clinician_signals = set()
        if not history_only_chunk:
            chunk_clinician_signals = _collect_matches(enriched_chunk, _CLINICIAN_RESTRICTION_PATTERNS)
        if chunk_clinician_signals:
            clinician_restriction_signals.update(chunk_clinician_signals)
            clinician_evidence.add(raw_chunk)

        if not _is_negated_severe_chunk(raw_chunk):
            chunk_high_risk = _collect_matches(enriched_chunk, _HIGH_RISK_PATTERNS)
            if "acl_mention" in chunk_high_risk:
                chunk_high_risk.discard("acl_mention")
                if not _is_acl_history_only_chunk(cleaned_chunk):
                    chunk_high_risk.add("acl_tear")
            if "acl_tear" in chunk_high_risk and _is_acl_history_only_chunk(cleaned_chunk):
                chunk_high_risk.discard("acl_tear")
            if history_only_chunk:
                chunk_high_risk.difference_update(_HISTORY_SUPPRESSIBLE_LABELS)
            if chunk_high_risk:
                high_risk_diagnoses.update(chunk_high_risk)
                high_risk_evidence.add(raw_chunk)

            if not history_only_chunk:
                scored = score_injury_phrase(cleaned_chunk)
                scored_type = str(scored.get("injury_type") or "")
                if _is_structural_severe_signal(text=cleaned_chunk, scored_injury_type=scored_type):
                    structural_severe_signals.add("structural_severe_signal")
                    structural_evidence.add(raw_chunk)

                for flag in scored.get("flags", []):
                    if str(flag).startswith("urgent"):
                        urgent_flags.add(str(flag))
                        urgent_evidence.add(raw_chunk)

    return TriageFeatures(
        high_risk_diagnoses=sorted(high_risk_diagnoses),
        red_flags=sorted(red_flags),
        structural_severe_signals=sorted(structural_severe_signals),
        function_loss_signals=sorted(function_loss_signals),
        clinician_restriction_signals=sorted(clinician_restriction_signals),
        urgent_flags=sorted(urgent_flags),
        raw_evidence={
            "all_input": sorted(set(raw_chunks)),
            "cleaned_input": sorted(set(cleaned_chunks)),
            "high_risk_diagnoses": sorted(high_risk_evidence),
            "red_flags": sorted(red_flag_evidence),
            "structural_severe_signals": sorted(structural_evidence),
            "function_loss_signals": sorted(function_loss_evidence),
            "clinician_restriction_signals": sorted(clinician_evidence),
            "urgent_flags": sorted(urgent_evidence),
        },
    )
