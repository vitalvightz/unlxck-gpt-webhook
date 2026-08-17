"""Health-data boundary for plan generation without health consent."""
from __future__ import annotations

from typing import Any

from .compliance_guards import HEALTH_ATHLETE_FIELDS, HEALTH_INTAKE_FIELDS

NON_HEALTH_GENERATION_MODE_KEY = "_generation_health_mode"
NON_HEALTH_GENERATION_MODE = "withheld"

_HEALTH_PLANNER_LABELS = frozenset({
    "Weight (kg)",
    "Target Weight (kg)",
    "Fatigue Level",
    "Any injuries or areas you need to work around?",
})


def _is_provided(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def health_generation_fields(payload: dict[str, Any]) -> list[str]:
    """Return health fields carrying a value, including nested athlete fields."""
    present = [key for key in HEALTH_INTAKE_FIELDS if _is_provided(payload.get(key))]
    athlete = payload.get("athlete")
    if isinstance(athlete, dict):
        present.extend(
            f"athlete.{key}"
            for key in HEALTH_ATHLETE_FIELDS
            if _is_provided(athlete.get(key))
        )
    return sorted(present)


def build_non_health_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip empty/default health keys and mark a request as non-health only.

    Callers must reject a request when :func:`health_generation_fields` is not
    empty before using this helper. The second check makes accidental direct
    use fail closed.
    """
    surviving = health_generation_fields(payload)
    if surviving:
        raise ValueError(f"health fields cannot enter non-health generation: {', '.join(surviving)}")
    cleaned = {key: value for key, value in payload.items() if key not in HEALTH_INTAKE_FIELDS}
    athlete = cleaned.get("athlete")
    if isinstance(athlete, dict):
        cleaned["athlete"] = {
            key: value for key, value in athlete.items() if key not in HEALTH_ATHLETE_FIELDS
        }
    cleaned[NON_HEALTH_GENERATION_MODE_KEY] = NON_HEALTH_GENERATION_MODE
    return cleaned


def non_health_planner_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove health schema entries rather than inventing neutral self-reports."""
    cleaned = dict(payload)
    cleaned.pop("guided_injury", None)
    cleaned.pop("guided_injuries", None)
    data = cleaned.get("data")
    if isinstance(data, dict):
        safe_data = dict(data)
        fields = safe_data.get("fields")
        if isinstance(fields, list):
            safe_data["fields"] = [
                field
                for field in fields
                if not isinstance(field, dict) or field.get("label") not in _HEALTH_PLANNER_LABELS
            ]
        cleaned["data"] = safe_data
    return cleaned
