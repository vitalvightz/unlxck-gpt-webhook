import logging
from typing import Literal

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

DEFAULT_PHASES = list(PHASE_VALUES)
_SCHEMA_WARNINGS_LOGGED: set[tuple[str, str, str]] = set()
_SCHEMA_ISSUES_KEY = "_schema_issues"
_SCHEMA_SAFETY_KEY = "_schema_safety"

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


def _mark_runtime_safety(item: dict) -> None:
    issues = set(item.get(_SCHEMA_ISSUES_KEY) or [])
    late_windows = item.get("late_windows")
    has_late_windows = isinstance(late_windows, list) and bool(late_windows)
    item[_SCHEMA_SAFETY_KEY] = {
        "late_fight_eligible": bool(has_late_windows and "missing_late_windows" not in issues),
        "unsafe_metadata": sorted(issues),
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
    if source_key.endswith("exercise_bank.json"):
        for key, default in _EXERCISE_SCHEMA_DEFAULTS.items():
            if key not in item:
                _record_issue(item, f"missing_{key}")
                if key == "late_windows":
                    _record_issue(item, "missing_late_windows")
                if mode == "audit":
                    item[key] = default.copy() if isinstance(default, list) else default
    elif source_key.endswith("conditioning_bank.json"):
        for key, default in _CONDITIONING_SCHEMA_DEFAULTS.items():
            if key not in item:
                _record_issue(item, f"missing_{key}")
                if key == "late_windows":
                    _record_issue(item, "missing_late_windows")
                if mode == "audit":
                    item[key] = default.copy() if isinstance(default, list) else default

    late_windows = item.get("late_windows")
    if "late_windows" in item and (not isinstance(late_windows, list) or not late_windows):
        _record_issue(item, "missing_late_windows")

    if mode == "strict" and item.get(_SCHEMA_ISSUES_KEY):
        issues = ", ".join(item[_SCHEMA_ISSUES_KEY])
        raise ValueError(f"Unsafe bank metadata for '{name}' in {source}: {issues}.")

    if mode == "runtime":
        _mark_runtime_safety(item)

    return item
