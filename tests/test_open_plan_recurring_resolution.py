import copy
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from api.models import WeeklySchedule
from api.services.plan_schedule import resolve_current_week, resolve_today_and_next
from api.services.open_plan_timeline import project_open_structured_plan
from api.services.today_service import (
    build_today_command_view,
    _structured_next_session_entry,
    _structured_today_session_entry,
    upsert_session_completion,
)
from fightcamp.weekly_schedule_view import extract_weekly_schedule
from tests.support import FakeStore


PLAN_ID = "11111111-1111-1111-1111-111111111111"


def _open_plan_brief(*, plan_creation_weekday: str | None = None):
    brief = {
        "open_plan_spec": {
            "plan_type": "open_ongoing_system",
            "weekly_template": {
                "training_days": ["Monday", "Wednesday", "Friday", "Saturday", "Tuesday"],
                "hard_sparring_days": ["Wednesday", "Friday"],
                "coach_owned_days": {
                    "technical_skill_days": ["Tuesday"],
                    "hard_sparring_days": ["Wednesday", "Friday"],
                },
            },
            "development_block": {
                "week_1": "Baseline",
                "week_2": "Progress",
                "week_3": "Highest controlled week",
                "week_4": "Deload and reassess",
            },
        },
        "stage1_selection_summary": {"current_phase": "GPP"},
    }
    if plan_creation_weekday:
        brief["athlete_snapshot"] = {
            "plan_creation_weekday": plan_creation_weekday,
            "plan_creation_weekday_basis": "athlete_local_weekday",
        }
    return brief


def test_open_plan_sunday_wraps_to_monday_from_full_seven_day_schedule():
    planning_brief = _open_plan_brief()

    schedule_data = extract_weekly_schedule(planning_brief, week_index=0)

    assert schedule_data is not None
    week = WeeklySchedule(plan_id=PLAN_ID, **schedule_data)
    assert [entry.weekday for entry in week.days] == [
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
        "Sat",
        "Sun",
    ]

    today_entry, next_entry = resolve_today_and_next(week, today=date(2026, 7, 12))

    assert today_entry is not None
    assert today_entry.weekday == "Sun"
    assert today_entry.effective_load == "none"
    assert next_entry is not None
    assert next_entry.weekday == "Mon"
    assert next_entry.title == "Mon training"


def test_open_plan_starts_the_next_four_week_cycle_after_week_four():
    plan_row = {
        "id": PLAN_ID,
        # Wednesday 1 July, so the block anchors to Monday 29 June.
        "created_at": "2026-07-01T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    # 44 days after the anchor = elapsed week 6, i.e. week 3 of the second block.
    week_index, week = resolve_current_week(plan_row, today=date(2026, 8, 12))

    assert week_index == 2
    assert week is not None
    assert week.week_index == 2
    assert week.day_label == "Development week 3"


def _open_structured_plan():
    def app_day(title: str):
        return {
            "date": "",
            "today_card": {"headline": title},
            "sessions": [{"title": title, "blocks": [{"display_name": "Main work"}]}],
        }

    def coach_day():
        return {
            "date": "",
            "today_card": {"headline": "Coach-led boxing"},
            "sessions": [],
        }

    days = [
        app_day("Support strength"),
        app_day("Technical rhythm"),
        coach_day(),
        coach_day(),
        app_day("Power transfer"),
    ]
    return {
        "weeks": [
            {"week_index": index, "days": [dict(day) for day in days]}
            for index in range(1, 5)
        ]
    }


def test_open_plan_projects_weekdays_and_dates_from_the_block_anchor():
    plan_row = {
        "id": PLAN_ID,
        # Sunday 12 July: too late to join that week, so the block starts on the
        # coming Monday.
        "created_at": "2026-07-12T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    projected, context = project_open_structured_plan(
        plan_row,
        _open_structured_plan(),
        current_training_day="2026-07-13",
    )

    assert context == {
        "schedule_mode": "open_recurring",
        "projection_status": "projected",
        "anchor_date": "2026-07-13",
        "current_training_day": "2026-07-13",
        "block_number": 1,
        "current_week_number": 1,
    }
    assert [day["weekday"] for day in projected["weeks"][0]["days"]] == [
        "Mon",
        "Tue",
        "Wed",
        "Fri",
        "Sat",
    ]
    assert [day["date"] for day in projected["weeks"][0]["days"]] == [
        "2026-07-13",
        "2026-07-14",
        "2026-07-15",
        "2026-07-17",
        "2026-07-18",
    ]
    assert all(not day["countdown_label"] for day in projected["weeks"][0]["days"])


def test_open_plan_created_midweek_starts_in_the_week_it_was_created():
    """A Mon-Thu plan is live the day it is generated.

    Anchoring forward to the *next* Monday left the athlete with a dormant plan
    for the rest of the week, and put every projected date a week ahead of the
    live training day — so the plan view showed next week's dates while nothing
    on it matched today.
    """

    plan_row = {
        "id": PLAN_ID,
        # Wednesday 29 July.
        "created_at": "2026-07-29T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    projected, context = project_open_structured_plan(
        plan_row,
        _open_structured_plan(),
        current_training_day="2026-07-31",
    )

    assert context["anchor_date"] == "2026-07-27"
    assert context["block_number"] == 1
    assert context["current_week_number"] == 1
    # Friday 31 July is a real row of week 1, not a date the athlete has to wait
    # a week to reach.
    assert "2026-07-31" in [day["date"] for day in projected["weeks"][0]["days"]]


def test_open_plan_created_late_in_the_week_starts_the_following_monday():
    plan_row = {
        "id": PLAN_ID,
        # Friday 31 July: only the weekend is left, so week 1 starts on 3 August.
        "created_at": "2026-07-31T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    _, context = project_open_structured_plan(
        plan_row,
        _open_structured_plan(),
        current_training_day="2026-07-31",
    )

    assert context["anchor_date"] == "2026-08-03"
    assert context["current_week_number"] == 1


def test_open_plan_before_start_surfaces_monday_as_next_not_future_saturday_as_today():
    structured_plan = _open_structured_plan()
    future_saturday = structured_plan["weeks"][0]["days"][-1]
    future_saturday["today_card"]["headline"] = "Fight-Pace Conditioning and Neural Primer"
    future_saturday["sessions"][0]["title"] = "Fight-Pace Conditioning and Neural Primer"
    plan_row = {
        "id": PLAN_ID,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Open plan",
        # Friday 31 July: the block starts on Monday 3 August.
        "created_at": "2026-07-31T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
        "structured_plan": structured_plan,
    }
    store = FakeStore()
    store.plans[PLAN_ID] = plan_row

    view = build_today_command_view(
        store,
        athlete_id="athlete-1",
        athlete_timezone="",
        now=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert view.today.training_day == "2026-08-01"
    assert view.today.session_scope == "next"
    assert view.today.next_session["session_relation"] == "next"
    assert view.today.next_session["calendar_date"] == "2026-08-03"
    assert view.today.next_session["title"] == "Support strength"

    with pytest.raises(HTTPException) as exc:
        upsert_session_completion(
            store,
            athlete_id="athlete-1",
            athlete_timezone="",
            payload={
                "plan_id": PLAN_ID,
                "session_id": "2026-08-08",
                "status": "started",
            },
            now=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
        )
    assert exc.value.status_code == 409
    assert "has not started" in str(exc.value.detail)


def test_open_plan_uses_local_thursday_when_utc_date_is_already_friday():
    plan_row = {
        "id": PLAN_ID,
        # 00:30 UTC Friday is still Thursday for an athlete west of UTC.
        "created_at": "2026-07-31T00:30:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(plan_creation_weekday="thursday"),
    }

    _, context = project_open_structured_plan(
        plan_row,
        _open_structured_plan(),
        current_training_day="2026-07-30",
    )

    # Thursday joins the current week rather than being delayed until 3 August.
    assert context["anchor_date"] == "2026-07-27"


def test_open_plan_uses_local_friday_when_utc_date_is_still_thursday():
    plan_row = {
        "id": PLAN_ID,
        # 23:30 UTC Thursday is already Friday for an athlete east of UTC.
        "created_at": "2026-07-30T23:30:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(plan_creation_weekday="friday"),
    }

    _, context = project_open_structured_plan(
        plan_row,
        _open_structured_plan(),
        current_training_day="2026-07-31",
    )

    # Friday is too late to join, so the block starts the coming Monday.
    assert context["anchor_date"] == "2026-08-03"


def test_open_plan_recovers_one_full_calendar_legacy_week_and_expands_the_block():
    plan_row = {
        "id": PLAN_ID,
        "created_at": "2026-07-12T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }
    structured = _open_structured_plan()
    base_week = copy.deepcopy(structured["weeks"][0])
    training_days = base_week["days"]

    def off_day(label: str):
        return {
            "date": "",
            "weekday": None,
            "day_type": "rest",
            "today_card": {"headline": label},
            "sessions": [],
        }

    # Historical open-card conversion emitted Monday-Sunday including the two
    # OFF days, but omitted every weekday field. Those empty off slots make this
    # seven-day ordering safe to recover without assigning work heuristically.
    base_week["days"] = [
        training_days[0],
        training_days[1],
        training_days[2],
        off_day("Thursday off"),
        training_days[3],
        training_days[4],
        off_day("Sunday off"),
    ]
    structured["weeks"] = [base_week]

    projected, context = project_open_structured_plan(
        plan_row,
        structured,
        current_training_day="2026-07-13",
    )

    assert context["projection_status"] == "projected"
    assert len(projected["weeks"]) == 4
    assert [day["weekday"] for day in projected["weeks"][0]["days"]] == [
        "Mon",
        "Tue",
        "Wed",
        "Fri",
        "Sat",
    ]
    assert [week["week_index"] for week in projected["weeks"]] == [1, 2, 3, 4]
    assert [week["week_goal"] for week in projected["weeks"]] == [
        "Baseline",
        "Progress",
        "Highest controlled week",
        "Deload and reassess",
    ]
    assert projected["weeks"][0]["days"][0]["date"] == "2026-07-13"
    assert projected["weeks"][3]["days"][0]["date"] == "2026-08-03"


def test_open_plan_projects_the_current_repeating_block_without_date_collisions():
    plan_row = {
        "id": PLAN_ID,
        "created_at": "2026-07-12T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    projected, context = project_open_structured_plan(
        plan_row,
        _open_structured_plan(),
        current_training_day="2026-08-10",
    )

    assert context["block_number"] == 2
    assert context["current_week_number"] == 1
    assert projected["weeks"][0]["days"][0]["date"] == "2026-08-10"


def test_open_plan_does_not_guess_when_legacy_day_count_is_ambiguous():
    plan_row = {
        "created_at": "2026-07-12T09:00:00+00:00",
        "planning_brief": _open_plan_brief(),
    }
    structured = _open_structured_plan()
    structured["weeks"][0]["days"].pop()

    projected, context = project_open_structured_plan(
        plan_row,
        structured,
        current_training_day="2026-07-13",
    )

    assert context["projection_status"] == "unavailable"
    assert projected["weeks"][0]["days"][0].get("date") == ""


def test_today_and_plan_detail_use_the_same_projected_open_plan_sessions():
    plan_row = {
        "id": PLAN_ID,
        "created_at": "2026-07-12T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
        "structured_plan": _open_structured_plan(),
    }

    today_entry = _structured_today_session_entry(plan_row, "2026-07-13")
    next_entry = _structured_next_session_entry(plan_row, "2026-07-12")

    assert today_entry is not None
    assert today_entry["calendar_date"] == "2026-07-13"
    assert today_entry["title"] == "Support strength"
    assert next_entry is not None
    assert next_entry["calendar_date"] == "2026-07-13"
    assert next_entry["session_id"] == today_entry["session_id"]


def test_undated_legacy_schedule_still_clamps_to_its_final_week():
    plan_row = {
        "id": PLAN_ID,
        "created_at": "2026-07-01T09:00:00+00:00",
        "planning_brief": {
            "weekly_role_map": {
                "weeks": [
                    {"phase": "GPP", "hard_sparring_plan": []},
                    {"phase": "SPP", "hard_sparring_plan": []},
                ]
            }
        },
    }

    week_index, week = resolve_current_week(plan_row, today=date(2026, 8, 20))

    assert week_index == 1
    assert week is not None
    assert week.phase == "SPP"
