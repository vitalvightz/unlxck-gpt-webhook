from __future__ import annotations

import re
from pathlib import Path
from typing import Any


STYLE_CONDITIONING_REPORT_FIELDS = (
    "name",
    "system",
    "phases",
    "rpe",
    "intensity",
    "lactate_load",
    "movement_cost",
    "impact_cost",
    "late_windows",
    "overstyled_name_flag",
    "aggressive_notes_flag",
    "dose_risk_flag",
    "late_fight_risk_flag",
    "camp_action",
    "late_fight_action",
    "manual_notes",
)

HIGH_INTENSITY_VALUES = {"high", "very_high", "max", "maximum"}
LATE_DOSE_FIELDS = (
    "duration",
    "timing",
    "load",
    "prescription",
    "work_sec",
    "rest_sec",
    "rounds",
    "total_minutes",
)
NOTE_FIELDS = (
    "notes",
    "description",
    "purpose",
    "load",
    "duration",
    "prescription",
    "equipment_note",
)

OVERSTYLED_NAME_TERMS = (
    "assassin",
    "beast mode",
    "berserker",
    "bloodbath",
    "death",
    "destroy",
    "gladiator",
    "hell",
    "killer",
    "mauler",
    "meat grinder",
    "obliterate",
    "prison rules",
    "punisher",
    "savage",
    "spartan",
    "stomper",
    "thug",
    "terminator",
    "torture",
    "warrior",
    "war",
)
AGGRESSIVE_TEXT_TERMS = (
    "all-out war",
    "annihilator",
    "bloodbath",
    "break them",
    "butcher",
    "carnage",
    "crusher",
    "cinematic",
    "devastation",
    "destroy",
    "domination",
    "executioner",
    "fight to the death",
    "hell",
    "kill",
    "kill mode",
    "mauler",
    "meat grinder",
    "movie scene",
    "no mercy",
    "obliterate",
    "prison rules",
    "punish",
    "savage",
    "stab",
    "stomper",
    "street fight",
    "torture",
    "violent",
    "war",
)
DESTRUCTIVE_WORDING_TERMS = (
    "annihilator",
    "bloodbath",
    "butcher",
    "carnage",
    "crusher",
    "death",
    "destroy",
    "devastation",
    "domination",
    "executioner",
    "fight to the death",
    "hell",
    "kill",
    "kill mode",
    "mauler",
    "meat grinder",
    "no mercy",
    "obliterate",
    "prison rules",
    "stab",
    "stomper",
    "torture",
    "violent",
    "war",
)

HIGH_DOSE_REASONS = {
    "high_rpe",
    "high_intensity",
    "high_lactate_load",
    "high_movement_cost",
    "high_impact_cost",
}
_PATTERN_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}


def _source_filename(source: str | None) -> str:
    return Path(str(source or "").replace("\\", "/")).name.lower()


def is_style_conditioning_source(source: str | None) -> bool:
    filename = _source_filename(source)
    return filename in {"style_conditioning_bank", "style_conditioning_bank.json"}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict, set, tuple)) and not value:
        return False
    return True


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalized_value(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    normalized_text = text.replace('-', ' ').replace('_', ' ')
    if terms not in _PATTERN_CACHE:
        normalized_terms = [term.replace('-', ' ').replace('_', ' ').casefold() for term in terms]
        union_pattern = '|'.join(re.escape(term) for term in normalized_terms)
        _PATTERN_CACHE[terms] = re.compile(
            r'(?<![a-z0-9])(' + union_pattern + r')(?![a-z0-9])',
            re.IGNORECASE,
        )
    return bool(_PATTERN_CACHE[terms].search(normalized_text))


def _joined_note_text(entry: dict[str, Any]) -> str:
    values: list[str] = []
    for field in NOTE_FIELDS:
        value = entry.get(field)
        if isinstance(value, (list, tuple, set)):
            values.extend(str(part) for part in value if _has_value(part))
        elif _has_value(value):
            values.append(str(value))
    return " ".join(values)


def _has_dose_metadata(entry: dict[str, Any]) -> bool:
    has_structure = any(_has_value(entry.get(field)) for field in LATE_DOSE_FIELDS)
    has_rpe = _number(entry.get("rpe")) is not None or _number(entry.get("rpe_max")) is not None
    return has_structure and has_rpe


def _phase_set(entry: dict[str, Any]) -> set[str]:
    phases = entry.get("phases")
    if not isinstance(phases, list):
        return set()
    return {str(phase).strip().upper() for phase in phases if str(phase).strip()}


def _has_clear_low_risk_dose(entry: dict[str, Any], *, max_rpe: float) -> bool:
    effective_rpe = max(
        [value for value in (_number(entry.get("rpe")), _number(entry.get("rpe_max"))) if value is not None],
        default=None,
    )
    return bool(
        effective_rpe is not None
        and effective_rpe <= max_rpe
        and _normalized_value(entry.get("lactate_load")) == "low"
        and _normalized_value(entry.get("movement_cost")) == "low"
        and _normalized_value(entry.get("impact_cost")) == "low"
        and _has_dose_metadata(entry)
    )


def _has_support_focus(entry: dict[str, Any]) -> bool:
    tags = " ".join(str(tag).lower() for tag in entry.get("tags") or [])
    text = _joined_note_text(entry).lower()
    name = str(entry.get("name") or "").lower()
    combined = f"{tags} {text} {name}"
    support_terms = (
        "breathing",
        "cognitive",
        "cue",
        "readiness",
        "recovery",
        "tactical",
        "visualization",
    )
    return any(term in combined for term in support_terms) or _normalized_value(entry.get("system")) in {
        "cognitive",
        "recovery",
    }


def _has_technical_focus(entry: dict[str, Any]) -> bool:
    raw_tags = entry.get('tags')
    tags_list = raw_tags if isinstance(raw_tags, (list, tuple, set)) else []
    tags = ' '.join(str(tag).lower() for tag in tags_list)
    text = _joined_note_text(entry).lower()
    name = str(entry.get('name') or '').lower()
    combined = f'{tags} {text} {name}'
    return any(term in combined for term in ("technical", "rhythm", "skill", "cue", "precision", "flow"))


def _has_d1_risky_modality(entry: dict[str, Any]) -> bool:
    equipment = " ".join(str(value).lower() for value in (entry.get("equipment") or []))
    text = f"{equipment} {_joined_note_text(entry).lower()} {str(entry.get('modality') or '').lower()}"
    return any(term in text for term in ("band", "ballistic", "isometric", "med ball", "medicine ball", "loaded"))


def _resolved_system(system_raw: Any) -> str:
    from .bank_schema import SYSTEM_ALIASES

    raw = str(system_raw or "").strip().lower()
    resolved = SYSTEM_ALIASES.get(raw, raw)
    return resolved.replace("-", "_").replace(" ", "_")


def _dose_risk_reason_codes(entry: dict[str, Any], reason_codes: list[str]) -> set[str]:
    reason_set = set(reason_codes)
    dose_reasons = set(reason_set & HIGH_DOSE_REASONS)
    phases = _phase_set(entry)
    system = _resolved_system(entry.get("system"))
    if "high_lactate_load" in dose_reasons and "high_rpe" not in reason_set and "high_intensity" not in reason_set:
        if "SPP" in phases and system in {"glycolytic", "alactic"}:
            dose_reasons.remove("high_lactate_load")
    if "high_movement_cost" in dose_reasons and "high_rpe" not in reason_set and "high_intensity" not in reason_set:
        if "SPP" in phases and system in {"glycolytic", "alactic"}:
            dose_reasons.remove("high_movement_cost")
    return dose_reasons
    reason_set = set(reason_codes)
    dose_reasons = set(reason_set & HIGH_DOSE_REASONS)
    phases = _phase_set(entry)
    system = _normalized_value(entry.get("system"))
    if "high_lactate_load" in dose_reasons and "high_rpe" not in reason_set and "high_intensity" not in reason_set:
        if "SPP" in phases and system in {"glycolytic", "atp_pcr", "alactic"}:
            dose_reasons.remove("high_lactate_load")
    if "high_movement_cost" in dose_reasons and "high_rpe" not in reason_set and "high_intensity" not in reason_set:
        if "SPP" in phases and system in {"glycolytic", "atp_pcr", "alactic"}:
            dose_reasons.remove("high_movement_cost")
    return dose_reasons


def _camp_action(
    entry: dict[str, Any],
    reason_codes: list[str],
    *,
    overstyled_name: bool,
    aggressive_notes: bool,
    destructive_wording: bool,
) -> str:
    reason_set = set(reason_codes)
    dose_reasons = _dose_risk_reason_codes(entry, reason_codes)
    missing_dose = "missing_dose_metadata" in reason_set
    if destructive_wording and (dose_reasons or missing_dose or aggressive_notes):
        return "delete_or_rebuild"
    if aggressive_notes and (dose_reasons or missing_dose):
        return "delete_or_rebuild"
    if aggressive_notes or "manual_review_required" in reason_set:
        return "manual_review"
    if overstyled_name and dose_reasons:
        return "rename_and_redose"
    if overstyled_name:
        return "rename"
    if dose_reasons:
        return "redose"
    if missing_dose:
        return "manual_review"
    return "keep"


def _late_fight_action(
    entry: dict[str, Any],
    reason_codes: list[str],
    *,
    overstyled_name: bool,
    aggressive_notes: bool,
    destructive_wording: bool,
) -> str:
    reason_set = set(reason_codes)
    hard_blocks = reason_set & {
        "explicit_late_fight_quarantine",
        "manual_review_required",
        "high_rpe",
        "high_intensity",
        "high_lactate_load",
        "high_movement_cost",
        "high_impact_cost",
        "missing_dose_metadata",
    }
    if hard_blocks or overstyled_name or aggressive_notes or destructive_wording:
        return "late_blocked"
    if "missing_late_windows" in reason_set:
        return "not_late_eligible"
    if _has_support_focus(entry) and _has_clear_low_risk_dose(entry, max_rpe=4) and not _has_d1_risky_modality(entry):
        return "late_support_candidate"
    if _has_technical_focus(entry) and _has_clear_low_risk_dose(entry, max_rpe=5):
        return "late_technical_candidate"
    if _has_clear_low_risk_dose(entry, max_rpe=6) and _normalized_value(entry.get("system")) != "glycolytic":
        return "late_conditioning_candidate"
    return "late_blocked"


def style_conditioning_quarantine_reason_codes(
    entry: dict[str, Any],
    *,
    source: str | None = "style_conditioning_bank.json",
) -> list[str]:
    reason_codes: list[str] = []

    def add(code: str) -> None:
        if code not in reason_codes:
            reason_codes.append(code)

    if entry.get("late_fight_quarantined") is True:
        add("explicit_late_fight_quarantine")
    if entry.get("manual_review_required") is True:
        add("manual_review_required")
    raw_q_codes = entry.get('quarantine_reason_codes')
    q_codes_list = raw_q_codes if isinstance(raw_q_codes, (list, tuple, set)) else []
    for code in q_codes_list:
        cleaned = str(code).strip().lower().replace(' ', '_')
        if cleaned:
            add(cleaned)

    if not is_style_conditioning_source(source):
        return reason_codes

    effective_rpe = max(
        [value for value in (_number(entry.get("rpe")), _number(entry.get("rpe_max"))) if value is not None],
        default=None,
    )
    if effective_rpe is not None and effective_rpe >= 8:
        add("high_rpe")

    if _normalized_value(entry.get("intensity")) in HIGH_INTENSITY_VALUES:
        add("high_intensity")
    if _normalized_value(entry.get("lactate_load")) == "high":
        add("high_lactate_load")
    if _normalized_value(entry.get("movement_cost")) == "high":
        add("high_movement_cost")
    if _normalized_value(entry.get("impact_cost")) == "high":
        add("high_impact_cost")

    late_windows = entry.get("late_windows")
    if not isinstance(late_windows, list) or not late_windows:
        add("missing_late_windows")

    if not _has_dose_metadata(entry):
        add("missing_dose_metadata")

    if _contains_term(str(entry.get("name") or ""), OVERSTYLED_NAME_TERMS):
        add("overstyled_name")
    if _contains_term(f"{entry.get('name') or ''} {_joined_note_text(entry)}", DESTRUCTIVE_WORDING_TERMS):
        add("violent_wording")
    if _contains_term(_joined_note_text(entry), AGGRESSIVE_TEXT_TERMS):
        add("aggressive_notes")

    return reason_codes


def classify_style_conditioning_entry(entry: dict[str, Any]) -> dict[str, Any]:
    reason_codes = style_conditioning_quarantine_reason_codes(entry, source="style_conditioning_bank.json")
    overstyled_name = "overstyled_name" in reason_codes
    aggressive_notes = "aggressive_notes" in reason_codes
    destructive_wording = "violent_wording" in reason_codes
    dose_risk = bool(_dose_risk_reason_codes(entry, reason_codes))
    late_fight_risk = bool(reason_codes)
    return {
        "overstyled_name_flag": overstyled_name,
        "aggressive_notes_flag": aggressive_notes,
        "dose_risk_flag": dose_risk,
        "late_fight_risk_flag": late_fight_risk,
        "camp_action": _camp_action(
            entry,
            reason_codes,
            overstyled_name=overstyled_name,
            aggressive_notes=aggressive_notes,
            destructive_wording=destructive_wording,
        ),
        "late_fight_action": _late_fight_action(
            entry,
            reason_codes,
            overstyled_name=overstyled_name,
            aggressive_notes=aggressive_notes,
            destructive_wording=destructive_wording,
        ),
        "quarantine_reason_codes": reason_codes,
        "manual_notes": "",
    }
