from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from api.services.effective_structured_plan import resolve_effective_structured_plan
from api.services.session_timing_notifications import build_session_timing_candidates_from_view
from api.services.today_service import build_today_command_view, upsert_session_completion
from api.services.xp_progress import _RecordRead, _opportunities
from api.notification_models import NotificationPreferences
from tests.support import FakeStore
from tests.test_structured_plan_models import _valid_plan


ATHLETE = "effective-plan-athlete"
PLAN = "22222222-2222-2222-2222-222222222222"


def _production_calendar() -> dict:
    plan = _valid_plan()
    week = copy.deepcopy(plan["weeks"][0])
    template = week["days"][0]

    def day(date: str, countdown: str, title: str | None) -> dict:
        row = copy.deepcopy(template)
        row["date"] = date
        row["countdown_label"] = countdown
        row["weekday"] = datetime.fromisoformat(date).strftime("%a")
        if title is None:
            row["day_type"] = "rest"
            row["sessions"] = []
            row["today_card"]["headline"] = "Rest"
        else:
            row["day_type"] = "moderate"
            row["sessions"] = [copy.deepcopy(template["sessions"][0])]
            row["sessions"][0]["session_id"] = f"{date}-{title.lower().replace(' ', '-')}"
            row["sessions"][0]["title"] = title
            row["today_card"]["headline"] = title
        return row

    week["days"] = [
        day("2026-09-14", "D-38", None),
        day("2026-09-15", "D-37", "Aerobic support"),
        day("2026-09-21", "D-31", "Hard sparring"),
    ]
    week["start_date"] = "2026-09-14"
    week["end_date"] = "2026-09-21"
    plan["weeks"] = [week]
    return plan


def test_effective_resolver_prefers_stored_then_reconstructs_and_fails_safe(monkeypatch):
    stored = _valid_plan()
    rebuilt = _production_calendar()
    calls = []

    def build(brief):
        calls.append(brief)
        return rebuilt

    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan", build
    )
    assert resolve_effective_structured_plan({"structured_plan": stored}) == stored
    assert calls == []
    brief = {"hard_sparring_days": ["Monday"]}
    assert resolve_effective_structured_plan(
        {"structured_plan": None, "planning_brief": brief}
    ) == rebuilt
    assert calls == [brief]

    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan",
        lambda _brief: None,
    )
    assert resolve_effective_structured_plan({"structured_plan": None}) is None


def test_missing_card_uses_canonical_calendar_across_today_xp_and_notifications(monkeypatch):
    calendar = _production_calendar()
    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan",
        lambda _brief: calendar,
    )
    store = FakeStore()
    store.plans[PLAN] = {
        "id": PLAN,
        "athlete_id": ATHLETE,
        "status": "ready",
        "name": "September camp",
        "fight_date": "2026-10-22",
        "created_at": "2026-09-14T08:00:00+00:00",
        "structured_plan": None,
        "planning_brief": {"hard_sparring_days": ["Monday"]},
        "weekly_schedule": {
            "Monday": {"title": "Hard sparring", "session_type": "sparring"}
        },
    }
    store.set_active_plan_id(ATHLETE, PLAN)

    monday = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="UTC", now=monday)
    assert view.today.next_session.get("title") == "Aerobic support"
    assert view.today.session_scope == "next"
    assert view.today.completion_status == "not_started"

    with pytest.raises(HTTPException):
        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="UTC",
            payload={"plan_id": PLAN, "session_id": "hard-sparring", "status": "started"},
            now=monday,
        )

    opportunities = _opportunities(
        store,
        athlete_id=ATHLETE,
        profile=object(),
        latest_intake=_RecordRead("ok", {}),
        latest_plan=_RecordRead("ok", store.plans[PLAN]),
        command=view,
        current_week=None,
    )
    assert "complete_today_session" not in {row["code"] for row in opportunities}
    candidates = build_session_timing_candidates_from_view(
        view,
        NotificationPreferences(preferred_training_time="12:00"),
        profile_id=ATHLETE,
        timezone_name="UTC",
        now_utc=monday,
        store=store,
    )
    assert all("hard spar" not in f"{row.title} {row.body}".lower() for row in candidates)

    tuesday = build_today_command_view(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="UTC",
        now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
    )
    assert tuesday.today.session_scope == "today"
    assert tuesday.today.next_session["title"] == "Aerobic support"

    d31 = build_today_command_view(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="UTC",
        now=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
    )
    assert d31.today.session_scope == "today"
    assert d31.today.next_session["title"] == "Hard sparring"


def test_populated_structured_plan_is_unchanged(monkeypatch):
    stored = _production_calendar()
    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan",
        lambda _brief: pytest.fail("stored structured plan must win"),
    )
    assert resolve_effective_structured_plan(
        {"structured_plan": stored, "planning_brief": {"hard_sparring_days": ["Monday"]}}
    ) == stored
