from __future__ import annotations

import math
import re


def parse_weight_value(raw: object) -> float:
    """Parse weight-like values from numeric or string input."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)

    text = str(raw).strip()
    if not text:
        return 0.0
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def compute_weight_cut_pct(current_weight: object, target_weight: object) -> float:
    """
    Return active cut percentage as body-mass delta:
      (current - target) / current * 100
    Clamped at zero and rounded to one decimal.
    """
    current = parse_weight_value(current_weight)
    target = parse_weight_value(target_weight)
    if current < 1.0:
        return 0.0
    return round(max(0.0, (current - target) / current * 100.0), 1)


def compute_cut_severity_score(weight_cut_pct: object, days_until_fight: object) -> float:
    """
    Deterministic active-cut severity score (0-100):
      3.2 * (cut_pct^1.15) * (1 + 1.8 * exp(-days_out / 15))
    """
    try:
        cut_pct = float(weight_cut_pct or 0.0)
    except (TypeError, ValueError):
        cut_pct = 0.0
    try:
        days_out = int(days_until_fight)
    except (TypeError, ValueError):
        days_out = 35

    cut_pct = max(0.0, cut_pct)
    days_out = max(0, days_out)
    raw_score = 3.2 * (cut_pct ** 1.15) * (1.0 + 1.8 * math.exp(-days_out / 15.0))
    return round(min(100.0, max(0.0, raw_score)), 1)


def cut_severity_bucket(score: object) -> str:
    """Map cut severity score to deterministic buckets."""
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value < 5.0:
        return "none"
    if value < 15.0:
        return "low"
    if value < 35.0:
        return "moderate"
    if value < 55.0:
        return "high"
    if value < 85.0:
        return "critical"
    return "extreme"


# Ordinal ordering of the severity buckets (higher index = more severe). Used to
# decide, from the deterministic smart score, when a cut is serious enough to
# warrant supervision / stop-and-report / red-flag copy versus a calm note.
_SEVERITY_ORDER = ("none", "low", "moderate", "high", "critical", "extreme")


def cut_severity_rank(bucket: object) -> int:
    """Ordinal rank of a severity bucket (0 = none, higher = more severe)."""
    key = str(bucket or "none").strip().lower()
    try:
        return _SEVERITY_ORDER.index(key)
    except ValueError:
        return 0


def cut_warnings_escalate(bucket: object) -> bool:
    """Whether a cut is *worse than moderate* (high / critical / extreme).

    This is the single gate for alarm-tier weight-cut copy. Only an escalated
    cut warrants supervision, stop-and-report red flags, or "seek qualified
    support" language. A ``none`` / ``low`` / ``moderate`` cut does NOT — it gets
    a brief, calm active note (with light precautions at moderate) instead of
    the plan shouting medical warnings at the athlete.
    """
    return cut_severity_rank(bucket) >= _SEVERITY_ORDER.index("high")


def weight_cut_risk_band(
    active: object,
    cut_pct: object,
    days_until_fight: object = None,
) -> str:
    """Athlete-facing weight-cut band, derived from the smart severity score.

    Returns one of ``none`` / ``moderate`` / ``high`` / ``severe``:

    * inactive cut -> ``none``
    * ``cut_pct >= 6`` -> ``severe`` (magnitude floor for a medically serious
      acute cut, independent of days-out)
    * smart bucket critical/extreme -> ``severe``
    * smart bucket high -> ``high``
    * any other active cut -> ``moderate`` (active, but not escalated)

    Crucially this does NOT promote a routine active cut to ``high`` just because
    a fight is near or the athlete is tired — the smart score already folds in
    days-out. Only a genuinely high/critical/extreme cut earns alarm-tier
    handling downstream.
    """
    if not active:
        return "none"
    try:
        pct = float(cut_pct or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    try:
        days = int(float(days_until_fight)) if days_until_fight is not None else None
    except (TypeError, ValueError):
        days = None
    if pct >= 6.0:
        return "severe"
    rank = cut_severity_rank(
        cut_severity_bucket(compute_cut_severity_score(pct, days))
    )
    if rank >= _SEVERITY_ORDER.index("critical"):
        return "severe"
    if rank >= _SEVERITY_ORDER.index("high"):
        return "high"
    return "moderate"


def weight_cut_supervision_required(
    active: object,
    cut_pct: object,
    days_until_fight: object = None,
) -> bool:
    """Whether a cut is serious enough to flag qualified supervision.

    True only for a magnitude-heavy cut (``>= 6%``) or a smart bucket that is
    worse than moderate. A moderate-or-lower cut never trips the supervision
    flag, so the plan stops recommending medical oversight for routine cuts.
    """
    if not active:
        return False
    try:
        pct = float(cut_pct or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    try:
        days = int(float(days_until_fight)) if days_until_fight is not None else None
    except (TypeError, ValueError):
        days = None
    if pct >= 6.0:
        return True
    return cut_warnings_escalate(
        cut_severity_bucket(compute_cut_severity_score(pct, days))
    )
