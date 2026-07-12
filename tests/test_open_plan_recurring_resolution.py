from datetime import date

from api.models import WeeklySchedule
from api.services.plan_schedule import resolve_current_week, resolve_today_and_next
from api.services.open_plan_timeline import project_open_structured_plan
from api.services.today_service import (
    _structured_next_session_entry,
    _structured_today_session_entry,
)
from fightcamp.weekly_schedule_view import extract_weekly_schedule


PLAN_ID = "11111111-1111-1111-1111-111111111111"


def _open_plan_brief():
    return {
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
        "created_at": "2026-07-01T09:00:00+00:00",
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    week_index, week = resolve_current_week(plan_row, today=date(2026, 8, 12))

    assert week_index == 1
    assert week is not None
    assert week.week_index == 1
    assert week.day_label == "Development week 2"


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


def test_open_plan_projects_weekdays_and_dates_from_first_monday_anchor():
    plan_row = {
        "id": PLAN_ID,
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
