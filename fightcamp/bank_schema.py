import logging

from .phases import PHASE_VALUES

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


def validate_training_item(
    item: dict,
    *,
    source: str,
    require_phases: bool = True,
    require_system: bool = False,
) -> dict:
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
        _warn_once(
            source,
            name,
            "missing_tags",
            f"[bank schema] Missing or invalid 'tags' for '{name}' in {source}; defaulting to [].",
        )
        item["tags"] = []

    if require_phases:
        phases = item.get("phases")
        if not isinstance(phases, list) or not phases:
            _warn_once(
                source,
                name,
                "missing_phases",
                f"[bank schema] Missing or invalid 'phases' for '{name}' in {source}; "
                f"defaulting to {DEFAULT_PHASES}.",
            )
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
                item[key] = default
    elif source_key.endswith("conditioning_bank.json"):
        for key, default in _CONDITIONING_SCHEMA_DEFAULTS.items():
            if key not in item:
                item[key] = default

    return item
