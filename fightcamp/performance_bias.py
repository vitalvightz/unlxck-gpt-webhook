"""Opt-in performance-bias layer.

The planner's default behaviour is deliberately conservative: weight-cut,
head-impact, and injury safety rules stack to protect the athlete, and those
defaults are intentionally left untouched (see
``docs/conservative_rules_assessment.md``).

This module adds a *purely opt-in* performance bias that only activates for
demonstrably low-risk profiles. When active it lets the bridge window
(D-21 to D-18) preserve **one extra low-risk performance exposure** — e.g.
alactic power, a low-volume strength touch, or low-noise aerobic conditioning.
It never restores hard sparring or hard glycolytic work, and it never fires
when any safety signal is present.

Eligibility is the gate. Performance bias is active only when:

* the athlete (or intake) opted in via the ``performance_bias`` flag, AND
* fatigue is low/none, AND
* there is no red-flag injury and no medical-hold / restricted-rehab /
  needs-review injury mode, AND
* the active injury has no instability, worsening, or daily symptoms and is at
  most mild severity, AND
* the weight-cut bucket is none / low / moderate (never high+), AND
* the fight is not D-7 or closer.
"""

from __future__ import annotations

from typing import Any

from .normalization import clean_list
from .sparring_dose_planner import _injury_assessment
from .weight_cut import compute_cut_severity_score, cut_severity_bucket

#: athlete_model / intake key used to opt in to the performance bias layer.
PERFORMANCE_BIAS_FLAG = "performance_bias"

_LOW_RISK_FATIGUE = {"", "none", "low"}
_LOW_RISK_CUT_BUCKETS = {"", "none", "low", "moderate"}
_BLOCKED_INJURY_MODES = {"medical_hold", "restricted_rehab_only", "needs_review"}
_RED_FLAG_READINESS = {"severe_injury", "red_flag_injury"}
_MODERATE_PLUS_SEVERITY = {"moderate", "high"}

#: Bridge sub-window (inclusive day range) that may receive the extra exposure.
PERFORMANCE_BIAS_BRIDGE_DAY_RANGE = (18, 21)


def performance_bias_requested(athlete_model: dict[str, Any]) -> bool:
    """True when the athlete/intake opted in to the performance bias layer."""
    return bool(athlete_model.get(PERFORMANCE_BIAS_FLAG))


def _resolved_cut_bucket(athlete_model: dict[str, Any]) -> str:
    bucket = str(athlete_model.get("cut_severity_bucket") or "").strip().lower()
    if bucket:
        return bucket
    try:
        score = compute_cut_severity_score(
            athlete_model.get("weight_cut_pct"),
            athlete_model.get("days_until_fight"),
        )
    except (TypeError, ValueError):
        return ""
    return str(cut_severity_bucket(score) or "").strip().lower()


def performance_bias_eligibility(athlete_model: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return ``(eligible, disqualifier_reason_codes)``.

    ``eligible`` is True only when *no* disqualifier fired. The reason codes are
    surfaced so the caller can explain exactly why the bias stayed off.
    """
    reasons: list[str] = []

    fatigue = str(
        athlete_model.get("fatigue") or athlete_model.get("fatigue_level") or ""
    ).strip().lower()
    if fatigue not in _LOW_RISK_FATIGUE:
        reasons.append("fatigue_not_low")

    cut_bucket = _resolved_cut_bucket(athlete_model)
    if cut_bucket and cut_bucket not in _LOW_RISK_CUT_BUCKETS:
        reasons.append("cut_bucket_above_moderate")

    injury_mode = str(athlete_model.get("injury_mode") or "").strip().lower()
    if injury_mode in _BLOCKED_INJURY_MODES:
        reasons.append("injury_mode_restricted")

    readiness = {str(flag).strip().lower() for flag in clean_list(athlete_model.get("readiness_flags", []))}
    if readiness & _RED_FLAG_READINESS:
        reasons.append("red_flag_injury")

    assessment = _injury_assessment(athlete_model)
    if assessment.get("severity") in _MODERATE_PLUS_SEVERITY:
        reasons.append("injury_severity_moderate_plus")
    if assessment.get("worsening"):
        reasons.append("injury_worsening")
    if assessment.get("instability"):
        reasons.append("injury_instability")
    if assessment.get("daily_symptoms"):
        reasons.append("injury_daily_symptoms")
    if assessment.get("high_risk"):
        reasons.append("injury_high_risk")

    days = athlete_model.get("days_until_fight")
    if isinstance(days, int) and 0 <= days <= 7:
        reasons.append("inside_fight_week")

    return (not reasons), reasons


def performance_bias_active(athlete_model: dict[str, Any]) -> bool:
    """True only when opted in *and* the low-risk eligibility gate passes."""
    if not performance_bias_requested(athlete_model):
        return False
    eligible, _ = performance_bias_eligibility(athlete_model)
    return eligible
