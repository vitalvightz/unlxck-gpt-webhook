"""Small scheduled-day safety helpers for late-camp normal planning.

These helpers do not choose training architecture. They only provide monotonic
load-shape signals that can be consumed by the existing normal planner.
"""

from __future__ import annotations

from typing import Any

from .weight_cut import compute_cut_severity_score, cut_severity_bucket


def resolved_cut_bucket(athlete_model: dict[str, Any]) -> str:
    explicit = str(athlete_model.get("cut_severity_bucket") or "").strip().lower()
    if explicit in {"none", "low", "moderate", "high", "critical", "extreme"}:
        return explicit
    try:
        score = float(athlete_model.get("cut_severity_score"))
    except (TypeError, ValueError):
        score = None
    if score is None:
        try:
            score = compute_cut_severity_score(
                athlete_model.get("weight_cut_pct"), athlete_model.get("days_until_fight")
            )
        except (TypeError, ValueError):
            return "none"
    return str(cut_severity_bucket(score) or "none").strip().lower()


def aggressive_cut_extra_compression(athlete_model: dict[str, Any], scheduled_d_day: int | None = None) -> int:
    """Return one extra non-spar compression slot for high+ late-camp cuts.

    Moderate/routine cuts receive no extra penalty here. High/critical/extreme
    cuts get one additional optional-stressor reduction while the normal camp
    architecture is still active. This is a load overlay, never a route switch.
    """

    bucket = resolved_cut_bucket(athlete_model)
    if bucket not in {"high", "critical", "extreme"}:
        return 0
    d_day = scheduled_d_day
    if d_day is None:
        raw = athlete_model.get("days_until_fight")
        try:
            d_day = int(raw)
        except (TypeError, ValueError):
            d_day = None
    if d_day is None or d_day < 0:
        return 0
    return 1 if d_day <= 28 else 0
