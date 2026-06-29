import logging
import re
from typing import Any, Literal

from .phases import PHASE_VALUES

ValidationMode = Literal["audit", "strict", "runtime"]
SourceKind = Literal["strength", "conditioning", "generic"]

SYSTEM_ALIASES = {
    "atp-pcr": "alactic",
    "anaerobic_alactic": "alactic",
    "cognitive": "alactic",
    "hypertrophy": "glycolytic",
    "parasympathetic": "aerobic",
    "recovery": "aerobic",
    "skill": "aerobic",
}

KNOWN_SYSTEMS = {"aerobic", "glycolytic", "alactic"}
SUPPORT_ONLY_SYSTEM_ALIASES = {"skill", "cognitive", "recovery", "parasympathetic"}

D21_TO_D14 = "d21_to_d14"
D13_TO_D8 = "d13_to_d8"
D7 = "d7"
D6_TO_D5 = "d6_to_d5"
D4_TO_D2 = "d4_to_d2"
D1 = "d1"
ACTIVE_LATE_WINDOWS = {D21_TO_D14, D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1}
D13_AND_UNDER_WINDOWS = {D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1}
D7_AND_UNDER_WINDOWS = {D7, D6_TO_D5, D4_TO_D2, D1}

DEFAULT_PHASES = list(PHASE_VALUES)
_SCHEMA_WARNINGS_LOGGED: set[tuple[str, str, str]] = set()
_SCHEMA_ISSUES_KEY = "_schema_issues"
_SCHEMA_SAFETY_KEY = "_schema_safety"
_SCHEMA_SOURCE_KEY = "_schema_source"

STRENGTH_BANK_SOURCES = {
    "exercise_bank.json",
    "universal_gpp_strength.json",
}
CONDITIONING_BANK_SOURCES = {
    "conditioning_bank.json",
    "coordination_bank.json",
    "footwork_conditioning_bank.json",
    "style_conditioning_bank.json",
    "style_taper_conditioning.json",
    "universal_gpp_conditioning.json",
}

COMMON_LATE_METADATA_FIELDS = (
    "late_windows",
    "impact_cost",
    "movement_cost",
    "stress_class",
    "cost_class",
    "support_only",
    "meaningful_stress",
)
STRENGTH_LATE_METADATA_FIELDS = (
    "cns_load",
    "soreness_risk",
    "eccentric_cost",
    "landing_cost",
)
CONDITIONING_LATE_METADATA_FIELDS = ("lactate_load",)
CONDITIONING_RPE_FIELDS = ("rpe", "rpe_max")
GOVERNANCE_METADATA_ISSUES = {
    "missing_stress_class",
    "missing_cost_class",
    "missing_support_only",
    "missing_meaningful_stress",
}
COST_METADATA_ISSUES = {
    "missing_impact_cost",
    "missing_movement_cost",
    "missing_cns_load",
    "missing_soreness_risk",
    "missing_eccentric_cost",
    "missing_landing_cost",
    "missing_lactate_load",
}

HIGH_LEVELS = {"high", "very_high", "max"}
LOADED_EQUIPMENT = {
    "barbell",
    "trap_bar",
    "dumbbell",
    "dumbbells",
    "kettlebell",
    "kettlebells",
    "sandbag",
    "sled",
    "weight_vest",
    "plate",
    "cable",
    "landmine",
}
MED_BALL_EQUIPMENT = {"medicine_ball", "med_ball", "slam_ball"}
BALLISTIC_TAGS = {"ballistic", "explosive", "mech_ballistic", "plyometric", "reactive"}
PRIMER_ONLY_TAGS = {"neural_primer", "cns_freshness", "support_accessory"}
STRENGTH_FULFILLMENT_TAGS = {
    "real_strength_maintenance",
    "maximal_strength_maintenance",
    "late_strength_touch",
}

_EXERCISE_SCHEMA_DEFAULTS = {
    "late_windows": [],
    "impact_cost": "",
    "movement_cost": "",
    "cns_load": "",
    "eccentric_cost": "",
    "landing_cost": "",
    "soreness_risk": "",
    "phase_role": "",
    "sport_specific": False,
}

_CONDITIONING_SCHEMA_DEFAULTS = {
    "late_windows": [],
    "work_sec": None,
    "rest_sec": None,
    "rounds": None,
    "total_minutes": None,
    "rpe": None,
    "impact_cost": "",
    "lactate_load": "",
    "movement_cost": "",
}

_STRENGTH_SCHEMA_DEFAULTS = {
    **_EXERCISE_SCHEMA_DEFAULTS,
    "stress_class": "",
    "cost_class": "",
    "support_only": None,
    "meaningful_stress": None,
}

_CONDITIONING_RUNTIME_DEFAULTS = {
    **_CONDITIONING_SCHEMA_DEFAULTS,
    "rpe_max": None,
    "stress_class": "",
    "cost_class": "",
    "support_only": None,
    "meaningful_stress": None,
}

logger = logging.getLogger(__name__)


def _warn_once(source: str, name: str, issue: str, message: str) -> None:
    key = (source, name, issue)
    if key in _SCHEMA_WARNINGS_LOGGED:
        return
    _SCHEMA_WARNINGS_LOGGED.add(key)
    logger.warning(message)


def _record_issue(item: dict, issue: str) -> None:
    issues = item.setdefault(_SCHEMA_ISSUES_KEY, [])
    if issue not in issues:
        issues.append(issue)


def _source_filename(source: str) -> str:
    return str(source or "").replace("\\", "/").split("/")[-1].lower()


def _source_kind(source: str) -> str:
    filename = _source_filename(source)
    if filename in STRENGTH_BANK_SOURCES:
        return "strength"
    if filename in CONDITIONING_BANK_SOURCES:
        return "conditioning"
    return "generic"


def _resolve_source_kind(source: str, source_kind: str | None = None) -> SourceKind:
    if source_kind is not None:
        normalized = str(source_kind).strip().lower()
        if normalized not in {"strength", "conditioning", "generic"}:
            raise ValueError(f"Unknown late-fight metadata source_kind: {source_kind!r}")
        return normalized  # type: ignore[return-value]
    return _source_kind(source)  # type: ignore[return-value]


def _schema_defaults_for_source(source: str) -> dict[str, Any]:
    kind = _source_kind(source)
    if kind == "strength":
        return _STRENGTH_SCHEMA_DEFAULTS
    if kind == "conditioning":
        return _CONDITIONING_RUNTIME_DEFAULTS
    return {}


def _clean_string(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_token(value: Any) -> str:
    return _clean_string(value).replace("-", "_").replace(" ", "_")


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value in (None, ""):
        values = []
    else:
        values = [value]
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        token = _normalize_token(item)
        if token and token not in seen:
            cleaned.append(token)
            seen.add(token)
    return cleaned


def _number_or_none(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _rpe_from_text(item: dict) -> float | None:
    text = _text_blob(item)
    for match in re.finditer(r"\brpe\s*(\d+(?:\.\d+)?)(?:\s*(?:-|\u2013|to)\s*(\d+(?:\.\d+)?))?", text):
        first = float(match.group(1))
        second = float(match.group(2)) if match.group(2) else first
        return max(first, second)
    return None


def _has_value(item: dict, field: str) -> bool:
    value = item.get(field)
    return value is not None and value != "" and value != []


def _boolean_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean_string(value) in {"true", "1", "yes", "y"}


def _late_window_for(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized if normalized in ACTIVE_LATE_WINDOWS else None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    if 14 <= days <= 21:
        return D21_TO_D14
    if 8 <= days <= 13:
        return D13_TO_D8
    if days == 7:
        return D7
    if 5 <= days <= 6:
        return D6_TO_D5
    if 2 <= days <= 4:
        return D4_TO_D2
    if 0 <= days <= 1:
        return D1
    return None


def _metadata_missing_issues(item: dict, *, source: str, source_kind: str | None = None) -> list[str]:
    kind = _resolve_source_kind(source, source_kind)
    if kind == "generic":
        return []

    issues: list[str] = []
    fields = list(COMMON_LATE_METADATA_FIELDS)
    if kind == "strength":
        fields.extend(STRENGTH_LATE_METADATA_FIELDS)
    elif kind == "conditioning":
        fields.extend(CONDITIONING_LATE_METADATA_FIELDS)

    for field in fields:
        if not _has_value(item, field):
            issue = "missing_late_windows" if field == "late_windows" else f"missing_{field}"
            issues.append(issue)

    if kind == "conditioning" and not any(_has_value(item, field) for field in CONDITIONING_RPE_FIELDS):
        issues.append("missing_rpe")

    return list(dict.fromkeys(issues))


def _system_state(item: dict) -> dict[str, Any]:
    raw = _clean_string(item.get("system"))
    normalized = SYSTEM_ALIASES.get(raw, raw)
    return {
        "raw": raw,
        "normalized": normalized,
        "is_alias": bool(raw and raw != normalized),
        "is_support_alias": raw in SUPPORT_ONLY_SYSTEM_ALIASES,
        "is_known": normalized in KNOWN_SYSTEMS,
    }


def _equipment_tokens(item: dict) -> set[str]:
    values: list[Any] = []
    for field in ("equipment", "equipment_required", "equipment_needed"):
        value = item.get(field)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value:
            values.extend(str(value).replace("/", " ").replace(",", " ").split())
    return set(_clean_list(values))


def _text_blob(item: dict) -> str:
    fields = (
        "name",
        "method",
        "movement",
        "modality",
        "load",
        "timing",
        "rest",
        "purpose",
        "notes",
        "description",
        "prescription",
    )
    return " ".join(str(item.get(field) or "") for field in fields).lower()


def _has_dense_glycolytic_profile(item: dict, *, normalized_system: str) -> bool:
    work_sec = _number_or_none(item.get("work_sec"))
    rest_sec = _number_or_none(item.get("rest_sec"))
    rounds = _number_or_none(item.get("rounds"))
    total_minutes = _number_or_none(item.get("total_minutes"))
    rpe = _number_or_none(item.get("rpe")) or _number_or_none(item.get("rpe_max"))
    lactate_load = _clean_string(item.get("lactate_load"))
    tags = set(_clean_list(item.get("tags")))
    text = _text_blob(item)
    structured_density = bool(
        lactate_load == "high"
        or (
            work_sec is not None
            and rest_sec is not None
            and rounds is not None
            and work_sec >= 45
            and rest_sec <= 90
            and rounds >= 3
        )
        or (
            total_minutes is not None
            and total_minutes >= 12
            and rpe is not None
            and rpe >= 7
        )
    )
    text_density = any(term in text for term in ("emom", "tabata", "amrap", "fight pace", "fight-pace"))
    return bool(normalized_system == "glycolytic" and (structured_density or text_density or "glycolytic" in tags))


def _has_d1_forbidden_modality(item: dict, *, source: str, source_kind: str | None = None) -> bool:
    kind = _resolve_source_kind(source, source_kind)
    tags = set(_clean_list(item.get("tags")))
    equipment = _equipment_tokens(item)
    text = _text_blob(item)
    method = _normalize_token(item.get("method"))
    loaded = bool(equipment & LOADED_EQUIPMENT) or any(term in text for term in ("barbell", "trap bar", "loaded"))
    isometric = "isometric" in tags or method == "isometric" or "isometric" in text or " iso" in f" {text}"
    med_ball = bool(equipment & MED_BALL_EQUIPMENT) or "med ball" in text or "medicine ball" in text
    bands = "bands" in equipment or "band" in equipment or "band" in text
    ballistic = bool(tags & BALLISTIC_TAGS) or any(term in text for term in ("ballistic", "explosive", "jump", "throw", "slam"))
    max_intent = "max_intent" in tags or "max intent" in text or "max-intent" in text
    high_rpe = (_number_or_none(item.get("rpe")) or _number_or_none(item.get("rpe_max")) or 0) >= 8
    loaded_physical = kind in {"strength", "conditioning"} and loaded
    return any((bands, med_ball, loaded_physical, isometric, ballistic, max_intent, high_rpe))


def _has_final_day_policy(item: dict) -> bool:
    tags = set(_clean_list(item.get("tags")))
    return bool(
        tags & {"d1_ok", "d1_if_familiar", "final_day_ok"}
        or _boolean_true(item.get("d1_ok"))
        or _boolean_true(item.get("final_day_ok"))
        or _boolean_true(item.get("final_day_policy"))
    )


def _effective_rpe(item: dict) -> float | None:
    rpe = _number_or_none(item.get("rpe"))
    rpe_max = _number_or_none(item.get("rpe_max"))
    effective = max([value for value in (rpe, rpe_max) if value is not None], default=None)
    return effective if effective is not None else _rpe_from_text(item)


def _claims_anchor_fulfillment(item: dict, *, source: str, source_kind: str | None = None) -> bool:
    kind = _resolve_source_kind(source, source_kind)
    tags = set(_clean_list(item.get("tags")))
    stress_class = _normalize_token(item.get("stress_class"))
    if kind == "strength":
        maintenance_tags = STRENGTH_FULFILLMENT_TAGS - {"late_strength_touch"}
        return bool(tags & maintenance_tags) or any(
            _boolean_true(item.get(field)) for field in maintenance_tags
        )
    if kind == "conditioning":
        return (
            stress_class in {"meaningful_stress", "anchor", "primary"}
            or item.get("support_only") is False
            or _boolean_true(item.get("conditioning_anchor"))
            or _boolean_true(item.get("meaningful_conditioning"))
        )
    return False


def _has_incomplete_governance(unsafe_metadata: set[str]) -> bool:
    return bool(unsafe_metadata & GOVERNANCE_METADATA_ISSUES)


def _has_physical_work_signal(item: dict, *, source: str, source_kind: str | None = None) -> bool:
    kind = _resolve_source_kind(source, source_kind)
    tags = set(_clean_list(item.get("tags")))
    equipment = _equipment_tokens(item)
    text = _text_blob(item)
    method = _normalize_token(item.get("method"))
    system_state = _system_state(item)
    physical_tags = {
        "conditioning",
        "strength",
        "power",
        "speed",
        "alactic",
        "aerobic",
        "glycolytic",
        "plyometric",
        "mech_ballistic",
        "ballistic",
        "explosive",
        "reactive",
        "loaded",
        "jump",
        "throw",
        "sprint",
        "work_capacity",
        "mobility",
        "movement",
        "footwork",
        "technical_rhythm",
    }
    physical_terms = (
        "round",
        "interval",
        "sprint",
        "shuttle",
        "jump",
        "throw",
        "slam",
        "loaded",
        "barbell",
        "trap bar",
        "med ball",
        "medicine ball",
        "band-resisted",
        "fight pace",
        "fight-pace",
    )
    return bool(
        kind in {"strength", "conditioning"}
        and system_state["normalized"] in KNOWN_SYSTEMS
        and not system_state["is_support_alias"]
    ) or bool(
        tags & physical_tags
        or equipment
        or method in {"isometric", "plyometric", "ballistic"}
        or any(term in text for term in physical_terms)
    )


def _has_high_intent_signal(item: dict) -> bool:
    tags = set(_clean_list(item.get("tags")))
    text = _text_blob(item)
    intensity = _clean_string(item.get("intensity"))
    return bool(
        intensity in HIGH_LEVELS
        or tags & (BALLISTIC_TAGS | {"max_intent", "high_intent", "high_cns", "plyometric", "power"})
        or any(
            term in text
            for term in (
                "max intent",
                "max-intent",
                "all-out",
                "all out",
                "explosive",
                "ballistic",
                "fight pace",
                "fight-pace",
                "sprint",
            )
        )
    )


def is_low_risk_support_candidate(
    item: dict,
    source: str,
    window: Any,
    *,
    source_kind: str | None = None,
) -> bool:
    """Return true for late-fight support inserts that are safe despite incomplete metadata."""
    kind = _resolve_source_kind(source, source_kind)
    resolved_window = _late_window_for(window)
    tags = set(_clean_list(item.get("tags")))
    equipment = _equipment_tokens(item)
    text = _text_blob(item)
    method = _normalize_token(item.get("method"))
    system_state = _system_state(item)
    effective_rpe = _effective_rpe(item)

    loaded = bool(equipment & LOADED_EQUIPMENT) or any(term in text for term in ("barbell", "trap bar", "loaded"))
    med_ball = bool(equipment & MED_BALL_EQUIPMENT) or "med ball" in text or "medicine ball" in text
    bands = "bands" in equipment or "band" in equipment or "band" in text
    isometric = "isometric" in tags or method == "isometric" or "isometric" in text or " iso" in f" {text}"
    ballistic = bool(tags & BALLISTIC_TAGS) or any(term in text for term in ("ballistic", "explosive", "jump", "throw", "slam"))
    glycolytic = system_state["normalized"] == "glycolytic" or "glycolytic" in tags
    fight_pace = any(term in text for term in ("fight pace", "fight-pace", "emom", "tabata", "amrap"))

    if _claims_anchor_fulfillment(item, source=source, source_kind=kind):
        return False
    if loaded or med_ball or ballistic or glycolytic or fight_pace or _has_high_intent_signal(item):
        return False
    if resolved_window == D1 and (bands or isometric):
        return False
    if effective_rpe is not None and effective_rpe >= 7:
        return False

    non_physical_support_tags = {
        "tactical",
        "strategy",
        "cue_card",
        "cue_cards",
        "breathing",
        "reset",
        "sleep",
        "sleep_downshift",
        "visualization",
        "self_review",
        "review",
        "readiness",
        "readiness_check",
        "wound_check",
        "recovery",
        "parasympathetic",
        "cognitive",
        "skill",
    }
    non_physical_terms = (
        "watch",
        "cue card",
        "cue-card",
        "tactical",
        "breathing",
        "breath",
        "sleep downshift",
        "sleep",
        "visualization",
        "visualisation",
        "self-review",
        "self review",
        "readiness check",
        "wound",
        "reset",
    )
    if tags & non_physical_support_tags or any(term in text for term in non_physical_terms):
        if resolved_window == D1:
            return True
        return True

    light_mobility = bool(tags & {"mobility", "recovery", "low_impact", "cns_freshness", "skill_refinement"}) or any(
        term in text for term in ("mobility", "easy reset", "light reset", "walkthrough", "walk-through")
    )
    low_equipment = not equipment or equipment <= {"bodyweight", "none", "mat"}
    easy_text = any(term in text for term in ("easy", "light", "gentle", "low intensity", "low-intensity", "nasal"))
    low_rpe = effective_rpe is not None and effective_rpe <= 4
    technical_rhythm = bool(tags & {"technical_rhythm", "skill_refinement", "coordination"}) or any(
        term in text for term in ("technical rhythm", "light rhythm", "easy rhythm")
    )

    if resolved_window == D1:
        return False
    if low_equipment and light_mobility and (low_rpe or easy_text):
        return True
    if low_equipment and technical_rhythm and (low_rpe or easy_text):
        return True

    return kind == "generic" and low_equipment and (low_rpe or easy_text)


def _primer_only_fulfillment_block(item: dict, *, source: str, source_kind: str | None = None) -> bool:
    if _resolve_source_kind(source, source_kind) != "strength":
        return False
    tags = set(_clean_list(item.get("tags")))
    has_primer_signal = _boolean_true(item.get("primer_only")) or bool(tags & PRIMER_ONLY_TAGS)
    maintenance_tags = STRENGTH_FULFILLMENT_TAGS - {"late_strength_touch"}
    claims_fulfillment = bool(tags & maintenance_tags) or any(
        _boolean_true(item.get(field)) for field in maintenance_tags
    )
    if not has_primer_signal or not claims_fulfillment:
        return False
    return not _boolean_true(item.get("real_strength_maintenance"))


def _support_only_fulfillment_block(item: dict, *, source: str, source_kind: str | None = None) -> bool:
    kind = _resolve_source_kind(source, source_kind)
    if not _claims_anchor_fulfillment(item, source=source, source_kind=kind):
        return False
    governance_complete = all(_has_value(item, field) for field in ("stress_class", "cost_class", "support_only", "meaningful_stress"))
    meaningful_declared = item.get("meaningful_stress") is True
    anchor_safe = governance_complete and item.get("support_only") is False and meaningful_declared
    return not anchor_safe


def _append_code(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def is_late_fight_metadata_safe(
    item: dict,
    source: str,
    countdown_offset_or_window: Any,
    *,
    source_kind: str | None = None,
) -> dict[str, Any]:
    """Return late-fight metadata safety state for selectors and runtime loaders."""
    kind = _resolve_source_kind(source, source_kind)
    window = _late_window_for(countdown_offset_or_window)
    existing_issues = set(item.get(_SCHEMA_ISSUES_KEY) or [])
    unsafe_metadata = set(existing_issues)
    unsafe_metadata.update(_metadata_missing_issues(item, source=source, source_kind=kind))

    block_codes: list[str] = []
    penalty_codes: list[str] = []
    reason_codes: list[str] = []

    if window is None:
        return {
            "safe": True,
            "severity": "safe",
            "block_codes": [],
            "reason_codes": [],
            "penalty_codes": [],
            "unsafe_metadata": sorted(unsafe_metadata),
        }

    claims_anchor = _claims_anchor_fulfillment(item, source=source, source_kind=kind)
    low_risk_support = is_low_risk_support_candidate(item, source, window, source_kind=kind)
    physical_work = _has_physical_work_signal(item, source=source, source_kind=kind)
    system_state = _system_state(item)
    text = _text_blob(item)
    tags = set(_clean_list(item.get("tags")))
    fight_pace_or_glycolytic = bool(
        system_state["normalized"] == "glycolytic"
        or "glycolytic" in tags
        or any(term in text for term in ("fight pace", "fight-pace", "emom", "tabata", "amrap"))
        or _has_dense_glycolytic_profile(item, normalized_system=system_state["normalized"])
    )

    if unsafe_metadata & {"missing_name", "missing_tags", "missing_phases"}:
        _append_code(block_codes, "late_block_missing_metadata")
    if "missing_late_windows" in unsafe_metadata:
        _append_code(block_codes, "late_block_missing_late_windows")

    missing_cost = unsafe_metadata & COST_METADATA_ISSUES
    missing_governance = unsafe_metadata & GOVERNANCE_METADATA_ISSUES
    if missing_cost:
        cost_blocks = False
        if window == D21_TO_D14:
            cost_blocks = claims_anchor or not low_risk_support
        elif window == D13_TO_D8:
            cost_blocks = claims_anchor or physical_work or _has_high_intent_signal(item)
        elif window in {D7, D6_TO_D5, D4_TO_D2, D1}:
            cost_blocks = claims_anchor or not low_risk_support
        if cost_blocks:
            _append_code(block_codes, "late_block_missing_cost_metadata")
        else:
            _append_code(penalty_codes, "late_penalty_missing_cost_metadata")

    if missing_governance:
        _append_code(penalty_codes, "late_penalty_missing_governance_metadata")

    if "missing_rpe" in unsafe_metadata:
        rpe_blocks = bool(
            (window in D13_AND_UNDER_WINDOWS and fight_pace_or_glycolytic)
            or (window in D7_AND_UNDER_WINDOWS and physical_work and not low_risk_support)
        )
        if rpe_blocks:
            _append_code(block_codes, "late_block_missing_rpe")
        else:
            _append_code(penalty_codes, "late_penalty_missing_rpe")
    if unsafe_metadata and not block_codes and not penalty_codes:
        _append_code(penalty_codes, "late_penalty_missing_metadata")

    if kind == "conditioning":
        if not system_state["is_known"]:
            _append_code(block_codes, "late_block_unknown_system")
            unsafe_metadata.add("unknown_system")
        elif system_state["is_support_alias"] and claims_anchor:
            alias_can_claim_meaningful = (
                item.get("meaningful_stress") is True
                and item.get("support_only") is False
                and not _has_incomplete_governance(unsafe_metadata)
                and not missing_cost
                and "missing_rpe" not in unsafe_metadata
            )
            if not alias_can_claim_meaningful:
                _append_code(block_codes, "late_block_alias_system_without_meaningful_stress")
                unsafe_metadata.add("alias_system_without_meaningful_stress")

    effective_rpe = _effective_rpe(item)
    if window in D7_AND_UNDER_WINDOWS and effective_rpe is not None and effective_rpe >= 8:
        _append_code(block_codes, "late_block_high_rpe")

    intensity = _clean_string(item.get("intensity"))
    if window in D7_AND_UNDER_WINDOWS and intensity in HIGH_LEVELS:
        _append_code(block_codes, "late_block_high_rpe")

    lactate_load = _clean_string(item.get("lactate_load"))
    if window in D13_AND_UNDER_WINDOWS and lactate_load in HIGH_LEVELS:
        _append_code(block_codes, "late_block_high_lactate")

    movement_cost = _clean_string(item.get("movement_cost"))
    if window in D13_AND_UNDER_WINDOWS and movement_cost in HIGH_LEVELS:
        _append_code(block_codes, "late_block_high_movement_cost")

    impact_cost = _clean_string(item.get("impact_cost"))
    if window in D7_AND_UNDER_WINDOWS and impact_cost in HIGH_LEVELS:
        _append_code(block_codes, "late_block_high_impact")

    if (
        window in D13_AND_UNDER_WINDOWS
        and _has_dense_glycolytic_profile(item, normalized_system=system_state["normalized"])
        and not _boolean_true(item.get("late_glycolytic_allowed"))
        and not _boolean_true(item.get("glycolytic_late_allowed"))
    ):
        _append_code(block_codes, "late_block_high_lactate")

    if (
        window == D1
        and _has_d1_forbidden_modality(item, source=source, source_kind=kind)
        and not _has_final_day_policy(item)
    ):
        _append_code(block_codes, "late_block_d1_forbidden_modality")

    if _primer_only_fulfillment_block(item, source=source, source_kind=kind):
        _append_code(block_codes, "late_block_primer_only_strength_fulfillment")
    if _support_only_fulfillment_block(item, source=source, source_kind=kind):
        _append_code(block_codes, "late_block_support_only_anchor_fulfillment")

    reason_codes = list(dict.fromkeys(block_codes + penalty_codes))
    severity = "blocked" if block_codes else "penalty" if penalty_codes else "safe"
    return {
        "safe": severity != "blocked",
        "severity": severity,
        "block_codes": block_codes,
        "reason_codes": reason_codes,
        "penalty_codes": penalty_codes,
        "unsafe_metadata": sorted(unsafe_metadata),
    }


def _mark_runtime_safety(item: dict) -> None:
    source = str(item.get(_SCHEMA_SOURCE_KEY) or "")
    safety = is_late_fight_metadata_safe(item, source, D21_TO_D14)
    item[_SCHEMA_SAFETY_KEY] = {
        "late_fight_eligible": bool(safety["safe"]),
        "severity": safety["severity"],
        "penalty_codes": list(safety.get("penalty_codes", [])),
        "unsafe_metadata": list(safety["unsafe_metadata"]),
    }


def validate_training_item(
    item: dict,
    *,
    source: str,
    require_phases: bool = True,
    require_system: bool = False,
    mode: ValidationMode = "runtime",
) -> dict:
    if mode not in {"audit", "strict", "runtime"}:
        raise ValueError(f"Unknown bank schema validation mode: {mode}")

    name = item.get("name")
    if not name or not str(name).strip():
        _warn_once(
            source,
            "<missing-name>",
            "missing_name",
            f"[bank schema] Missing required 'name' in {source} item={item}",
        )
        raise ValueError(f"Missing required 'name' in bank item from {source}.")

    tags = item.get("tags")
    if not isinstance(tags, list):
        _record_issue(item, "missing_tags")
        _warn_once(
            source,
            name,
            "missing_tags",
            f"[bank schema] Missing or invalid 'tags' for '{name}' in {source}.",
        )
        if mode == "strict":
            raise ValueError(f"Missing or invalid 'tags' for '{name}' in {source}.")
        if mode == "audit":
            item["tags"] = []

    if require_phases:
        phases = item.get("phases")
        if not isinstance(phases, list) or not phases:
            _record_issue(item, "missing_phases")
            _warn_once(
                source,
                name,
                "missing_phases",
                f"[bank schema] Missing or invalid 'phases' for '{name}' in {source}.",
            )
            if mode == "strict":
                raise ValueError(f"Missing or invalid 'phases' for '{name}' in {source}.")
            if mode == "audit":
                item["phases"] = DEFAULT_PHASES.copy()

    if require_system:
        system = item.get("system")
        if not system:
            _warn_once(
                source,
                name,
                "missing_system",
                f"[bank schema] Missing required 'system' for '{name}' in {source}.",
            )
            raise ValueError(f"Missing required 'system' for '{name}' in {source}.")

    source_key = str(source).lower()
    item[_SCHEMA_SOURCE_KEY] = _source_filename(source_key)
    defaults = _schema_defaults_for_source(source_key)
    for key, default in defaults.items():
        if key not in item:
            issue = "missing_late_windows" if key == "late_windows" else f"missing_{key}"
            _record_issue(item, issue)
            if mode == "audit":
                item[key] = default.copy() if isinstance(default, list) else default

    for issue in _metadata_missing_issues(item, source=source_key):
        _record_issue(item, issue)

    late_windows = item.get("late_windows")
    if "late_windows" in item and (not isinstance(late_windows, list) or not late_windows):
        _record_issue(item, "missing_late_windows")

    if mode == "strict" and item.get(_SCHEMA_ISSUES_KEY):
        issues = ", ".join(item[_SCHEMA_ISSUES_KEY])
        raise ValueError(f"Unsafe bank metadata for '{name}' in {source}: {issues}.")

    if mode == "runtime":
        _mark_runtime_safety(item)

    return item
