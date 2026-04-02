from __future__ import annotations

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
    if current <= 0:
        return 0.0
    return round(max(0.0, (current - target) / current * 100.0), 1)

