from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .config import DATA_DIR
from .late_selector_windows import classify_late_selector_window

_NEGATION_MARKERS = (
    "avoid",
    "do not",
    "don't",
    "no ",
    "not ",
    "skip",
    "remove",
    "drop",
    "without",
    "instead of",
)
_COUNTDOWN_LABEL_LINE = re.compile(r"^(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?D-(\d+)\b", re.IGNORECASE)
_MARKDOWN_HEADER = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET_PREFIX = re.compile(r"^\s*[-*•]\s+")


def _normalize_exercise_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def _is_instruction_only(line: str) -> bool:
    normalized = (line or "").lower()
    return any(marker in normalized for marker in _NEGATION_MARKERS)


def _is_countdown_block_boundary(line: str) -> bool:
    if _COUNTDOWN_LABEL_LINE.match(line):
        return False
    return bool(_MARKDOWN_HEADER.match(line))


def _countdown_blocks_by_day(final_plan_text: str) -> dict[int, list[str]]:
    blocks: dict[int, list[str]] = {}
    current_day: int | None = None
    for raw_line in (final_plan_text or "").splitlines():
        cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
        if not cleaned:
            continue
        match = _COUNTDOWN_LABEL_LINE.match(cleaned)
        if match:
            current_day = int(match.group(1))
            blocks.setdefault(current_day, []).append(cleaned)
            continue
        if _is_countdown_block_boundary(cleaned):
            current_day = None
            continue
        if current_day is not None:
            blocks.setdefault(current_day, []).append(cleaned)
    return blocks


@lru_cache(maxsize=1)
def _taper_bank_late_window_records() -> tuple[dict[str, Any], ...]:
    try:
        with (DATA_DIR / "exercise_bank.json").open(encoding="utf-8") as handle:
            items = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return ()

    records: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        phases = {str(phase).strip().upper() for phase in item.get("phases", []) or []}
        if "TAPER" not in phases:
            continue
        late_windows = {
            str(window).strip().lower()
            for window in item.get("late_windows", []) or []
            if str(window).strip()
        }
        if not late_windows:
            continue
        key = _normalize_exercise_key(name)
        if key:
            records.append({"name": name, "key": key, "late_windows": late_windows})

    records.sort(key=lambda record: len(str(record.get("key") or "")), reverse=True)
    return tuple(records)


def _matching_late_window_records(line: str) -> list[dict[str, Any]]:
    normalized_line = _normalize_exercise_key(line)
    if not normalized_line:
        return []
    return [
        record
        for record in _taper_bank_late_window_records()
        if str(record.get("key") or "") in normalized_line
    ]


def late_window_exercise_warnings(*, planning_brief: dict, final_plan_text: str) -> list[dict[str, Any]]:
    spec = planning_brief.get("late_fight_plan_spec") or {}
    payload_mode = str(spec.get("payload_mode") or "")
    if not isinstance(spec, dict) or payload_mode in {"", "camp_payload"}:
        return []

    day_blocks = _countdown_blocks_by_day(final_plan_text)
    if not day_blocks:
        days_out_bucket = str(spec.get("days_out_bucket") or "")
        match = re.match(r"^D-(\d+)$", days_out_bucket, flags=re.IGNORECASE)
        if match:
            day_blocks[int(match.group(1))] = [
                _BULLET_PREFIX.sub("", line).strip()
                for line in (final_plan_text or "").splitlines()
                if _BULLET_PREFIX.sub("", line).strip()
            ]

    warnings: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for day, lines in day_blocks.items():
        window = classify_late_selector_window(day)
        if not window:
            continue
        window_key = str(window).strip().lower()
        for line in lines:
            if _is_instruction_only(line) or _COUNTDOWN_LABEL_LINE.match(line.strip()):
                continue
            for record in _matching_late_window_records(line):
                allowed_windows = set(record.get("late_windows") or set())
                if window_key in allowed_windows:
                    continue
                key = (day, str(record.get("name") or ""), line)
                if key in seen:
                    continue
                seen.add(key)
                warnings.append(
                    {
                        "code": "late_fight_window_forbidden_exercise",
                        "message": (
                            f"D-{day} renders {record['name']} in {window_key}, "
                            "outside its bank late_windows."
                        ),
                        "payload_mode": payload_mode,
                        "days_out_bucket": f"D-{day}",
                        "window": window_key,
                        "line": line,
                        "matched_terms": [record["name"]],
                        "allowed_late_windows": sorted(allowed_windows),
                        "blocking": True,
                    }
                )
    return warnings
