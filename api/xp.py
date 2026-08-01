"""Server-owned XP configuration and daily award orchestration.

The public HTTP route exposes only the daily-login claim. Other actions are
defined here and in the database ledger so trusted server integrations can add
them later without giving the browser a generic score-writing endpoint.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Protocol

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - zoneinfo ships with supported Python.
    ZoneInfo = None  # type: ignore[assignment]


XpAction = Literal[
    "daily_login",
    "training_logged",
    "planned_session_completed",
    "recommended_fighter_content_watched",
    "full_training_week_completed",
]

XP_REWARD_AMOUNTS: dict[XpAction, int] = {
    "daily_login": 10,
    "training_logged": 25,
    "planned_session_completed": 50,
    "recommended_fighter_content_watched": 10,
    "full_training_week_completed": 100,
}


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
    """Resolve an account day without accepting a browser-supplied date."""

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
    calendar_date = resolve_xp_calendar_date(athlete_timezone, now=now).isoformat()
    return store.award_xp(
        athlete_id,
        action="daily_login",
        idempotency_key=f"daily-login:{calendar_date}",
        calendar_date=calendar_date,
    )
