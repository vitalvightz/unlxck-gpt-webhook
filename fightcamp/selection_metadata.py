"""Shared metadata and score evidence helpers for exercise selection payloads."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


COST_DEFAULT = "moderate"

SELECTION_METADATA_DEFAULTS: dict[str, Any] = {
    "primary_adaptation": "unknown",
    "secondary_adaptations": [],
    "tissue_targets": [],
    "movement_cost": COST_DEFAULT,
    "impact_cost": COST_DEFAULT,
    "eccentric_cost": COST_DEFAULT,
    "landing_cost": COST_DEFAULT,
    "contact_cost": COST_DEFAULT,
    "lactate_load": COST_DEFAULT,
    "cns_load": COST_DEFAULT,
    "soreness_risk": COST_DEFAULT,
    "movement_complexity": COST_DEFAULT,
    "late_windows": [],
    "cut_buckets_allowed": [],
    "contraindication_tags": [],
    "restriction_tags": [],
    "mechanical_risk_tags": [],
    "min_training_age": "unknown",
    "work_sec": None,
    "rest_sec": None,
    "rounds": None,
    "total_minutes": None,
    "rpe": None,
}

LIST_METADATA_FIELDS = {
    "secondary_adaptations",
    "tissue_targets",
    "late_windows",
    "cut_buckets_allowed",
    "contraindication_tags",
    "restriction_tags",
    "mechanical_risk_tags",
}

SCALAR_METADATA_FIELDS = set(SELECTION_METADATA_DEFAULTS) - LIST_METADATA_FIELDS

BOOLEAN_METADATA_FIELDS = {
    "anchor_capable",
    "ballistic_low_volume",
    "cns_freshness",
    "generic_fallback",
    "low_eccentric",
    "low_impact",
    "low_soreness",
    "meaningful_stress",
    "neural_primer",
    "sport_specific",
    "support_only",
}

SCORE_EVIDENCE_DEFAULTS: dict[str, Any] = {
    "score": 0.0,
    "reason_codes": [],
    "penalties": 0,
    "restriction_hits": 0,
    "late_window_adjustment": 0,
}


def _clean_string(value: Any) -> str:
    return str(value).strip()


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        cleaned = [_clean_string(item) for item in value if _clean_string(item)]
    else:
        cleaned = [_clean_string(value)] if _clean_string(value) else []
    seen: set[str] = set()
    result: list[str] = []
    for item in cleaned:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _number_or_default(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return int(parsed) if parsed.is_integer() else parsed


def normalize_selection_metadata(item: dict | None) -> dict[str, Any]:
    """Return explicit item metadata with conservative defaults for unknown fields."""
    item = item or {}
    metadata = deepcopy(SELECTION_METADATA_DEFAULTS)

    for field in LIST_METADATA_FIELDS:
        metadata[field] = _clean_list(item.get(field, metadata[field]))

    for field in SCALAR_METADATA_FIELDS:
        default = metadata[field]
        value = item.get(field, default)
        if field in {"work_sec", "rest_sec", "rounds", "total_minutes", "rpe"}:
            metadata[field] = _number_or_default(value, default)
        elif value is None or value == "":
            metadata[field] = default
        else:
            metadata[field] = value

    for field in BOOLEAN_METADATA_FIELDS:
        if field in item:
            metadata[field] = bool(item.get(field))

    return metadata


def build_score_evidence(
    *,
    score: Any = None,
    reasons: dict | None = None,
    explanation: str | None = None,
    score_evidence: dict | None = None,
) -> dict[str, Any]:
    """Normalize selector scoring output for Stage 2 payload consumers."""
    reasons = reasons or {}
    provided_evidence = score_evidence or {}
    evidence = deepcopy(SCORE_EVIDENCE_DEFAULTS)
    evidence.update(provided_evidence)

    score_value = score if score is not None else reasons.get("final_score", evidence["score"])
    evidence["score"] = _number_or_default(score_value, SCORE_EVIDENCE_DEFAULTS["score"])
    evidence["reason_codes"] = _clean_list(
        provided_evidence.get("reason_codes") or reasons.get("reason_codes") or []
    )
    penalties = provided_evidence.get("penalties") if "penalties" in provided_evidence else reasons.get("penalties")
    evidence["penalties"] = _number_or_default(
        penalties,
        SCORE_EVIDENCE_DEFAULTS["penalties"],
    )
    restriction_hits = (
        provided_evidence.get("restriction_hits")
        if "restriction_hits" in provided_evidence
        else reasons.get("restriction_hits")
    )
    evidence["restriction_hits"] = _number_or_default(
        restriction_hits,
        SCORE_EVIDENCE_DEFAULTS["restriction_hits"],
    )
    late_window_adjustment = (
        provided_evidence.get("late_window_adjustment")
        if "late_window_adjustment" in provided_evidence
        else reasons.get("late_window_adjustment")
    )
    evidence["late_window_adjustment"] = _number_or_default(
        late_window_adjustment,
        SCORE_EVIDENCE_DEFAULTS["late_window_adjustment"],
    )

    for key in (
        "goal_hits",
        "weakness_hits",
        "style_hits",
        "phase_hits",
        "load_adjustments",
        "equipment_boost",
        "boxing_aerobic_preference",
        "deterministic_scoring",
    ):
        if key in reasons and key not in evidence:
            evidence[key] = reasons[key]

    if explanation:
        evidence["explanation"] = explanation

    return evidence
