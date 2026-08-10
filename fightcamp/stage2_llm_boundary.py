"""Stage 2 LLM-boundary sanitization.

Stage 1 is allowed to keep normalized/internal tactical-family signals for
selection and programming. Stage 2 is a rendering boundary: it should receive
the athlete's declared tactical identity, not parent-family aliases or
stance-derived tactical signals.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .tactical_watch_library import STYLE_FAMILIES, declared_tactical_style_labels


_INTERNAL_TACTICAL_FAMILY_TAGS = set(STYLE_FAMILIES)


def _normalize_tag(value: Any) -> str:
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def _sanitize_preferred_tags(value: Any) -> None:
    """Remove internal tactical-family tags from LLM-facing role metadata."""

    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "preferred_tags" and isinstance(item, list):
                value[key] = [
                    tag
                    for tag in item
                    if _normalize_tag(tag) not in _INTERNAL_TACTICAL_FAMILY_TAGS
                ]
            else:
                _sanitize_preferred_tags(item)
    elif isinstance(value, list):
        for item in value:
            _sanitize_preferred_tags(item)


def _sanitize_athlete_identity(athlete: dict[str, Any]) -> None:
    """Project normalized runtime style state back to athlete-facing identity."""

    labels = declared_tactical_style_labels(athlete)
    if "tactical_styles" in athlete or labels:
        athlete["tactical_styles"] = labels
    if "tactical_style" in athlete:
        athlete["tactical_style"] = labels[0] if labels else ""
    if "style_tactical" in athlete:
        raw = athlete.get("style_tactical")
        athlete["style_tactical"] = (
            labels if isinstance(raw, (list, tuple)) else (labels[0] if labels else "")
        )


def build_stage2_llm_planning_brief(
    planning_brief: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a non-mutating planning-brief projection safe for Stage 2 rendering.

    Internal Stage 1 state remains unchanged. Only the copy crossing the LLM
    boundary has tactical identity projected to the athlete-facing label and
    internal tactical-family preferred tags removed.
    """

    if not isinstance(planning_brief, dict):
        return planning_brief

    llm_brief = deepcopy(planning_brief)
    for key in ("athlete_snapshot", "athlete_model"):
        athlete = llm_brief.get(key)
        if isinstance(athlete, dict):
            _sanitize_athlete_identity(athlete)

    _sanitize_preferred_tags(llm_brief)
    return llm_brief
