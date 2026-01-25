"""Centralized bank loading to avoid duplication across modules."""

import json
import logging
from pathlib import Path
from typing import Any
from .config import DATA_DIR

logger = logging.getLogger(__name__)

# Cache for loaded banks to avoid redundant file I/O
_BANK_CACHE: dict[str, Any] = {}


def _load_json(filename: str, use_cache: bool = True) -> Any:
    """Load a JSON file from the data directory with optional caching."""
    if use_cache and filename in _BANK_CACHE:
        return _BANK_CACHE[filename]
    
    path = DATA_DIR / filename
    with open(path) as f:
        data = json.load(f)
    
    if use_cache:
        _BANK_CACHE[filename] = data
    
    return data


def load_exercise_bank() -> list[dict]:
    """Load the main exercise bank."""
    return _load_json("exercise_bank.json")


def load_conditioning_bank_raw() -> list[dict]:
    """Load the conditioning bank without validation (for custom processing)."""
    return _load_json("conditioning_bank.json", use_cache=False)


def load_style_conditioning_bank_raw() -> list[dict]:
    """Load the style-specific conditioning bank without validation (for custom processing)."""
    return _load_json("style_conditioning_bank.json", use_cache=False)


def load_universal_gpp_strength() -> list[dict]:
    """Load the universal GPP strength exercises."""
    return _load_json("universal_gpp_strength.json")


def load_universal_gpp_conditioning() -> list[dict]:
    """Load the universal GPP conditioning drills."""
    return _load_json("universal_gpp_conditioning.json")


def load_style_taper_conditioning() -> list[dict]:
    """Load the style-specific taper conditioning drills."""
    return _load_json("style_taper_conditioning.json")


def load_coordination_bank() -> dict:
    """Load the coordination bank."""
    return _load_json("coordination_bank.json")


def load_rehab_bank() -> list[dict]:
    """Load the rehab/recovery bank."""
    return _load_json("rehab_bank.json")


def load_format_energy_weights() -> dict:
    """Load format energy system weights."""
    return _load_json("format_energy_weights.json")


def load_injury_exclusion_map() -> dict:
    """Load the injury exclusion map."""
    return _load_json("injury_exclusion_map.json")


def load_tag_vocabulary() -> dict:
    """Load the tag vocabulary."""
    return _load_json("tag_vocabulary.json")


def clear_cache():
    """Clear the bank cache (useful for testing)."""
    _BANK_CACHE.clear()
