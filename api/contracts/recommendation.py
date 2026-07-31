"""Recommendation TTL / validity (Block 4 §3).

A recommendation is valid only for the athlete's current local training day
(see ``training_day.py``). After the 03:00 rollover the previous recommendation
expires and the live state returns to ``not_checked_in``; an expired
recommendation may only be shown as clearly-labelled history, never as the
current/live readiness.

Pure functions over plain mappings so the API, command-view builder, and tests
share one implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Mapping

# The live readiness state surfaced on Today/Overview. ``not_checked_in`` is the
# default whenever no *valid* recommendation exists for the current training day.
RecommendationState = Literal[
    "not_checked_in",
    "train_as_planned",
    "modify",
    "pull_back",
]

LIVE_RECOMMENDATION_STATES: frozenset[str] = frozenset(
    {"train_as_planned", "modify", "pull_back"}
)


@dataclass(frozen=True)
class RecommendationView:
    """Resolved live readiness for the current training day.

    * ``state`` is the live state (``not_checked_in`` when expired/absent).
    * ``reason`` is the live reason string, or ``None`` when not current.
    * ``training_day`` is the day the stored recommendation was produced for.
    * ``is_history`` is ``True`` when a stored recommendation exists but has
      expired — the consumer may show it as labelled history only.
    * ``history_reason`` is the expired recommendation's reason (history only).
    * ``triggers`` are the engine's trigger codes behind a LIVE decision, from
      which the consumer derives the athlete-facing contributors. Empty whenever
      the recommendation is not current, for the same reason ``reason`` is.
    """

    state: RecommendationState
    reason: str | None
    training_day: str | None
    is_history: bool
    history_reason: str | None = None
    triggers: tuple[str, ...] = ()


def _as_iso(day: date | str) -> str:
    if isinstance(day, date):
        return day.isoformat()
    return str(day or "").strip()


def _clean_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _recommendation_day(recommendation: Mapping[str, Any]) -> str | None:
    return _clean_str(recommendation.get("training_day"))


def _recommendation_decision(recommendation: Mapping[str, Any]) -> str:
    raw = recommendation.get("decision")
    if raw is None:
        raw = recommendation.get("recommendation_state")
    return str(raw or "").strip()


def _recommendation_reason(recommendation: Mapping[str, Any]) -> str | None:
    raw = recommendation.get("reason")
    if raw is None:
        raw = recommendation.get("recommendation_reason")
    return _clean_str(raw)


def _recommendation_triggers(recommendation: Mapping[str, Any]) -> tuple[str, ...]:
    raw = recommendation.get("triggers")
    if raw is None:
        raw = recommendation.get("recommendation_triggers")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(text for text in (_clean_str(item) for item in raw) if text)


def is_recommendation_valid(
    recommendation: Mapping[str, Any] | None,
    *,
    current_training_day: date | str,
) -> bool:
    """True only when the recommendation is for the current training day."""
    if not recommendation:
        return False
    rec_day = _recommendation_day(recommendation)
    if not rec_day:
        return False
    if _recommendation_decision(recommendation) not in LIVE_RECOMMENDATION_STATES:
        return False
    return rec_day == _as_iso(current_training_day)


def resolve_recommendation_state(
    recommendation: Mapping[str, Any] | None,
    *,
    current_training_day: date | str,
) -> RecommendationView:
    """Resolve the live readiness state for the current training day.

    Returns ``not_checked_in`` (with ``reason=None``) whenever no valid
    recommendation exists. When a stored recommendation has expired, the view
    still reports ``not_checked_in`` but flags ``is_history`` so the consumer can
    label and show it as history rather than current readiness.
    """
    if not recommendation:
        return RecommendationView(
            state="not_checked_in",
            reason=None,
            training_day=None,
            is_history=False,
        )

    rec_day = _recommendation_day(recommendation)
    decision = _recommendation_decision(recommendation)
    reason = _recommendation_reason(recommendation)

    if is_recommendation_valid(recommendation, current_training_day=current_training_day):
        return RecommendationView(
            state=decision,  # type: ignore[arg-type]  # narrowed by is_recommendation_valid
            reason=reason,
            training_day=rec_day,
            is_history=False,
            triggers=_recommendation_triggers(recommendation),
        )

    # Stored but not current: expired (or malformed). Never surface as live
    # readiness; expose only as labelled history.
    return RecommendationView(
        state="not_checked_in",
        reason=None,
        training_day=rec_day,
        is_history=bool(rec_day),
        history_reason=reason if rec_day else None,
    )
