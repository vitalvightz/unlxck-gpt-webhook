from datetime import date

from api.models import WeeklySchedule
from api.services.plan_schedule import resolve_today_and_next
from fightcamp.weekly_schedule_view import extract_weekly_schedule


PLAN_ID = "11111111-1111-1111-1111-111111111111"


def test_open_plan_sunday_wraps_to_monday_from_full_seven_day_schedule():
    planning_brief = {
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
