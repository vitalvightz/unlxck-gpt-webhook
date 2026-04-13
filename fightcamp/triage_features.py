from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .injury_scoring import score_injury_phrase
from .injury_synonyms import remove_negated_phrases
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

_HIGH_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bopen\s+fracture\b", "open_fracture"),
    (r"\bstress\s+fracture\b", "stress_fracture"),
    (r"\brib\s+fracture\b|\bbroken\s+rib\b", "broken_rib"),
    (r"\bfracture\b", "fracture"),
    (r"\bdislocation\b", "dislocation"),
    (r"\bsuspected\s+concussion\b", "suspected_concussion"),
    (r"\bconcussion\b", "concussion"),
    (r"\bachilles\b[\w\s-]{0,30}\b(?:rupture|tear|avulsion)\b|\b(?:rupture|tear|avulsion)\b[\w\s-]{0,30}\bachilles\b", "achilles_rupture"),
    (r"\bfull[-\s]?thickness\s+rotator\s+cuff\s+tear\b", "full_thickness_rotator_cuff_tear"),
    (r"\btendon\s+(?:rupture|avulsion)\b|\b(?:rupture|avulsion)\s+tendon\b", "tendon_rupture_or_avulsion"),
    (r"\bcomplete\s+ligament\s+tear\b|\bligament\s+tear\s+complete\b", "complete_ligament_tear"),
    (r"\bacl\b[\w\s-]{0,30}\b(?:tear|rupture|reconstruction)\b|\b(?:tear|rupture)\b[\w\s-]{0,30}\bacl\b", "acl_tear"),
)

_STRUCTURAL_SEVERE_TERMS = (
    "tear",
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
)

_NEGATED_SEVERE_PATTERNS = (
    r"\b(?:no|not|without|denies?|denied)\s+(?:an?\s+)?(?:fracture|stress\s+fracture|dislocation|concussion|acl\s+tear|tear|rupture)\b",
    r"\bruled\s+out\s+(?:an?\s+)?(?:fracture|dislocation|concussion|tear|rupture)\b",
    r"\bacl\s+intact\b",
)

_FUNCTION_LOSS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bcan(?:not|'t)?\s+bear\s+weight\b|\bunable\s+to\s+bear\s+weight\b", "cannot_bear_weight"),
    (r"\bcannot\s+lift\s+arm\b|\bunable\s+to\s+lift\s+arm\b", "cannot_lift_arm"),
    (r"\bgiving\s+way\b|\bbuckled\b", "instability_event"),
)

_CLINICIAN_RESTRICTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bavoid\s+(?:contact|spar|impact|loaded|weight\s*bearing)\b", "avoid_high_load"),
    (r"\bno\s+spar(?:ring)?\b", "no_sparring"),
    (r"\bpost[-\s]?op\b|\breconstruction\b|\bsurgery\b", "post_op_or_reconstruction"),
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


def _collect_matches(text: str, patterns: tuple[tuple[str, str], ...]) -> set[str]:
    lowered = str(text or "").lower()
    matches: set[str] = set()
    for pattern, label in patterns:
        if re.search(pattern, lowered):
            matches.add(label)
    return matches


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


def build_triage_features(
    *,
    injuries: str,
    parsed_injuries: list[dict[str, Any]] | None,
    guided_injury: GuidedInjury | None,
    restrictions: list[dict[str, Any]] | None,
) -> TriageFeatures:
    raw_chunks: list[str] = []
    if injuries:
        raw_chunks.extend([chunk.strip() for chunk in injuries.split(",") if chunk.strip()])
    raw_chunks.extend(
        str(item.get("original_phrase") or "").strip()
        for item in (parsed_injuries or [])
        if isinstance(item, dict)
    )
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
        cleaned_chunks.append(cleaned_chunk)

        chunk_red_flags = _collect_matches(cleaned_chunk, _RED_FLAG_PATTERNS)
        if chunk_red_flags:
            red_flags.update(chunk_red_flags)
            red_flag_evidence.add(raw_chunk)

        chunk_function_loss = _collect_matches(cleaned_chunk, _FUNCTION_LOSS_PATTERNS)
        if chunk_function_loss:
            function_loss_signals.update(chunk_function_loss)
            function_loss_evidence.add(raw_chunk)

        chunk_clinician_signals = _collect_matches(cleaned_chunk, _CLINICIAN_RESTRICTION_PATTERNS)
        if chunk_clinician_signals:
            clinician_restriction_signals.update(chunk_clinician_signals)
            clinician_evidence.add(raw_chunk)

        if not _is_negated_severe_chunk(raw_chunk):
            chunk_high_risk = _collect_matches(cleaned_chunk, _HIGH_RISK_PATTERNS)
            if chunk_high_risk:
                high_risk_diagnoses.update(chunk_high_risk)
                high_risk_evidence.add(raw_chunk)

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
