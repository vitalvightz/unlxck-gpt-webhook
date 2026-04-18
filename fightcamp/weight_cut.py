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
      3.2 * (cut_pct^1.15) * (1 + 1.8 * exp(-days_out / 10))
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
    raw_score = 3.2 * (cut_pct ** 1.15) * (1.0 + 1.8 * math.exp(-days_out / 10.0))
    return round(min(100.0, max(0.0, raw_score)), 1)


def cut_severity_bucket(score: object) -> str:
    """Map cut severity score to deterministic buckets."""
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value < 10.0:
        return "none"
    if value < 18.0:
        return "low"
    if value < 35.0:
        return "moderate"
    if value < 55.0:
        return "high"
    return "critical"
