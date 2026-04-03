from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR


_REGEX_CONFIG_PATH = Path(DATA_DIR) / "regex_patterns.json"


@lru_cache(maxsize=1)
def _load_regex_config() -> dict[str, object]:
    with _REGEX_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _lookup(section: str, key: str) -> object:
    config = _load_regex_config()
    section_config = config.get(section)
    if not isinstance(section_config, dict) or key not in section_config:
        raise KeyError(f"Missing regex config for {section}.{key}")
    return section_config[key]


def compile_regex(section: str, key: str, *, flags: int = 0) -> re.Pattern[str]:
    value = _lookup(section, key)
    if not isinstance(value, str):
        raise TypeError(f"Regex config {section}.{key} must be a string")
    return re.compile(value, flags)


def compile_regex_list(section: str, key: str, *, flags: int = 0) -> tuple[re.Pattern[str], ...]:
    value = _lookup(section, key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"Regex config {section}.{key} must be a list of strings")
    return tuple(re.compile(item, flags) for item in value)
