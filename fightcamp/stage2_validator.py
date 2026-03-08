from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .restriction_filtering import evaluate_restriction_impact

_BULLET_PREFIX = re.compile(r"^\s*(?:[-*\u2022]+|\d+[.)]|#+)\s*")
_PHASE_HEADER = re.compile(r"\b(?:GPP|SPP|TAPER)\b", re.IGNORECASE)
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
        phase_match = _PHASE_HEADER.search(cleaned)
        if phase_match:
            current_phase = phase_match.group(0).upper()
        if current_phase:
            sections[current_phase].append(cleaned)
    return dict(sections)


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


def validate_stage2_output(*, planning_brief: dict, final_plan_text: str) -> dict:
    plan_lines = _extract_plan_lines(final_plan_text)
    phase_sections = _phase_sections(final_plan_text)
    restricted_hits = _find_restricted_hits(planning_brief, plan_lines)
    missing_required_elements = _find_missing_required_elements(planning_brief, final_plan_text)
    missing_phase_sections = _find_missing_phase_sections(planning_brief, phase_sections)

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

    return {
        "is_valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "missing_required_elements": missing_required_elements,
        "missing_phase_sections": missing_phase_sections,
        "restricted_hits": restricted_hits,
    }
