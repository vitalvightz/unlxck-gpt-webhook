from datetime import date

from api.models import WeeklySchedule
from api.services.plan_schedule import resolve_current_week, resolve_today_and_next
from fightcamp.weekly_schedule_view import extract_weekly_schedule


PLAN_ID = "11111111-1111-1111-1111-111111111111"


def _open_plan_brief():
    return {
        "open_plan_spec": {
            "plan_type": "open_ongoing_system",
            "weekly_template": {
                "training_days": ["Monday", "Wednesday", "Friday", "Saturday", "Tuesday"],
                "hard_sparring_days": ["Wednesday", "Friday"],
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

    week_index, week = resolve_current_week(plan_row, today=date(2026, 8, 5))

    assert week_index == 1
    assert week is not None
    assert week.week_index == 1
    assert week.day_label == "Development week 2"


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
