"""Low-risk bridge profile (the planner's single "is this athlete safe to keep
one more low-risk performance exposure?" gate).

The planner's load caps are deliberately conservative, and the genuine safety
rules — weight-cut + head-impact suppression in the bridge window, injury
gating — are intentionally left untouched (see
``docs/conservative_rules_assessment.md``).

This module isolates the one *load-shape* decision that is tunable rather than
safety-critical: in the D-21..D-18 bridge window, a demonstrably low-risk
athlete may keep **one extra low-risk performance exposure** (alactic power, a
low-volume strength touch, or low-noise aerobic) instead of being throttled to
the minimal taper-on-ramp shape. This raises the active-role count by one; it
never restores hard sparring or hard glycolytic work, which stay where the
safety rules left them.

``bridge_low_risk_profile`` is the gate. It returns True only when **all** of:

* fatigue is low/none, AND
* there is no red-flag injury and no medical-hold / restricted-rehab /
  needs-review injury mode, AND
* the active injury has no instability, worsening, or daily symptoms and is at
  most mild severity, AND
* the weight-cut bucket is none / low / moderate (never high+), AND
* the fight is not D-7 or closer.

It is applied as a **default** (no opt-in flag): a clean or mildly-managed
athlete gets the unified cap automatically; any safety signal drops them back to
the conservative baseline.
"""

from __future__ import annotations

from typing import Any

from .normalization import clean_list
from .sparring_dose_planner import _injury_assessment
from .weight_cut import compute_cut_severity_score, cut_severity_bucket

_LOW_RISK_FATIGUE = {"", "none", "low"}
_LOW_RISK_CUT_BUCKETS = {"", "none", "low", "moderate"}
_BLOCKED_INJURY_MODES = {"medical_hold", "restricted_rehab_only", "needs_review"}
_RED_FLAG_READINESS = {"severe_injury", "red_flag_injury"}
_MODERATE_PLUS_SEVERITY = {"moderate", "high"}

#: Bridge sub-window (inclusive day range) that may receive the extra exposure.
BRIDGE_EXTRA_EXPOSURE_DAY_RANGE = (18, 21)


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


def low_risk_profile_blockers(athlete_model: dict[str, Any]) -> list[str]:
    """Return the reason codes (if any) that disqualify the low-risk profile.

    An empty list means the athlete qualifies as low-risk. Surfacing the reasons
    lets callers explain exactly why the conservative baseline stayed in force.
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

    return reasons


def bridge_low_risk_profile(athlete_model: dict[str, Any]) -> bool:
    """True when the athlete qualifies for the unified low-risk bridge cap."""
    return not low_risk_profile_blockers(athlete_model)
