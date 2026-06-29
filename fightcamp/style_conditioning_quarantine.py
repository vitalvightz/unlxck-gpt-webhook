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
    "late_fight_risk_flag",
    "recommended_action",
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
    "killer",
    "obliterate",
    "punisher",
    "savage",
    "spartan",
    "terminator",
    "warrior",
)
AGGRESSIVE_TEXT_TERMS = (
    "all-out war",
    "bloodbath",
    "break them",
    "cinematic",
    "destroy",
    "fight to the death",
    "kill",
    "movie scene",
    "no mercy",
    "obliterate",
    "punish",
    "savage",
    "street fight",
    "violent",
)

HIGH_DOSE_REASONS = {
    "high_rpe",
    "high_intensity",
    "high_lactate_load",
    "high_movement_cost",
}


def _source_filename(source: str | None) -> str:
    return Path(str(source or "").replace("\\", "/")).name.lower()


def is_style_conditioning_source(source: str | None) -> bool:
    filename = _source_filename(source)
    return filename in {"style_conditioning_bank", "style_conditioning_bank.json"}


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


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
    return str(value or "").strip().lower().replace("-", "_")


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term.casefold()) + r"(?![a-z0-9])"
        if re.search(pattern, normalized):
            return True
    return False


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


def _recommended_action(reason_codes: list[str], *, overstyled_name: bool, aggressive_notes: bool) -> str:
    reason_set = set(reason_codes)
    if aggressive_notes and reason_set & HIGH_DOSE_REASONS:
        return "delete_candidate"
    if aggressive_notes:
        return "manual_review"
    if overstyled_name:
        return "rename"
    if reason_set & HIGH_DOSE_REASONS:
        return "redose"
    if reason_set:
        return "quarantine_from_late_fight"
    return "keep"


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
    for code in entry.get("quarantine_reason_codes") or []:
        cleaned = str(code).strip().lower().replace(" ", "_")
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

    late_windows = entry.get("late_windows")
    if not isinstance(late_windows, list) or not late_windows:
        add("missing_late_windows")

    if not _has_dose_metadata(entry):
        add("missing_dose_metadata")

    if _contains_term(str(entry.get("name") or ""), OVERSTYLED_NAME_TERMS):
        add("overstyled_name")
    if _contains_term(_joined_note_text(entry), AGGRESSIVE_TEXT_TERMS):
        add("aggressive_notes")

    return reason_codes


def classify_style_conditioning_entry(entry: dict[str, Any]) -> dict[str, Any]:
    reason_codes = style_conditioning_quarantine_reason_codes(entry, source="style_conditioning_bank.json")
    overstyled_name = "overstyled_name" in reason_codes
    aggressive_notes = "aggressive_notes" in reason_codes
    late_fight_risk = bool(reason_codes)
    return {
        "overstyled_name_flag": overstyled_name,
        "aggressive_notes_flag": aggressive_notes,
        "late_fight_risk_flag": late_fight_risk,
        "recommended_action": _recommended_action(
            reason_codes,
            overstyled_name=overstyled_name,
            aggressive_notes=aggressive_notes,
        ),
        "quarantine_reason_codes": reason_codes,
    }
