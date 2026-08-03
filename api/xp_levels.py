"""Shared XP level ladder used by backend notifications and the web app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "shared" / "xp-levels.json"


def _load_xp_levels() -> tuple[tuple[int, str, int], ...]:
    try:
        contract_text = _CONTRACT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(
            "XP level contract is missing from the backend runtime at "
            f"{_CONTRACT_PATH}. Ensure shared/xp-levels.json is packaged."
        ) from exc

    try:
        raw: Any = json.loads(contract_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"XP level contract at {_CONTRACT_PATH} is not valid JSON"
        ) from exc

    if not isinstance(raw, list) or not raw:
        raise RuntimeError("XP level contract must be a non-empty list")

    levels: list[tuple[int, str, int]] = []
    previous_threshold = -1
    for expected_level, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise RuntimeError("XP level contract entries must be objects")
        level = item.get("level")
        title = item.get("title")
        threshold = item.get("threshold")
        if isinstance(level, bool) or not isinstance(level, int) or level != expected_level:
            raise RuntimeError("XP levels must be contiguous and start at 1")
        if not isinstance(title, str) or not title.strip():
            raise RuntimeError("XP level titles must be non-empty strings")
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
            raise RuntimeError("XP thresholds must be non-negative integers")
        if expected_level == 1 and threshold != 0:
            raise RuntimeError("Level 1 must start at 0 XP")
        if threshold <= previous_threshold:
            raise RuntimeError("XP thresholds must increase strictly")
        levels.append((level, title.strip(), threshold))
        previous_threshold = threshold
    return tuple(levels)


XP_LEVELS = _load_xp_levels()


def resolve_xp_level(total_xp: Any) -> tuple[int, str, int]:
    try:
        total = max(0, int(total_xp))
    except (TypeError, ValueError, OverflowError):
        total = 0
    current = XP_LEVELS[0]
    for level in XP_LEVELS[1:]:
        if total < level[2]:
            break
        current = level
    return current


__all__ = ["XP_LEVELS", "resolve_xp_level"]
