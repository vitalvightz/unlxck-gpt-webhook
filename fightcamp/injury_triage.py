from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from .input_parsing import GuidedInjury, PlanInput
from .injury_registry import (
    MINOR_SURFACE_TRAIN_THROUGH_TYPES,
    SURFACE_MINOR_TRAIN_THROUGH_NOTE,
)
from .injury_negation import remove_negated_phrases
from .injury_synonyms import parse_injury_phrase, split_injury_text
from .sparring_advisories import summarize_sparring_injury_risk
from .triage_features import build_triage_features, parse_guided_note_tags
from .injury_location import get_injury_location


FULL_PLAN = "full_plan"
RESTRICTED_REHAB_ONLY = "restricted_rehab_only"
MEDICAL_HOLD = "medical_hold"
NEEDS_REVIEW = "needs_review"

MODE_EXPLANATIONS: dict[str, str] = {
    MEDICAL_HOLD: "Training guidance is blocked because urgent medical-risk signals were detected.",
    RESTRICTED_REHAB_ONLY: "Normal fight-camp loading is blocked. Only restricted rehab/support guidance is allowed.",
    NEEDS_REVIEW: "Automatic planning is blocked until a coach/admin reviews the injury context.",
}

NEXT_STEPS: dict[str, str] = {
    MEDICAL_HOLD: "Stop automatic training guidance and seek appropriate medical/clinical review.",
    RESTRICTED_REHAB_ONLY: "Generate only restricted rehab/support guidance until cleared.",
    NEEDS_REVIEW: "Hold normal plan generation until coach/admin review.",
}


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

TRIAGE_CATEGORY_ALIASES: dict[str, str] = {
    "tendon_rupture": "tendon_rupture_or_avulsion",
    "ligament_tear": "complete_ligament_tear",
    "mcl_tear": "complete_ligament_tear",
    "lcl_tear": "complete_ligament_tear",
    "nerve_involvement": "neurological_symptoms",
    "infection": "septic_joint_or_bone_infection",
}

_CRITICAL_MEDICAL_HOLD_RED_FLAGS = {
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
    "uncontrolled_bleeding",
}

_DANGEROUS_RED_FLAGS = {
    *_CRITICAL_MEDICAL_HOLD_RED_FLAGS,
    "shortness_of_breath",
    "chest_pain",
    "breathing_pain",
}

# Neurological red flags must never silently route to a full plan. When they
# survive every higher-severity gate above (medical hold, restricted rehab,
# structural history, surface, combo), they still warrant coach/admin review
# rather than automatic full-plan generation. These tokens are only added to
# ``red_flags`` for non-negated, current neurological symptoms (see the negation
# guards in triage_features), so gating on them does not over-fire on "no
# numbness"-style phrasing.
_NEUROLOGICAL_RED_FLAGS = {
    "numbness",
    "tingling",
    "weakness",
    "neurological_symptoms",
}

_WORSENING_TRENDS = {"worse", "worsening", "regressing", "worsened"}

# Red flags that signal a *current* danger. Their presence blocks the RULE 1/2
# resolution/benign-noise down-gate (a resolved or benign mention with any of
# these is no longer benign and must keep its blocking mode).
_CURRENT_DANGER_RED_FLAGS = {
    *_DANGEROUS_RED_FLAGS,
    *_NEUROLOGICAL_RED_FLAGS,
    "cannot_bear_weight",
    "rapid_swelling",
    "worsening_course",
    "deformity",
}

# ``injury_type_source`` values set by guided_injury_resolver when the resolved
# injury_type came from the guided card rather than the free-text parser. These
# must not suppress guided structured diagnosis (see use_guided_diagnosis_fields).
_GUIDED_DERIVED_TYPE_SOURCES = {
    "surface_type",
    "guided_serious_type",
    "guided_tendon_ligament",
    "guided_subtype",
    "guided_type",
    "fallback",
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

_STRUCTURAL_BREAK_RE = re.compile(
    r"\b(?:broke|broken|crack(?:ed)?|snap(?:ped)?)\b"
)
_BROKE_IT_RE = re.compile(r"\b(?:broke|broken)\s+it\b")

_BENIGN_JOINT_NOISE_RE = re.compile(
    r"\b(?:crack(?:ed)?|click(?:ed|ing)?|pop(?:ped)?|snap(?:ped)?)\b"
)

_BENIGN_JOINT_NOISE_SUPPRESSOR_PATTERNS = (
    r"\bno\s+pain\b",
    r"\bpainless\b",
    r"\bno\s+sore(?:ness)?\b",
    r"\bno\s+ach(?:e|ing)\b",
    r"\bno\s+(?:\w+\s+){0,3}swelling\b",
    r"\bno\s+swelling\b",
    r"\bno\s+deformity\b",
    r"\bcan\s+bear\s+weight\b",
    r"\bable\s+to\s+bear\s+weight\b",
    r"\bcan\s+walk\b",
    r"\bcan\s+still\s+walk\b",
    r"\bstill\s+walking\b",
    r"\bfull\s+range\s+of\s+motion\b",
    r"\bmoving\s+fine\b",
    r"\bno\s+bruising\b",
    r"\bsound\s+only\b",
    r"\bnoise\s+only\b",
    r"\bclick(?:ed)?\s+only\b",
    r"\bcrack(?:ed)?\s+only\b",
)

_JOINT_NOISE_ESCALATION_PATTERNS = (
    r"\bcannot\s+bear\s+weight\b",
    r"\bcan'?t\s+bear\s+weight\b",
    r"\bunable\s+to\s+bear\s+weight\b",
    r"\bunable\s+to\s+walk\b",
    r"\bcan'?t\s+walk\b",
    r"\b(?:visible|obvious)\s+deformity\b",
    r"\b(?:rapid\s+)?swelling\b",
    r"\b(?:severe|sharp)\s+pain\b",
    r"\binstability\b",
    r"\bgiv(?:ing|e|en)\s+way\b",
    r"\bbuckled\b",
    r"\blocked\s+joint\b",
    r"\b(?:fall|collision|impact|tackle|twist)\b",
    r"\b(?:confirmed|suspected)\s+fracture\b",
    r"\bdislocation\b",
    r"\brupture\b",
    r"\bruptured\b",
    r"\btear\b",
    r"\btorn\b",
    r"\bavulsion\b",
)

_RECENT_INJURY_TIMELINE_RE = re.compile(
    r"\b(?:"
    r"last\s+(?:day|week|month)|"
    r"this\s+(?:week|month)|"
    r"recent(?:ly)?|"
    r"in\s+the\s+last\s+\d+\s*(?:day|days|week|weeks|month|months)"
    r")\b"
)

_STRUCTURAL_HISTORY_KEYWORDS = ("fracture", "dislocat", "rupture", "tear")
_NEGATED_STRUCTURAL_HISTORY_RE = re.compile(
    r"\b(?:no|not|without|denies?|denied|did\s+not)\s+(?:\w+\s+){0,3}"
    r"(?:fracture|dislocat\w*|rupture|tear)\b"
)

# Matches an explicit denial of the break/crack/snap signal in the SAME chunk
# (e.g. "not broken", "scan ruled out fracture", "ankle not cracked"). Used by
# _has_structural_break_with_location to keep a structural keyword from
# routing fracture when the chunk itself negates it.
_NEGATED_STRUCTURAL_BREAK_RE = re.compile(
    r"\b(?:no|not|without|denies?|denied|did\s+not|ruled\s+out)\s+(?:\w+\s+){0,3}"
    r"(?:broke|broken|crack(?:ed)?|snap(?:ped)?)\b"
)


# ``SURFACE_MINOR_TRAIN_THROUGH_NOTE`` (calm coach-facing note) and
# ``MINOR_SURFACE_TRAIN_THROUGH_TYPES`` are defined in injury_registry so the rehab
# formatter can share them; re-exported here for callers/tests.
_MINOR_SURFACE_TRAIN_THROUGH_TYPES = MINOR_SURFACE_TRAIN_THROUGH_TYPES

# Structured surface routing signals that veto minor train-through: each routes to
# review / medical hold via its own gate. Kept in sync with the surface danger
# gates in ``_apply_surface_injury_signals`` and the surface review gate below.
_SURFACE_DANGER_ROUTING_SIGNALS = {
    "structured:open_wound",
    "structured:needs_stitches",
    "structured:eye_area_wound",
    "structured:sensitive_area_wound",
    "structured:bruise_danger_area",
    "structured:bruise_worsening",
    "structured:infection_signs",
    "structured:systemic_infection",
    "structured:uncontrolled_bleeding",
}


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
    surface_minor_train_through: bool = False
    global_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _GuidedCard:
    severity: str = ""
    trend: str = ""
    avoid: str = ""
    notes: str = ""
    location: str = ""


def _normalize_guided_severity_token(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "mild":
        return "low"
    if normalized == "severe":
        return "high"
    return normalized


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_triage_category(category: str | None) -> str:
    normalized = str(category or "").strip().lower()
    return TRIAGE_CATEGORY_ALIASES.get(normalized, normalized)


def _normalize_triage_categories(categories: set[str]) -> tuple[set[str], set[str]]:
    normalized_categories: set[str] = set()
    raw_aliases: set[str] = set()
    for category in categories:
        normalized_category = normalize_triage_category(category)
        normalized_categories.add(normalized_category)
        if normalized_category != category:
            raw_aliases.add(category)
    return normalized_categories, raw_aliases


def _has_injury_location_context(text: str) -> bool:
    if not text:
        return False
    _, parsed_location = parse_injury_phrase(text)
    return bool(parsed_location)


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _is_benign_joint_noise_chunk(text: str) -> bool:
    if not text:
        return False

    chunk = text.strip().lower()
    if not _BENIGN_JOINT_NOISE_RE.search(chunk):
        return False

    if not _has_any_pattern(chunk, _BENIGN_JOINT_NOISE_SUPPRESSOR_PATTERNS):
        return False

    if _has_any_pattern(chunk, _JOINT_NOISE_ESCALATION_PATTERNS):
        return False

    return True


# ── RULE 1 (resolution/negation) & RULE 2 (benign joint noise) down-gate ──────
# A structural mention that is either benign joint noise or an old/resolved/ruled-
# out history, with NO current danger symptom, must not block planning. These
# helpers classify the free-text evidence so triage can suppress text-scored
# structural signals for those cases (see _structural_signals_are_downgradeable).

_RESOLUTION_MARKER_RE = re.compile(
    r"\b(?:old|former|previous(?:ly)?|prior|history\s+of|"
    r"years?\s+ago|months?\s+ago|long\s+ago|"
    r"healed|fully\s+recovered|recovered|resolved|"
    r"cleared|rehabbed|used\s+to|ruled\s+out)\b"
)

# Present-tense danger SYMPTOMS only. Structural nouns ("fracture"/"tear"/…) name
# the injury rather than a current symptom, so they are deliberately excluded —
# otherwise "old tendon rupture, now healed" would look like a live danger.
_CURRENT_DANGER_SYMPTOM_RE = re.compile(
    r"\b(?:cannot\s+bear\s+weight|can'?t\s+bear\s+weight|unable\s+to\s+bear\s+weight|"
    r"unable\s+to\s+walk|can'?t\s+walk|"
    r"swelling|swollen|"
    r"(?:severe|sharp)\s+pain|"
    r"instability|giv(?:ing|e|en)\s+way|buckl(?:ed|ing)|locked\s+joint|"
    r"(?:visible|obvious)\s+deformity|"
    r"numb(?:ness)?|tingl(?:e|ing)|weak(?:ness)?)\b"
)
_PLAIN_PAIN_RE = re.compile(r"\bpain(?:ful)?\b|\bach(?:e|ing|y)\b|\bsore(?:ness)?\b")

_STRUCTURAL_OR_NOISE_KEYWORD_RE = re.compile(
    r"\b(?:fracture[d]?|broke|broken|dislocat\w*|rupture[d]?|"
    r"tear|torn|acl|achilles|tendon|ligament|meniscus|"
    r"crack(?:ed)?|snap(?:ped)?|pop(?:ped)?|click(?:ed|ing)?)\b"
)

# Confirmed serious structural failure (RULE 3). A bare rupture/avulsion or a
# complete/full-thickness tear is treated as a structural-severe signal when it
# is not resolved/benign (the resolution gate runs first).
_SERIOUS_RUPTURE_RE = re.compile(
    r"\b(?:rupture[d]?|avulsion|complete\s+(?:tear|rupture)|full[-\s]thickness\s+tear)\b"
)


def _text_has_current_danger(text: str) -> bool:
    """Whether the text carries a present-tense danger symptom that is not negated
    ("no pain"/"no swelling"/"can walk"). spaCy negation runs first, then the
    explicit benign suppressors are stripped, so conjunction-split phrasing like
    "ankle popped but no pain, no swelling" does not read as a live danger."""
    cleaned = remove_negated_phrases(str(text or "")).lower()
    # Strip negated symptom lists first ("no pain or swelling") before the narrow
    # per-symptom suppressors, which otherwise consume "no pain" and orphan "or
    # swelling".
    cleaned = re.sub(
        r"\bno\s+(?:pain|swelling|swollen)(?:\s*(?:or|and)\s*(?:pain|swelling|swollen))*\b",
        " ",
        cleaned,
    )
    for pattern in _BENIGN_JOINT_NOISE_SUPPRESSOR_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned)
    if _CURRENT_DANGER_SYMPTOM_RE.search(cleaned):
        return True
    if _PLAIN_PAIN_RE.search(cleaned):
        return True
    return False


def _structural_signals_are_downgradeable(injury_texts: list[str]) -> bool:
    """True when the injury text carries a structural / joint-noise keyword, has no
    current danger symptom, and is either benign joint noise (RULE 2) or an
    old/resolved/ruled-out history (RULE 1). Evaluated over the whole text so a
    suppressor or resolution marker in a different clause still applies. Callers
    additionally require the absence of other live danger signals before acting."""
    combined = " ".join(str(t or "") for t in injury_texts).strip().lower()
    if not combined or not _STRUCTURAL_OR_NOISE_KEYWORD_RE.search(combined):
        return False
    if _text_has_current_danger(combined):
        return False
    is_benign_noise = bool(_BENIGN_JOINT_NOISE_RE.search(combined)) and _has_any_pattern(
        combined, _BENIGN_JOINT_NOISE_SUPPRESSOR_PATTERNS
    )
    is_resolved = bool(
        _RESOLUTION_MARKER_RE.search(combined)
        or _NEGATED_STRUCTURAL_HISTORY_RE.search(combined)
        or _NEGATED_STRUCTURAL_BREAK_RE.search(combined)
    )
    return is_benign_noise or is_resolved


# A serious structural FAILURE (not benign joint noise). Used to ensure a
# resolution/benign marker on one injury cannot down-gate a *different* current
# serious injury in the same payload (e.g. "old fracture healed, new Achilles
# rupture today").
_SERIOUS_STRUCTURAL_KEYWORD_RE = re.compile(
    r"\b(?:rupture[d]?|avulsion|fracture[d]?|broke|broken|dislocat\w*|"
    r"acl|achilles|complete\s+(?:tear|rupture)|full[-\s]thickness\s+tear|tear|torn)\b"
)


def _chunk_resolved_or_benign(chunk: str) -> bool:
    if _is_benign_joint_noise_chunk(chunk):
        return True
    if _text_has_current_danger(chunk):
        return False
    return bool(
        _RESOLUTION_MARKER_RE.search(chunk)
        or _NEGATED_STRUCTURAL_HISTORY_RE.search(chunk)
        or _NEGATED_STRUCTURAL_BREAK_RE.search(chunk)
    )


def _has_unresolved_serious_structural(injury_texts: list[str]) -> bool:
    """True when any clause names a serious structural injury that is NOT itself
    resolved/old/benign. Evaluated per chunk so a resolution marker in one clause
    cannot mask a live serious injury in another. This blocks the RULE 1/2
    down-gate from ever clearing a current serious structural signal."""
    for raw in injury_texts:
        for chunk in split_injury_text(str(raw or "")):
            c = str(chunk or "").strip().lower()
            if not c or not _SERIOUS_STRUCTURAL_KEYWORD_RE.search(c):
                continue
            if not _chunk_resolved_or_benign(c):
                return True
    return False


def _has_structural_break_with_location(text: str) -> bool:
    if not text:
        return False

    for chunk in split_injury_text(text):
        raw_chunk = str(chunk or "").strip().lower()
        if not raw_chunk or not _STRUCTURAL_BREAK_RE.search(raw_chunk):
            continue

        # Must happen before negation stripping.
        # Example: "neck cracked but no pain" needs "no pain" intact.
        if _is_benign_joint_noise_chunk(raw_chunk):
            continue

        # Catch explicit denials that the spaCy-based remove_negated_phrases
        # may miss (e.g. "not broken", "ruled out fracture").
        if _NEGATED_STRUCTURAL_BREAK_RE.search(raw_chunk):
            continue

        cleaned_chunk = remove_negated_phrases(raw_chunk).strip().lower()
        if not cleaned_chunk or not _STRUCTURAL_BREAK_RE.search(cleaned_chunk):
            continue

        if _has_injury_location_context(cleaned_chunk):
            return True

    return False


def _has_structural_break_signal(*, text: str, context_text: str) -> bool:
    if not text:
        return False

    for chunk in split_injury_text(text):
        raw_chunk = str(chunk or "").strip().lower()
        if not raw_chunk or not _STRUCTURAL_BREAK_RE.search(raw_chunk):
            continue

        # Must happen before negation stripping.
        # Example: "ankle cracked but no pain" needs "no pain" intact.
        if _is_benign_joint_noise_chunk(raw_chunk):
            continue

        # Catch explicit denials that the spaCy-based remove_negated_phrases
        # may miss (e.g. "not broken", "ruled out fracture").
        if _NEGATED_STRUCTURAL_BREAK_RE.search(raw_chunk):
            continue

        cleaned_chunk = remove_negated_phrases(raw_chunk).strip().lower()
        if not cleaned_chunk or not _STRUCTURAL_BREAK_RE.search(cleaned_chunk):
            continue

        if _has_injury_location_context(cleaned_chunk):
            return True

        if _BROKE_IT_RE.search(cleaned_chunk) and _has_injury_location_context(context_text):
            return True

    return False


def _has_mapped_route(categories: set[str], route: str) -> bool:
    return any(_HIGH_RISK_CATEGORY_ROUTE.get(category) == route for category in categories)


def _build_result(
    *,
    mode: str,
    reasons: list[str],
    clinician_clearance_required: bool,
    should_block_stage2: bool,
    red_flags: set[str],
    matched_categories: set[str],
    routing_reasons: set[str],
    urgent_flags: set[str],
    sparring_risk_band: str,
    surface_minor_train_through: bool = False,
    global_notes: list[str] | None = None,
) -> InjuryTriageResult:
    return InjuryTriageResult(
        mode=mode,
        reasons=reasons,
        clinician_clearance_required=clinician_clearance_required,
        red_flags=sorted(red_flags),
        matched_high_risk_categories=sorted(matched_categories),
        routing_reasons=sorted(routing_reasons),
        should_block_stage2=should_block_stage2,
        urgent_flags=sorted(urgent_flags),
        sparring_risk_band=sparring_risk_band,
        surface_minor_train_through=surface_minor_train_through,
        global_notes=list(global_notes or []),
    )


def _parsed_entry_location(entry: dict[str, Any]) -> str:
    return _normalized_text(get_injury_location(entry))


def _guided_card_from_parsed_entry(entry: dict[str, Any]) -> _GuidedCard | None:
    card = _GuidedCard(
        severity=_normalize_guided_severity_token(entry.get("severity") or ""),
        trend=_normalized_text(entry.get("trend")),
        avoid=_normalized_text(entry.get("avoid")),
        notes=_normalized_text(entry.get("notes")),
        location=_parsed_entry_location(entry),
    )
    if any((card.severity, card.trend, card.avoid, card.notes, card.location)):
        return card
    return None


def _collect_guided_card_evidence(plan_input: PlanInput) -> list[_GuidedCard]:
    cards: list[_GuidedCard] = []

    for entry in plan_input.parsed_injuries or []:
        if not isinstance(entry, dict):
            continue
        card = _guided_card_from_parsed_entry(entry)
        if card is not None and any((card.severity, card.trend, card.avoid, card.notes)):
            cards.append(card)

    if cards:
        return cards

    for guided in _effective_guided_injuries(plan_input):
        fallback_card = _GuidedCard(
            severity=_normalize_guided_severity_token(guided.severity or ""),
            trend=_normalized_text(guided.trend),
            avoid=_normalized_text(guided.avoid),
            notes=_normalized_text(guided.notes),
            location=_normalized_text(guided.area),
        )
        if any(asdict(fallback_card).values()):
            cards.append(fallback_card)

    return cards


def _effective_guided_injuries(plan_input: PlanInput) -> list[GuidedInjury]:
    guided_injuries = getattr(plan_input, "guided_injuries", None)
    if guided_injuries:
        return list(guided_injuries)

    guided = getattr(plan_input, "guided_injury", None)
    return [guided] if guided is not None else []


_GUIDED_STRUCTURAL_INJURY_TYPES = {"fracture", "dislocation", "tendon_ligament"}


def _guided_card_resolved_structural(guided: GuidedInjury) -> bool | None:
    """For a structural guided card (fracture/dislocation/tendon-ligament), return
    whether it is old-and-cleared with no current concern (RULE 1). Returns None
    when the card is not a structural type (so callers can ignore it)."""
    injury_type = _normalized_text(guided.injury_type)
    if injury_type not in _GUIDED_STRUCTURAL_INJURY_TYPES:
        return None
    timeframe = _normalized_text(guided.timeframe)
    cleared = _normalized_text(guided.cleared)
    severity = _normalize_guided_severity_token(guided.severity or "")
    trend = _normalized_text(guided.trend)
    tags = parse_guided_note_tags(_normalized_text(guided.notes))
    dislocation_tags = tags.get("dislocation", set())
    recurrent = "recurrent_yes" in dislocation_tags or bool(
        {"relocated_no", "relocated_not_sure"} & dislocation_tags
    )
    return (
        timeframe in _OLD_CLEARED_TIMEFRAMES
        and cleared == "yes"
        and severity != "high"
        and trend not in _WORSENING_TRENDS
        and not recurrent
    )


def _guided_combos(cards: list[_GuidedCard]) -> set[tuple[str, str]]:
    return {
        (card.severity, card.trend)
        for card in cards
        if card.severity or card.trend
    }


def _joined_card_field(cards: list[_GuidedCard], field_name: str) -> str:
    return " | ".join(
        value
        for card in cards
        if (value := getattr(card, field_name, ""))
    )


def _has_guided_structural_broke_signal(
    *,
    guided_notes: str,
    cleaned_combined_text: str,
) -> bool:
    return _has_structural_break_signal(
        text=guided_notes,
        context_text=cleaned_combined_text,
    )


def _apply_card_area_broke_signals(
    *,
    cards: list[_GuidedCard],
    matched_categories: set[str],
    routing_reasons: set[str],
) -> None:
    for card in cards:
        raw_notes = str(card.notes or "").strip().lower()
        if not raw_notes:
            continue

        contextual_card_text = " ".join(
            part for part in (card.location, raw_notes) if part
        )

        if _has_structural_break_signal(
            text=contextual_card_text,
            context_text=contextual_card_text,
        ):
            matched_categories.add("fracture")
            routing_reasons.add("guided_injury:card_area_context_broke_signal")


def _has_recent_structural_history_signal(cards: list[_GuidedCard]) -> bool:
    for card in cards:
        raw_notes = (card.notes or "").strip().lower()
        notes = remove_negated_phrases(raw_notes).strip().lower()
        if not notes:
            continue

        has_recent_timeline = bool(_RECENT_INJURY_TIMELINE_RE.search(notes))
        has_negated_structural_history = bool(_NEGATED_STRUCTURAL_HISTORY_RE.search(raw_notes))
        has_structural_signal = bool(
            _has_structural_break_signal(
                text=raw_notes,
                context_text=f"{card.location} {raw_notes}",
            )
            or (
                not has_negated_structural_history
                and any(keyword in notes for keyword in _STRUCTURAL_HISTORY_KEYWORDS)
            )
        )

        if has_recent_timeline and has_structural_signal:
            return True

    return False


def _apply_urgent_flags(
    *,
    urgent_flags: set[str],
    red_flags: set[str],
    matched_categories: set[str],
    routing_reasons: set[str],
) -> None:
    if "urgent_fracture" in urgent_flags:
        matched_categories.add("fracture")
        # Surface the emergency in the clinician-facing red flags too.
        red_flags.add("fracture")
        routing_reasons.add("urgent_flag:urgent_fracture")

    if "urgent_dislocation" in urgent_flags:
        matched_categories.add("dislocation")
        red_flags.add("dislocation")
        routing_reasons.add("urgent_flag:urgent_dislocation")

    if "urgent_nerve" in urgent_flags:
        red_flags.add("neurological_symptoms")
        routing_reasons.add("urgent_flag:urgent_nerve")


def _apply_high_risk_mapping_reasons(
    *,
    matched_categories: set[str],
    routing_reasons: set[str],
) -> None:
    for category in matched_categories:
        route = _HIGH_RISK_CATEGORY_ROUTE.get(category)
        if route:
            routing_reasons.add(f"mapped:{category}:{route}")


def _chest_with_systemic_red_flags(*, red_flags: set[str], combined_text: str) -> bool:
    return "chest_pain" in red_flags and (
        "shortness_of_breath" in red_flags
        or "coughing_blood" in red_flags
        or _has_any_pattern(combined_text, _TRAUMA_CONTEXT_PATTERNS)
        or "worsening_course" in red_flags
    )


def _rib_breathing_unsafe(
    *,
    red_flags: set[str],
    matched_categories: set[str],
    combined_text: str,
) -> bool:
    rib_or_chest_context = any(
        token in combined_text for token in ("rib", "intercostal", "chest")
    )

    if not rib_or_chest_context or "breathing_pain" not in red_flags:
        return False

    return (
        any(
            category in matched_categories
            for category in ("broken_rib", "fracture", "open_fracture")
        )
        or _has_any_pattern(combined_text, _TRAUMA_CONTEXT_PATTERNS)
        or "shortness_of_breath" in red_flags
    )


def _neurological_combo(*, red_flags: set[str], combined_text: str) -> bool:
    explicit_neuro_context = bool(re.search(_NEURO_CONTEXT_PATTERN, combined_text)) and any(
        flag in red_flags
        for flag in ("loss_of_consciousness", "numbness", "weakness", "confusion")
    )

    loss_of_consciousness_with_neuro_symptoms = (
        "loss_of_consciousness" in red_flags
        and any(flag in red_flags for flag in ("numbness", "weakness", "tingling", "confusion"))
    )

    return explicit_neuro_context or loss_of_consciousness_with_neuro_symptoms


def _initial_medical_hold_gate(
    *,
    red_flags: set[str],
    matched_categories: set[str],
    combined_text: str,
    routing_reasons: set[str],
) -> tuple[bool, bool, bool]:
    medical_hold = False

    if red_flags & _CRITICAL_MEDICAL_HOLD_RED_FLAGS:
        medical_hold = True
        routing_reasons.add("critical_red_flag")

    if _has_mapped_route(matched_categories, MEDICAL_HOLD):
        medical_hold = True
        routing_reasons.add("mapped_medical_hold_category")

    chest_with_systemic = _chest_with_systemic_red_flags(
        red_flags=red_flags,
        combined_text=combined_text,
    )
    if chest_with_systemic:
        medical_hold = True
        routing_reasons.add("chest_red_flag_combination")

    rib_breathing_unsafe = _rib_breathing_unsafe(
        red_flags=red_flags,
        matched_categories=matched_categories,
        combined_text=combined_text,
    )
    if rib_breathing_unsafe:
        medical_hold = True
        routing_reasons.add("rib_breathing_red_flag_combination")

    neuro_combo = _neurological_combo(
        red_flags=red_flags,
        combined_text=combined_text,
    )
    if neuro_combo:
        medical_hold = True
        routing_reasons.add("neurological_red_flag_combination")

    return medical_hold, chest_with_systemic or rib_breathing_unsafe, neuro_combo


def _initial_restricted_rehab_gate(
    *,
    red_flags: set[str],
    matched_categories: set[str],
    structural_severe_signals: set[str],
    clinician_restriction_signals: set[str],
    routing_reasons: set[str],
) -> bool:
    restricted_rehab = False

    if (
        _has_mapped_route(matched_categories, RESTRICTED_REHAB_ONLY)
        or "structural_high_severity" in matched_categories
    ):
        restricted_rehab = True
        routing_reasons.add("mapped_restricted_category")

    if any(flag in red_flags for flag in ("cannot_bear_weight", "rapid_swelling")):
        restricted_rehab = True
        routing_reasons.add("structural_function_red_flag")

    if structural_severe_signals:
        restricted_rehab = True
        routing_reasons.add("scored_structural_severe_signal")

    if clinician_restriction_signals:
        restricted_rehab = True
        routing_reasons.add("clinician_restriction_signal")

    return restricted_rehab


def _apply_sparring_risk_gate(
    *,
    injury_texts: list[str],
    has_guided_high_severity: bool,
    red_flags: set[str],
    restricted_rehab: bool,
    medical_hold: bool,
    routing_reasons: set[str],
) -> tuple[str, bool, bool]:
    sparring_risk = summarize_sparring_injury_risk(injury_texts=injury_texts)
    highest_band = str(sparring_risk.get("risk_band") or "green")

    if (
        highest_band in {"red", "black"}
        and has_guided_high_severity
        and (restricted_rehab or medical_hold)
    ):
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

    return highest_band, restricted_rehab, medical_hold


def _has_uncertainty_trigger(
    *,
    cards: list[_GuidedCard],
    matched_categories: set[str],
    red_flags: set[str],
    features: Any,
    clinician_restriction_signals: set[str],
    urgent_flags: set[str],
) -> bool:
    if not cards:
        return False

    has_any_safety_signal = any(
        (
            matched_categories,
            red_flags,
            features.structural_severe_signals,
            clinician_restriction_signals,
            features.function_loss_signals,
            urgent_flags,
        )
    )
    if has_any_safety_signal:
        return False

    return sum(len(card.notes.split()) for card in cards) < 3


def _combo_gate_result(
    *,
    combos: set[tuple[str, str]],
    red_flags: set[str],
    matched_categories: set[str],
    routing_reasons: set[str],
    urgent_flags: set[str],
    highest_band: str,
    features: Any,
    has_chest_or_neuro_combo: bool,
    has_mapped_medical_hold: bool,
    has_mapped_restricted: bool,
    has_dangerous_red_flags: bool,
    has_structural_severe_signal: bool,
    has_clinician_restriction_signal: bool,
    has_function_loss_signal: bool,
    has_uncertainty_trigger: bool,
) -> InjuryTriageResult | None:
    if any(("high", trend) in combos for trend in _WORSENING_TRENDS):
        routing_reasons.add("combo_gate:high_worsening")

        if has_dangerous_red_flags or has_chest_or_neuro_combo or has_mapped_medical_hold:
            return _build_result(
                mode=MEDICAL_HOLD,
                reasons=[
                    "High-severity worsening injury with dangerous escalation signals was detected.",
                    "Training guidance is blocked pending immediate medical review.",
                ],
                clinician_clearance_required=True,
                should_block_stage2=True,
                red_flags=red_flags,
                matched_categories=matched_categories,
                routing_reasons=routing_reasons,
                urgent_flags=urgent_flags,
                sparring_risk_band=highest_band,
            )

        # RULE 3: a high-severity *worsening* injury is a confirmed serious signal
        # and is held in restricted rehab, not merely flagged for review.
        return _build_result(
            mode=RESTRICTED_REHAB_ONLY,
            reasons=[
                "High-severity worsening injury is held in restricted rehab before any normal plan.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=True,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if ("high", "") in combos:
        routing_reasons.add("combo_gate:high_trend_missing")

        if (
            has_structural_severe_signal
            or has_mapped_restricted
            or has_clinician_restriction_signal
            or has_function_loss_signal
        ):
            return _build_result(
                mode=RESTRICTED_REHAB_ONLY,
                reasons=[
                    "High-severity injury with missing trend still shows structural/restriction risk signals.",
                    "Normal fight-camp loading/sparring generation remains suspended.",
                ],
                clinician_clearance_required=True,
                should_block_stage2=True,
                red_flags=red_flags,
                matched_categories=matched_categories,
                routing_reasons=routing_reasons,
                urgent_flags=urgent_flags,
                sparring_risk_band=highest_band,
            )

        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "High-severity injury is missing trend status and requires coach/admin review.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if ("high", "stable") in combos:
        routing_reasons.add("combo_gate:high_stable")

        if (
            has_structural_severe_signal
            or has_mapped_restricted
            or has_clinician_restriction_signal
            or has_function_loss_signal
        ):
            return _build_result(
                mode=RESTRICTED_REHAB_ONLY,
                reasons=[
                    "High-severity stable injury still shows structural/restriction risk signals.",
                    "Normal fight-camp loading/sparring generation remains suspended.",
                ],
                clinician_clearance_required=True,
                should_block_stage2=True,
                red_flags=red_flags,
                matched_categories=matched_categories,
                routing_reasons=routing_reasons,
                urgent_flags=urgent_flags,
                sparring_risk_band=highest_band,
            )

        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "High-severity stable injury requires coach/admin review before any normal plan.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if any(("moderate", trend) in combos for trend in _WORSENING_TRENDS):
        routing_reasons.add("combo_gate:moderate_worsening")

        if has_dangerous_red_flags or has_mapped_medical_hold:
            return _build_result(
                mode=MEDICAL_HOLD,
                reasons=[
                    "Moderate worsening injury includes dangerous escalation signals.",
                    "Training guidance is blocked pending immediate medical review.",
                ],
                clinician_clearance_required=True,
                should_block_stage2=True,
                red_flags=red_flags,
                matched_categories=matched_categories,
                routing_reasons=routing_reasons,
                urgent_flags=urgent_flags,
                sparring_risk_band=highest_band,
            )

        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "Moderate worsening injury requires coach/admin review before any normal plan.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if any(("low", trend) in combos for trend in _WORSENING_TRENDS):
        routing_reasons.add("combo_gate:low_worsening")

        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "Low-severity worsening injury still requires review before normal planning.",
                "Automatic full-plan generation is blocked by triage combo gate.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if ("moderate", "stable") in combos:
        routing_reasons.add("combo_gate:moderate_stable_allowlist_check")

        has_mapped_serious_category = has_mapped_medical_hold or has_mapped_restricted
        should_block = (
            has_dangerous_red_flags
            or has_structural_severe_signal
            or has_clinician_restriction_signal
            or has_mapped_serious_category
            or has_uncertainty_trigger
        )

        if should_block:
            routing_reasons.add("combo_gate:moderate_stable_blocked")

            return _build_result(
                mode=NEEDS_REVIEW,
                reasons=[
                    "Moderate stable injury did not meet the strict allowlist for automatic full planning.",
                    "Coach/admin review is required before normal plan generation.",
                ],
                clinician_clearance_required=False,
                should_block_stage2=True,
                red_flags=red_flags,
                matched_categories=matched_categories,
                routing_reasons=routing_reasons,
                urgent_flags=urgent_flags,
                sparring_risk_band=highest_band,
            )

    return None


_STRUCTURED_TEAR_KEYWORDS = re.compile(
    r"\b(?:tear|torn|rupture|ruptured|pop|snap|instability|giving\s+way)\b",
    re.IGNORECASE,
)

_STRUCTURED_STITCHES_KEYWORDS = re.compile(
    r"\b(?:stitches|needs?\s+stitches|deep\s+gash|sutures?)\b",
    re.IGNORECASE,
)

_RIB_CHEST_HEAD_EYE_PATTERN = re.compile(
    r"\b(?:rib|chest|head|eye|temple|orbital|skull)\b",
    re.IGNORECASE,
)

_OLD_CLEARED_TIMEFRAMES = {"old_cleared", "three_plus_months"}

_HEAD_IMPACT_RED_FLAG_TOKENS = {
    "loss_of_consciousness",
    "vomiting",
    "severe_headache",
    "memory_loss",
    "blurred_or_double_vision",
    "confusion",
    "slurred_speech",
    "seizure",
}

_HEAD_IMPACT_TAG_TO_RED_FLAG = {
    "loss_of_consciousness": "loss_of_consciousness",
    "vomiting": "vomiting_after_head_impact",
    "severe_headache": "severe_headache_after_head_impact",
    "memory_loss": "amnesia_or_memory_loss",
    "blurred_or_double_vision": "blurred_or_double_vision",
    "confusion": "confusion",
    "slurred_speech": "slurred_speech",
    "seizure": "seizure_or_convulsion",
}

_CHEST_TAG_TO_RED_FLAG = {
    "breathing_pain": "breathing_pain",
    "shortness_of_breath": "shortness_of_breath",
    "chest_pain": "chest_pain",
    "coughing_blood": "coughing_blood",
}

_NERVE_TAG_TO_RED_FLAGS = {
    "type_numbness": {"numbness"},
    "type_tingling": {"tingling"},
    "type_weakness": {"weakness"},
    "type_mixed": {"numbness", "tingling", "weakness"},
}

_INFECTION_SYSTEMIC_SIGNS = {"fever", "spreading"}
_INFECTION_LOCAL_SIGNS = {"pus", "redness_heat"}


def _apply_structured_injury_signals(
    *,
    guided: GuidedInjury,
    matched_categories: set[str],
    red_flags: set[str],
    clinician_restriction_signals: set[str],
    routing_reasons: set[str],
    use_guided_diagnosis_fields: bool,
) -> None:
    injury_type = (guided.injury_type or "").strip().lower()
    surface_type = (guided.surface_type or "").strip().lower()
    timeframe = (guided.timeframe or "").strip().lower()
    cleared = (guided.cleared or "").strip().lower()
    severity = (guided.severity or "").strip().lower()
    trend = (guided.trend or "").strip().lower()
    open_wound = (guided.open_wound or "").strip().lower()
    bleeding_status = (guided.bleeding_status or "").strip().lower()
    infection_signs = {s.strip().lower() for s in (guided.infection_signs or []) if s.strip()}
    impact_related = (guided.impact_related or "").strip().lower()
    sensitive_area = (guided.sensitive_area or "").strip().lower()
    notes = (guided.notes or "").strip().lower()
    area = (guided.area or "").strip().lower()
    note_tags = parse_guided_note_tags(notes)

    old_and_cleared = timeframe in _OLD_CLEARED_TIMEFRAMES and cleared == "yes"
    has_current_concern = (
        severity == "high"
        or trend in _WORSENING_TRENDS
        or cleared in ("no", "not_sure")
    )

    if use_guided_diagnosis_fields:
        if injury_type == "fracture":
            if old_and_cleared and not has_current_concern:
                routing_reasons.add("structured:fracture_old_cleared_no_concern")
            else:
                matched_categories.add("fracture")
                routing_reasons.add("structured:fracture")

        elif injury_type == "dislocation":
            dislocation_tags = note_tags.get("dislocation", set())
            if "recurrent_yes" in dislocation_tags:
                routing_reasons.add("tagged_note:dislocation:recurrent_yes")
                matched_categories.add("dislocation")
                has_current_concern = True

            if {"relocated_no", "relocated_not_sure"} & dislocation_tags:
                routing_reasons.add("tagged_note:dislocation:relocation_uncertain_or_no")
                matched_categories.add("dislocation")
                has_current_concern = True

            if old_and_cleared and not has_current_concern:
                routing_reasons.add("structured:dislocation_old_cleared_no_concern")
            else:
                matched_categories.add("dislocation")
                routing_reasons.add("structured:dislocation")

        elif injury_type == "tendon_ligament":
            should_flag = (
                severity == "high"
                or trend in _WORSENING_TRENDS
                or cleared in ("no", "not_sure")
                or bool(_STRUCTURED_TEAR_KEYWORDS.search(notes))
            )
            if should_flag:
                matched_categories.add("tendon_rupture_or_avulsion")
                routing_reasons.add("structured:tendon_ligament_risk")
            else:
                routing_reasons.add("structured:tendon_ligament_mild")

        elif injury_type == "post_surgery":
            clinician_restriction_signals.add("post_op_or_reconstruction")
            routing_reasons.add("structured:post_surgery")
            if cleared in ("no", "not_sure"):
                routing_reasons.add("structured:post_surgery_not_cleared")
            elif old_and_cleared:
                routing_reasons.add("structured:post_surgery_old_cleared")

        elif injury_type == "head_impact":
            matched_categories.add("concussion")
            routing_reasons.add("structured:head_impact")

        elif injury_type == "nerve_symptoms":
            routing_reasons.add("structured:nerve_symptoms")
            if trend in _WORSENING_TRENDS or impact_related == "yes":
                routing_reasons.add("structured:nerve_symptoms_escalated")

        elif injury_type == "chest_breathing":
            routing_reasons.add("structured:chest_breathing")

        elif injury_type == "surface_injury":
            _apply_surface_injury_signals(
                surface_type=surface_type,
                bleeding_status=bleeding_status,
                open_wound=open_wound,
                sensitive_area=sensitive_area,
                infection_signs=infection_signs,
                impact_related=impact_related,
                trend=trend,
                severity=severity,
                notes=notes,
                area=area,
                red_flags=red_flags,
                matched_categories=matched_categories,
                routing_reasons=routing_reasons,
            )

    for token in note_tags.get("red_flags", set()):
        mapped = _HEAD_IMPACT_TAG_TO_RED_FLAG.get(token)
        if mapped:
            red_flags.add(mapped)
            routing_reasons.add(f"tagged_note:red_flags:{token}")

    nerve_tags = note_tags.get("nerve_symptoms", set())
    if use_guided_diagnosis_fields and injury_type == "nerve_symptoms" and not nerve_tags:
        red_flags.add("numbness")

    for token in nerve_tags:
        mapped = _NERVE_TAG_TO_RED_FLAGS.get(token)
        if mapped:
            red_flags.update(mapped)
            routing_reasons.add(f"tagged_note:nerve_symptoms:{token}")

    chest_tags = note_tags.get("chest_symptoms", set())
    if use_guided_diagnosis_fields and injury_type == "chest_breathing" and not chest_tags:
        red_flags.add("breathing_pain")
        red_flags.add("chest_pain")

    for token in chest_tags:
        mapped = _CHEST_TAG_TO_RED_FLAG.get(token)
        if mapped:
            red_flags.add(mapped)
            routing_reasons.add(f"tagged_note:chest_symptoms:{token}")

    if injury_type == "surface_injury":
        _apply_surface_injury_signals(
            surface_type=surface_type,
            bleeding_status=bleeding_status,
            open_wound=open_wound,
            sensitive_area=sensitive_area,
            infection_signs=infection_signs,
            impact_related=impact_related,
            trend=trend,
            severity=severity,
            notes=notes,
            area=area,
            red_flags=red_flags,
            matched_categories=matched_categories if use_guided_diagnosis_fields else set(),
            routing_reasons=routing_reasons,
        )


def _apply_surface_injury_signals(
    *,
    surface_type: str,
    bleeding_status: str,
    open_wound: str,
    sensitive_area: str,
    infection_signs: set[str],
    impact_related: str,
    trend: str,
    severity: str,
    notes: str,
    area: str,
    red_flags: set[str],
    matched_categories: set[str],
    routing_reasons: set[str],
) -> None:
    routing_reasons.add(f"structured:surface_{surface_type or 'unspecified'}")

    if bleeding_status in {"wont_stop", "uncontrolled"}:
        red_flags.add("uncontrolled_bleeding")
        routing_reasons.add("structured:uncontrolled_bleeding")

    if open_wound == "yes":
        red_flags.add("open_wound")
        routing_reasons.add("structured:open_wound")

    if sensitive_area == "eye":
        red_flags.add("eye_area_wound")
        routing_reasons.add("structured:eye_area_wound")
    elif sensitive_area in ("mouth", "face", "yes"):
        red_flags.add("sensitive_area_wound")
        routing_reasons.add("structured:sensitive_area_wound")

    active_infection = infection_signs - {"none", ""}
    if active_infection:
        red_flags.add("infection_signs")
        routing_reasons.add("structured:infection_signs")
        if active_infection & _INFECTION_SYSTEMIC_SIGNS:
            routing_reasons.add("structured:systemic_infection")

    if surface_type in ("cut", "laceration"):
        if _STRUCTURED_STITCHES_KEYWORDS.search(notes):
            red_flags.add("needs_stitches")
            routing_reasons.add("structured:needs_stitches")

    if surface_type == "bruise":
        if impact_related == "yes" and _RIB_CHEST_HEAD_EYE_PATTERN.search(area):
            routing_reasons.add("structured:bruise_danger_area")
        if trend in _WORSENING_TRENDS:
            routing_reasons.add("structured:bruise_worsening")


def _minor_surface_train_through(
    *,
    plan_input: PlanInput,
    routing_reasons: set[str],
    red_flags: set[str],
    matched_categories: set[str],
    urgent_flags: set[str],
) -> bool:
    """Whether the payload is a minor, skin-level surface injury that should train
    through with only a calm global note.

    Requires an actual minor surface type (graze/abrasion/scrape/blister/mild
    bruise/minor contusion) and the absence of any surface danger signal, red flag,
    urgent flag, or high-risk category. This is the ``surface_minor_train_through``
    concept: it never relaxes a real safety gate — it is only evaluated on the
    full-plan path, so every danger gate has already passed by the time it runs.
    """
    if red_flags or urgent_flags or matched_categories:
        return False
    if routing_reasons & _SURFACE_DANGER_ROUTING_SIGNALS:
        return False

    def _is_minor(value: Any) -> bool:
        return _normalized_text(value) in _MINOR_SURFACE_TRAIN_THROUGH_TYPES

    for guided in _effective_guided_injuries(plan_input):
        if _normalized_text(guided.injury_type) == "surface_injury" and _is_minor(
            guided.surface_type
        ):
            return True

    for item in plan_input.parsed_injuries or []:
        if not isinstance(item, dict):
            continue
        if any(
            _is_minor(item.get(key))
            for key in ("guided_surface_type", "injury_type", "rehab_type")
        ):
            return True

    return False


def triage_injuries(plan_input: PlanInput) -> InjuryTriageResult:
    features = build_triage_features(
        injuries=plan_input.injuries,
        parsed_injuries=plan_input.parsed_injuries,
        guided_injury=plan_input.guided_injury,
        guided_injuries=_effective_guided_injuries(plan_input),
        restrictions=plan_input.restrictions,
    )

    injury_texts = list(features.raw_evidence.get("all_input") or [])
    combined_text = " | ".join(injury_texts).lower()
    cleaned_combined_text = " | ".join(features.raw_evidence.get("cleaned_input") or [])

    safety_context_text = cleaned_combined_text

    routing_reasons: set[str] = set()
    matched_categories = set(features.high_risk_diagnoses)
    for category in list(matched_categories):
        normalized = normalize_triage_category(category)
        if normalized != category:
            matched_categories.add(normalized)
            routing_reasons.add(f"triage_category_alias:{category}->{normalized}")
    # RULE 4: a parsed-injury ``injury_type`` (e.g. "ligament_tear") that aliases
    # to a known high-risk category is added as that specific category rather than
    # being left to a generic fallback later.
    for item in plan_input.parsed_injuries or []:
        if not isinstance(item, dict):
            continue
        parsed_category = normalize_triage_category(_normalized_text(item.get("injury_type")))
        if parsed_category in _HIGH_RISK_CATEGORY_ROUTE:
            matched_categories.add(parsed_category)
            routing_reasons.add(f"parsed_injury_category:{parsed_category}")
    red_flags = set(features.red_flags)
    urgent_flags = set(features.urgent_flags)
    clinician_restriction_signals = set(features.clinician_restriction_signals)

    _apply_high_risk_mapping_reasons(
        matched_categories=matched_categories,
        routing_reasons=routing_reasons,
    )
    _apply_urgent_flags(
        urgent_flags=urgent_flags,
        red_flags=red_flags,
        matched_categories=matched_categories,
        routing_reasons=routing_reasons,
    )

    # Only a free-text *parser*-derived injury type should suppress the guided
    # diagnosis fields. Guided-sourced types are now merged into parsed_injuries,
    # so keying off the bare merged ``injury_type`` would let a guided card disable
    # its own structured handling. Items whose ``injury_type`` originated from the
    # guided card (injury_type_source in _GUIDED_DERIVED_TYPE_SOURCES) must not
    # count; items without a source marker are treated as parser-derived.
    use_guided_diagnosis_fields = not any(
        isinstance(item, dict)
        and str(item.get("injury_type") or "").strip()
        and item.get("injury_type_source") not in _GUIDED_DERIVED_TYPE_SOURCES
        for item in plan_input.parsed_injuries or []
    )

    for guided in _effective_guided_injuries(plan_input):
        _apply_structured_injury_signals(
            guided=guided,
            matched_categories=matched_categories,
            red_flags=red_flags,
            clinician_restriction_signals=clinician_restriction_signals,
            routing_reasons=routing_reasons,
            use_guided_diagnosis_fields=use_guided_diagnosis_fields,
        )

    guided_cards = _collect_guided_card_evidence(plan_input)
    combos = _guided_combos(guided_cards)

    guided_notes = _joined_card_field(guided_cards, "notes")
    guided_avoid = _joined_card_field(guided_cards, "avoid")

    has_guided_high_severity = any(card.severity == "high" for card in guided_cards)
    has_guided_worsening = any(card.trend in _WORSENING_TRENDS for card in guided_cards)

    if has_guided_high_severity:
        routing_reasons.add("guided_injury:high_severity")
        if any(
            token in safety_context_text
            for token in ("rib", "fracture", "dislocation", "instability", "cannot bear weight")
        ):
            matched_categories.add("structural_high_severity")

    if has_guided_worsening:
        red_flags.add("worsening_course")
        routing_reasons.add("guided_injury:worsening")

    if _has_guided_structural_broke_signal(
        guided_notes=guided_notes,
        cleaned_combined_text=cleaned_combined_text,
    ):
        matched_categories.add("fracture")
        routing_reasons.add("guided_injury:structural_broke_signal")

    _apply_card_area_broke_signals(
        cards=guided_cards,
        matched_categories=matched_categories,
        routing_reasons=routing_reasons,
    )

    has_recent_structural_history_signal = _has_recent_structural_history_signal(guided_cards)

    if _has_structural_break_signal(text=combined_text, context_text=combined_text):
        matched_categories.add("fracture")
        routing_reasons.add("raw_injury:structural_broke_signal")

    if any(
        token in guided_avoid
        for token in ("contact", "spar", "impact", "loaded", "weight bearing", "cut", "jump")
    ):
        routing_reasons.add("guided_injury:avoid_high_load")

    cleaned_guided_notes = remove_negated_phrases(guided_notes).strip()
    if "breath" in cleaned_guided_notes and any(token in safety_context_text for token in ("rib", "chest", "pain")):
        red_flags.add("breathing_pain")
        routing_reasons.add("guided_injury:breathing_symptoms")

    # RULE 1 (resolution/negation) & RULE 2 (benign joint noise): when the only
    # structural evidence is old/resolved/ruled-out history or benign joint noise,
    # and no other live danger signal is present, suppress the text-scored
    # structural signals and text-derived high-severity combos so the case is not
    # blocked. A current danger symptom (handled above via red flags / guided
    # high-severity / worsening) keeps the block.
    structural_severe_signals = set(features.structural_severe_signals or [])
    # Only a genuine guided card (not one synthesized from the parsed free text we
    # are evaluating) counts as an independent high-severity/worsening report. A
    # medical-hold category or a non-structural urgent flag (e.g. urgent_nerve)
    # must keep the block; structural urgent flags (urgent_fracture/dislocation)
    # may themselves be a false positive on a resolved/benign mention.
    _guided_eff = _effective_guided_injuries(plan_input)
    _real_guided_serious = any(
        _normalize_guided_severity_token(g.severity or "") == "high"
        or _normalized_text(g.trend) in _WORSENING_TRENDS
        for g in _guided_eff
    )
    # Guided structural cards that are all old-and-cleared with no current concern.
    _guided_resolved_flags = [
        f for g in _guided_eff if (f := _guided_card_resolved_structural(g)) is not None
    ]
    _guided_structural_resolved = bool(_guided_resolved_flags) and all(_guided_resolved_flags)
    # Free-text path: exclude structured serialization tokens like "cleared:no" /
    # "timeframe:last_month" so guided metadata cannot masquerade as resolved
    # free text. Guided resolution is decided by _guided_structural_resolved above.
    _free_text_evidence = [t for t in injury_texts if ":" not in str(t)]
    # Genuine free-text injury input (not synthesized guided representations), used
    # to detect a *current* serious structural injury that must never be cleared by
    # a resolution marker belonging to a different injury in the same payload.
    _raw_injuries = plan_input.injuries
    _genuine_free_text = (
        [str(x) for x in _raw_injuries]
        if isinstance(_raw_injuries, (list, tuple))
        else [str(_raw_injuries or "")]
    )
    _STRUCTURAL_URGENT_FLAGS = {"urgent", "urgent_fracture", "urgent_dislocation"}
    _blocking_urgent = urgent_flags - _STRUCTURAL_URGENT_FLAGS
    downgraded_resolved_or_benign = (
        (_structural_signals_are_downgradeable(_free_text_evidence) or _guided_structural_resolved)
        and not _has_unresolved_serious_structural(_genuine_free_text)
        and not _blocking_urgent
        and not (red_flags & _CURRENT_DANGER_RED_FLAGS)
        and not _real_guided_serious
        and not _has_mapped_route(matched_categories, MEDICAL_HOLD)
    )
    if downgraded_resolved_or_benign:
        routing_reasons.add("resolution_or_benign_downgrade")
        structural_severe_signals.clear()
        clinician_restriction_signals = {
            sig for sig in clinician_restriction_signals if not sig.startswith("danger_term:")
        }
        # Clear the structural categories/urgent flags explained by the resolved or
        # benign mention (anything routing to RESTRICTED, plus the generic fallbacks).
        for category in list(matched_categories):
            if category in {"fracture", "structural_high_severity"} or (
                _HIGH_RISK_CATEGORY_ROUTE.get(category) == RESTRICTED_REHAB_ONLY
            ):
                matched_categories.discard(category)
        urgent_flags = urgent_flags - _STRUCTURAL_URGENT_FLAGS
        combos = {(sev, tr) for (sev, tr) in combos if sev not in {"high", "moderate"}}
        has_recent_structural_history_signal = False
    elif _SERIOUS_RUPTURE_RE.search(" ".join(str(t) for t in _free_text_evidence).lower()):
        # RULE 3: a confirmed serious structural rupture/avulsion that was NOT
        # resolved/benign is a structural-severe signal (→ restricted rehab).
        structural_severe_signals.add("scored_structural_severe:rupture")

    medical_hold, has_chest_or_rib_combo, has_neuro_combo = _initial_medical_hold_gate(
        red_flags=red_flags,
        matched_categories=matched_categories,
        combined_text=safety_context_text,
        routing_reasons=routing_reasons,
    )

    restricted_rehab = _initial_restricted_rehab_gate(
        red_flags=red_flags,
        matched_categories=matched_categories,
        structural_severe_signals=structural_severe_signals,
        clinician_restriction_signals=clinician_restriction_signals,
        routing_reasons=routing_reasons,
    )

    highest_band, restricted_rehab, medical_hold = _apply_sparring_risk_gate(
        injury_texts=injury_texts,
        has_guided_high_severity=has_guided_high_severity,
        red_flags=red_flags,
        restricted_rehab=restricted_rehab,
        medical_hold=medical_hold,
        routing_reasons=routing_reasons,
    )

    for severity, trend in combos:
        if severity == "high" and trend in _WORSENING_TRENDS:
            routing_reasons.add("combo_gate:high_worsening")
        elif severity == "high" and trend == "":
            routing_reasons.add("combo_gate:high_trend_missing")
        elif severity == "high" and trend == "stable":
            routing_reasons.add("combo_gate:high_stable")
        elif severity == "moderate" and trend in _WORSENING_TRENDS:
            routing_reasons.add("combo_gate:moderate_worsening")
        elif severity == "low" and trend in _WORSENING_TRENDS:
            routing_reasons.add("combo_gate:low_worsening")

    if not medical_hold and "structured:systemic_infection" in routing_reasons:
        medical_hold = True
        routing_reasons.add("structured:infection_medical_hold")

    if medical_hold:
        return _build_result(
            mode=MEDICAL_HOLD,
            reasons=[
                "Urgent or medically disqualifying injury signals were detected before planning.",
                "Training guidance is blocked pending immediate medical review.",
            ],
            clinician_clearance_required=True,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if restricted_rehab:
        return _build_result(
            mode=RESTRICTED_REHAB_ONLY,
            reasons=[
                "Serious structural injury signals were detected before planning.",
                "Normal fight-camp loading/sparring generation is suspended until clinician clearance.",
            ],
            clinician_clearance_required=True,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    if has_recent_structural_history_signal:
        routing_reasons.add("guided_injury:recent_structural_history_signal")

        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "Recent structural injury history was detected in guided injury notes.",
                "Coach/admin review is required before normal plan generation.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    _SURFACE_NEEDS_REVIEW_SIGNALS = {
        "structured:open_wound",
        "structured:needs_stitches",
        "structured:eye_area_wound",
        "structured:sensitive_area_wound",
        "structured:bruise_danger_area",
        "structured:bruise_worsening",
    }
    _SURFACE_INFECTION_REVIEW = "structured:infection_signs"

    if routing_reasons & _SURFACE_NEEDS_REVIEW_SIGNALS or _SURFACE_INFECTION_REVIEW in routing_reasons:
        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "Surface injury signals require coach/admin review before contact planning.",
                "Automatic full-plan generation is paused by structured injury triage.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    has_mapped_medical_hold = _has_mapped_route(matched_categories, MEDICAL_HOLD)
    has_mapped_restricted = _has_mapped_route(matched_categories, RESTRICTED_REHAB_ONLY)
    has_dangerous_red_flags = bool(red_flags & _DANGEROUS_RED_FLAGS)
    has_chest_or_neuro_combo = has_chest_or_rib_combo or has_neuro_combo
    has_structural_severe_signal = bool(structural_severe_signals)
    has_clinician_restriction_signal = bool(clinician_restriction_signals)
    has_function_loss_signal = bool(features.function_loss_signals)
    has_uncertainty_trigger = _has_uncertainty_trigger(
        cards=guided_cards,
        matched_categories=matched_categories,
        red_flags=red_flags,
        features=features,
        clinician_restriction_signals=clinician_restriction_signals,
        urgent_flags=urgent_flags,
    )

    combo_result = _combo_gate_result(
        combos=combos,
        red_flags=red_flags,
        matched_categories=matched_categories,
        routing_reasons=routing_reasons,
        urgent_flags=urgent_flags,
        highest_band=highest_band,
        features=features,
        has_chest_or_neuro_combo=has_chest_or_neuro_combo,
        has_mapped_medical_hold=has_mapped_medical_hold,
        has_mapped_restricted=has_mapped_restricted,
        has_dangerous_red_flags=has_dangerous_red_flags,
        has_structural_severe_signal=has_structural_severe_signal,
        has_clinician_restriction_signal=has_clinician_restriction_signal,
        has_function_loss_signal=has_function_loss_signal,
        has_uncertainty_trigger=has_uncertainty_trigger,
    )
    if combo_result is not None:
        return combo_result

    # Safety backstop: current neurological symptoms (numbness/tingling/weakness)
    # that survived every gate above must be held for review rather than routed
    # to an automatic full plan. Placed after the combo gate so it can only
    # upgrade a would-be full plan to needs_review — never downgrade a block.
    if (red_flags | matched_categories) & _NEUROLOGICAL_RED_FLAGS:
        routing_reasons.add("neurological_red_flags_require_review")
        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "Neurological symptoms (numbness, tingling, or weakness) were detected.",
                "Coach/admin review is required before normal plan generation.",
            ],
            clinician_clearance_required=False,
            should_block_stage2=True,
            red_flags=red_flags,
            matched_categories=matched_categories,
            routing_reasons=routing_reasons,
            urgent_flags=urgent_flags,
            sparring_risk_band=highest_band,
        )

    surface_minor_train_through = _minor_surface_train_through(
        plan_input=plan_input,
        routing_reasons=routing_reasons,
        red_flags=red_flags,
        matched_categories=matched_categories,
        urgent_flags=urgent_flags,
    )
    global_notes: list[str] = []
    if surface_minor_train_through:
        routing_reasons.add("surface_minor_train_through")
        global_notes.append(SURFACE_MINOR_TRAIN_THROUGH_NOTE)

    return _build_result(
        mode=FULL_PLAN,
        reasons=["No pre-planning medical hold signals detected."],
        clinician_clearance_required=False,
        should_block_stage2=False,
        red_flags=red_flags,
        matched_categories=matched_categories,
        routing_reasons=routing_reasons,
        urgent_flags=urgent_flags,
        sparring_risk_band=highest_band,
        surface_minor_train_through=surface_minor_train_through,
        global_notes=global_notes,
    )


def _blocked_severity_summary(parsed_injuries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for item in parsed_injuries or []:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "").strip().lower()
        severity_source = str(item.get("severity_source") or "").strip().lower()
        severity_evidence = item.get("severity_evidence") or []
        if not severity and not severity_source and not severity_evidence:
            continue
        area = ""
        for key in ("display_location", "canonical_location", "location", "area", "original_phrase"):
            value = str(item.get(key) or "").strip()
            if value:
                area = value
                break
        entry: dict[str, Any] = {
            "area": area,
            "injury_type": str(item.get("injury_type") or "").strip(),
            "severity": severity or "unknown",
            "severity_source": severity_source or "unknown",
            "severity_evidence": [
                str(piece).strip() for piece in severity_evidence if str(piece or "").strip()
            ],
            "original_phrase": str(item.get("original_phrase") or "").strip(),
        }
        summary.append(entry)
    return summary


def blocked_mode_output(
    *, triage: InjuryTriageResult, parsed_injuries: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
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

    blocked_output = {
        "title": "Injury triage blocked normal plan generation",
        "mode": str(triage.mode or "").strip().lower(),
        "what_was_detected": list(triage.reasons),
        "why_plan_blocked": MODE_EXPLANATIONS.get(
            str(triage.mode or "").strip().lower(),
            "Automatic planning is blocked until injury triage is reviewed.",
        ),
        "severity_summary": _blocked_severity_summary(parsed_injuries),
        "detected_risks": sorted(
            {
                *[str(item).strip() for item in triage.urgent_flags if str(item or "").strip()],
                *[str(item).strip() for item in triage.red_flags if str(item or "").strip()],
            }
        ),
        "red_flags": list(triage.red_flags),
        "high_risk_categories": list(triage.matched_high_risk_categories),
        "routing_reasons": list(triage.routing_reasons),
        "stage2_blocked": bool(triage.should_block_stage2),
        "clinician_clearance_required": bool(triage.clinician_clearance_required),
        "next_step": NEXT_STEPS.get(
            str(triage.mode or "").strip().lower(),
            "Do not generate a normal fight-camp plan until reviewed and cleared.",
        ),
    }

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
        "blocked_output": blocked_output,
    }
