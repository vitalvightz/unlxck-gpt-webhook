"""Server-owned XP configuration and award orchestration."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Protocol

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


XpAction = Literal[
    "daily_login",
    "training_logged",
    "planned_session_completed",
    "recommended_fighter_content_watched",
    "full_training_week_completed",
    "profile_completed",
    "first_intake_completed",
    "first_plan_ready",
    "first_checkin_completed",
    "readiness_checkin_completed",
    "injury_update_completed",
    "stop_decision_followed",
    "feedback_submitted",
    "feedback_with_comment",
    "first_plan_completed",
    "phase_completed",
    "camp_completed",
]

XP_REWARD_AMOUNTS: dict[XpAction, int] = {
    "daily_login": 0,
    "training_logged": 25,
    "planned_session_completed": 50,
    "recommended_fighter_content_watched": 10,
    "full_training_week_completed": 100,
    "profile_completed": 25,
    "first_intake_completed": 50,
    "first_plan_ready": 100,
    "first_checkin_completed": 25,
    "readiness_checkin_completed": 10,
    "injury_update_completed": 10,
    "stop_decision_followed": 15,
    "feedback_submitted": 1,
    "feedback_with_comment": 3,
    "first_plan_completed": 250,
    "phase_completed": 200,
    "camp_completed": 500,
}

# Mirrors the xp_awards_calendar_scope_check constraint: these actions must
# carry a calendar_date and every other action must leave it null.
XP_CALENDAR_SCOPED_ACTIONS: frozenset[str] = frozenset(
    {
        "daily_login",
        "training_logged",
        "planned_session_completed",
        "full_training_week_completed",
        "readiness_checkin_completed",
        "injury_update_completed",
        "stop_decision_followed",
        "feedback_submitted",
        "feedback_with_comment",
    }
)


class XpAwardStore(Protocol):
    def award_xp(
        self,
        athlete_id: str,
        *,
        action: XpAction,
        idempotency_key: str,
        calendar_date: str | None = None,
    ) -> dict: ...


def resolve_xp_calendar_date(
    athlete_timezone: str | None,
    *,
    now: datetime | None = None,
) -> date:
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    zone_name = str(athlete_timezone or "").strip()
    if zone_name and ZoneInfo is not None:
        try:
            return reference.astimezone(ZoneInfo(zone_name)).date()
        except (KeyError, ValueError):
            pass
    return reference.astimezone(timezone.utc).date()


def claim_daily_login_reward(
    store: XpAwardStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
) -> dict:
    """Retained for API compatibility; daily-login XP is retired."""

    calendar_date = resolve_xp_calendar_date(athlete_timezone, now=now).isoformat()
    return store.award_xp(
        athlete_id,
        action="daily_login",
        idempotency_key=f"daily-login-retired:{calendar_date}",
        calendar_date=calendar_date,
    )
