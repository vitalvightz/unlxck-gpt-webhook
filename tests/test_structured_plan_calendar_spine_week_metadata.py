from __future__ import annotations

from datetime import date, timedelta

import pytest

from api.structured_plan_calendar_spine import reconcile_calendar_spine


FIGHT_DATE = "2026-09-17"  # Thursday
FIGHT = date(2026, 9, 17)
_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day(d_day: int) -> dict:
    current = FIGHT - timedelta(days=d_day)
    return {
        "date": current.isoformat(),
        "weekday": _WEEKDAY_SHORT[current.weekday()],
        "day_type": "competition" if d_day == 0 else "rest",
        "countdown_label": f"D-{d_day}",
        "phase_label": "TAPER",
        "today_card": {
            "headline": "Fight day" if d_day == 0 else "",
            "readiness_status": "train_as_planned",
            "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
        },
        "sessions": [],
    }


def _calendar_weeks() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for d_day in range(21, -1, -1):
        day = _day(d_day)
        current = date.fromisoformat(day["date"])
        monday = (current - timedelta(days=current.weekday())).isoformat()
        groups.setdefault(monday, []).append(day)

    weeks = []
    for index, monday in enumerate(sorted(groups), start=1):
        days = groups[monday]
        ddays = [int(day["countdown_label"][2:]) for day in days]
        dates = [day["date"] for day in days]
        weeks.append(
            {
                "week_id": f"wk-{index}",
                "week_index": index,
                "phase_label": "TAPER",
                "week_goal": "",
                "start_date": min(dates),
                "end_date": max(dates),
                "countdown_start": f"D-{max(ddays)}",
                "countdown_end": f"D-{min(ddays)}",
                "load_focus": {
                    "volume": "moderate",
                    "intensity": "moderate",
                    "specificity": "moderate",
                    "fatigue_target": "moderate",
                },
                "progression": {"week_type": "build", "planned_change_from_previous": ""},
                "days": days,
            }
        )
    return weeks


def _brief(sport: str = "mma") -> dict:
    return {
        "fight_date": FIGHT_DATE,
        "days_until_fight": 21,
        "athlete_model": {"sport": sport, "fight_date": FIGHT_DATE, "days_until_fight": 21},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "countdown_span": {"start_day": 21, "end_day": 0},
                }
            ]
        },
    }


def test_correct_days_with_stale_week_boundary_metadata_are_rebuilt() -> None:
    weeks = _calendar_weeks()
    first = weeks[0]
    assert first["countdown_start"] == "D-21"
    assert first["countdown_end"] == "D-18"

    # Reproduce the production card bug: the day rows are correct, but the week
    # summary still says the week is only one day long.
    first["end_date"] = first["start_date"]
    first["countdown_end"] = first["countdown_start"]

    plan = {"weeks": weeks}
    out = reconcile_calendar_spine(plan, _brief())

    assert out is not plan
    repaired = out["weeks"][0]
    assert repaired["countdown_start"] == "D-21"
    assert repaired["countdown_end"] == "D-18"
    assert repaired["start_date"] == "2026-08-27"
    assert repaired["end_date"] == "2026-08-30"


@pytest.mark.parametrize(
    "sport",
    ["boxing", "mma", "muay_thai", "kickboxing", "bjj", "wrestling", "general_combat"],
)
def test_week_boundary_repair_is_sport_independent(sport: str) -> None:
    weeks = _calendar_weeks()
    weeks[0]["end_date"] = weeks[0]["start_date"]
    weeks[0]["countdown_end"] = weeks[0]["countdown_start"]

    out = reconcile_calendar_spine({"weeks": weeks}, _brief(sport))

    first = out["weeks"][0]
    assert first["countdown_start"] == "D-21"
    assert first["countdown_end"] == "D-18"
    assert first["start_date"] == "2026-08-27"
    assert first["end_date"] == "2026-08-30"
