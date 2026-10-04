"""Stable exercise identity helpers shared by planner and API.

The deterministic planner owns exercise identity. Athlete-facing labels and
Stage-2 display copy may change freely, but media lookup keys must not.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DOSE_SUFFIX_RE = re.compile(r"\s+[-–—]\s+\d[^-–—]*$")


def strip_dose_suffix(name: str | None) -> str:
    """Drop a trailing spaced-dash dose while preserving real exercise names."""
    text = str(name or "")
    stripped = _DOSE_SUFFIX_RE.sub("", text).rstrip()
    return stripped if re.search(r"[A-Za-z]", stripped) else text


def normalize_exercise_key(name: str | None) -> str:
    """Normalize an exercise identity without collapsing meaningful qualifiers."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name).lower()).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    return _NON_ALNUM_RE.sub("-", text).strip("-")


def canonical_exercise_key(name: Any) -> str | None:
    """Canonical key for a planner-authored exercise name."""
    key = normalize_exercise_key(strip_dose_suffix(str(name or "")))
    return key or None


def stamp_selected_exercise_assignment_keys(weekly_role_map: Any) -> Any:
    """Stamp deterministic selected assignments before the Stage-2 handoff."""
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            for assignment in role.get("selected_exercise_assignments", []) or []:
                if not isinstance(assignment, dict):
                    continue
                key = canonical_exercise_key(assignment.get("name"))
                if key:
                    assignment["exercise_key"] = key
            microdose = role.get("priority_microdose")
            if isinstance(microdose, dict):
                key = canonical_exercise_key(microdose.get("name"))
                if key:
                    microdose["exercise_key"] = key
    return weekly_role_map
