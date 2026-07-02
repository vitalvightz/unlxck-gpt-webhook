from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .phases import PHASE_HEADER_PATTERN
from .regex_config import compile_regex, compile_regex_list
from .restriction_filtering import evaluate_restriction_impact
from .normalization import clean_list, phrase_in_text, dedupe_preserve_order
from .late_selector_windows import classify_late_selector_window
from .fight_day_override import FIGHT_DAY_PROTOCOL_TEXT
from .stage2_render_guards import _has_active_injury_from_athlete_model

_BULLET_PREFIX = compile_regex("stage2_validator", "bullet_prefix")
_PHASE_HEADER = PHASE_HEADER_PATTERN
_WEEK_HEADER = compile_regex("stage2_validator", "week_header", flags=re.IGNORECASE)
_MARKDOWN_HEADER = compile_regex("stage2_validator", "markdown_header")
_NEGATION_MARKERS = (
    "avoid",
    "do not",
    "don't",
    "no ",
    "not ",
    "skip",
    "remove",
    "drop",
    "without",
    "instead of",
)
_SECTION_HINTS = {
    "primary_strength": ("strength", "strength & power", "power"),
    "extra_strength_accessory": ("strength", "strength & power", "accessory"),
    "rehab": ("rehab", "rehabilitation", "prehab", "therapy"),
    "aerobic": ("aerobic", "zone 2", "tempo", "roadwork"),
    "glycolytic": ("glycolytic", "fight pace", "fight-pace", "conditioning"),
    "alactic": ("alactic", "speed", "sharpness", "primer"),
}
_NON_PHASE_TOP_LEVEL_SECTIONS = {
    "coach notes",
    "selection rationale",
    "nutrition",
    "recovery",
    "rehab protocols",
    "mindset overview",
    "sparring & conditioning adjustments",
    "sparring & conditioning adjustments table",
    "nutrition adjustments for unknown sparring load",
    "athlete profile",
}
_CONDITIONAL_PATTERNS = compile_regex_list("stage2_validator", "conditional_patterns", flags=re.IGNORECASE)
_CONDITIONING_ALTERNATIVE_PATTERN = compile_regex(
    "stage2_validator",
    "conditioning_alternative_pattern",
    flags=re.IGNORECASE,
)
_GENERIC_FILLER_PATTERNS = compile_regex_list("stage2_validator", "generic_filler_patterns", flags=re.IGNORECASE)
_GENERIC_OPENER_PATTERNS = compile_regex_list("stage2_validator", "generic_opener_patterns", flags=re.IGNORECASE)
_GENERIC_MOTIVATION_PATTERNS = compile_regex_list("stage2_validator", "generic_motivation_patterns", flags=re.IGNORECASE)
_HEDGED_ADJUSTMENT_PATTERNS = compile_regex_list("stage2_validator", "hedged_adjustment_patterns", flags=re.IGNORECASE)
_ADJUSTMENT_CONTEXT_PATTERN = compile_regex("stage2_validator", "adjustment_context_pattern", flags=re.IGNORECASE)
_EMPTY_SAFETY_PATTERNS = compile_regex_list("stage2_validator", "empty_safety_patterns", flags=re.IGNORECASE)
_OPERATIONAL_GUARDRAIL_PATTERN = compile_regex("stage2_validator", "operational_guardrail_pattern", flags=re.IGNORECASE)
_WEIGHT_CUT_PATTERNS = compile_regex_list("stage2_validator", "weight_cut_patterns", flags=re.IGNORECASE)
_WEIGHT_CUT_NONE_PATTERNS = compile_regex_list("stage2_validator", "weight_cut_none_patterns", flags=re.IGNORECASE)
_OVERSTYLED_PATTERNS = compile_regex_list("stage2_validator", "overstyled_patterns", flags=re.IGNORECASE)
_SPORT_LANGUAGE_LEAKS = {
    "boxing": {
        "takedown",
        "double-leg",
        "double leg",
        "sprawl",
        "thai clinch",
        "clinch knee",
        "cage",
        "octagon",
        "ground and pound",
        "grappling",
    }
}
_SESSION_TITLE_HINTS = {
    "strength",
    "recovery",
    "aerobic support",
    "fight-pace conditioning",
    "alactic sharpness",
    "neural primer",
    "sharpness session",
    "sharpness",
    "power touch",
    "neural touch",
    "technical rhythm",
    "technical touch",
    "freshness session",
    "freshness primer",
    "fight-week freshness",
    "neural speed touch",
    "rhythm flush",
    "activation",
    "warm-up",
    "fight-day warm-up",
    "walk-through",
    "rhythm day",
    "mobility / reset",
    "conditioning",
    "aerobic",
    "glycolytic",
    "alactic",
    "technical polish",
}
_TEMPLATE_PREFIXES = ("primary:", "fallback:", "drill:", "system:")
_OPTION_ENUM_PATTERN = compile_regex("stage2_validator", "option_enum_pattern", flags=re.IGNORECASE)
_WEEKDAY_HEADING = compile_regex("stage2_validator", "weekday_heading", flags=re.IGNORECASE)
_NUMBERED_SESSION_HEADING = compile_regex("stage2_validator", "numbered_session_heading", flags=re.IGNORECASE)
_LATE_FIGHT_TOKEN_PHRASES = {
    "hard_sparring": ("hard spar", "hard sparring", "live spar", "full spar", "hard contact"),
    "standalone_glycolytic": ("glycolytic", "fight pace", "fight-pace", "repeatability", "hard shuttle", "bag sprint"),
    "primary_strength_anchor": ("primary strength", "structural strength", "neural plus strength", "strength anchor", "loaded strength"),
    "conditioning": ("conditioning", "fight pace", "fight-pace", "repeatability", "shuttle", "bag sprint", "air bike sprint"),
    "glycolytic": ("glycolytic", "fight pace", "fight-pace", "repeatability", "hard shuttle", "bag sprint"),
    "hinge_transfer": ("hinge transfer", "hip hinge", "deadlift", "rdl", "romanian deadlift"),
    "jumps": ("jump", "jumps", "plyometric", "bounds", "hops"),
    "contrast_work": ("contrast", "contrast pair", "complex pair"),
    "fight_pace_conditioning": ("fight pace conditioning", "fight-pace conditioning", "fight pace", "fight-pace", "repeatability"),
    "strength": ("strength", "deadlift", "squat", "press", "loaded carry", "trap bar"),
    "sharpness_touch": ("alactic", "sharpness", "primer", "neural primer", "power touch", "neural touch", "low-noise power"),
    "recovery": ("recovery", "freshness", "mobility", "breathing", "reset"),
    "technical": ("technical", "rhythm", "shadowboxing", "flow rounds", "drill"),
    "layered_rehab_stack": ("rehab stack",),
}
_LATE_FIGHT_REHAB_PHRASES = ("rehab", "band external rotation", "scap", "mobility", "tissue", "breathing")
_LATE_FIGHT_BAND_REHAB_ALLOW_PHRASES = (
    "mobility",
    "recovery",
    "rehab",
    "rehab friendly",
    "prehab",
    "injury prevention",
    "reset",
)
_COUNTDOWN_LABEL_LINE = re.compile(r"^(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?(D-(\d+))\b", re.IGNORECASE)
_COUNTDOWN_CONTRACT_WEEKDAY = (
    r"mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:sday)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?"
)
_COUNTDOWN_CONTRACT_HEADER = re.compile(
    rf"^(?:#{{1,6}}\s*)?(?:[-*]\s*)?(?:\*\*)?D-(\d+)\s*"
    rf"\(\s*(?:{_COUNTDOWN_CONTRACT_WEEKDAY})\s*\)\s*(?:—|-|:)\s*\S",
    re.IGNORECASE,
)
_INTERNAL_RENDER_LABEL_PATTERNS = (
    ("anchor_label", re.compile(r"^\s*(?:\d+\)\s*)?anchor\s*(?:—|-|:)", re.IGNORECASE)),
    ("role_key", re.compile(r"\brole_key\b", re.IGNORECASE)),
    ("taper_micro_support", re.compile(r"\btaper_micro_support\b", re.IGNORECASE)),
    ("ownership_label", re.compile(r"^\s*ownership\s*:", re.IGNORECASE)),
    ("hard_sparring_summary_label", re.compile(r"^\s*hard-sparring summary\s*:", re.IGNORECASE)),
    ("spp_additions_summary_label", re.compile(r"^\s*spp additions summary\s*:", re.IGNORECASE)),
    ("late_camp_sparring_label", re.compile(r"^\s*late-camp sparring\s*:", re.IGNORECASE)),
    ("short_support_notes_label", re.compile(r"^\s*short support notes\s*:", re.IGNORECASE)),
    ("final_coaching_call_label", re.compile(r"^\s*final coaching call\s*:", re.IGNORECASE)),
    ("schedule_integrity_label", re.compile(r"^\s*schedule integrity\s*:", re.IGNORECASE)),
    ("camp_plan_closing_label", re.compile(r"that[’']s the camp plan", re.IGNORECASE)),
    ("candidate pool", re.compile(r"\bcandidate\s+pools?\b", re.IGNORECASE)),
    ("validator", re.compile(r"\bvalidator\b", re.IGNORECASE)),
    ("planning brief", re.compile(r"\bplanning\s+brief\b", re.IGNORECASE)),
)
_COACH_LED_SESSION_PATTERN = re.compile(
    r"\bcoach[-\s]+led\s+(?:boxing|mma|muay\s+thai|kickboxing)\b",
    re.IGNORECASE,
)
_COACH_LED_DETAIL_PATTERN = re.compile(
    r"\b(?:rounds?|rpe|intensity|dose|work\s*:\s*rest|live rounds?|technical sparring|"
    r"pad|bag|clinch|moderate intensity|\d+\s*(?:-|to|x|×)\s*\d+\s*min)\b",
    re.IGNORECASE,
)
_INJURY_LEAD_SUMMARY_PATTERN = re.compile(
    r"\b(?:injur|pain|strain|sprain|restriction|constraint|rehab|symptom|stop rule|clearance)\b",
    re.IGNORECASE,
)
_WEIGHT_CUT_LEAD_SUMMARY_PATTERN = re.compile(
    r"\b(?:weight[-\s]?cut|weigh[-\s]?in|cut stress|target weight|scale|recovery margin|"
    r"dehydrat|rehydrat|refeed)\b",
    re.IGNORECASE,
)
_LATE_FIGHT_COUNTDOWN_BLOCKED_DRILLS = {
    3: (
        "throw",
        "toss",
        "medicine ball pass",
        "medicine-ball pass",
        "med-ball pass",
    ),
    13: (
        "Band-Resisted Sprint Start",
        "Band-Resisted Sprint Starts (ATP-PCr)",
        "resisted acceleration",
        "sprint start",
    ),
    6: (
        "Band-Assisted Jump Reset",
        "Band-Resisted Sprint Start",
        "Band-Resisted Sprint Starts (ATP-PCr)",
    ),
    1: (
        "Staggered-Stance Medicine-Ball Punch Throw",
        "medicine ball",
        "med-ball",
        "band",
        "banded",
        "Band-Resisted Sprint Start",
        "Band-Resisted Sprint Starts (ATP-PCr)",
        "Jump Reset",
        "Heavy Bag",
        "Pull-Up Hold",
        "barbell",
        "trap bar",
        "slow eccentric",
        "loaded strength",
        "band-resisted",
        "resisted punch",
        "resisted punching",
        "sprint start",
        "jump",
        "plyometric",
    ),
}
_LATE_FIGHT_ALLOWED_GENERIC_PHRASES = (
    "breathing",
    "breath",
    "mobility",
    "reset",
    "shadowboxing",
    "shadow boxing",
    "technical cue",
    "technical touch",
    "rehab",
    "prehab",
    "coach-led",
    "coach led",
    "warm-up",
    "warm up",
    "readiness",
    "off",
    "rest",
    "walk-through",
    "walk through",
    "shoulder mobility",
    "neck mobility",
    "hip mobility",
)
_LATE_FIGHT_EXERCISE_SIGNALS = (
    "squat",
    "jump",
    "sprint",
    "acceleration",
    "jab",
    "cross",
    "punch",
    "throw",
    "deadlift",
    "row",
    "pull",
    "press",
    "shuffle",
    "bike",
    "run",
    "carry",
    "plank",
    "burpee",
    "med-ball",
    "medicine ball",
    "band",
    "resisted",
    "box",
)
_LATE_FIGHT_NEURAL_POWER_SIGNALS = (
    "speed box squat",
    "box squat",
    "jump",
    "sprint",
    "acceleration",
    "explosive",
    "reactive",
    "shuffle",
    "medicine-ball",
    "medicine ball",
    "med-ball",
    "punch throw",
    "jab-cross",
    "jab cross",
    "primer",
    "neural",
    "power",
)

# Descriptive sub-labels that annotate an already-selected exercise/session
# (e.g. "Purpose: ...", "Stop/regress: ...", "Progression/regression: ...").
# These lines explain or qualify the surrounding prescription; they are not a
# new exercise selection and must not be treated as one even when they mention
# dose tokens (e.g. "3 x 6") or exercise keywords (e.g. "punch", "carry").
_LATE_FIGHT_ANNOTATION_LABEL = re.compile(
    r"^\s*(?:"
    r"purpose|why|goals?|aims?|intent|objectives?|rationale|focus|"
    r"outputs?|results?|outcomes?|"
    r"notes?|coach(?:ing)?\s+(?:note|cue)s?|cues?|"
    r"stop(?:\s*[\/\-]\s*regress(?:ion)s?)?|stop\s+rule|"
    r"regress(?:ion)s?|"
    r"progress(?:ion)s?(?:\s*[\/\-]\s*regress(?:ion)s?)?|"
    r"setup|set[\s-]?up|tempo|load(?:ing)?|dose|dosage|rest|format|"
    r"equipment|targets?|scaling|adjust(?:ment)s?|modif(?:y|ication)s?"
    r")\s*[:\-–—]",
    re.IGNORECASE,
)

# Non-physical countdown tasks (film study, tactical review, cue cards). These
# are mental/tactical work, not exercise selections, but often carry a duration
# (e.g. "Watch 8-12 min") that would otherwise read as a dose.
_LATE_FIGHT_NON_EXERCISE_TASK = re.compile(
    r"\b(?:"
    r"re-?watch(?:es)?|watch(?:es)?|film\s+(?:stud(?:y|ies)|reviews?|clips?)|video\s+reviews?|"
    r"cue\s+cards?|tactical\s+cues?|game\s*plans?|"
    r"take\s+notes|journal(?:ing|s)?|visuali[sz]e|mental\s+rehearsals?"
    r")\b",
    re.IGNORECASE,
)

# Warm-up / movement-prep / activation lines. Brief band activation, mobility
# swings, and movement prep inside a countdown session are not the day's
# exercise selection and are allowed (band-based prep stays allowed except on
# D-1, where all band work is blocked).
_LATE_FIGHT_WARMUP_PREP = re.compile(
    r"\b(?:warm[\s-]?ups?|movement\s+preps?|mobility\s+preps?|cool[\s-]?downs?|activations?)\b",
    re.IGNORECASE,
)


def _late_fight_line_is_annotation_or_task(line: str) -> bool:
    """True for descriptive annotation labels and non-exercise tactical tasks."""
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _LATE_FIGHT_ANNOTATION_LABEL.match(stripped):
        return True
    return bool(_LATE_FIGHT_NON_EXERCISE_TASK.search(stripped))


def _late_fight_line_is_warmup_prep(line: str) -> bool:
    return bool(_LATE_FIGHT_WARMUP_PREP.search(line or ""))




def _extract_plan_lines(plan_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in (plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _phase_sections(plan_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = defaultdict(list)
    current_phase = ""
    for raw_line in (plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        if not cleaned:
            continue
        header_match = _MARKDOWN_HEADER.match(raw_line)
        header_text = header_match.group(2).strip() if header_match else cleaned
        normalized_header = header_text.lower()
        phase_match = _PHASE_HEADER.search(header_text)
        if phase_match:
            current_phase = phase_match.group(0).upper()
        elif current_phase and normalized_header in _NON_PHASE_TOP_LEVEL_SECTIONS:
            current_phase = ""
            continue
        if current_phase:
            sections[current_phase].append(cleaned)
    return dict(sections)


def _normalize_render_line(line: str) -> str:
    return re.sub(r"[*_`]+", "", (line or "")).strip().lower()


def _is_session_heading(line: str) -> bool:
    normalized = _normalize_render_line(line)
    if not normalized:
        return False
    if normalized in _SESSION_TITLE_HINTS:
        return True
    if _WEEKDAY_HEADING.match(normalized):
        return True
    return bool(_NUMBERED_SESSION_HEADING.match(normalized))


def _normalize_session_title(line: str) -> str:
    normalized = _normalize_render_line(line)
    if not normalized:
        return normalized
    if _WEEKDAY_HEADING.match(normalized):
        normalized = _WEEKDAY_HEADING.sub("", normalized, count=1).strip(" :-|")
    return normalized


def _phase_session_blocks(phase_lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in phase_lines:
        normalized = _normalize_render_line(line)
        if not normalized:
            continue
        if _PHASE_HEADER.search(normalized.upper()):
            continue
        if _is_session_heading(line):
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _section_blocks(plan_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title = ""
    current_lines: list[str] = []

    for raw_line in (plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        header_match = _MARKDOWN_HEADER.match(raw_line)
        if header_match:
            if current_title or current_lines:
                sections.append({"title": current_title, "lines": current_lines})
            current_title = _normalize_render_line(header_match.group(2))
            current_lines = []
            continue
        if cleaned:
            current_lines.append(cleaned)

    if current_title or current_lines:
        sections.append({"title": current_title, "lines": current_lines})
    return sections


def _restriction_guard_entry(restriction: dict) -> dict:
    return {
        "restriction": restriction.get("restriction", "generic_constraint"),
        "region": restriction.get("region"),
        "strength": restriction.get("strength") or "avoid",
        "original_phrase": restriction.get("source_phrase") or restriction.get("restriction", ""),
    }


def _restriction_phrases(restriction: dict) -> list[str]:
    phrases = []
    phrases.extend(clean_list(restriction.get("blocked_patterns")))
    phrases.extend(clean_list(restriction.get("mechanical_equivalents")))
    source_phrase = str(restriction.get("source_phrase", "")).strip()
    if source_phrase:
        phrases.append(source_phrase)
    restriction_key = str(restriction.get("restriction", "")).strip().replace("_", " ")
    if restriction_key:
        phrases.append(restriction_key)
    return dedupe_preserve_order([phrase for phrase in phrases if phrase])


def _line_is_instruction_only(line: str, phrase: str | None = None) -> bool:
    normalized = line.lower()
    if phrase and not phrase_in_text(normalized, phrase):
        return False
    return any(marker in normalized for marker in _NEGATION_MARKERS)


def _find_restricted_hits(planning_brief: dict, plan_lines: list[str]) -> list[dict]:
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for restriction in planning_brief.get("restrictions", []):
        phrases = _restriction_phrases(restriction)
        guard_entry = _restriction_guard_entry(restriction)
        for line in plan_lines:
            line_key = line.lower()
            phrase_match = next((phrase for phrase in phrases if phrase_in_text(line_key, phrase)), None)
            if _line_is_instruction_only(line, phrase_match):
                continue
            guard_result = evaluate_restriction_impact(
                [guard_entry],
                text=line,
                tags=[],
                limit_penalty=-0.75,
            )
            if bool(guard_result.get("matched", [])) and _line_is_instruction_only(line):
                continue
            matched = bool(phrase_match) or bool(guard_result.get("matched", []))
            if not matched:
                continue
            dedupe_key = (restriction.get("restriction", "generic_constraint"), line_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            hits.append(
                {
                    "restriction": restriction.get("restriction", "generic_constraint"),
                    "strength": restriction.get("strength") or "avoid",
                    "line": line,
                    "matched_phrase": phrase_match,
                    "match_method": "phrase+guard" if phrase_match and guard_result.get("matched") else "phrase" if phrase_match else "guard",
                    "region": restriction.get("region"),
                }
            )
    return hits


def _slot_candidate_names(slot: dict) -> list[str]:
    names: list[str] = []
    selected = slot.get("selected") or {}
    selected_name = str(selected.get("name", "")).strip()
    if selected_name:
        names.append(selected_name)
    for alternate in slot.get("alternates", []) or []:
        name = str((alternate or {}).get("name", "")).strip()
        if name:
            names.append(name)
    return dedupe_preserve_order(names)


def _slots_for_requirement(phase_pool: dict, requirement: str) -> list[dict]:
    strength_slots = list(phase_pool.get("strength_slots", []))
    conditioning_slots = list(phase_pool.get("conditioning_slots", []))
    rehab_slots = list(phase_pool.get("rehab_slots", []))

    if requirement == "rehab":
        return rehab_slots
    if requirement in {"aerobic", "glycolytic", "alactic"}:
        return [slot for slot in conditioning_slots if slot.get("role") == requirement]
    if requirement == "primary_strength":
        return strength_slots[:1]
    if requirement == "extra_strength_accessory":
        return strength_slots[1:]

    return [slot for slot in conditioning_slots + strength_slots + rehab_slots if slot.get("role") == requirement]


def _line_matches_requirement(line: str, requirement: str, candidate_names: list[str]) -> bool:
    if _line_is_instruction_only(line):
        return False
    normalized = line.lower()
    if any(phrase_in_text(normalized, name) for name in candidate_names):
        return True
    section_hints = _SECTION_HINTS.get(requirement, ())
    return any(phrase_in_text(normalized, hint) for hint in section_hints)


def _find_missing_phase_sections(planning_brief: dict, phase_sections: dict[str, list[str]]) -> list[dict]:
    expected_phases = [phase for phase, strategy in (planning_brief.get("phase_strategy") or {}).items() if clean_list(strategy.get("must_keep", []))]
    if len(expected_phases) <= 1:
        return []

    missing_sections: list[dict] = []
    for phase in expected_phases:
        if phase not in phase_sections:
            missing_sections.append(
                {
                    "phase": phase,
                    "severity": "warning",
                    "reason": f"Final plan is missing an explicit {phase} section, so phase-specific validation is incomplete.",
                }
            )
    return missing_sections


def _find_missing_required_elements(planning_brief: dict, plan_text: str) -> list[dict]:
    missing: list[dict] = []
    phase_sections = _phase_sections(plan_text)
    all_plan_lines = _extract_plan_lines(plan_text)
    candidate_pools = planning_brief.get("candidate_pools", {})
    phase_strategy = planning_brief.get("phase_strategy", {})
    multi_phase_expected = len(phase_strategy) > 1

    for phase, strategy in phase_strategy.items():
        phase_pool = candidate_pools.get(phase, {})
        phase_lines = phase_sections.get(phase, []) if multi_phase_expected else phase_sections.get(phase, all_plan_lines)
        for requirement in clean_list(strategy.get("must_keep", [])):
            slots = _slots_for_requirement(phase_pool, requirement)
            if not slots:
                continue
            candidate_names = dedupe_preserve_order([name for slot in slots for name in _slot_candidate_names(slot)])
            if any(_line_matches_requirement(line, requirement, candidate_names) for line in phase_lines):
                continue
            missing.append(
                {
                    "phase": phase,
                    "requirement": requirement,
                    "candidate_names": candidate_names,
                    "severity": "warning",
                    "reason": f"No known {requirement.replace('_', ' ')} option from the planning brief appeared in the {phase} portion of the final plan.",
                }
            )
    return missing


def _candidate_option_names(options: list[dict]) -> list[str]:
    return dedupe_preserve_order(
        [
            str(option.get("name", "")).strip()
            for option in options
            if str(option.get("name", "")).strip()
        ]
    )


def _athlete_snapshot(planning_brief: dict) -> dict:
    athlete_model = planning_brief.get("athlete_model")
    if isinstance(athlete_model, dict) and athlete_model:
        return athlete_model
    athlete_snapshot = planning_brief.get("athlete_snapshot")
    if isinstance(athlete_snapshot, dict):
        return athlete_snapshot
    return {}


def _weight_cut_context(planning_brief: dict) -> dict[str, bool]:
    athlete = _athlete_snapshot(planning_brief)
    readiness_flags = set(clean_list(athlete.get("readiness_flags", [])))
    active = bool(
        athlete.get("weight_cut_risk")
        or readiness_flags & {"active_weight_cut", "aggressive_weight_cut"}
    )
    fatigue = str(athlete.get("fatigue", "")).strip().lower()
    days_until_fight = athlete.get("days_until_fight")
    high_pressure = bool(
        "aggressive_weight_cut" in readiness_flags
        or (
            active
            and (
                fatigue in {"moderate", "high"}
                or (isinstance(days_until_fight, int) and days_until_fight <= 28)
            )
        )
    )
    return {"active": active, "high_pressure": high_pressure}


def _risk_tone_context(planning_brief: dict) -> dict[str, bool]:
    athlete = _athlete_snapshot(planning_brief)
    readiness_flags = set(clean_list(athlete.get("readiness_flags", [])))
    fatigue = str(athlete.get("fatigue", "")).strip().lower()
    days_until_fight = athlete.get("days_until_fight")
    weight_cut = _weight_cut_context(planning_brief)
    injury_present = _has_active_injury_from_athlete_model(athlete) or "injury_management" in readiness_flags
    fight_week = bool(
        "fight_week" in readiness_flags
        or (isinstance(days_until_fight, int) and days_until_fight <= 7)
    )
    return {
        "high_fatigue": fatigue == "high" or "high_fatigue" in readiness_flags,
        "injury_present": injury_present,
        "active_weight_cut": weight_cut["active"],
        "high_pressure_weight_cut": weight_cut["high_pressure"],
        "fight_week": fight_week,
    }


def _active_risk_labels(risk_context: dict[str, bool]) -> list[str]:
    labels: list[str] = []
    if risk_context.get("high_fatigue"):
        labels.append("high_fatigue")
    if risk_context.get("injury_present"):
        labels.append("injury_present")
    if risk_context.get("fight_week"):
        labels.append("fight_week")
    if risk_context.get("high_pressure_weight_cut"):
        labels.append("high_pressure_weight_cut")
    elif risk_context.get("active_weight_cut"):
        labels.append("active_weight_cut")
    return labels


def _session_has_adjustment_context(session_lines: list[str]) -> bool:
    return any(_ADJUSTMENT_CONTEXT_PATTERN.search(line) for line in session_lines)


def _line_has_risk_context(line: str) -> bool:
    normalized = line.lower()
    return bool(
        _ADJUSTMENT_CONTEXT_PATTERN.search(line)
        or "weight cut" in normalized
        or "fight week" in normalized
        or "weigh-in" in normalized
    )


def _normalize_equipment_set(values: Any) -> set[str]:
    equipment: set[str] = set()
    for value in clean_list(values):
        normalized = str(value).strip().lower().replace(" ", "_")
        if normalized:
            equipment.add(normalized)
    return equipment


def _option_records_by_phase(planning_brief: dict) -> dict[str, list[dict]]:
    records: dict[str, list[dict]] = defaultdict(list)
    for phase, phase_pool in (planning_brief.get("candidate_pools") or {}).items():
        for slot_group in ("strength_slots", "conditioning_slots", "rehab_slots"):
            for slot in phase_pool.get(slot_group, []) or []:
                slot_session_index = int(slot.get("session_index", 1) or 1)
                options = [slot.get("selected") or {}] + list(slot.get("alternates") or [])
                for option in options:
                    name = str(option.get("name", "")).strip()
                    if not name:
                        continue
                    records[phase].append(
                        {
                            "name": name,
                            "phase": phase,
                            "role": slot.get("role"),
                            "session_index": int(option.get("session_index", slot_session_index) or slot_session_index),
                            "required_equipment": _normalize_equipment_set(option.get("required_equipment", [])),
                            "universally_available": bool(option.get("universally_available")),
                            "generic_fallback": bool(option.get("generic_fallback")),
                            "has_access_contingency": bool(
                                str(
                                    option.get("availability_contingency_reason")
                                    or option.get("availability_contingency")
                                    or slot.get("availability_contingency_reason")
                                    or slot.get("availability_contingency")
                                    or ""
                                ).strip()
                            ),
                        }
                    )
    return records


def _matching_option_records(line: str, option_records: list[dict]) -> list[dict]:
    normalized = line.lower()
    return [
        record
        for record in option_records
        if phrase_in_text(normalized, record.get("name", ""))
    ]


def _strength_session_quality_warnings(
    planning_brief: dict,
    phase_sections: dict[str, list[str]],
    plan_lines: list[str],
) -> list[dict]:
    warnings: list[dict] = []
    candidate_pools = planning_brief.get("candidate_pools", {}) or {}
    phase_strategy = planning_brief.get("phase_strategy", {}) or {}
    multi_phase_expected = len(phase_strategy) > 1

    for phase, phase_pool in candidate_pools.items():
        phase_lines = phase_sections.get(phase, []) if multi_phase_expected else plan_lines
        if not phase_lines:
            continue
        session_slots: dict[int, list[dict]] = defaultdict(list)
        for slot in phase_pool.get("strength_slots", []) or []:
            session_slots[int(slot.get("session_index", 1) or 1)].append(slot)
        for session_index, slots in session_slots.items():
            anchor_names: list[str] = []
            support_names: list[str] = []
            session_names: list[str] = []
            for slot in slots:
                selected = slot.get("selected") or {}
                alternates = list(slot.get("alternates", []) or [])
                session_names.extend(_slot_candidate_names(slot))
                if selected.get("anchor_capable"):
                    anchor_names.extend(_candidate_option_names([selected]))
                if selected.get("support_only"):
                    support_names.extend(_candidate_option_names([selected]))
                anchor_names.extend(
                    _candidate_option_names([option for option in alternates if option.get("anchor_capable")])
                )
                support_names.extend(
                    _candidate_option_names([option for option in alternates if option.get("support_only")])
                )
            anchor_names = dedupe_preserve_order(anchor_names)
            support_names = dedupe_preserve_order(support_names)
            if not anchor_names:
                continue
            matched_lines = [
                line
                for line in phase_lines
                if any(phrase_in_text(line, name) for name in session_names)
            ]
            if not matched_lines:
                continue
            anchor_lines = [
                line
                for line in matched_lines
                if any(phrase_in_text(line, name) for name in anchor_names)
            ]
            support_lines = [
                line
                for line in matched_lines
                if any(phrase_in_text(line, name) for name in support_names)
            ]
            if not anchor_lines and support_lines:
                warnings.append(
                    {
                        "code": "weak_anchor_session",
                        "message": f"{phase} session {session_index} is missing a serious anchor option even though the candidate pool had one.",
                        "phase": phase,
                        "session_index": session_index,
                        "anchor_candidates": anchor_names,
                        "matched_lines": matched_lines,
                    }
                )
                first_two = matched_lines[:2]
                if len(first_two) >= 1 and all(
                    any(phrase_in_text(line, name) for name in support_names)
                    for line in first_two[: min(2, len(first_two))]
                ):
                    warnings.append(
                        {
                            "code": "support_takeover_before_anchor",
                            "message": f"{phase} session {session_index} opens with support work before any available anchor exercise.",
                            "phase": phase,
                            "session_index": session_index,
                            "anchor_candidates": anchor_names,
                            "matched_lines": first_two,
                        }
                    )
            elif support_lines:
                first_two = matched_lines[:2]
                if first_two and not any(
                    any(phrase_in_text(line, name) for name in anchor_names)
                    for line in first_two
                ) and all(
                    any(phrase_in_text(line, name) for name in support_names)
                    for line in first_two
                ):
                    warnings.append(
                        {
                            "code": "support_takeover_before_anchor",
                            "message": f"{phase} session {session_index} opens with support work before the available anchor exercise appears.",
                            "phase": phase,
                            "session_index": session_index,
                            "anchor_candidates": anchor_names,
                            "matched_lines": first_two,
                        }
                    )
    return warnings


def _conditioning_choice_warnings(plan_lines: list[str]) -> list[dict]:
    warnings: list[dict] = []
    seen_lines: set[str] = set()
    for line in plan_lines:
        normalized = _normalize_render_line(line)
        if normalized.startswith("fallback:"):
            continue
        if any(pattern.search(line) for pattern in _CONDITIONAL_PATTERNS) or _CONDITIONING_ALTERNATIVE_PATTERN.search(line):
            if normalized in seen_lines:
                continue
            seen_lines.add(normalized)
            warnings.append(
                {
                    "code": "conditional_conditioning_choice",
                    "message": "Conditioning prescription is still conditional instead of decisive.",
                    "line": line,
                }
            )
    return warnings


def _rendering_discipline_warnings(planning_brief: dict, phase_sections: dict[str, list[str]]) -> list[dict]:
    warnings: list[dict] = []
    risk_context = _risk_tone_context(planning_brief)
    active_risk_labels = _active_risk_labels(risk_context)
    for phase, phase_lines in phase_sections.items():
        for session_index, session_lines in enumerate(_phase_session_blocks(phase_lines), start=1):
            normalized_lines = [_normalize_render_line(line) for line in session_lines if _normalize_render_line(line)]
            if not normalized_lines:
                continue
            template_lines = [
                line
                for line in normalized_lines
                if line.startswith(_TEMPLATE_PREFIXES)
                or line.startswith(("weekly progression:", "if time short:", "if fatigue high:", "dosage template:"))
            ]
            fallback_lines = [line for line in normalized_lines if line.startswith("fallback:")]
            conditional_lines = [
                line
                for line in session_lines
                if any(pattern.search(line) for pattern in _CONDITIONAL_PATTERNS) or _CONDITIONING_ALTERNATIVE_PATTERN.search(line)
            ]
            option_markers: set[str] = set()
            for line in session_lines:
                for match in _OPTION_ENUM_PATTERN.findall(line):
                    option_markers.add(str(match).lower())
            if len(fallback_lines) > 1:
                warnings.append(
                    {
                        "code": "too_many_fallbacks",
                        "message": f"{phase} session {session_index} still contains more than one fallback branch.",
                        "phase": phase,
                        "session_index": session_index,
                        "matched_lines": session_lines,
                    }
                )
            if len(template_lines) >= 3 and len(template_lines) >= max(2, len(normalized_lines) // 2):
                warnings.append(
                    {
                        "code": "template_like_session_render",
                        "message": f"{phase} session {session_index} still reads like a template or session library instead of a final prescription.",
                        "phase": phase,
                        "session_index": session_index,
                        "matched_lines": session_lines,
                    }
                )
            if len(option_markers) > 2:
                blocking_option_overload = bool(
                    _session_has_adjustment_context(session_lines)
                    or phase == "TAPER"
                    or active_risk_labels
                )
                warnings.append(
                    {
                        "code": "option_overload",
                        "message": (
                            f"{phase} session {session_index} still presents more than two options "
                            "in a corrective or high-risk context."
                            if blocking_option_overload
                            else f"{phase} session {session_index} still presents more than two options."
                        ),
                        "phase": phase,
                        "session_index": session_index,
                        "matched_lines": session_lines,
                        "rewrite_hint": "Collapse choices to at most two safe, materially equivalent options, or resolve to one final prescription.",
                        "blocking": blocking_option_overload,
                        "risk_context": active_risk_labels,
                    }
                )
            if phase == "TAPER" and (len(fallback_lines) > 1 or len(conditional_lines) > 0 or len(template_lines) > 2):
                warnings.append(
                    {
                        "code": "taper_option_overload",
                        "message": f"Taper session {session_index} still contains too much branching or template structure.",
                        "phase": phase,
                        "session_index": session_index,
                        "matched_lines": session_lines,
                    }
                )
    return warnings


def _equipment_congruence_warnings(
    planning_brief: dict,
    phase_sections: dict[str, list[str]],
    plan_lines: list[str],
) -> list[dict]:
    warnings: list[dict] = []
    athlete_equipment = _normalize_equipment_set(_athlete_snapshot(planning_brief).get("equipment", []))
    option_records_by_phase = _option_records_by_phase(planning_brief)
    multi_phase_expected = len((planning_brief.get("phase_strategy") or {}).keys()) > 1
    seen: set[tuple[str, str]] = set()

    for phase, option_records in option_records_by_phase.items():
        phase_lines = phase_sections.get(phase, []) if multi_phase_expected else plan_lines
        for line in phase_lines:
            for record in _matching_option_records(line, option_records):
                if not record["required_equipment"] or record["universally_available"]:
                    continue
                if record["required_equipment"].issubset(athlete_equipment):
                    continue
                dedupe_key = (phase, line.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                warnings.append(
                    {
                        "code": "equipment_incongruent_selection",
                        "message": f"{phase} includes '{record['name']}' even though it requires equipment outside the athlete profile.",
                        "phase": phase,
                        "line": line,
                        "required_equipment": sorted(record["required_equipment"]),
                    }
                )
    return warnings


def _unresolved_access_fallback_warnings(
    planning_brief: dict,
    phase_sections: dict[str, list[str]],
) -> list[dict]:
    warnings: list[dict] = []
    athlete_equipment = _normalize_equipment_set(_athlete_snapshot(planning_brief).get("equipment", []))
    option_records_by_phase = _option_records_by_phase(planning_brief)

    for phase, phase_lines in phase_sections.items():
        phase_option_records = option_records_by_phase.get(phase, [])
        for session_index, session_lines in enumerate(_phase_session_blocks(phase_lines), start=1):
            for line in session_lines:
                normalized = _normalize_render_line(line)
                if not normalized.startswith("fallback:"):
                    continue
                matching_records = _matching_option_records(line, phase_option_records)
                if not matching_records:
                    warnings.append(
                        {
                            "code": "unresolved_access_fallback",
                            "message": f"{phase} session {session_index} still renders a fallback branch without a matched contingency option.",
                            "phase": phase,
                            "session_index": session_index,
                            "line": line,
                        }
                    )
                    continue
                if any(record["has_access_contingency"] for record in matching_records):
                    continue
                if all(
                    not record["required_equipment"]
                    or record["required_equipment"].issubset(athlete_equipment)
                    for record in matching_records
                ):
                    warnings.append(
                        {
                            "code": "unresolved_access_fallback",
                            "message": f"{phase} session {session_index} keeps a fallback branch even though the athlete profile already resolves access.",
                            "phase": phase,
                            "session_index": session_index,
                            "line": line,
                        }
                    )
    return warnings


def _week_sections(plan_text: str) -> dict[int, dict[str, Any]]:
    sections: dict[int, dict[str, Any]] = {}
    current_phase = ""
    current_week: int | None = None

    for raw_line in (plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        if not cleaned:
            continue
        header_match = _MARKDOWN_HEADER.match(raw_line)
        header_text = header_match.group(2).strip() if header_match else cleaned
        phase_match = _PHASE_HEADER.search(header_text)
        if phase_match:
            current_phase = phase_match.group(0).upper()
        week_match = _WEEK_HEADER.search(header_text)
        if week_match:
            current_week = int(week_match.group(1))
            sections.setdefault(current_week, {"phase": current_phase, "lines": []})
            sections[current_week]["phase"] = current_phase
            continue
        if current_week is not None:
            sections.setdefault(current_week, {"phase": current_phase, "lines": []})
            sections[current_week]["lines"].append(cleaned)
    return sections


def _week_session_titles(week_lines: list[str]) -> list[str]:
    return [
        _normalize_session_title(block[0])
        for block in _phase_session_blocks(week_lines)
        if block
    ]


def _week_completeness_warnings(planning_brief: dict, plan_text: str) -> list[dict]:
    weekly_role_map = planning_brief.get("weekly_role_map") or {}
    weeks = list(weekly_role_map.get("weeks") or [])
    if len(weeks) <= 1:
        return []

    warnings: list[dict] = []
    week_sections = _week_sections(plan_text)
    active_week_count = len(weeks)
    late_week_start = max(1, active_week_count - 1)
    sport_key = str(_athlete_snapshot(planning_brief).get("sport", "")).strip().lower()

    for week in weeks:
        week_index = int(week.get("week_index", 0) or 0)
        if week_index <= 0:
            continue
        expected_roles = list(week.get("session_roles") or [])
        expected_role_days = [
            {
                "role_key": role.get("role_key"),
                "scheduled_day_hint": role.get("scheduled_day_hint", ""),
            }
            for role in expected_roles
            if role.get("role_key")
        ]
        week_section = week_sections.get(week_index)
        if not week_section:
            warnings.append(
                {
                    "code": "late_camp_session_incomplete" if week_index >= late_week_start else "missing_week_session_role",
                    "message": f"Week {week_index} is missing from the final plan even though it is active in the planning brief.",
                    "week_index": week_index,
                    "phase": week.get("phase"),
                    "expected_roles": [role.get("role_key") for role in expected_roles],
                    "expected_role_days": expected_role_days,
                }
            )
            continue

        session_blocks = _phase_session_blocks(week_section.get("lines", []))
        actual_session_count = len(session_blocks)
        expected_session_count = len(expected_roles)
        if actual_session_count < expected_session_count:
            warnings.append(
                {
                    "code": "late_camp_session_incomplete" if week_index >= late_week_start else "missing_week_session_role",
                    "message": f"Week {week_index} is structurally incomplete compared with the weekly role map.",
                    "week_index": week_index,
                    "phase": week.get("phase"),
                    "expected_session_count": expected_session_count,
                    "actual_session_count": actual_session_count,
                    "expected_roles": [role.get("role_key") for role in expected_roles],
                    "expected_role_days": expected_role_days,
                }
            )
        elif actual_session_count > expected_session_count:
            warnings.append(
                {
                    "code": "weekly_session_overage",
                    "message": f"Week {week_index} renders {actual_session_count} active sessions even though the planning brief only allows {expected_session_count}.",
                    "week_index": week_index,
                    "phase": week.get("phase"),
                    "expected_session_count": expected_session_count,
                    "actual_session_count": actual_session_count,
                    "expected_roles": [role.get("role_key") for role in expected_roles],
                    "expected_role_days": expected_role_days,
                }
            )

        if sport_key == "boxing" and str(week.get("phase", "")).upper() in {"GPP", "SPP"}:
            expected_strength_roles = sum(1 for role in expected_roles if role.get("category") == "strength")
            has_recovery_role = any(role.get("category") == "recovery" for role in expected_roles)
            if expected_strength_roles >= 2 and has_recovery_role:
                titles = _week_session_titles(week_section.get("lines", []))
                strength_positions = [
                    idx for idx, title in enumerate(titles)
                    if title.startswith("strength") or title.startswith("neural primer")
                ]
                recovery_positions = [
                    idx for idx, title in enumerate(titles)
                    if title.startswith("recovery")
                ]
                if recovery_positions and len(strength_positions) >= 2 and recovery_positions[0] + 1 != strength_positions[1]:
                    warnings.append(
                        {
                            "code": "weekly_rhythm_broken",
                            "message": f"Week {week_index} breaks the default boxer rhythm where recovery should sit immediately before the primary strength day.",
                            "week_index": week_index,
                            "phase": week.get("phase"),
                            "titles": titles,
                        }
                    )
    return warnings


def _crowded_week_block_matches_day(block: list[str], scheduled_day_hint: str) -> bool:
    if not block or not scheduled_day_hint:
        return False
    return phrase_in_text(_normalize_render_line(block[0]), scheduled_day_hint.strip().lower())


def _match_crowded_week_session_block_index(
    session_blocks: list[list[str]],
    role: dict[str, Any],
    *,
    fallback_index: int,
    used_indices: set[int],
) -> int | None:
    scheduled_day_hint = str(role.get("scheduled_day_hint") or "").strip()
    if scheduled_day_hint:
        for idx, block in enumerate(session_blocks):
            if idx in used_indices:
                continue
            if _crowded_week_block_matches_day(block, scheduled_day_hint):
                return idx

    if 0 <= fallback_index < len(session_blocks) and fallback_index not in used_indices:
        return fallback_index

    return next((idx for idx in range(len(session_blocks)) if idx not in used_indices), None)


def _boxing_crowded_week_warnings(planning_brief: dict, final_plan_text: str) -> list[dict]:
    weekly_role_map = planning_brief.get("weekly_role_map") or {}
    weeks = list(weekly_role_map.get("weeks") or [])
    if not weeks:
        return []
    if str(_athlete_snapshot(planning_brief).get("sport", "")).strip().lower() != "boxing":
        return []

    warnings: list[dict] = []
    week_sections = _week_sections(final_plan_text)

    for week in weeks:
        intentional_compression = week.get("intentional_compression") or {}
        if not (intentional_compression.get("active") and intentional_compression.get("policy") == "boxing_crowded_week"):
            continue

        week_index = int(week.get("week_index", 0) or 0)
        if week_index <= 0:
            continue
        week_section = week_sections.get(week_index)
        if not week_section:
            continue

        expected_roles = list(week.get("session_roles") or [])
        session_blocks = _phase_session_blocks(week_section.get("lines", []))
        actual_hard_spar_count = sum(1 for block in session_blocks if _block_contains_token(block, "hard_sparring"))
        max_non_spar_roles = int(intentional_compression.get("max_non_spar_roles") or 0)
        actual_non_spar_sessions = max(0, len(session_blocks) - actual_hard_spar_count)
        used_block_indices: set[int] = set()

        if max_non_spar_roles >= 0 and actual_non_spar_sessions > max_non_spar_roles:
            warnings.append(
                {
                    "code": "crowded_week_non_spar_overage",
                    "message": (
                        f"Week {week_index} renders {actual_non_spar_sessions} non-spar sessions even though "
                        f"the crowded-week budget only allows {max_non_spar_roles}."
                    ),
                    "week_index": week_index,
                    "phase": week.get("phase"),
                    "actual_non_spar_sessions": actual_non_spar_sessions,
                    "max_non_spar_roles": max_non_spar_roles,
                    "risk_signals": clean_list(intentional_compression.get("risk_signals", [])),
                    "blocking": True,
                }
            )

        for session_index, role in enumerate(expected_roles, start=1):
            governance = role.get("governance") or {}
            main_job = str(governance.get("main_job") or "").strip()
            if main_job not in {"anchor", "support_recovery"}:
                continue

            forbidden_tokens = clean_list(governance.get("forbidden_secondary_stressors", []))
            if not forbidden_tokens:
                continue

            block_index = _match_crowded_week_session_block_index(
                session_blocks,
                role,
                fallback_index=session_index - 1,
                used_indices=used_block_indices,
            )
            if block_index is None:
                continue
            used_block_indices.add(block_index)

            block = session_blocks[block_index]
            body_lines = block[1:] if len(block) > 1 else []
            matched_lines: list[str] = []
            matched_tokens: list[str] = []
            for line in body_lines:
                for token in forbidden_tokens:
                    if _line_matches_late_fight_token(line, token):
                        matched_lines.append(line)
                        matched_tokens.append(token)
                        break

            if not matched_lines:
                continue

            warning = {
                "week_index": week_index,
                "phase": week.get("phase"),
                "session_index": block_index + 1,
                "role_key": role.get("role_key"),
                "line": block[0],
                    "matched_lines": dedupe_preserve_order(matched_lines),
                    "matched_tokens": dedupe_preserve_order(matched_tokens),
                "blocking": True,
            }
            if main_job == "anchor":
                warnings.append(
                    {
                        **warning,
                        "code": "anchor_day_identity_overload",
                        "message": (
                            f"Week {week_index} anchor day reintroduces extra meaningful stress instead of "
                            "staying a single main-job anchor session."
                        ),
                    }
                )
            else:
                warnings.append(
                    {
                        **warning,
                        "code": "support_recovery_day_stress_leak",
                        "message": (
                            f"Week {week_index} support/recovery day regained meaningful stress instead of "
                            "staying low-load."
                        ),
                    }
                )

    return warnings


def _line_mentions_weight_cut(line: str) -> bool:
    return any(pattern.search(line) for pattern in _WEIGHT_CUT_PATTERNS)


def _weight_cut_acknowledgement_warnings(planning_brief: dict, final_plan_text: str) -> list[dict]:
    context = _weight_cut_context(planning_brief)
    if not context["active"]:
        return []

    non_profile_lines: list[str] = []

    for section in _section_blocks(final_plan_text):
        title = section.get("title", "")
        if title == "athlete profile":
            continue
        matching_lines = [
            line
            for line in section.get("lines", [])
            if _line_mentions_weight_cut(line)
        ]
        if not matching_lines:
            continue
        non_profile_lines.extend(matching_lines)

    warnings: list[dict] = []
    if not non_profile_lines:
        warnings.append(
            {
                "code": "missing_weight_cut_acknowledgement",
                "message": "Active weight cut shaped the camp, but the final plan does not acknowledge it outside raw profile fields.",
                "line": "",
            }
        )
    return warnings


def _weight_cut_contradiction_warnings(planning_brief: dict, final_plan_text: str) -> list[dict]:
    context = _weight_cut_context(planning_brief)
    if not context["active"]:
        return []

    contradictory_lines = [
        line
        for line in _extract_plan_lines(final_plan_text)
        if any(pattern.search(line) for pattern in _WEIGHT_CUT_NONE_PATTERNS)
    ]
    if not contradictory_lines:
        return []

    return [
        {
            "code": "weight_cut_state_contradiction",
            "message": "Plan marks weight cut as inactive/standard recovery even though active cut stress is present in the planning context.",
            "line": contradictory_lines[0],
            "high_pressure": context["high_pressure"],
        }
    ]


def _late_fight_header_contract_warnings(planning_brief: dict, plan_lines: list[str]) -> list[dict]:
    spec = _late_fight_plan_spec(planning_brief)
    if not spec:
        return []

    countdown_heading_lines = [line for line in plan_lines if _COUNTDOWN_LABEL_LINE.match(line)]
    if not countdown_heading_lines:
        return [
            {
                "code": "late_fight_missing_countdown_header",
                "message": "Late-fight output must lead active days with D-X countdown headers.",
                "payload_mode": spec.get("payload_mode"),
                "days_out_bucket": spec.get("days_out_bucket"),
                "blocking": True,
            }
        ]

    warnings: list[dict] = []
    for line in countdown_heading_lines:
        if _COUNTDOWN_CONTRACT_HEADER.match(line):
            continue
        warnings.append(
            {
                "code": "late_fight_countdown_header_format",
                "message": "Late-fight countdown headers must use D-X (Weekday) — Session role.",
                "payload_mode": spec.get("payload_mode"),
                "days_out_bucket": spec.get("days_out_bucket"),
                "line": line,
                "blocking": True,
            }
        )
    return warnings


def _late_fight_d0_protocol_warnings(
    planning_brief: dict,
    final_plan_text: str,
    plan_lines: list[str],
) -> list[dict]:
    spec = _late_fight_plan_spec(planning_brief)
    if not spec:
        return []

    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    d0_lines = day_blocks.get(0)
    if not d0_lines and str(spec.get("days_out_bucket") or "").strip().upper() == "D-0":
        d0_lines = plan_lines
    if not d0_lines:
        return []

    protocol_text = _normalize_render_line(FIGHT_DAY_PROTOCOL_TEXT)
    protocol_body_only = _normalize_render_line(
        re.sub(r"^fight day protocol\s*[—:-]\s*", "", FIGHT_DAY_PROTOCOL_TEXT, flags=re.IGNORECASE)
    )
    header_line = _normalize_render_line(d0_lines[0] if d0_lines else "")
    body_lines = [line for line in d0_lines[1:] if _normalize_render_line(line)]
    if not body_lines and protocol_text in header_line:
        return []
    normalized_body_line = _normalize_render_line(body_lines[0]) if len(body_lines) == 1 else ""
    if len(body_lines) == 1 and normalized_body_line in {protocol_text, protocol_body_only}:
        return []

    return [
        {
            "code": "late_fight_d0_protocol_expanded",
            "message": "D-0 must render fight day protocol only.",
            "payload_mode": spec.get("payload_mode"),
            "days_out_bucket": "D-0",
            "line": d0_lines[0] if d0_lines else "",
            "body_lines": body_lines[:3],
            "blocking": True,
        }
    ]

def _late_fight_missing_terminal_d0_warnings(
    planning_brief: dict,
    final_plan_text: str,
) -> list[dict]:
    spec = _late_fight_plan_spec(planning_brief)
    if not spec:
        return []

    payload_mode = str(spec.get("payload_mode") or "")
    if payload_mode in {"", "camp_payload"}:
        return []

    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    if 0 in day_blocks:
        return []

    return [
        {
            "code": "late_fight_missing_terminal_d0_protocol",
            "message": "Late-fight output must include a terminal D-0 fight-day protocol block.",
            "payload_mode": payload_mode,
            "days_out_bucket": spec.get("days_out_bucket"),
            "blocking": True,
        }
    ]

def _internal_render_contract_leak_warnings(plan_lines: list[str]) -> list[dict]:
    warnings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in plan_lines:
        for label, pattern in _INTERNAL_RENDER_LABEL_PATTERNS:
            if not pattern.search(line):
                continue
            dedupe_key = (label, _normalize_render_line(line))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            warnings.append(
                {
                    "code": "internal_render_contract_leak",
                    "message": f"Final plan exposes internal render label: {label}.",
                    "label": label,
                    "line": line,
                    "blocking": True,
                }
            )
    return warnings


def _render_contract_blocks(final_plan_text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for raw_line in (final_plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        if not cleaned:
            continue
        header_match = _MARKDOWN_HEADER.match(raw_line)
        heading_text = header_match.group(2).strip() if header_match else cleaned
        is_heading = bool(
            header_match
            or _COUNTDOWN_LABEL_LINE.match(heading_text)
            or _WEEKDAY_HEADING.match(_normalize_render_line(heading_text))
            or _is_session_heading(heading_text)
            or _COACH_LED_SESSION_PATTERN.search(heading_text)
        )
        if is_heading:
            if current:
                blocks.append(current)
            current = [heading_text]
            continue
        if current:
            current.append(cleaned)
    if current:
        blocks.append(current)
    return blocks


def _coach_led_body_line_is_minimal(line: str) -> bool:
    normalized = _normalize_render_line(line)
    if _COACH_LED_DETAIL_PATTERN.search(line):
        return False
    return (
        phrase_in_text(normalized, "coach-owned combat session")
        or phrase_in_text(normalized, "coach owned combat session")
        or phrase_in_text(normalized, "no extra s&c")
        or phrase_in_text(normalized, "no app s&c")
    ) and phrase_in_text(normalized, "freshness priority")


def _coach_owned_sparring_detail_warnings(final_plan_text: str) -> list[dict]:
    warnings: list[dict] = []
    for block in _render_contract_blocks(final_plan_text):
        block_text = " ".join(block)
        if not _COACH_LED_SESSION_PATTERN.search(block_text):
            continue

        heading = block[0]
        body_lines = [line for line in block[1:] if _normalize_render_line(line)]
        detailed_lines = [
            line
            for line in block
            if _COACH_LED_DETAIL_PATTERN.search(line)
        ]
        non_minimal_body = [
            line
            for line in body_lines
            if not _coach_led_body_line_is_minimal(line)
        ]

        if not detailed_lines and len(body_lines) <= 1 and not non_minimal_body:
            continue

        warnings.append(
            {
                "code": "coach_owned_sparring_overdetailed",
                "message": "Coach-led sparring/boxing day includes app-authored detail beyond the minimal coach-owned render.",
                "line": heading,
                "matched_lines": (detailed_lines or non_minimal_body or body_lines)[:3],
                "blocking": True,
            }
        )
    return warnings


def _lead_summary_contract_warnings(planning_brief: dict, plan_lines: list[str]) -> list[dict]:
    lead_text = "\n".join(plan_lines[:10])
    warnings: list[dict] = []
    risk_context = _risk_tone_context(planning_brief)
    weight_cut = _weight_cut_context(planning_brief)

    if risk_context.get("injury_present") and not _INJURY_LEAD_SUMMARY_PATTERN.search(lead_text):
        warnings.append(
            {
                "code": "missing_injury_lead_summary",
                "message": "Active injury context must be summarized before training detail.",
                "blocking": True,
            }
        )
    if weight_cut["active"] and not _WEIGHT_CUT_LEAD_SUMMARY_PATTERN.search(lead_text):
        warnings.append(
            {
                "code": "missing_weight_cut_lead_summary",
                "message": "Active cut context must be summarized before training detail.",
                "high_pressure": weight_cut["high_pressure"],
                "blocking": True,
            }
        )
    return warnings


def _overstyled_name_warnings(plan_lines: list[str]) -> list[dict]:
    warnings: list[dict] = []
    seen_lines: set[str] = set()
    for line in plan_lines:
        normalized = line.lower()
        if normalized in seen_lines:
            continue
        if any(pattern.search(line) for pattern in _OVERSTYLED_PATTERNS):
            seen_lines.add(normalized)
            warnings.append(
                {
                    "code": "overstyled_drill_name",
                    "message": "Replace overstyled drill naming with plain coach-readable language.",
                    "line": line,
                }
            )
    return warnings


def _coach_voice_warnings(planning_brief: dict, plan_lines: list[str]) -> list[dict]:
    warnings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    risk_context = _risk_tone_context(planning_brief)
    active_risk_labels = _active_risk_labels(risk_context)

    for line in plan_lines:
        normalized = _normalize_render_line(line)
        if not normalized:
            continue

        warning: dict | None = None
        line_has_risk_context = _line_has_risk_context(line) or bool(active_risk_labels)
        if any(pattern.search(line) for pattern in _EMPTY_SAFETY_PATTERNS) and not _OPERATIONAL_GUARDRAIL_PATTERN.search(line):
            warning = {
                "code": "empty_safety_language",
                "message": (
                    "High-risk guidance uses empty safety language instead of operational guardrails."
                    if line_has_risk_context
                    else "Replace empty safety language with operational guardrails that change the prescription."
                ),
                "line": line,
                "rewrite_hint": "State the constraint or symptom rule plainly and say what changes today or tomorrow.",
                "blocking": line_has_risk_context,
                "risk_context": active_risk_labels,
            }
        elif any(pattern.search(line) for pattern in _GENERIC_OPENER_PATTERNS):
            warning = {
                "code": "generic_instruction_opener",
                "message": "Generic opener weakens the coaching line; start with a direct verb-led instruction.",
                "line": line,
                "rewrite_hint": "Start with the instruction itself, then add one short reason if needed.",
            }
        elif any(pattern.search(line) for pattern in _GENERIC_MOTIVATION_PATTERNS):
            warning = {
                "code": "generic_motivation_cliche",
                "message": "Replace generic motivation cliches with concrete confidence or execution language.",
                "line": line,
                "rewrite_hint": "Swap generic hype for one specific action, checkpoint, or proof-based confidence cue.",
            }
        elif any(pattern.search(line) for pattern in _GENERIC_FILLER_PATTERNS):
            warning = {
                "code": "generic_filler_phrase",
                "message": "Replace low-trust filler with concrete coach language and next actions.",
                "line": line,
                "rewrite_hint": "Replace the filler phrase with a direct instruction and an operational cue.",
            }
        elif any(pattern.search(line) for pattern in _HEDGED_ADJUSTMENT_PATTERNS) and _ADJUSTMENT_CONTEXT_PATTERN.search(line):
            warning = {
                "code": "hedged_adjustment_without_decision",
                "message": "Adjustment language stays too hedged instead of making a clear coaching call.",
                "line": line,
                "rewrite_hint": "Turn the suggestion into a direct coaching call, then add one short why.",
                "blocking": True,
            }

        if not warning:
            continue
        dedupe_key = (str(warning.get("code", "")), normalized)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        warnings.append(warning)

    return warnings


def _sport_language_warnings(planning_brief: dict, plan_lines: list[str]) -> list[dict]:
    athlete_model = planning_brief.get("athlete_model", {}) or {}
    sport_key = str(
        athlete_model.get("sport")
        or (planning_brief.get("sport_load_profile", {}) or {}).get("key")
        or ""
    ).strip().lower()
    restricted_terms = _SPORT_LANGUAGE_LEAKS.get(sport_key, set())
    if not restricted_terms:
        return []
    warnings: list[dict] = []
    seen_lines: set[str] = set()
    for line in plan_lines:
        normalized = line.lower()
        if normalized in seen_lines:
            continue
        if any(term in normalized for term in restricted_terms):
            seen_lines.add(normalized)
            warnings.append(
                {
                    "code": "sport_language_leak",
                    "message": f"Line uses sport language that does not fit the athlete's {sport_key} context cleanly.",
                    "line": line,
                    "sport": sport_key,
                }
            )
    return warnings



_WEEKDAY_ALIASES = {
    "mon": "monday",
    "monday": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "tuesday": "tuesday",
    "wed": "wednesday",
    "weds": "wednesday",
    "wednesday": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "thursday": "thursday",
    "fri": "friday",
    "friday": "friday",
    "sat": "saturday",
    "saturday": "saturday",
    "sun": "sunday",
    "sunday": "sunday",
}

def _calendar_weekday_key(value: Any) -> str:
    normalized = _normalize_render_line(str(value or ""))
    for token in re.findall(r"[a-z]+", normalized):
        weekday = _WEEKDAY_ALIASES.get(token)
        if weekday:
            return weekday
    return ""

def _calendar_heading_weekday(heading_line: str, allowed_days: dict[str, dict]) -> str:
    weekday = _calendar_weekday_key(heading_line)
    return weekday if weekday in allowed_days else ""

def _calendar_block_is_off_or_recovery_only(block: list[str]) -> bool:
    block_text = _normalize_render_line(" ".join(block))

    if not block_text:
        return False

    off_markers = (
        "off",
        "rest",
        "recovery only",
        "off / recovery",
        "off/recovery",
        "no extra s&c",
        "no app s&c",
        "no app-led",
        "passive recovery",
    )

    training_signals = (
        "strength",
        "conditioning",
        "fight-pace",
        "fight pace",
        "sparring",
        "coach-led boxing",
        "coach led boxing",
        "deadlift",
        "squat",
        "shuttle",
        "interval",
        "rounds",
        "med-ball",
        "medicine ball",
        "throw",
        "slams",
        "sprint",
        "bike intervals",
        "loaded",
    )

    return any(marker in block_text for marker in off_markers) and not any(
        signal in block_text for signal in training_signals
    )


def _calendar_spine_warnings(planning_brief: dict, final_plan_text: str) -> list[dict]:
    weekly_role_map = planning_brief.get("weekly_role_map") or {}
    weeks = [week for week in (weekly_role_map.get("weeks") or []) if isinstance(week, dict)]
    if not weeks:
        return []

    warnings: list[dict] = []
    normalized_text = _normalize_render_line(final_plan_text)

    if "d-2 to d-1 window depends" in normalized_text:
        warnings.append(
            {
                "code": "calendar_spine_ambiguous_countdown_window",
                "message": "Rendered text uses ambiguous D-2 to D-1 window language even though calendar_days already defines exact D-days.",
                "blocking": True,
            }
        )

    week_sections = _week_sections(final_plan_text)

    for week in weeks:
        week_index = int(week.get("week_index", 0) or 0)
        if week_index <= 0:
            continue

        section = week_sections.get(week_index)
        if not section:
            continue

        allowed_days: dict[str, dict] = {}
        for day in week.get("calendar_days") or []:
            if not isinstance(day, dict):
                continue
            weekday = _calendar_weekday_key(day.get("weekday"))
            if weekday:
                allowed_days[weekday] = day

        if not allowed_days:
            continue

        authorized_session_days = {
            weekday
            for role in (week.get("session_roles") or [])
            if isinstance(role, dict)
            if (weekday := _calendar_weekday_key(role.get("scheduled_day_hint")))
        }

        for block in _phase_session_blocks(section.get("lines", [])):
            heading_line = _normalize_render_line(block[0]) if block else ""
            heading_day = _calendar_heading_weekday(heading_line, allowed_days)

            if not heading_day:
                warnings.append(
                    {
                        "code": "calendar_spine_unmapped_weekday_rendered",
                        "message": f"Week {week_index} renders a weekday heading not present in calendar_days.",
                        "week_index": week_index,
                        "line": block[0],
                        "blocking": True,
                    }
                )
                continue

            calendar_day = allowed_days.get(heading_day)
            if not calendar_day:
                continue

            expected_d = calendar_day.get("d_day")
            block_text = _normalize_render_line(" ".join(block))

            if isinstance(expected_d, int) and expected_d >= 0 and f"d-{expected_d}" not in block_text:
                if re.search(r"\bd-\d+\b", block_text):
                    warnings.append(
                        {
                            "code": "calendar_spine_d_day_mismatch",
                            "message": f"Week {week_index} {heading_day.title()} rendered with a D-day that does not match calendar_days.",
                            "week_index": week_index,
                            "line": block[0],
                            "expected_d_day": expected_d,
                            "blocking": True,
                        }
                    )

            if bool(calendar_day.get("is_after_fight_day")) and any(
                _normalize_render_line(line) for line in block[1:]
            ):
                warnings.append(
                    {
                        "code": "calendar_spine_post_fight_training_rendered",
                        "message": f"Week {week_index} renders app-led training on {heading_day.title()} after D-0.",
                        "week_index": week_index,
                        "line": block[0],
                        "blocking": True,
                    }
                )

            if bool(calendar_day.get("is_fight_day")):
                body_lines = [line.strip() for line in block[1:] if _normalize_render_line(line)]
                protocol_text = _normalize_render_line(FIGHT_DAY_PROTOCOL_TEXT)

                if len(body_lines) != 1 or _normalize_render_line(body_lines[0]) != protocol_text:
                    warnings.append(
                        {
                            "code": "calendar_spine_fight_day_protocol_violation",
                            "message": f"Week {week_index} fight day must render exact fight-day protocol text only.",
                            "week_index": week_index,
                            "line": block[0],
                            "blocking": True,
                        }
                    )

                continue

            if (
                heading_day not in authorized_session_days
                and not _calendar_block_is_off_or_recovery_only(block)
            ):
                warnings.append(
                    {
                        "code": "calendar_spine_session_role_not_authorized",
                        "message": f"Week {week_index} renders {heading_day.title()}, but no session_role authorizes that weekday.",
                        "week_index": week_index,
                        "line": block[0],
                        "blocking": True,
                    }
                )

    return warnings


def _late_fight_plan_spec(planning_brief: dict) -> dict[str, Any]:
    spec = planning_brief.get("late_fight_plan_spec") or {}
    return spec if isinstance(spec, dict) else {}


def _days_from_countdown_bucket(days_out_bucket: str) -> int | None:
    if not re.match(r"^D-\d+$", days_out_bucket):
        return None
    try:
        return int(days_out_bucket[2:])
    except ValueError:
        return None


_LATE_FIGHT_WINDOW_EXERCISE_RULES: dict[str, dict[str, list[str]]] = {
    "d21_to_d14": {
        "blocked": ["Hard Shuttle Intervals", "Bag Sprint Repeats", "Band-Assisted Jump Reset", "Dense Conditioning Circuit"],
        "preferred": ["Trap Bar Deadlift", "Staggered-Stance Medicine-Ball Punch Throw", "Band-Resisted Jab-Cross Primer", "Mobility Reset Flow"],
    },
    "d13_to_d8": {
        "blocked": ["Sandbag Shouldering", "Band-Assisted Jump Reset", "Band-Resisted Sprint Start", "Band-Resisted Sprint Starts (ATP-PCr)", "Dense Conditioning Circuit"],
        "preferred": ["Staggered-Stance Medicine-Ball Punch Throw", "Band-Resisted Jab-Cross Primer", "Explosive Boxing Burst Intervals", "Reactive Shuffle Repeats", "Mobility Reset Flow", "Breathing Reset"],
    },
    "d7": {
        "blocked": ["Sandbag Shouldering", "Trap Bar Deadlift", "Trap-Bar Deadlift", "Band-Assisted Jump Reset", "Band-Resisted Sprint Start", "Band-Resisted Sprint Starts (ATP-PCr)", "Heavy Bag Density Rounds", "Slow-Lowered Pull-Up", "Bulgarian Split Squat"],
        "preferred": ["Reactive Shuffle Repeats", "Explosive Boxing Burst Intervals", "Technical Shadowboxing Tempo", "Mobility Reset Flow"],
    },
    "d6_to_d5": {
        "blocked": ["Sandbag Shouldering", "Band-Assisted Jump Reset", "Band-Resisted Sprint Start", "Band-Resisted Sprint Starts (ATP-PCr)", "Trap Bar Deadlift", "Trap-Bar Deadlift", "Dense Conditioning Circuit", "Slow-Lowered Pull-Up", "Bulgarian Split Squat"],
        "preferred": ["Explosive Boxing Burst Intervals", "Reactive Shuffle Repeats"],
    },
    "d4_to_d2": {
        "blocked": ["Sandbag Shouldering", "Trap Bar Deadlift", "Trap-Bar Deadlift", "Band-Resisted Sprint Start", "Band-Resisted Sprint Starts (ATP-PCr)", "Band-Assisted Jump Reset", "Heavy Bag Density Rounds", "Medicine Ball Power Circuit", "Slow-Lowered Pull-Up", "Bulgarian Split Squat"],
        "preferred": ["Technical Shadowboxing Tempo", "Mobility Reset Flow", "Breathing Reset", "Band Face Pull", "Light Band Punch Cue", "Mirror Drill"],
    },
    "d1": {
        "blocked": ["Sandbag Shouldering", "Staggered-Stance Medicine-Ball Punch Throw", "Light Heavy-Bag Technical Tempo", "Scapular Pull-Up Hold", "Medicine Ball Power Circuit", "Heavy Bag Density Rounds", "Pull-Up Iso Hold", "band", "banded", "Band-Resisted Sprint Start", "Band-Resisted Sprint Starts (ATP-PCr)", "Band-Assisted Jump Reset", "Barbell Push Press", "Trap Bar Deadlift", "Trap-Bar Deadlift", "Slow-Lowered Pull-Up", "Bulgarian Split Squat"],
        "preferred": [
            "Technical Shadowboxing Tempo",
            "Mobility Reset Flow",
            "Breathing Reset",
        ],
    },
}

_COUNTDOWN_DAY_LABEL = re.compile(r"\bD-(\d{1,2})\b", re.IGNORECASE)


def _countdown_sections(final_plan_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for section in _section_blocks(final_plan_text):
        title = str(section.get("title") or "")
        lines = list(section.get("lines") or [])
        search_text = " ".join([title, *(lines[:1] if lines else [])])
        match = _COUNTDOWN_DAY_LABEL.search(search_text)
        if not match:
            continue
        day_label = f"D-{int(match.group(1))}"
        days_until_fight = _days_from_countdown_bucket(day_label)
        window = classify_late_selector_window(days_until_fight)
        if not window:
            continue
        sections.append(
            {
                "day_label": day_label,
                "window": window,
                "title": title,
                "lines": lines,
            }
        )
    return sections


def _late_fight_session_blocks(final_plan_text: str) -> list[list[str]]:
    blocks = _phase_session_blocks(_extract_plan_lines(final_plan_text))
    active_blocks: list[list[str]] = []

    for block in blocks:
        if not block:
            continue

        header_match = _COUNTDOWN_LABEL_LINE.match(block[0])
        if header_match and int(header_match.group(2)) == 0:
            continue

        active_blocks.append(block)

    return active_blocks

def _late_fight_block_body(block: list[str]) -> list[str]:
    if len(block) <= 1:
        return []
    return [line for line in block[1:] if _normalize_render_line(line)]


def _block_contains_token(block: list[str], token: str) -> bool:
    text = " ".join(block).lower()
    phrases = _LATE_FIGHT_TOKEN_PHRASES.get(token, ())
    return any(phrase_in_text(text, phrase) for phrase in phrases)


def _line_matches_late_fight_token(line: str, token: str) -> bool:
    if _line_is_instruction_only(line):
        return False
    lowered = line.lower()
    phrases = _LATE_FIGHT_TOKEN_PHRASES.get(token, ())
    return any(phrase_in_text(lowered, phrase) for phrase in phrases)


def _late_fight_meaningful_exposure_count(blocks: list[list[str]]) -> tuple[int, list[dict[str, Any]]]:
    counted: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        tags = {
            token
            for token in ("hard_sparring", "standalone_glycolytic", "primary_strength_anchor", "conditioning", "sharpness_touch")
            if _block_contains_token(block, token)
        }
        if not tags:
            continue
        if tags == {"conditioning"} and _block_contains_token(block, "recovery"):
            continue
        counted.append(
            {
                "session_index": index,
                "heading": block[0],
                "tags": sorted(tags),
            }
        )
    return len(counted), counted


def _late_fight_forbidden_matches(token: str, plan_lines: list[str], blocks: list[list[str]]) -> list[str]:
    if token == "layered_rehab_stack":
        matched: list[str] = []
        for block in blocks:
            rehab_lines = [
                line
                for line in _late_fight_block_body(block)
                if any(phrase_in_text(line.lower(), phrase) for phrase in _LATE_FIGHT_REHAB_PHRASES)
            ]
            if len(rehab_lines) >= 2:
                matched.append(block[0])
        return matched
    return [line for line in plan_lines if _line_matches_late_fight_token(line, token)]


def _late_fight_countdown_blocks_by_day(final_plan_text: str) -> dict[int, list[str]]:
    blocks: dict[int, list[str]] = {}
    current_day: int | None = None
    for raw_line in (final_plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        if not cleaned:
            continue
        match = _COUNTDOWN_LABEL_LINE.match(cleaned)
        if match:
            current_day = int(match.group(2))
            blocks.setdefault(current_day, []).append(cleaned)
            continue
        if _is_countdown_block_boundary(cleaned):
            current_day = None
            continue
        if current_day is not None:
            blocks.setdefault(current_day, []).append(cleaned)
    return blocks


def _countdown_blocked_drills_from_spec(spec: dict[str, Any]) -> dict[int, tuple[str, ...]]:
    blocked: dict[int, list[str]] = {
        day: list(phrases)
        for day, phrases in _LATE_FIGHT_COUNTDOWN_BLOCKED_DRILLS.items()
    }
    for rule in spec.get("countdown_exercise_rules", []) or []:
        if not isinstance(rule, dict):
            continue
        label = str(rule.get("countdown_label") or "")
        match = re.search(r"D-(\d+)", label, flags=re.IGNORECASE)
        if not match:
            continue
        day = int(match.group(1))
        phrases = clean_list(rule.get("blocked_drills"))
        if phrases:
            blocked.setdefault(day, []).extend(phrases)
    return {
        day: tuple(dedupe_preserve_order([phrase for phrase in phrases if phrase]))
        for day, phrases in blocked.items()
    }


def _late_fight_countdown_blocked_drill_warnings(
    spec: dict[str, Any],
    final_plan_text: str,
    plan_lines: list[str],
) -> list[dict]:
    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    if not day_blocks:
        days_out_bucket = str(spec.get("days_out_bucket") or "")
        match = re.match(r"^D-(\d+)$", days_out_bucket, flags=re.IGNORECASE)
        if match:
            day_blocks[int(match.group(1))] = plan_lines

    blocked_by_day = _countdown_blocked_drills_from_spec(spec)
    warnings: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    for day, lines in day_blocks.items():
        blocked_phrases = blocked_by_day.get(day, ())
        if not blocked_phrases:
            continue
        for line in lines:
            if _line_is_instruction_only(line):
                continue
            line_lower = line.lower()
            line_compact = re.sub(r"[^a-z0-9]+", " ", line_lower).strip()
            for phrase in blocked_phrases:
                phrase_lower = phrase.lower()
                phrase_compact = re.sub(r"[^a-z0-9]+", " ", phrase_lower).strip()
                if not (
                    phrase_in_text(line_lower, phrase)
                    or phrase_lower in line_lower
                    or (phrase_compact and phrase_compact in line_compact)
                ):
                    continue
                key = (day, phrase.casefold(), line)
                if key in seen:
                    continue
                seen.add(key)
                warnings.append(
                    {
                        "code": "late_fight_countdown_blocked_drill",
                        "message": f"D-{day} includes a drill that is blocked for that countdown day: {phrase}.",
                        "days_out_bucket": f"D-{day}",
                        "blocked_drill": phrase,
                        "line": line,
                        "blocking": True,
                    }
                )
    return warnings


def _late_fight_d3_throw_signal(line: str) -> bool:
    if _line_is_instruction_only(line):
        return False
    return (
        any(phrase_in_text(line, phrase) for phrase in ("throw", "toss"))
        or (
            any(phrase_in_text(line, phrase) for phrase in ("medicine ball", "med-ball", "medicine-ball"))
            and phrase_in_text(line, "pass")
        )
    )


def _late_fight_countdown_banded_lockout_warnings(
    spec: dict[str, Any],
    final_plan_text: str,
    plan_lines: list[str],
) -> list[dict]:
    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    if not day_blocks:
        days_out_bucket = str(spec.get("days_out_bucket") or "")
        match = re.match(r"^D-(\d+)$", days_out_bucket, flags=re.IGNORECASE)
        if match:
            day_blocks[int(match.group(1))] = plan_lines

    warnings: list[dict] = []
    for day, lines in day_blocks.items():
        if day > 7:
            continue
        for line in lines:
            if _line_is_instruction_only(line):
                continue
            has_band_token = any(
                phrase_in_text(line, token)
                for token in (
                    "band",
                    "band resisted",
                    "banded",
                    "resistance band",
                    "mini band",
                    "band assisted",
                    "resisted jab",
                    "resisted jab-cross",
                    "resisted punching",
                    "resisted punch",
                )
            )
            if not has_band_token:
                continue
            if day != 1:
                if any(phrase_in_text(line, phrase) for phrase in _LATE_FIGHT_BAND_REHAB_ALLOW_PHRASES):
                    continue
                # Brief band activation inside warm-up/movement prep, and band
                # mentions inside descriptive annotations (e.g. a regression
                # note), are not the day's prescribed band work. Only D-1 blocks
                # all band work outright.
                if _late_fight_line_is_warmup_prep(line) or _late_fight_line_is_annotation_or_task(line):
                    continue
            warnings.append(
                {
                    "code": "late_fight_countdown_blocked_drill",
                    "message": (
                        f"D-{day} includes band work, which is fully blocked on D-1."
                        if day == 1
                        else f"D-{day} includes non-rehab band work, which is blocked from D-7 and closer."
                    ),
                    "days_out_bucket": f"D-{day}",
                    "blocked_drill": "d1_band_work" if day == 1 else "non_rehab_band_work",
                    "line": line,
                    "blocking": True,
                }
            )
    return warnings


# Inside the taper (D-10 to the fight) the plan may offer regressions and stop
# rules only — never a "make it harder" option. Strength & conditioning
# sessions lock earlier: from D-13, an S&C card (strength, power, alactic,
# aerobic, fight-pace, neural speed work) must also stop progressing, while
# fillers, rehab, mobility, and light recovery work keep progressing until the
# D-10 lockout. These phrases mark an explicit
# progression suggestion (add load/sets, heavier ball, stronger band, "to
# progress"). Genuine regression advice ("regress to a lighter ball", "reduce
# to 3 x 3", "drop a set") never matches these — the negation guard below is
# scoped to the progression cue itself so a regression clause that happens to
# say "drop"/"reduce" on the same line does not suppress the check.
_LATE_FIGHT_PROGRESSION_ADVICE_PHRASES = (
    "to progress",
    "to advance",
    "progress to",
    "progress by",
    "progress the drill",
    "advance to",
    "advance the drill",
    "to make it harder",
    "to load up",
)

# The lockout only inspects the card's progression/regression annotation line
# (where this advice lives), not exercise or tactical-cue lines — otherwise
# movement language like "Partner advances after each teep" or a cue such as
# "advance to close distance" would false-positive on the "advance" phrases.
_LATE_FIGHT_PROGRESSION_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*"
    r"(?:progress(?:ion)?s?(?:\s*[\/\-]\s*regress(?:ion)?s?)?|regress(?:ion)?s?)"
    r"\s*[:\-–—]",
    re.IGNORECASE,
)

# Negators that, when they immediately precede the progression cue, mean the
# line is stating *not* to progress (e.g. "do not progress the drill").
_LATE_FIGHT_PROGRESSION_NEGATOR_PATTERN = re.compile(
    r"\b(?:do\s+not|don['’]t|dont|never|no|not|avoid|without|instead\s+of)\b|n['’]t\b",
    re.IGNORECASE,
)

# Session title from a countdown header line: "D-12 (Monday) — Strength".
_LATE_FIGHT_COUNTDOWN_TITLE = re.compile(
    r"^(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?D-\d+\s*(?:\([^)]*\)\s*)?(?:—|–|-|:)\s*(?P<title>.+)$",
    re.IGNORECASE,
)

# Titles that mark an actual strength & conditioning session for the extended
# D-13..D-11 lockout. Aligned with the athlete-facing labels in
# fightcamp/role_labels.py ("Strength", "Conditioning", "Fight-pace
# conditioning", "Alactic sharpness", "Aerobic support", "Neural speed touch").
_LATE_FIGHT_SC_LOCKOUT_TITLE_PATTERN = re.compile(
    r"\b(?:strength|conditioning|power|explosive|plyo(?:metric)?s?|alactic|aerobic|glycolytic|neural)\b"
    r"|fight[\s\-]?pace",
    re.IGNORECASE,
)

# Filler / rehab / light-work titles are exempt from the extended D-13..D-11
# lockout even when they also carry an S&C word ("Light conditioning flush").
# They stay under the blanket D-10 lockout only.
_LATE_FIGHT_SC_LOCKOUT_EXCLUDE_PATTERN = re.compile(
    r"\b(?:rehab|recovery|mobility|filler|flush|technical|tactical|sparring"
    r"|warm[\s\-]?up|activation|reset|light)\b",
    re.IGNORECASE,
)


def _late_fight_countdown_block_title(lines: list[str]) -> str:
    for line in lines:
        match = _LATE_FIGHT_COUNTDOWN_TITLE.match(line)
        if match:
            return match.group("title").strip().strip("*_`").strip()
    return ""


def _late_fight_title_is_strength_conditioning(title: str) -> bool:
    if not title:
        return False
    if _LATE_FIGHT_SC_LOCKOUT_EXCLUDE_PATTERN.search(title):
        return False
    return bool(_LATE_FIGHT_SC_LOCKOUT_TITLE_PATTERN.search(title))


def _late_fight_progression_phrase_match(line: str, phrase: str) -> int | None:
    """Return the start index of an un-negated progression cue, else None."""
    parts = [re.escape(part) for part in re.split(r"[\s\-]+", phrase.lower()) if part]
    if not parts:
        return None
    pattern = r"\b" + r"[\s\-]+".join(parts) + r"\b"
    line_lower = line.lower()
    for match in re.finditer(pattern, line_lower):
        window = line_lower[max(0, match.start() - 24):match.start()]
        if _LATE_FIGHT_PROGRESSION_NEGATOR_PATTERN.search(window):
            continue
        return match.start()
    return None


def _late_fight_progression_lockout_warnings(
    spec: dict[str, Any],
    final_plan_text: str,
    plan_lines: list[str],
) -> list[dict]:
    """Flag progression suggestions inside the taper lockout windows.

    D-10 and closer: no session may suggest a progression. D-13 to D-11:
    actual strength & conditioning sessions may not progress either, while
    fillers, rehab, mobility, and light recovery work still may.
    """
    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    if not day_blocks:
        days_out_bucket = str(spec.get("days_out_bucket") or "")
        match = re.match(r"^D-(\d+)$", days_out_bucket, flags=re.IGNORECASE)
        if match:
            day_blocks[int(match.group(1))] = plan_lines

    warnings: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for day, lines in day_blocks.items():
        if not (0 <= day <= 13):
            continue
        sc_only_window = day >= 11
        if sc_only_window and not _late_fight_title_is_strength_conditioning(
            _late_fight_countdown_block_title(lines)
        ):
            continue
        for line in lines:
            if not _LATE_FIGHT_PROGRESSION_LINE.match(line):
                continue
            matched = next(
                (
                    phrase
                    for phrase in _LATE_FIGHT_PROGRESSION_ADVICE_PHRASES
                    if _late_fight_progression_phrase_match(line, phrase) is not None
                ),
                None,
            )
            if not matched:
                continue
            key = (day, line)
            if key in seen:
                continue
            seen.add(key)
            if sc_only_window:
                message = (
                    f"D-{day} is a strength & conditioning session that suggests a progression "
                    f"(\"{matched}\"), but from D-13 to the fight, strength and conditioning "
                    "work allows regressions and stop rules only."
                )
            else:
                message = (
                    f"D-{day} suggests a progression (\"{matched}\"), but from D-10 to the "
                    "fight the taper allows regressions and stop rules only."
                )
            warnings.append(
                {
                    "code": "late_fight_progression_suggested",
                    "message": message,
                    "days_out_bucket": f"D-{day}",
                    "line": line,
                    "blocking": True,
                }
            )
    return warnings


def _normalize_exercise_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def _allowed_exercises_by_countdown_day(spec: dict[str, Any]) -> dict[int, dict[str, Any]]:
    raw_allowed = spec.get("allowed_exercises_by_day") or {}
    if not isinstance(raw_allowed, dict):
        return {}
    allowed_by_day: dict[int, dict[str, Any]] = {}
    for raw_day, raw_names in raw_allowed.items():
        match = re.search(r"(\d+)", str(raw_day or ""))
        if not match:
            continue
        names = clean_list(raw_names)
        if raw_names is None:
            continue
        allowed_by_day[int(match.group(1))] = {
            "names": dedupe_preserve_order(names),
            "keys": {
                normalized
                for normalized in (_normalize_exercise_key(name) for name in names)
                if normalized
            },
        }
    return allowed_by_day


def _late_fight_line_has_allowed_exercise(line: str, allowed_keys: set[str]) -> bool:
    normalized_line = _normalize_exercise_key(line)
    return any(key and key in normalized_line for key in allowed_keys)


def _late_fight_line_is_generic_allowed(line: str) -> bool:
    lowered = line.lower()
    if any(phrase_in_text(lowered, phrase) for phrase in _LATE_FIGHT_ALLOWED_GENERIC_PHRASES):
        if "band" not in lowered and "resisted" not in lowered:
            return True
        return any(phrase_in_text(lowered, phrase) for phrase in _LATE_FIGHT_BAND_REHAB_ALLOW_PHRASES)
    return False


def _late_fight_line_is_exercise_like(line: str) -> bool:
    if _line_is_instruction_only(line):
        return False
    if _COUNTDOWN_LABEL_LINE.match(line.strip()):
        return False
    # Descriptive annotations (Purpose/Stop/Progression/regression/...), warm-up
    # and movement-prep lines, and non-exercise tactical tasks (film study, cue
    # cards) are not exercise selections even when they carry dose tokens.
    if _late_fight_line_is_annotation_or_task(line):
        return False
    if _late_fight_line_is_warmup_prep(line):
        return False
    lowered = line.lower()
    if re.search(r"\b\d+\s*(?:x|sets?|reps?|sec|seconds?|min|minutes?|rounds?|bursts?)\b", lowered):
        return True
    return any(phrase_in_text(lowered, signal) for signal in _LATE_FIGHT_EXERCISE_SIGNALS)


def _rendered_exercise_label(line: str) -> str:
    cleaned = re.sub(r"^(?:[-*]\s*)?", "", (line or "").strip())
    cleaned = re.sub(r"^\*\*?|\*\*?$", "", cleaned).strip()
    cleaned = re.sub(r"^\(?[A-Za-z]{2,9}\)?\s*[-:]\s*", "", cleaned).strip()
    match = re.split(r"\s+(?:[-–—]|:)\s+|,|\(", cleaned, maxsplit=1)
    label = match[0].strip(" -*_`")
    return label or cleaned[:80]


def _late_fight_allowed_exercise_warnings(
    spec: dict[str, Any],
    final_plan_text: str,
    plan_lines: list[str],
) -> list[dict]:
    allowed_by_day = _allowed_exercises_by_countdown_day(spec)
    if not allowed_by_day:
        return []

    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    if not day_blocks:
        days_out_bucket = str(spec.get("days_out_bucket") or "")
        match = re.match(r"^D-(\d+)$", days_out_bucket, flags=re.IGNORECASE)
        if match:
            day_blocks[int(match.group(1))] = plan_lines

    warnings: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for day, lines in day_blocks.items():
        allowed = allowed_by_day.get(day)
        if not allowed:
            continue
        allowed_keys = allowed.get("keys") or set()
        for line in lines:
            if not _late_fight_line_is_exercise_like(line):
                continue
            if _late_fight_line_has_allowed_exercise(line, allowed_keys):
                continue
            if _late_fight_line_is_generic_allowed(line):
                continue
            rendered = _rendered_exercise_label(line)
            key = (day, line)
            if key in seen:
                continue
            seen.add(key)
            warnings.append(
                {
                    "code": "late_fight_unapproved_exercise_rendered",
                    "message": f"D-{day} renders an exercise that was not selected or allowed for that countdown day.",
                    "days_out_bucket": f"D-{day}",
                    "rendered_exercise": rendered,
                    "line": line,
                    "allowed_exercises": list(allowed.get("names") or [])[:20],
                    "blocking": True,
                }
            )
    return warnings


def _late_fight_neural_power_stack_warnings(
    spec: dict[str, Any],
    final_plan_text: str,
    plan_lines: list[str],
) -> list[dict]:
    day_blocks = _late_fight_countdown_blocks_by_day(final_plan_text)
    if not day_blocks:
        days_out_bucket = str(spec.get("days_out_bucket") or "")
        match = re.match(r"^D-(\d+)$", days_out_bucket, flags=re.IGNORECASE)
        if match:
            day_blocks[int(match.group(1))] = plan_lines

    warnings: list[dict] = []
    for day, lines in day_blocks.items():
        if day > 7:
            continue
        matched_lines: list[str] = []
        for line in lines:
            if _line_is_instruction_only(line) or _COUNTDOWN_LABEL_LINE.match(line.strip()):
                continue
            if _late_fight_line_is_generic_allowed(line):
                continue
            lowered = line.lower()
            if any(phrase_in_text(lowered, signal) for signal in _LATE_FIGHT_NEURAL_POWER_SIGNALS):
                matched_lines.append(line)
        if len(matched_lines) >= 2:
            warnings.append(
                {
                    "code": "late_fight_neural_power_stacking",
                    "message": f"D-{day} stacks multiple neural or power drills inside the late-fight taper.",
                    "days_out_bucket": f"D-{day}",
                    "matched_lines": matched_lines[:5],
                    "blocking": True,
                }
            )
    return warnings


# ---------------------------------------------------------------------------
# Late-fight dosage ceiling helpers (Patch B)
# ---------------------------------------------------------------------------

# Pattern to extract a leading integer or low–high range from text, e.g.:
#   "4–6 bursts", "6–10 rounds", "3 bursts", "2x3"
_DOSE_RANGE_PREFIX = re.compile(
    r"\b(\d+)\s*[–\-x×]\s*(\d+)\b|\b(\d+)\b",
    re.IGNORECASE,
)

# Patterns that signal an alactic burst / sharpness effort line
_ALACTIC_BURST_SIGNALS = re.compile(
    r"\b(burst|bursts?|alactic|sharpness|primer|neural|pop)\b",
    re.IGNORECASE,
)

# Patterns that signal a technical or conditioning round line
_TECHNICAL_ROUND_SIGNALS = re.compile(
    r"\b(round|rounds?|technical|rhythm|shadowbox|flow round|walk.?through|drill round)\b",
    re.IGNORECASE,
)

# Patterns that indicate a conditioning-style round structure (forbidden on D-1).
# Matches patterns like "3 rounds of 2 min", "10 rounds of 6 sec".
# Uses \s+ throughout and avoids alternation on digit groups to prevent ReDoS.
_CONDITIONING_ROUND_STRUCTURE = re.compile(
    r"\d+\s+(?:rounds?|rnd)\s+(?:of|@|x)\s+\d+\s*(?:min|sec)\b",
    re.IGNORECASE,
)


def _extract_leading_count(text: str) -> int | None:
    """Return the *upper* bound of the first numeric range (or single number) in *text*."""
    m = _DOSE_RANGE_PREFIX.search(text)
    if not m:
        return None
    if m.group(1) and m.group(2):
        return int(m.group(2))
    if m.group(3):
        return int(m.group(3))
    return None


def _late_fight_dosage_ceilings(days_until_fight: int) -> dict[str, int]:
    """Return per-day dosage ceilings: max_alactic_bursts, max_technical_rounds."""
    table: dict[int, dict[str, int]] = {
        5: {"max_alactic_bursts": 6, "max_technical_rounds": 4},
        4: {"max_alactic_bursts": 5, "max_technical_rounds": 3},
        3: {"max_alactic_bursts": 4, "max_technical_rounds": 3},
        2: {"max_alactic_bursts": 4, "max_technical_rounds": 2},
        1: {"max_alactic_bursts": 3, "max_technical_rounds": 2},
        0: {"max_alactic_bursts": 4, "max_technical_rounds": 0},
    }
    return table.get(days_until_fight, {})


def _count_dosage_in_blocks(
    blocks: list[list[str]],
) -> tuple[int, int]:
    """Parse rendered plan blocks and return (max_alactic_count, max_technical_count) seen."""
    max_alactic = 0
    max_technical = 0
    for block in blocks:
        for line in _late_fight_block_body(block):
            low = line.lower()
            count = _extract_leading_count(low)
            if count is None:
                continue
            if _ALACTIC_BURST_SIGNALS.search(low):
                max_alactic = max(max_alactic, count)
            elif _TECHNICAL_ROUND_SIGNALS.search(low):
                max_technical = max(max_technical, count)
    return max_alactic, max_technical


def _has_conditioning_round_structure(blocks: list[list[str]]) -> list[str]:
    """Return lines that contain a conditioning-style round structure (e.g. '6–10 rounds of 6–12 sec')."""
    matches: list[str] = []
    for block in blocks:
        for line in _late_fight_block_body(block):
            if _CONDITIONING_ROUND_STRUCTURE.search(line):
                matches.append(line)
    return matches


def _late_fight_dosage_warnings(
    spec: dict[str, Any],
    blocks: list[list[str]],
) -> list[dict]:
    """Emit dosage-ceiling warnings for late-fight countdown days (days_until_fight <= 5)."""
    days_out_bucket = str(spec.get("days_out_bucket") or "")
    payload_mode = str(spec.get("payload_mode") or "")

    # Derive days_until_fight from the bucket string, e.g. "D-5" → 5.
    # Only process buckets matching the expected "D-N" format.
    if not re.match(r"^D-\d+$", days_out_bucket):
        return []
    try:
        days_int = int(days_out_bucket[2:])
    except ValueError:
        return []

    if days_int > 5:
        return []

    ceilings = _late_fight_dosage_ceilings(days_int)
    if not ceilings:
        return []

    warnings: list[dict] = []
    actual_alactic, actual_technical = _count_dosage_in_blocks(blocks)

    max_alactic = ceilings.get("max_alactic_bursts")
    if max_alactic is not None and actual_alactic > max_alactic:
        warnings.append(
            {
                "code": "late_fight_alactic_dose_overage",
                "message": (
                    f"{days_out_bucket} contains {actual_alactic} alactic efforts, "
                    f"exceeding the {max_alactic}-effort ceiling for this countdown day."
                ),
                "payload_mode": payload_mode,
                "days_out_bucket": days_out_bucket,
                "actual_alactic_count": actual_alactic,
                "max_alactic_bursts": max_alactic,
                "blocking": True,
            }
        )

    max_technical = ceilings.get("max_technical_rounds")
    if max_technical is not None and actual_technical > max_technical:
        warnings.append(
            {
                "code": "late_fight_technical_round_overage",
                "message": (
                    f"{days_out_bucket} contains {actual_technical} technical rounds, "
                    f"exceeding the {max_technical}-round ceiling for this countdown day."
                ),
                "payload_mode": payload_mode,
                "days_out_bucket": days_out_bucket,
                "actual_technical_count": actual_technical,
                "max_technical_rounds": max_technical,
                "blocking": True,
            }
        )

    # D-1 specific: no conditioning-style round structures at all
    if days_int == 1:
        cond_lines = _has_conditioning_round_structure(blocks)
        if cond_lines:
            warnings.append(
                {
                    "code": "late_fight_conditioning_round_structure_forbidden",
                    "message": (
                        "D-1 plan contains conditioning-style round structures, "
                        "which are forbidden on the day before fight."
                    ),
                    "payload_mode": payload_mode,
                    "days_out_bucket": days_out_bucket,
                    "matched_lines": cond_lines[:3],
                    "blocking": True,
                }
            )

    return warnings


def _late_fight_warnings(planning_brief: dict, final_plan_text: str) -> list[dict]:
    spec = _late_fight_plan_spec(planning_brief)
    payload_mode = str(spec.get("payload_mode") or "")
    if not spec or payload_mode in {"", "camp_payload"}:
        return []

    plan_lines = _extract_plan_lines(final_plan_text)
    blocks = _late_fight_session_blocks(final_plan_text)
    warnings: list[dict] = []
    days_out_bucket = str(spec.get("days_out_bucket") or "")

    max_active_roles = spec.get("max_active_roles")
    if isinstance(max_active_roles, int) and max_active_roles >= 0 and len(blocks) > max_active_roles:
        warnings.append(
            {
                "code": "late_fight_active_role_overage",
                "message": f"{days_out_bucket or payload_mode} renders {len(blocks)} active sessions even though the late-fight cap is {max_active_roles}.",
                "payload_mode": payload_mode,
                "days_out_bucket": days_out_bucket,
                "actual_sessions": len(blocks),
                "max_active_roles": max_active_roles,
                "blocking": True,
            }
        )

    max_blocks_per_session = spec.get("max_blocks_per_session")
    if isinstance(max_blocks_per_session, int) and max_blocks_per_session > 0:
        for session_index, block in enumerate(blocks, start=1):
            body_lines = _late_fight_block_body(block)
            if len(body_lines) <= max_blocks_per_session:
                continue
            warnings.append(
                {
                    "code": "late_fight_block_overage",
                    "message": f"{days_out_bucket or payload_mode} session {session_index} exceeds the {max_blocks_per_session}-block ceiling.",
                    "payload_mode": payload_mode,
                    "days_out_bucket": days_out_bucket,
                    "session_index": session_index,
                    "line": block[0],
                    "actual_block_count": len(body_lines),
                    "max_blocks_per_session": max_blocks_per_session,
                    "blocking": True,
                }
            )

    max_meaningful_stress_exposures = spec.get("max_meaningful_stress_exposures")
    if isinstance(max_meaningful_stress_exposures, int) and max_meaningful_stress_exposures >= 0:
        exposure_count, exposures = _late_fight_meaningful_exposure_count(blocks)
        if exposure_count > max_meaningful_stress_exposures:
            warnings.append(
                {
                    "code": "late_fight_meaningful_stress_overage",
                    "message": f"{days_out_bucket or payload_mode} carries {exposure_count} meaningful stress exposures even though the cap is {max_meaningful_stress_exposures}.",
                    "payload_mode": payload_mode,
                    "days_out_bucket": days_out_bucket,
                    "actual_exposures": exposure_count,
                    "max_meaningful_stress_exposures": max_meaningful_stress_exposures,
                    "exposures": exposures,
                    "blocking": True,
                }
            )

    hard_sparring_blocks = [
        {
            "session_index": index,
            "line": block[0],
        }
        for index, block in enumerate(blocks, start=1)
        if _block_contains_token(block, "hard_sparring")
    ]
    if days_out_bucket == "D-7" and len(hard_sparring_blocks) > 1:
        warnings.append(
            {
                "code": "late_fight_hard_sparring_overage",
                "message": "D-7 contains more than one hard sparring exposure.",
                "payload_mode": payload_mode,
                "days_out_bucket": days_out_bucket,
                "hard_sparring_sessions": hard_sparring_blocks,
                "blocking": True,
            }
        )
    elif days_out_bucket in {"D-6", "D-5", "D-4", "D-3", "D-2", "D-1", "D-0"} and hard_sparring_blocks:
        warnings.append(
            {
                "code": "late_fight_hard_sparring_overage",
                "message": f"{days_out_bucket} still contains true hard sparring, which late-fight logic forbids.",
                "payload_mode": payload_mode,
                "days_out_bucket": days_out_bucket,
                "hard_sparring_sessions": hard_sparring_blocks,
                "blocking": True,
            }
        )

    for token in spec.get("forbidden_blocks", []) or []:
        if token in {"hard_sparring", "multiple_hard_sparring_exposures"}:
            continue
        matches = _late_fight_forbidden_matches(token, plan_lines, blocks)
        if not matches:
            continue
        warnings.append(
            {
                "code": "late_fight_forbidden_content",
                "message": f"{days_out_bucket or payload_mode} includes forbidden late-fight content: {token.replace('_', ' ')}.",
                "payload_mode": payload_mode,
                "days_out_bucket": days_out_bucket,
                "forbidden_block": token,
                "line": matches[0],
                "matched_lines": matches[:3],
                "blocking": True,
            }
        )

    if days_out_bucket != "D-0":
        mislabel_lines = [
            line
            for line in plan_lines
            if phrase_in_text(line, "D-7") and phrase_in_text(line, "fight day")
        ]
        if mislabel_lines:
            warnings.append(
                {
                    "code": "late_fight_countdown_fight_day_mislabel",
                    "message": "D-7 is not fight day. Fight day must render only as D-0.",
                    "payload_mode": payload_mode,
                    "days_out_bucket": days_out_bucket,
                    "line": mislabel_lines[0],
                    "matched_lines": mislabel_lines[:3],
                    "blocking": True,
                }
            )

    countdown_sections = _countdown_sections(final_plan_text)
    if countdown_sections:
        for section in countdown_sections:
            section_lines = [str(line) for line in section.get("lines", [])]
            window_key = str(section.get("window") or "")
            day_label = str(section.get("day_label") or days_out_bucket)
            window_rules = _LATE_FIGHT_WINDOW_EXERCISE_RULES.get(window_key, {})
            matched_hits: list[dict[str, str]] = []
            for line in section_lines:
                if _line_is_instruction_only(line):
                    continue
                lowered = line.lower()
                if day_label.upper() == "D-3" and _late_fight_d3_throw_signal(line):
                    matched_hits.append({"term": "D3 throw lockout", "line": line})
                    continue
                for term in window_rules.get("blocked", []):
                    if phrase_in_text(lowered, term.lower()):
                        matched_hits.append({"term": term, "line": line})
                        break
            if matched_hits:
                warnings.append(
                    {
                        "code": "late_fight_window_forbidden_exercise",
                        "message": f"{day_label} includes exercises blocked for {window_key}.",
                        "payload_mode": payload_mode,
                        "days_out_bucket": day_label,
                        "window": window_key,
                        "section_title": section.get("title"),
                        "line": matched_hits[0]["line"],
                        "matched_terms": dedupe_preserve_order([hit["term"] for hit in matched_hits])[:5],
                        "matched_lines": dedupe_preserve_order([hit["line"] for hit in matched_hits])[:3],
                        "blocking": True,
                    }
                )
            preferred_terms = window_rules.get("preferred", [])
            preferred_present = any(
                phrase_in_text(line.lower(), term.lower())
                for line in section_lines
                if not _line_is_instruction_only(line)
                for term in preferred_terms
            )
            if preferred_terms and not preferred_present:
                warnings.append(
                    {
                        "code": "late_fight_window_preferred_missing",
                        "message": f"{day_label} does not show any preferred exercise cues for {window_key}.",
                        "payload_mode": payload_mode,
                        "days_out_bucket": day_label,
                        "window": window_key,
                        "section_title": section.get("title"),
                        "preferred_terms": preferred_terms[:5],
                        "blocking": False,
                    }
                )

    warnings.extend(_late_fight_countdown_blocked_drill_warnings(spec, final_plan_text, plan_lines))
    warnings.extend(_late_fight_countdown_banded_lockout_warnings(spec, final_plan_text, plan_lines))
    warnings.extend(_late_fight_progression_lockout_warnings(spec, final_plan_text, plan_lines))
    warnings.extend(_late_fight_allowed_exercise_warnings(spec, final_plan_text, plan_lines))
    warnings.extend(_late_fight_neural_power_stack_warnings(spec, final_plan_text, plan_lines))
    warnings.extend(_late_fight_dosage_warnings(spec, blocks))

    return warnings




def _issue(*, code: str, message: str, severity: str, confidence: str, line: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "confidence": confidence,
        "line": line,
        **extra,
    }


def _normalize_warning(item: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "code": "stage2_warning",
        "message": "Stage 2 validation warning.",
        "severity": "warning",
        "confidence": "medium",
        "line": "",
    }
    return {**defaults, **item}


def _stage2_output_incomplete_errors(final_plan_text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in str(final_plan_text or "").splitlines() if line.strip()]
    if not lines:
        return []
    last_line = lines[-1]
    if re.search(r"(?:^|\s)(?:Anchor|Support|Rehab)\s*[—-]\s*$", last_line, re.IGNORECASE):
        return [_issue(code="stage2_output_truncated", message="Stage 2 output ends on an unfinished label.", severity="blocker", confidence="high", line=last_line)]
    if re.search(r"^\s*(?:#+\s*)?D-\d+\s*(?:\([^)]*\))?\s*(?:—|-|:)\s*$", last_line, re.IGNORECASE):
        return [_issue(code="stage2_output_truncated", message="Stage 2 output ends on an unfinished heading.", severity="blocker", confidence="high", line=last_line)]
    if re.search(r"(?:^|\s)(?:Why|Coach|Support|Rehab)\s*:\s*$", last_line, re.IGNORECASE):
        return [_issue(code="stage2_output_truncated", message="Stage 2 output looks cut off mid-line.", severity="blocker", confidence="high", line=last_line)]
    return []


def _is_countdown_block_boundary(line: str) -> bool:
    """Return True when a line ends the current countdown day's body.

    Countdown days (``D-X ...``) render as a header line followed by their own
    bullet/why body. Everything *after* the last countdown day — ``## Nutrition``,
    ``## Recovery``, ``## Selection Rationale``, ``## Athlete Profile`` and the
    like — is a separate top-level section, not part of that day. Those sections
    routinely mention "strength", "conditioning", etc. in prose, so if they get
    absorbed into the final (often D-0) block they trip the day-level training
    guards as a false positive. A markdown section header is a reliable boundary
    because countdown days themselves are never sub-sectioned with headers.
    """
    if _COUNTDOWN_LABEL_LINE.match(line):
        return False
    return bool(_MARKDOWN_HEADER.match(line))


def _countdown_blocks(final_plan_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in str(final_plan_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _COUNTDOWN_LABEL_LINE.match(line)
        if match:
            if current:
                blocks.append(current)
            current = {"day": int(match.group(2)), "header": line, "lines": []}
            continue
        if _is_countdown_block_boundary(line):
            if current:
                blocks.append(current)
            current = None
            continue
        if current:
            current["lines"].append(line)
    if current:
        blocks.append(current)
    return blocks


HARD_SPARRING_TERMS = (
    "hard spar",
    "hard sparring",
    "live spar",
    "live sparring",
    "full spar",
    "full sparring",
    "full contact",
    "hard contact",
    "fight-pace sparring",
    "competitive sparring",
    "open sparring",
)

_HARD_SPARRING_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in HARD_SPARRING_TERMS) + r")\b",
    re.IGNORECASE,
)

_NEGATED_HARD_SPARRING_PATTERN = re.compile(
    r"\b(?:no|avoid|without|do\s+not|don't|not)\s+(?:\w+\s+){0,3}"
    r"(?:" + "|".join(re.escape(t) for t in HARD_SPARRING_TERMS) + r")$",
    re.IGNORECASE,
)


def _has_blocking_hard_sparring(text: str) -> bool:
    if not text:
        return False
    for match in _HARD_SPARRING_PATTERN.finditer(text):
        window_start = max(0, match.start() - 40)
        candidate = text[window_start:match.end()]
        if _NEGATED_HARD_SPARRING_PATTERN.search(candidate):
            continue
        return True
    return False

def validate_stage2_output(*, planning_brief: dict, final_plan_text: str) -> dict:
    plan_lines = _extract_plan_lines(final_plan_text)
    phase_sections = _phase_sections(final_plan_text)
    restricted_hits = _find_restricted_hits(planning_brief, plan_lines)
    countdown_blocks = _countdown_blocks(final_plan_text)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not plan_lines:
        errors.append(_issue(code="stage2_output_empty", message="Stage 2 output is empty.", severity="blocker", confidence="high"))
    errors.extend(_stage2_output_incomplete_errors(final_plan_text))
    errors.extend(
        _issue(code="restriction_violation", message=f"Restriction {hit['restriction']} matched line.", severity="blocker", confidence="high", line=hit["line"], restriction=hit["restriction"], strength=hit.get("strength"))
        for hit in restricted_hits
    )
    internal_patterns = (
        r"\brole(?:_|\s+)key\b",
        r"\bcandidate(?:_|\s+)pool\b",
        r"\bplanning(?:_|\s+)brief\b",
        r"\bstage2(?:_|\s+)payload\b",
        r"\bstage2(?:_|\s+)handoff\b",
        r"\bvalidator(?:_|\s+)report\b",
        r"\bwhy(?:_|\s+)log\b",
        r"\btaper(?:_|\s+)micro(?:_|\s+)support\b",
        r"\brender(?:_|\s+)contract\b",
    )
    for pattern in internal_patterns:
        for line in plan_lines:
            leak_match = re.search(pattern, line, re.IGNORECASE)
            if leak_match:
                leaked = leak_match.group(0)
                errors.append(_issue(code="true_internal_system_leak", message=f"Internal system term leaked: {leaked}.", severity="blocker", confidence="high", line=line))
                break
    d1_risk_pattern = re.compile(r"\b(strength|conditioning|sprints?|interval|heavy|loaded|deadlift|squat|trap bar|barbell)\b", re.IGNORECASE)
    # Only concrete app-prescribed training modalities should block fight day.
    # Generic prose words ("extra", "plus", "add") live in coach notes/rationale
    # and caused false fight_day_protocol_violation flags.
    d0_extra_pattern = re.compile(r"\b(?:conditioning|strength|finisher|circuit|sprint|lift|deadlift|squat|barbell)\b", re.IGNORECASE)
    protocol_full = _normalize_render_line(FIGHT_DAY_PROTOCOL_TEXT)
    protocol_body = _normalize_render_line(
        re.sub(r"^fight day protocol\s*[—:-]\s*", "", FIGHT_DAY_PROTOCOL_TEXT, flags=re.IGNORECASE)
    )

    def _is_fight_day_protocol_line(line: str) -> bool:
        cleaned = _BULLET_PREFIX.sub("", line).strip()
        normalized = _normalize_render_line(cleaned)
        if not normalized:
            return False
        return normalized in {protocol_full, protocol_body} or normalized in protocol_full

    for block in countdown_blocks:
        day = int(block["day"])
        safe_lines = [
            line
            for line in block["lines"]
            if not _line_is_instruction_only(line) and not _is_fight_day_protocol_line(line)
        ]
        joined = " ".join(safe_lines)
        has_blocking_hard_sparring = _has_blocking_hard_sparring(block["header"]) or _has_blocking_hard_sparring(joined)
        if day == 12 and has_blocking_hard_sparring:
            warnings.append(_issue(code="late_fight_hard_sparring_d12_review", message="Hard sparring appears on D-12; review coach load and recovery risk.", severity="review", confidence="medium", line=block["header"]))
        if 0 <= day <= 11 and has_blocking_hard_sparring:
            errors.append(_issue(code="late_fight_hard_sparring_violation", message="Hard sparring appears inside D-11 to D-0.", severity="blocker", confidence="high", line=block["header"]))
        if day == 1 and d1_risk_pattern.search(joined):
            errors.append(_issue(code="dangerous_late_fight_strength_or_conditioning", message="D-1 includes hard strength/conditioning exposure.", severity="blocker", confidence="medium", line=block["header"]))
        if day == 0 and d0_extra_pattern.search(joined):
            errors.append(_issue(code="fight_day_protocol_violation", message="D-0 includes extra training beyond fight-day protocol.", severity="blocker", confidence="medium", line=block["header"]))

    missing_required_elements = _find_missing_required_elements(planning_brief, final_plan_text)
    missing_phase_sections = _find_missing_phase_sections(planning_brief, phase_sections)
    strength_session_warnings = _strength_session_quality_warnings(planning_brief, phase_sections, plan_lines)
    conditioning_choice_warnings = _conditioning_choice_warnings(plan_lines)
    rendering_discipline_warnings = _rendering_discipline_warnings(planning_brief, phase_sections)
    equipment_congruence_warnings = _equipment_congruence_warnings(planning_brief, phase_sections, plan_lines)
    unresolved_access_fallback_warnings = _unresolved_access_fallback_warnings(planning_brief, phase_sections)
    week_completeness_warnings = _week_completeness_warnings(planning_brief, final_plan_text)
    crowded_week_warnings = _boxing_crowded_week_warnings(planning_brief, final_plan_text)
    weight_cut_acknowledgement_warnings = _weight_cut_acknowledgement_warnings(planning_brief, final_plan_text)
    weight_cut_contradiction_warnings = _weight_cut_contradiction_warnings(planning_brief, final_plan_text)
    late_fight_header_contract_warnings = _late_fight_header_contract_warnings(planning_brief, plan_lines)
    late_fight_d0_protocol_warnings = _late_fight_d0_protocol_warnings(planning_brief, final_plan_text, plan_lines)
    late_fight_missing_terminal_d0_warnings = _late_fight_missing_terminal_d0_warnings(
        planning_brief,
        final_plan_text,
    )
    internal_render_contract_leak_warnings = _internal_render_contract_leak_warnings(plan_lines)
    coach_owned_sparring_detail_warnings = _coach_owned_sparring_detail_warnings(final_plan_text)
    lead_summary_contract_warnings = _lead_summary_contract_warnings(planning_brief, plan_lines)
    overstyled_name_warnings = _overstyled_name_warnings(plan_lines)
    coach_voice_warnings = _coach_voice_warnings(planning_brief, plan_lines)
    calendar_spine_warnings = _calendar_spine_warnings(planning_brief, final_plan_text)
    late_fight_warnings = _late_fight_warnings(planning_brief, final_plan_text)
    sport_language_warnings = _sport_language_warnings(planning_brief, plan_lines)

    warnings.extend(
        _issue(
            code="missing_required_element",
            message=item.get("reason", "Missing required element."),
            severity=item.get("severity", "warning"),
            confidence="medium",
            phase=item.get("phase"),
            requirement=item.get("requirement"),
            candidate_names=item.get("candidate_names"),
        )
        for item in missing_required_elements
    )
    warnings.extend(
        _issue(
            code="phase_section_missing",
            message=item.get("reason", "Missing required phase section."),
            severity=item.get("severity", "warning"),
            confidence="medium",
            phase=item.get("phase"),
        )
        for item in missing_phase_sections
    )
    warnings.extend(_normalize_warning(item) for item in strength_session_warnings)
    warnings.extend(_normalize_warning(item) for item in conditioning_choice_warnings)
    warnings.extend(_normalize_warning(item) for item in rendering_discipline_warnings)
    warnings.extend(_normalize_warning(item) for item in equipment_congruence_warnings)
    warnings.extend(_normalize_warning(item) for item in unresolved_access_fallback_warnings)
    warnings.extend(_normalize_warning(item) for item in week_completeness_warnings)
    warnings.extend(_normalize_warning(item) for item in crowded_week_warnings)
    warnings.extend(_normalize_warning(item) for item in weight_cut_acknowledgement_warnings)
    warnings.extend(_normalize_warning(item) for item in weight_cut_contradiction_warnings)
    warnings.extend(_normalize_warning(item) for item in late_fight_header_contract_warnings)
    warnings.extend(_normalize_warning(item) for item in late_fight_d0_protocol_warnings)
    warnings.extend(_normalize_warning(item) for item in late_fight_missing_terminal_d0_warnings)
    warnings.extend(_normalize_warning(item) for item in internal_render_contract_leak_warnings)
    warnings.extend(_normalize_warning(item) for item in coach_owned_sparring_detail_warnings)
    warnings.extend(_normalize_warning(item) for item in lead_summary_contract_warnings)
    warnings.extend(_normalize_warning(item) for item in overstyled_name_warnings)
    warnings.extend(_normalize_warning(item) for item in coach_voice_warnings)
    warnings.extend(_normalize_warning(item) for item in calendar_spine_warnings)
    warnings.extend(_normalize_warning(item) for item in late_fight_warnings)
    warnings.extend(_normalize_warning(item) for item in sport_language_warnings)

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "missing_required_elements": missing_required_elements,
        "missing_phase_sections": missing_phase_sections,
        "restricted_hits": restricted_hits,
        "strength_session_warnings": strength_session_warnings,
        "conditioning_choice_warnings": conditioning_choice_warnings,
        "rendering_discipline_warnings": rendering_discipline_warnings,
        "equipment_congruence_warnings": equipment_congruence_warnings,
        "unresolved_access_fallback_warnings": unresolved_access_fallback_warnings,
        "week_completeness_warnings": week_completeness_warnings,
        "crowded_week_warnings": crowded_week_warnings,
        "weight_cut_acknowledgement_warnings": weight_cut_acknowledgement_warnings,
        "weight_cut_contradiction_warnings": weight_cut_contradiction_warnings,
        "late_fight_header_contract_warnings": late_fight_header_contract_warnings,
        "late_fight_d0_protocol_warnings": late_fight_d0_protocol_warnings,
        "late_fight_missing_terminal_d0_warnings": late_fight_missing_terminal_d0_warnings,
        "internal_render_contract_leak_warnings": internal_render_contract_leak_warnings,
        "coach_owned_sparring_detail_warnings": coach_owned_sparring_detail_warnings,
        "lead_summary_contract_warnings": lead_summary_contract_warnings,
        "overstyled_name_warnings": overstyled_name_warnings,
        "gimmick_name_warnings": [],
        "coach_voice_warnings": coach_voice_warnings,
        "calendar_spine_warnings": calendar_spine_warnings,
        "late_fight_warnings": late_fight_warnings,
        "stage2_output_incomplete_warnings": [],
        "sport_language_warnings": sport_language_warnings,
    }
