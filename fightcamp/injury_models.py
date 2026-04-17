"""
injury_models.py
----------------
Shared data types for the injury pipeline.

Kept deliberately minimal — this module must not import from any other
fightcamp module, so it can be safely imported by both injury_guard and
injury_filtering without creating a circular dependency.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """
    Result of an injury-guard evaluation for a single training item.

    Attributes
    ----------
    action : str
        ``"allow"`` or ``"exclude"``.
    risk_score : float
        Computed injury risk score (0.0–1.0+).
    threshold : float
        The risk threshold that was active when the decision was made.
    matched_tags : list[str]
        Exercise tags that triggered the evaluation.
    mods : list[str]
        Recommended modifications when action is ``"allow"``.
    reason : dict
        Structured breakdown of the decision — region, severity, matches, etc.
    """

    action: str
    risk_score: float
    threshold: float
    matched_tags: list[str]
    mods: list[str]
    reason: dict
