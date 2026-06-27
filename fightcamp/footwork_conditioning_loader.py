from __future__ import annotations

import logging
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)
_FOOTWORK_BANK_CACHE: list[dict[str, Any]] | None = None


def _as_list(bank: Any) -> list[dict[str, Any]]:
    if isinstance(bank, list):
        return [item for item in bank if isinstance(item, dict)]
    if isinstance(bank, dict):
        merged: list[dict[str, Any]] = []
        for items in bank.values():
            if isinstance(items, list):
                merged.extend(item for item in items if isinstance(item, dict))
        return merged
    return []


def _bank_key(item: dict[str, Any]) -> tuple[str, str]:
    name = str(item.get("name", "")).strip().lower()
    modality = str(item.get("modality", "")).strip().lower()
    return name, modality


def _merge_unique(
    base: list[dict[str, Any]],
    extras: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(base)
    seen = {_bank_key(item) for item in merged}

    for item in extras:
        key = _bank_key(item)
        if key in seen:
            continue
        merged.append(item)
        seen.add(key)
    return merged


def _load_footwork_bank(conditioning_module: Any) -> list[dict[str, Any]]:
    global _FOOTWORK_BANK_CACHE
    if _FOOTWORK_BANK_CACHE is not None:
        return _FOOTWORK_BANK_CACHE

    try:
        bank = conditioning_module._load_bank(
            DATA_DIR / "footwork_conditioning_bank.json",
            source="footwork_conditioning_bank.json",
            enforce_conditioning_systems=True,
        )
    except FileNotFoundError:
        logger.warning("[bank-load] optional footwork conditioning bank missing")
        bank = []

    _FOOTWORK_BANK_CACHE = _as_list(bank)
    return _FOOTWORK_BANK_CACHE


def install() -> None:
    from . import conditioning as conditioning_module

    if getattr(conditioning_module, "_FOOTWORK_CONDITIONING_BANK_INSTALLED", False):
        return

    original_get_conditioning_bank = conditioning_module.get_conditioning_bank

    def get_conditioning_bank() -> list[dict[str, Any]]:
        base = list(original_get_conditioning_bank())
        footwork_bank = _load_footwork_bank(conditioning_module)
        merged = _merge_unique(base, footwork_bank)
        conditioning_module._conditioning_bank_cache = merged
        return merged

    conditioning_module.get_conditioning_bank = get_conditioning_bank
    conditioning_module._FOOTWORK_CONDITIONING_BANK_INSTALLED = True


def get_footwork_conditioning_bank() -> list[dict[str, Any]]:
    from . import conditioning as conditioning_module

    return list(_load_footwork_bank(conditioning_module))
