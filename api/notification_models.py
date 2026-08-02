from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

NotificationCategory = Literal[
    "session_reminders",
    "checkin_reminders",
    "injury_followups",
    "plan_update_alerts",
    "progress_milestones",
    "coach_messages",
]

_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class NotificationPreferences(BaseModel):
    push_enabled: bool = True
    session_reminders: bool = True
    checkin_reminders: bool = True
    injury_followups: bool = True
    plan_update_alerts: bool = True
    progress_milestones: bool = True
    coach_messages: bool = True
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"

    @field_validator("quiet_hours_start", "quiet_hours_end", mode="before")
    @classmethod
    def normalize_time(cls, value: Any) -> str:
        text = str(value or "").strip()
        if len(text) >= 5:
            text = text[:5]
        if not _TIME_PATTERN.fullmatch(text):
            raise ValueError("quiet hours must use 24-hour HH:MM format")
        return text


class NotificationPreferencesUpdate(BaseModel):
    push_enabled: bool | None = None
    session_reminders: bool | None = None
    checkin_reminders: bool | None = None
    injury_followups: bool | None = None
    plan_update_alerts: bool | None = None
    progress_milestones: bool | None = None
    coach_messages: bool | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None

    @field_validator("quiet_hours_start", "quiet_hours_end", mode="before")
    @classmethod
    def normalize_optional_time(cls, value: Any) -> str | None:
        if value is None:
            return None
        return NotificationPreferences.normalize_time(value)


class PushSettingsResponse(BaseModel):
    enabled: bool
    public_key: str = ""
    preferences: NotificationPreferences = Field(default_factory=NotificationPreferences)
