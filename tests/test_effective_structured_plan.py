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

    def build(brief, plan_text=None):
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

    for unusable in ({"weeks": []}, {"weeks": [{"days": [{"weekday": "Monday"}]}]}):
        assert resolve_effective_structured_plan(
            {"structured_plan": unusable, "planning_brief": brief}
        ) == rebuilt
    assert calls == [brief, brief, brief]

    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan",
        lambda _brief, plan_text=None: None,
    )
    assert resolve_effective_structured_plan({"structured_plan": None}) is None


def test_missing_card_uses_canonical_calendar_across_today_xp_and_notifications(monkeypatch):
    calendar = _production_calendar()
    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan",
        lambda _brief, plan_text=None: calendar,
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


def test_rebuilt_card_reads_the_same_plan_text_on_every_surface(monkeypatch):
    """Today/progress pass no markdown; they must still get the row's plan text."""
    seen = []

    def build(_brief, plan_text=None):
        seen.append(plan_text)
        return _production_calendar()

    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan", build
    )
    row = {
        "structured_plan": None,
        "planning_brief": {"hard_sparring_days": ["Monday"]},
        "plan_text": "D-17 — Flush\n- Tempo Shadowboxing: duration 20 min.",
        "final_plan_text": "held for review",
    }
    resolve_effective_structured_plan(row)
    resolve_effective_structured_plan(row, raw_markdown=row["plan_text"])
    # A held plan shows no text, so its unreleased Stage 2 copy is never read.
    resolve_effective_structured_plan({**row, "plan_text": ""})

    assert seen == [row["plan_text"], row["plan_text"], None]


def test_populated_structured_plan_is_unchanged(monkeypatch):
    stored = _production_calendar()
    monkeypatch.setattr(
        "api.services.effective_structured_plan.build_deterministic_structured_plan",
        lambda _brief, plan_text=None: pytest.fail("stored structured plan must win"),
    )
    assert resolve_effective_structured_plan(
        {"structured_plan": stored, "planning_brief": {"hard_sparring_days": ["Monday"]}}
    ) == stored


def _idless_sparring_day_calendar() -> dict:
    """Production shape from 2026-09-25: the converter emitted ``session_id: null``
    for a Breathing Reset placed on the athlete's declared hard-sparring day."""
    plan = _production_calendar()
    day = plan["weeks"][0]["days"][2]
    day["sessions"][0]["session_id"] = None
    day["sessions"][0]["title"] = "Breathing Reset"
    day["sessions"].append(copy.deepcopy(day["sessions"][0]))
    day["today_card"]["headline"] = "Hard sparring"
    day["today_card"]["coach_led_contact"] = "Hard sparring"
    return plan


def test_idless_sessions_get_stable_plan_scoped_ids_without_mutating_the_card():
    from api.services.effective_structured_plan import ensure_structured_session_ids

    stored = _idless_sparring_day_calendar()
    before = copy.deepcopy(stored)
    row = {"id": PLAN, "structured_plan": stored}

    first = resolve_effective_structured_plan(row)
    second = resolve_effective_structured_plan(copy.deepcopy(row))
    ids = [s["session_id"] for s in first["weeks"][0]["days"][2]["sessions"]]

    # Every reader derives the same ids; a repeated title on one day stays unique.
    assert ids == [s["session_id"] for s in second["weeks"][0]["days"][2]["sessions"]]
    assert ids == [
        "ses-22222222-2026-09-21-breathing-reset",
        "ses-22222222-2026-09-21-breathing-reset-2",
    ]
    # Explicit ids are never rewritten, and the stored card is untouched.
    assert first["weeks"][0]["days"][1]["sessions"][0]["session_id"] == "2026-09-15-aerobic-support"
    assert stored == before
    # A regenerated plan cannot collide with the old plan's completion rows.
    other = resolve_effective_structured_plan({"id": "33333333-0000", "structured_plan": stored})
    assert other["weeks"][0]["days"][2]["sessions"][0]["session_id"].startswith("ses-33333333-")
    # Undated weekday templates fall back to their week/day slot.
    template = copy.deepcopy(stored)
    template["weeks"][0]["days"][2]["date"] = None
    slotted = ensure_structured_session_ids(template, plan_id=PLAN)
    assert slotted["weeks"][0]["days"][2]["sessions"][0]["session_id"] == (
        "ses-22222222-w1d3-breathing-reset"
    )


def test_idless_session_on_declared_sparring_day_is_startable_and_counts(monkeypatch):
    from api.services.week_progress import evaluate_week_completion, find_week_for_training_day

    store = FakeStore()
    store.plans[PLAN] = {
        "id": PLAN,
        "athlete_id": ATHLETE,
        "status": "ready",
        "name": "September camp",
        "fight_date": "2026-10-22",
        "created_at": "2026-09-14T08:00:00+00:00",
        "structured_plan": _idless_sparring_day_calendar(),
        "planning_brief": {"hard_sparring_days": ["Monday"]},
    }
    store.set_active_plan_id(ATHLETE, PLAN)
    monday = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)

    view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="UTC", now=monday)
    session_id = view.today.next_session.get("session_id")
    assert view.today.session_scope == "today"
    assert session_id == "ses-22222222-2026-09-21-breathing-reset"
    assert view.today.next_session.get("coach_led_contact") == "Hard sparring"

    upsert_session_completion(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="UTC",
        payload={"plan_id": PLAN, "session_id": session_id, "status": "started"},
        now=monday,
    )
    after = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="UTC", now=monday)
    assert after.today.completion_status == "started"

    # Week progress sees the derived ids too, so the idless work is planned work.
    week = find_week_for_training_day(store.plans[PLAN], "2026-09-21")
    result = evaluate_week_completion(week=week, completions=[])
    assert result["planned"] == 3
    assert "ses-22222222-2026-09-21-breathing-reset" in result["unresolved_session_ids"]
