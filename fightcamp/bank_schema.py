SYSTEM_ALIASES = {
    "atp-pcr": "alactic",
    "anaerobic_alactic": "alactic",
    "cognitive": "alactic",
}

KNOWN_SYSTEMS = {"aerobic", "glycolytic", "alactic"}

DEFAULT_PHASES = ["GPP", "SPP", "TAPER"]
_SCHEMA_WARNINGS_LOGGED: set[tuple[str, str, str]] = set()


def _warn_once(source: str, name: str, issue: str, message: str) -> None:
    key = (source, name, issue)
    if key in _SCHEMA_WARNINGS_LOGGED:
        return
    _SCHEMA_WARNINGS_LOGGED.add(key)
    print(message)


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

    return item
