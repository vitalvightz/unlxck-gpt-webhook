from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .phases import PHASE_HEADER_PATTERN
from .regex_config import compile_regex, compile_regex_list
from .restriction_filtering import evaluate_restriction_impact

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
        "single-leg",
        "single leg",
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
    "sharpness_touch": ("alactic", "sharpness", "primer", "neural primer", "power touch", "neural touch", "technical touch", "low-noise power"),
    "recovery": ("recovery", "freshness", "mobility", "breathing", "reset"),
    "technical": ("technical", "rhythm", "shadowboxing", "flow rounds", "drill"),
    "layered_rehab_stack": ("rehab stack",),
}
_LATE_FIGHT_REHAB_PHRASES = ("rehab", "band external rotation", "scap", "mobility", "tissue", "breathing")


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _phrase_in_text(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    parts = [re.escape(part) for part in re.split(r"[\s-]+", phrase.strip().lower()) if part]
    if not parts:
        return False
    pattern = r"\b" + r"[\s-]+".join(parts) + r"\b"
    return re.search(pattern, text.lower()) is not None


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
    phrases.extend(_clean_list(restriction.get("blocked_patterns")))
    phrases.extend(_clean_list(restriction.get("mechanical_equivalents")))
    source_phrase = str(restriction.get("source_phrase", "")).strip()
    if source_phrase:
        phrases.append(source_phrase)
    restriction_key = str(restriction.get("restriction", "")).strip().replace("_", " ")
    if restriction_key:
        phrases.append(restriction_key)
    return _dedupe_preserve_order([phrase for phrase in phrases if phrase])


def _line_is_instruction_only(line: str, phrase: str | None = None) -> bool:
    normalized = line.lower()
    if phrase and not _phrase_in_text(normalized, phrase):
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
            phrase_match = next((phrase for phrase in phrases if _phrase_in_text(line_key, phrase)), None)
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
    return _dedupe_preserve_order(names)


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
    if any(_phrase_in_text(normalized, name) for name in candidate_names):
        return True
    section_hints = _SECTION_HINTS.get(requirement, ())
    return any(_phrase_in_text(normalized, hint) for hint in section_hints)


def _find_missing_phase_sections(planning_brief: dict, phase_sections: dict[str, list[str]]) -> list[dict]:
    expected_phases = [phase for phase, strategy in (planning_brief.get("phase_strategy") or {}).items() if _clean_list(strategy.get("must_keep", []))]
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
        for requirement in _clean_list(strategy.get("must_keep", [])):
            slots = _slots_for_requirement(phase_pool, requirement)
            if not slots:
                continue
            candidate_names = _dedupe_preserve_order([name for slot in slots for name in _slot_candidate_names(slot)])
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
    return _dedupe_preserve_order(
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
    readiness_flags = set(_clean_list(athlete.get("readiness_flags", [])))
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
    readiness_flags = set(_clean_list(athlete.get("readiness_flags", [])))
    fatigue = str(athlete.get("fatigue", "")).strip().lower()
    days_until_fight = athlete.get("days_until_fight")
    weight_cut = _weight_cut_context(planning_brief)
    injury_present = bool(_clean_list(athlete.get("injuries"))) or "injury_management" in readiness_flags
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
    for value in _clean_list(values):
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
        if _phrase_in_text(normalized, record.get("name", ""))
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
            anchor_names = _dedupe_preserve_order(anchor_names)
            support_names = _dedupe_preserve_order(support_names)
            if not anchor_names:
                continue
            matched_lines = [
                line
                for line in phase_lines
                if any(_phrase_in_text(line, name) for name in session_names)
            ]
            if not matched_lines:
                continue
            anchor_lines = [
                line
                for line in matched_lines
                if any(_phrase_in_text(line, name) for name in anchor_names)
            ]
            support_lines = [
                line
                for line in matched_lines
                if any(_phrase_in_text(line, name) for name in support_names)
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
                    any(_phrase_in_text(line, name) for name in support_names)
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
                    any(_phrase_in_text(line, name) for name in anchor_names)
                    for line in first_two
                ) and all(
                    any(_phrase_in_text(line, name) for name in support_names)
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


def _late_fight_plan_spec(planning_brief: dict) -> dict[str, Any]:
    spec = planning_brief.get("late_fight_plan_spec") or {}
    return spec if isinstance(spec, dict) else {}


def _late_fight_session_blocks(final_plan_text: str) -> list[list[str]]:
    blocks = _phase_session_blocks(_extract_plan_lines(final_plan_text))
    return [block for block in blocks if block]


def _late_fight_block_body(block: list[str]) -> list[str]:
    if len(block) <= 1:
        return []
    return [line for line in block[1:] if _normalize_render_line(line)]


def _block_contains_token(block: list[str], token: str) -> bool:
    text = " ".join(block).lower()
    phrases = _LATE_FIGHT_TOKEN_PHRASES.get(token, ())
    return any(_phrase_in_text(text, phrase) for phrase in phrases)


def _line_matches_late_fight_token(line: str, token: str) -> bool:
    if _line_is_instruction_only(line):
        return False
    lowered = line.lower()
    phrases = _LATE_FIGHT_TOKEN_PHRASES.get(token, ())
    return any(_phrase_in_text(lowered, phrase) for phrase in phrases)


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
                if any(_phrase_in_text(line.lower(), phrase) for phrase in _LATE_FIGHT_REHAB_PHRASES)
            ]
            if len(rehab_lines) >= 2:
                matched.append(block[0])
        return matched
    return [line for line in plan_lines if _line_matches_late_fight_token(line, token)]


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

    return warnings


def validate_stage2_output(*, planning_brief: dict, final_plan_text: str) -> dict:
    plan_lines = _extract_plan_lines(final_plan_text)
    phase_sections = _phase_sections(final_plan_text)
    restricted_hits = _find_restricted_hits(planning_brief, plan_lines)
    missing_required_elements = _find_missing_required_elements(planning_brief, final_plan_text)
    missing_phase_sections = _find_missing_phase_sections(planning_brief, phase_sections)
    strength_session_warnings = _strength_session_quality_warnings(
        planning_brief,
        phase_sections,
        plan_lines,
    )
    conditioning_choice_warnings = _conditioning_choice_warnings(plan_lines)
    rendering_discipline_warnings = _rendering_discipline_warnings(planning_brief, phase_sections)
    equipment_congruence_warnings = _equipment_congruence_warnings(
        planning_brief,
        phase_sections,
        plan_lines,
    )
    unresolved_access_fallback_warnings = _unresolved_access_fallback_warnings(
        planning_brief,
        phase_sections,
    )
    week_completeness_warnings = _week_completeness_warnings(
        planning_brief,
        final_plan_text,
    )
    weight_cut_acknowledgement_warnings = _weight_cut_acknowledgement_warnings(
        planning_brief,
        final_plan_text,
    )
    weight_cut_contradiction_warnings = _weight_cut_contradiction_warnings(
        planning_brief,
        final_plan_text,
    )
    overstyled_name_warnings = _overstyled_name_warnings(plan_lines)
    coach_voice_warnings = _coach_voice_warnings(planning_brief, plan_lines)
    sport_language_warnings = _sport_language_warnings(planning_brief, plan_lines)
    late_fight_warnings = _late_fight_warnings(planning_brief, final_plan_text)

    errors = [
        {
            "code": "restriction_violation",
            "message": f"Restriction {hit['restriction']} matched line: {hit['line']}",
            "restriction": hit["restriction"],
            "line": hit["line"],
            "strength": hit.get("strength"),
        }
        for hit in restricted_hits
    ]
    warnings = [
        {
            "code": "missing_required_element",
            "message": item["reason"],
            "phase": item["phase"],
            "requirement": item["requirement"],
            "candidate_names": item["candidate_names"],
        }
        for item in missing_required_elements
    ]
    warnings.extend(
        {
            "code": "phase_section_missing",
            "message": item["reason"],
            "phase": item["phase"],
        }
        for item in missing_phase_sections
    )
    warnings.extend(strength_session_warnings)
    warnings.extend(conditioning_choice_warnings)
    warnings.extend(rendering_discipline_warnings)
    warnings.extend(equipment_congruence_warnings)
    warnings.extend(unresolved_access_fallback_warnings)
    warnings.extend(week_completeness_warnings)
    warnings.extend(weight_cut_acknowledgement_warnings)
    warnings.extend(weight_cut_contradiction_warnings)
    warnings.extend(overstyled_name_warnings)
    warnings.extend(coach_voice_warnings)
    warnings.extend(sport_language_warnings)
    warnings.extend(late_fight_warnings)

    return {
        "is_valid": not errors,
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
        "weight_cut_acknowledgement_warnings": weight_cut_acknowledgement_warnings,
        "weight_cut_contradiction_warnings": weight_cut_contradiction_warnings,
        "overstyled_name_warnings": overstyled_name_warnings,
        "gimmick_name_warnings": overstyled_name_warnings,
        "coach_voice_warnings": coach_voice_warnings,
        "late_fight_warnings": late_fight_warnings,
        "sport_language_warnings": sport_language_warnings,
    }
