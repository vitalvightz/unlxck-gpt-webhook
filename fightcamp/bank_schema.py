import logging
import re
from typing import Any, Literal

from .phases import PHASE_VALUES

ValidationMode = Literal["audit", "strict", "runtime"]

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


def _metadata_missing_issues(item: dict, *, source: str) -> list[str]:
    kind = _source_kind(source)
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


def _has_d1_forbidden_modality(item: dict, *, source: str) -> bool:
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
    loaded_strength = _source_kind(source) == "strength" and loaded
    return any((bands, med_ball, loaded_strength, isometric, ballistic, max_intent, high_rpe))


def _has_final_day_policy(item: dict) -> bool:
    tags = set(_clean_list(item.get("tags")))
    return bool(
        tags & {"d1_ok", "d1_if_familiar", "final_day_ok"}
        or _boolean_true(item.get("d1_ok"))
        or _boolean_true(item.get("final_day_ok"))
        or _boolean_true(item.get("final_day_policy"))
    )


def _primer_only_fulfillment_block(item: dict, *, source: str) -> bool:
    if _source_kind(source) != "strength":
        return False
    tags = set(_clean_list(item.get("tags")))
    has_primer_signal = _boolean_true(item.get("primer_only")) or bool(tags & PRIMER_ONLY_TAGS)
    claims_fulfillment = bool(tags & STRENGTH_FULFILLMENT_TAGS) or any(
        _boolean_true(item.get(field)) for field in STRENGTH_FULFILLMENT_TAGS
    )
    if not has_primer_signal or not claims_fulfillment:
        return False
    return not _boolean_true(item.get("real_strength_maintenance"))


def _support_only_fulfillment_block(item: dict, *, source: str) -> bool:
    tags = set(_clean_list(item.get("tags")))
    claims_strength = _source_kind(source) == "strength" and (
        bool(tags & STRENGTH_FULFILLMENT_TAGS)
        or any(_boolean_true(item.get(field)) for field in STRENGTH_FULFILLMENT_TAGS)
    )
    stress_class = _normalize_token(item.get("stress_class"))
    claims_conditioning_anchor = _source_kind(source) == "conditioning" and stress_class in {
        "meaningful_stress",
        "anchor",
        "primary",
    }
    if not (claims_strength or claims_conditioning_anchor):
        return False
    return item.get("support_only") is True or item.get("meaningful_stress") is False


def _append_code(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def is_late_fight_metadata_safe(
    item: dict,
    source: str,
    countdown_offset_or_window: Any,
) -> dict[str, Any]:
    """Return late-fight metadata safety state for selectors and runtime loaders."""
    window = _late_window_for(countdown_offset_or_window)
    existing_issues = set(item.get(_SCHEMA_ISSUES_KEY) or [])
    unsafe_metadata = set(existing_issues)
    unsafe_metadata.update(_metadata_missing_issues(item, source=source))

    block_codes: list[str] = []
    reason_codes: list[str] = []

    if window is None:
        return {
            "safe": True,
            "block_codes": [],
            "reason_codes": [],
            "unsafe_metadata": sorted(unsafe_metadata),
        }

    if "missing_late_windows" in unsafe_metadata:
        _append_code(block_codes, "late_block_missing_late_windows")
    missing_cost = {
        issue
        for issue in unsafe_metadata
        if issue
        in {
            "missing_impact_cost",
            "missing_movement_cost",
            "missing_cns_load",
            "missing_soreness_risk",
            "missing_eccentric_cost",
            "missing_landing_cost",
            "missing_lactate_load",
            "missing_stress_class",
            "missing_cost_class",
            "missing_support_only",
            "missing_meaningful_stress",
        }
    }
    if missing_cost:
        _append_code(block_codes, "late_block_missing_cost_metadata")
    if "missing_rpe" in unsafe_metadata:
        _append_code(block_codes, "late_block_missing_rpe")
    if unsafe_metadata and not block_codes:
        _append_code(block_codes, "late_block_missing_metadata")

    kind = _source_kind(source)
    system_state = _system_state(item)
    if kind == "conditioning":
        if not system_state["is_known"]:
            _append_code(block_codes, "late_block_unknown_system")
            unsafe_metadata.add("unknown_system")
        elif system_state["is_support_alias"] and not _boolean_true(item.get("meaningful_stress")):
            stress_class = _normalize_token(item.get("stress_class"))
            support_only = item.get("support_only")
            claims_meaningful = stress_class in {"meaningful_stress", "anchor", "primary"} or support_only is False
            if claims_meaningful:
                _append_code(block_codes, "late_block_alias_system_without_meaningful_stress")
                unsafe_metadata.add("alias_system_without_meaningful_stress")

    rpe = _number_or_none(item.get("rpe"))
    rpe_max = _number_or_none(item.get("rpe_max"))
    effective_rpe = max([value for value in (rpe, rpe_max) if value is not None], default=None)
    if effective_rpe is None:
        effective_rpe = _rpe_from_text(item)
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

    if window == D1 and _has_d1_forbidden_modality(item, source=source) and not _has_final_day_policy(item):
        _append_code(block_codes, "late_block_d1_forbidden_modality")

    if _primer_only_fulfillment_block(item, source=source):
        _append_code(block_codes, "late_block_primer_only_strength_fulfillment")
    if _support_only_fulfillment_block(item, source=source):
        _append_code(block_codes, "late_block_support_only_anchor_fulfillment")

    reason_codes = list(block_codes)
    return {
        "safe": not block_codes,
        "block_codes": block_codes,
        "reason_codes": reason_codes,
        "unsafe_metadata": sorted(unsafe_metadata),
    }


def _mark_runtime_safety(item: dict) -> None:
    source = str(item.get(_SCHEMA_SOURCE_KEY) or "")
    safety = is_late_fight_metadata_safe(item, source, D21_TO_D14)
    item[_SCHEMA_SAFETY_KEY] = {
        "late_fight_eligible": bool(safety["safe"]),
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
