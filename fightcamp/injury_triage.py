from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from .input_parsing import PlanInput
from .injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
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
}

_DANGEROUS_RED_FLAGS = {
    *_CRITICAL_MEDICAL_HOLD_RED_FLAGS,
    "shortness_of_breath",
    "chest_pain",
    "breathing_pain",
}

_WORSENING_TRENDS = {"worse", "worsening", "regressing", "worsened"}

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

_RECENT_INJURY_TIMELINE_RE = re.compile(
    r"\b(?:"
    r"last\s+(?:day|week|month)|"
    r"this\s+(?:week|month)|"
    r"recent(?:ly)?|"
    r"in\s+the\s+last\s+\d+\s*(?:day|days|week|weeks|month|months)"
    r")\b"
)

_STRUCTURAL_HISTORY_KEYWORDS = ("fracture", "dislocat", "rupture", "tear")


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


def _has_injury_location_context(text: str) -> bool:
    if not text:
        return False
    _, parsed_location = parse_injury_phrase(text)
    return bool(parsed_location)


def _has_structural_break_with_location(text: str) -> bool:
    if not text:
        return False
    for chunk in split_injury_text(text):
        cleaned_chunk = remove_negated_phrases(chunk).strip().lower()
        if not cleaned_chunk or not _STRUCTURAL_BREAK_RE.search(cleaned_chunk):
            continue
        if _has_injury_location_context(cleaned_chunk):
            return True
    return False


def _has_mapped_route(categories: set[str], route: str) -> bool:
    return any(_HIGH_RISK_CATEGORY_ROUTE.get(category) == route for category in categories)


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


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
    )


def _parsed_entry_location(entry: dict[str, Any]) -> str:
    return _normalized_text(
        entry.get("display_location")
        or entry.get("canonical_location")
        or entry.get("area")
        or entry.get("region")
        or entry.get("location")
    )


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

    guided = plan_input.guided_injury
    if guided is None:
        return []

    fallback_card = _GuidedCard(
        severity=_normalize_guided_severity_token(guided.severity or ""),
        trend=_normalized_text(guided.trend),
        avoid=_normalized_text(guided.avoid),
        notes=_normalized_text(guided.notes),
        location=_normalized_text(guided.area),
    )
    return [fallback_card] if any(asdict(fallback_card).values()) else []


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
    cleaned_notes = remove_negated_phrases(guided_notes).strip().lower()
    return bool(_has_structural_break_with_location(cleaned_notes) and _has_injury_location_context(cleaned_combined_text))


def _apply_card_area_broke_signals(
    *,
    cards: list[_GuidedCard],
    matched_categories: set[str],
    routing_reasons: set[str],
) -> None:
    for card in cards:
        note_text = remove_negated_phrases(card.notes).strip().lower()
        if not note_text:
            continue

        contextual_card_text = " ".join(
            part for part in (card.location, note_text) if part
        )

        if _has_structural_break_with_location(note_text) and _has_injury_location_context(
            contextual_card_text
        ):
            matched_categories.add("fracture")
            routing_reasons.add("guided_injury:card_area_context_broke_signal")


def _has_recent_structural_history_signal(cards: list[_GuidedCard]) -> bool:
    for card in cards:
        notes = remove_negated_phrases(card.notes).strip().lower()
        if not notes:
            continue

        has_recent_timeline = bool(_RECENT_INJURY_TIMELINE_RE.search(notes))
        has_structural_signal = bool(
            _STRUCTURAL_BREAK_RE.search(notes)
            or any(keyword in notes for keyword in _STRUCTURAL_HISTORY_KEYWORDS)
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
        routing_reasons.add("urgent_flag:urgent_fracture")

    if "urgent_dislocation" in urgent_flags:
        matched_categories.add("dislocation")
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
    features: Any,
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

    if features.structural_severe_signals:
        restricted_rehab = True
        routing_reasons.add("scored_structural_severe_signal")

    if features.clinician_restriction_signals:
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

    if highest_band in {"red", "black"} and has_guided_high_severity:
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
    urgent_flags: set[str],
) -> bool:
    if not cards:
        return False

    has_any_safety_signal = any(
        (
            matched_categories,
            red_flags,
            features.structural_severe_signals,
            features.clinician_restriction_signals,
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

        return _build_result(
            mode=NEEDS_REVIEW,
            reasons=[
                "High-severity worsening injury requires coach/admin review before any normal plan.",
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


def triage_injuries(plan_input: PlanInput) -> InjuryTriageResult:
    features = build_triage_features(
        injuries=plan_input.injuries,
        parsed_injuries=plan_input.parsed_injuries,
        guided_injury=plan_input.guided_injury,
        restrictions=plan_input.restrictions,
    )

    injury_texts = list(features.raw_evidence.get("all_input") or [])
    combined_text = " | ".join(injury_texts).lower()
    cleaned_combined_text = " | ".join(features.raw_evidence.get("cleaned_input") or [])

    matched_categories = set(features.high_risk_diagnoses)
    red_flags = set(features.red_flags)
    urgent_flags = set(features.urgent_flags)
    routing_reasons: set[str] = set()

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

    guided_cards = _collect_guided_card_evidence(plan_input)
    combos = _guided_combos(guided_cards)

    guided_notes = _joined_card_field(guided_cards, "notes")
    guided_avoid = _joined_card_field(guided_cards, "avoid")

    has_guided_high_severity = any(card.severity == "high" for card in guided_cards)
    has_guided_worsening = any(card.trend in _WORSENING_TRENDS for card in guided_cards)

    if has_guided_high_severity:
        routing_reasons.add("guided_injury:high_severity")
        if any(
            token in combined_text
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

    if _has_structural_break_with_location(cleaned_combined_text) and _has_injury_location_context(
        cleaned_combined_text
    ):
        matched_categories.add("fracture")
        routing_reasons.add("raw_injury:structural_broke_signal")

    if any(
        token in guided_avoid
        for token in ("contact", "spar", "impact", "loaded", "weight bearing")
    ):
        routing_reasons.add("guided_injury:avoid_high_load")

    if "breath" in guided_notes and any(token in combined_text for token in ("rib", "chest", "pain")):
        red_flags.add("breathing_pain")
        routing_reasons.add("guided_injury:breathing_symptoms")

    medical_hold, has_chest_or_rib_combo, has_neuro_combo = _initial_medical_hold_gate(
        red_flags=red_flags,
        matched_categories=matched_categories,
        combined_text=combined_text,
        routing_reasons=routing_reasons,
    )

    restricted_rehab = _initial_restricted_rehab_gate(
        red_flags=red_flags,
        matched_categories=matched_categories,
        features=features,
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

    has_mapped_medical_hold = _has_mapped_route(matched_categories, MEDICAL_HOLD)
    has_mapped_restricted = _has_mapped_route(matched_categories, RESTRICTED_REHAB_ONLY)
    has_dangerous_red_flags = bool(red_flags & _DANGEROUS_RED_FLAGS)
    has_chest_or_neuro_combo = has_chest_or_rib_combo or has_neuro_combo
    has_structural_severe_signal = bool(features.structural_severe_signals)
    has_clinician_restriction_signal = bool(features.clinician_restriction_signals)
    has_function_loss_signal = bool(features.function_loss_signals)
    has_uncertainty_trigger = _has_uncertainty_trigger(
        cards=guided_cards,
        matched_categories=matched_categories,
        red_flags=red_flags,
        features=features,
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
