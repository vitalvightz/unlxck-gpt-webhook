"""Readiness/fatigue status and the safe (non-AI) adaptation rules layer.

Everything in this module is a pure function over plain dicts/records so it can
be unit-tested without a store or app. The route layer (api/routes/daily.py)
is responsible for persisting the resulting decisions as ``adaptation_notes``
rows and opening ``admin_reviews`` when a decision asks for one — adjustments
are always recorded as history, never silent plan mutations.

Rule set (deliberately conservative, Phase 1):

* open injury flag (or an injury reported on today's check-in) -> ``injury_flag``
  state, suggest a session swap, and flag for admin review
* high self-reported fatigue/soreness, very low readiness, or badly broken
  sleep -> ``high_fatigue`` state, reduce intensity + add recovery
* moderate signals -> ``caution`` state (monitor, no change)
* repeated high RPE (>= HIGH_RPE_THRESHOLD on the last
  HIGH_RPE_STREAK_LENGTH completed sessions) -> reduce intensity
* repeated missed sessions in the last 7 logged days -> keep plan but record a
  schedule note; at MISSED_SESSIONS_REVIEW_THRESHOLD missed, flag admin review
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .models import AdaptationDecisionValue, ReadinessState, ReadinessSummary

HIGH_RPE_THRESHOLD = 8
HIGH_RPE_STREAK_LENGTH = 3
MISSED_SESSIONS_CAUTION_THRESHOLD = 2
MISSED_SESSIONS_REVIEW_THRESHOLD = 3

READINESS_STATE_LABELS: dict[str, str] = {
    "ready": "Ready",
    "caution": "Caution",
    "high_fatigue": "High Fatigue",
    "injury_flag": "Injury Flag",
}


@dataclass(frozen=True)
class AdaptationDecision:
    """One rule outcome, persisted by the caller as an adaptation_notes row."""

    rule_code: str
    decision: AdaptationDecisionValue
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    requires_admin_review: bool = False


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _checkin_fatigue_signals(checkin: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Return (high_signals, caution_signals) from one check-in's 1-5 scales."""
    high: list[str] = []
    caution: list[str] = []

    readiness = _int_or_none(checkin.get("readiness"))
    fatigue = _int_or_none(checkin.get("fatigue"))
    soreness = _int_or_none(checkin.get("soreness"))
    sleep_quality = _int_or_none(checkin.get("sleep_quality"))
    sleep_hours_raw = checkin.get("sleep_hours")
    try:
        sleep_hours = float(sleep_hours_raw) if sleep_hours_raw is not None else None
    except (TypeError, ValueError):
        sleep_hours = None

    if fatigue is not None and fatigue >= 4:
        high.append(f"Fatigue reported at {fatigue}/5")
    elif fatigue == 3:
        caution.append("Moderate fatigue (3/5)")

    if soreness is not None and soreness >= 4:
        high.append(f"Soreness reported at {soreness}/5")
    elif soreness == 3:
        caution.append("Moderate soreness (3/5)")

    if readiness is not None and readiness <= 2:
        high.append(f"Self-rated readiness at {readiness}/5")
    elif readiness == 3:
        caution.append("Middling self-rated readiness (3/5)")

    if sleep_quality is not None and sleep_quality <= 2:
        if sleep_hours is not None and sleep_hours < 6:
            high.append(f"Poor sleep ({sleep_quality}/5 quality, {sleep_hours:g}h)")
        else:
            caution.append(f"Poor sleep quality ({sleep_quality}/5)")

    return high, caution


def count_recent_high_rpe(session_logs: Sequence[Mapping[str, Any]]) -> int:
    """Length of the high-RPE streak over the most recent completed sessions.

    ``session_logs`` must be ordered most-recent-first (the store's order).
    Only the last HIGH_RPE_STREAK_LENGTH completed sessions are considered,
    and the streak breaks on the first one below the threshold.
    """
    streak = 0
    considered = 0
    for log in session_logs:
        if not log.get("completed", True):
            continue
        considered += 1
        rpe = _int_or_none(log.get("rpe"))
        if rpe is not None and rpe >= HIGH_RPE_THRESHOLD:
            streak += 1
        else:
            break
        if considered >= HIGH_RPE_STREAK_LENGTH:
            break
    return streak


def count_recent_missed_sessions(session_logs: Sequence[Mapping[str, Any]]) -> int:
    """Number of logs explicitly marked not-completed (caller scopes the window)."""
    return sum(1 for log in session_logs if log.get("completed") is False)


def compute_readiness_summary(
    *,
    latest_checkin: Mapping[str, Any] | None,
    open_injury_flag_count: int,
    recent_session_logs: Sequence[Mapping[str, Any]] = (),
) -> ReadinessSummary:
    """Current Ready / Caution / High Fatigue / Injury Flag status."""
    reasons: list[str] = []
    state: ReadinessState = "ready"

    high_signals: list[str] = []
    caution_signals: list[str] = []
    if latest_checkin:
        high_signals, caution_signals = _checkin_fatigue_signals(latest_checkin)

    high_rpe_streak = count_recent_high_rpe(recent_session_logs)
    missed = count_recent_missed_sessions(recent_session_logs)
    if high_rpe_streak >= HIGH_RPE_STREAK_LENGTH:
        caution_signals.append(
            f"RPE >= {HIGH_RPE_THRESHOLD} on the last {high_rpe_streak} completed sessions"
        )
    if missed >= MISSED_SESSIONS_CAUTION_THRESHOLD:
        caution_signals.append(f"{missed} missed sessions in the recent log window")

    if open_injury_flag_count > 0:
        state = "injury_flag"
        plural = "s" if open_injury_flag_count != 1 else ""
        reasons.append(f"{open_injury_flag_count} open injury flag{plural}")
        reasons.extend(high_signals)
    elif high_signals:
        state = "high_fatigue"
        reasons.extend(high_signals)
    elif caution_signals:
        state = "caution"
        reasons.extend(caution_signals)
    elif latest_checkin is None:
        state = "caution"
        reasons.append("No check-in yet — submit today's check-in for an accurate status")

    return ReadinessSummary(
        state=state,
        label=READINESS_STATE_LABELS[state],
        reasons=reasons,
    )


def evaluate_checkin_adaptations(
    *,
    checkin: Mapping[str, Any],
    open_injury_flag_count: int,
) -> list[AdaptationDecision]:
    """Safe rule decisions to record when a daily check-in is submitted."""
    decisions: list[AdaptationDecision] = []
    high_signals, _ = _checkin_fatigue_signals(checkin)
    injury_note = str(checkin.get("injury_note") or "").strip()

    if injury_note:
        decisions.append(
            AdaptationDecision(
                rule_code="injury_reported",
                decision="swap_session",
                summary=(
                    "Injury reported on check-in — substitute or skip drills that load the "
                    "affected area until reviewed"
                ),
                details={"injury_note": injury_note},
                requires_admin_review=True,
            )
        )
        decisions.append(
            AdaptationDecision(
                rule_code="injury_reported",
                decision="flag_admin_review",
                summary="Injury report needs coach review before the next hard session",
                details={"injury_note": injury_note},
                requires_admin_review=True,
            )
        )
    elif open_injury_flag_count > 0:
        decisions.append(
            AdaptationDecision(
                rule_code="open_injury_flag",
                decision="swap_session",
                summary="Open injury flag — keep substitutions in place for the affected area",
                details={"open_injury_flag_count": open_injury_flag_count},
            )
        )

    if high_signals:
        decisions.append(
            AdaptationDecision(
                rule_code="high_fatigue_reduce_load",
                decision="reduce_intensity",
                summary="High fatigue signals — reduce today's intensity/volume by one notch",
                details={"signals": high_signals},
            )
        )
        decisions.append(
            AdaptationDecision(
                rule_code="high_fatigue_add_recovery",
                decision="add_recovery",
                summary="Add a recovery block (mobility, easy aerobic flush, extra sleep) today",
                details={"signals": high_signals},
            )
        )

    if not decisions:
        decisions.append(
            AdaptationDecision(
                rule_code="checkin_ok",
                decision="keep_plan",
                summary="Check-in within normal ranges — plan unchanged",
            )
        )
    return decisions


def evaluate_session_log_adaptations(
    *,
    log: Mapping[str, Any],
    recent_session_logs: Sequence[Mapping[str, Any]],
) -> list[AdaptationDecision]:
    """Safe rule decisions to record when a session log is submitted.

    ``recent_session_logs`` must include the new log, most-recent-first.
    """
    decisions: list[AdaptationDecision] = []

    high_rpe_streak = count_recent_high_rpe(recent_session_logs)
    if high_rpe_streak >= HIGH_RPE_STREAK_LENGTH:
        decisions.append(
            AdaptationDecision(
                rule_code="repeated_high_rpe",
                decision="reduce_intensity",
                summary=(
                    f"RPE >= {HIGH_RPE_THRESHOLD} on {high_rpe_streak} consecutive sessions — "
                    "cap the next session's intensity and monitor"
                ),
                details={"streak": high_rpe_streak, "threshold": HIGH_RPE_THRESHOLD},
            )
        )

    missed = count_recent_missed_sessions(recent_session_logs)
    if missed >= MISSED_SESSIONS_REVIEW_THRESHOLD:
        decisions.append(
            AdaptationDecision(
                rule_code="missed_sessions",
                decision="flag_admin_review",
                summary=(
                    f"{missed} missed sessions in the recent window — coach should review the "
                    "schedule fit"
                ),
                details={"missed": missed},
                requires_admin_review=True,
            )
        )
    elif missed >= MISSED_SESSIONS_CAUTION_THRESHOLD:
        decisions.append(
            AdaptationDecision(
                rule_code="missed_sessions",
                decision="keep_plan",
                summary=(
                    f"{missed} missed sessions recently — keep the plan but tighten the next "
                    "week's scheduling"
                ),
                details={"missed": missed},
            )
        )

    if not decisions:
        decisions.append(
            AdaptationDecision(
                rule_code="session_logged",
                decision="keep_plan",
                summary="Session logged within normal ranges — plan unchanged",
            )
        )
    return decisions
