from __future__ import annotations

from typing import Any

D21_TO_D14 = "d21_to_d14"
D13_TO_D8 = "d13_to_d8"
D7 = "d7"
D6_TO_D5 = "d6_to_d5"
D4_TO_D2 = "d4_to_d2"
D1 = "d1"

STYLE_TAPER_WINDOWS = {D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1}
ALL_LATE_WINDOWS = {D21_TO_D14, *STYLE_TAPER_WINDOWS}

SPORT_TAGS = {
    "boxing",
    "kickboxing",
    "muay_thai",
    "mma",
    "bjj",
    "wrestling",
    "grappling",
}
STYLE_TAGS = {
    "brawler",
    "pressure_fighter",
    "clinch_fighter",
    "counter_striker",
    "distance_striker",
    "submission_hunter",
    "kicker",
    "scrambler",
    "grappler",
    "wrestler",
}

TACTICAL_REACTION_TAGS = {
    "reaction",
    "reactive_decision",
    "visual_reactive",
    "visual_processing",
}
MECHANICAL_REACTION_TAGS = {"mech_reactive", "mech_reactive_rebound"}
GENERIC_REACTIVE_TAG = "reactive"

ALLOWED_CONTACT_BY_WINDOW = {
    D13_TO_D8: {"none", "touch", "cooperative", "controlled"},
    D7: {"none", "touch", "cooperative"},
    D6_TO_D5: {"none", "touch", "cooperative"},
    D4_TO_D2: {"none", "touch"},
    D1: {"none"},
}
RPE_MAX_BY_WINDOW = {
    D13_TO_D8: 6.0,
    D7: 5.0,
    D6_TO_D5: 5.0,
    D4_TO_D2: 4.0,
    D1: 3.0,
}
ALLOWED_EXECUTION_INTENTS = {
    "relaxed",
    "technical_crisp",
    "competition_rhythm",
    "fast_crisp",
}
D1_ALLOWED_EQUIPMENT = {
    "bodyweight",
    "none",
    "mat",
    "mats",
    "mat_space",
    "open_space",
    "floor",
}


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _tokens(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw = value
    elif value in (None, ""):
        raw = []
    else:
        raw = [value]
    return list(dict.fromkeys(token for token in (_token(item) for item in raw) if token))


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def style_taper_entry_window_eligible(entry: dict[str, Any], window: str) -> bool:
    """Return whether a style-taper entry explicitly declares the requested D-day window."""
    resolved = _token(window)
    return resolved in set(_tokens(entry.get("late_windows")))


def style_taper_entry_issues(entry: dict[str, Any]) -> list[str]:
    """Validate Style Taper Bank 2.0 semantics without changing shared bank-schema behavior."""
    issues: list[str] = []

    def add(code: str) -> None:
        if code not in issues:
            issues.append(code)

    tags = set(_tokens(entry.get("tags")))
    late_windows = _tokens(entry.get("late_windows"))
    contact = _token(entry.get("contact_level"))
    execution_intent = _token(entry.get("execution_intent"))
    system = _token(entry.get("system"))
    equipment = set(_tokens(entry.get("equipment")))
    rpe_max = _number(entry.get("rpe_max"))

    if not str(entry.get("name") or "").strip():
        add("missing_name")
    if not tags:
        add("missing_tags")
    if not tags.intersection(SPORT_TAGS):
        add("missing_canonical_sport")
    if not tags.intersection(STYLE_TAGS):
        add("missing_canonical_style")
    if GENERIC_REACTIVE_TAG in tags:
        add("generic_reactive_tag")

    if not late_windows:
        add("missing_late_windows")
    if D21_TO_D14 in late_windows:
        add("style_taper_starts_too_early")
    for window in late_windows:
        if window not in STYLE_TAPER_WINDOWS:
            add("unknown_style_taper_window")

    if system not in {"alactic", "aerobic"}:
        add("invalid_style_taper_system")
    if rpe_max is None:
        add("missing_rpe_max")

    if not execution_intent:
        add("missing_execution_intent")
    elif execution_intent not in ALLOWED_EXECUTION_INTENTS:
        add("invalid_execution_intent")

    if not contact:
        add("missing_contact_level")
    elif contact == "live":
        add("live_contact_forbidden")
    elif contact not in {"none", "touch", "cooperative", "controlled"}:
        add("unknown_contact_level")

    if entry.get("support_only") is not True:
        add("style_taper_must_be_support_only")
    if entry.get("meaningful_stress") is not False:
        add("style_taper_must_not_claim_meaningful_stress")
    if _token(entry.get("stress_class")) != "support":
        add("invalid_stress_class")
    if _token(entry.get("cost_class")) != "low":
        add("invalid_cost_class")
    if _token(entry.get("lactate_load")) not in {"none", "low"}:
        add("excess_lactate_load")
    if _token(entry.get("impact_cost")) not in {"none", "low"}:
        add("excess_impact_cost")
    if _token(entry.get("movement_cost")) not in {"none", "low"}:
        add("excess_movement_cost")

    for window in late_windows:
        if window not in STYLE_TAPER_WINDOWS:
            continue
        allowed_contact = ALLOWED_CONTACT_BY_WINDOW[window]
        if contact and contact not in allowed_contact:
            add(f"contact_too_high:{window}")
        if rpe_max is not None and rpe_max > RPE_MAX_BY_WINDOW[window]:
            add(f"rpe_too_high:{window}")

    if D1 in late_windows:
        if contact != "none":
            add("d1_contact_forbidden")
        if equipment - D1_ALLOWED_EQUIPMENT:
            add("d1_equipment_forbidden")

    return issues


def assert_style_taper_entry(entry: dict[str, Any]) -> None:
    issues = style_taper_entry_issues(entry)
    if issues:
        name = str(entry.get("name") or "<unnamed>")
        raise ValueError(f"Unsafe style taper entry '{name}': {issues}")
