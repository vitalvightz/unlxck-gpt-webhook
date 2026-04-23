from fightcamp.weekly_schedule_view import extract_weekly_schedule
from api.models import WeeklyDayEntry


def _planning_brief() -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "declared_hard_sparring_days": ["Monday", "Wednesday"],
                    "declared_support_work_days": ["Tuesday"],
                    "hard_sparring_plan": [
                        {
                            "day": "Monday",
                            "hard_day_class": "primary_hard",
                            "effective_load": "hard",
                            "status": "hard_as_planned",
                            "reason": "",
                            "reason_codes": [],
                        },
                        {
                            "day": "Wednesday",
                            "hard_day_class": "managed_hard",
                            "effective_load": "reduced",
                            "status": "deload_suggested",
                            "reason": "high fatigue",
                            "reason_codes": ["high_fatigue"],
                            "coach_note": "Keep the rounds controlled.",
                        },
                    ],
                }
            ]
        }
    }


def test_extract_weekly_schedule_maps_hard_days_in_weekday_order_without_support_tiles():
    schedule = extract_weekly_schedule(_planning_brief())

    assert schedule is not None
    assert schedule["week_index"] == 0
    assert schedule["week_count"] == 1
    assert schedule["phase"] == "SPP"
    assert [day["weekday"] for day in schedule["days"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Mon"]["sparring_day_class"] == "primary_hard"
    assert by_day["Mon"]["effective_load"] == "hard"
    assert by_day["Tue"]["sparring_day_class"] == "none"
    assert by_day["Tue"]["effective_load"] == "none"
    assert by_day["Wed"]["sparring_day_class"] == "managed_hard"
    assert by_day["Wed"]["effective_load"] == "reduced"
    assert by_day["Wed"]["reason_codes"] == ["high_fatigue"]
    assert by_day["Wed"]["coach_note"] == "Keep the rounds controlled."

    for weekday in ("Thu", "Fri", "Sat", "Sun"):
        assert by_day[weekday]["sparring_day_class"] == "none"
        assert by_day[weekday]["effective_load"] == "none"


def test_extract_weekly_schedule_returns_none_for_missing_or_out_of_range_week():
    assert extract_weekly_schedule({"schema_version": "planning_brief.v1"}) is None
    assert extract_weekly_schedule(_planning_brief(), week_index=1) is None
    assert extract_weekly_schedule(_planning_brief(), week_index=-1) is None


def test_extract_weekly_schedule_legacy_declared_hard_days_become_primary_hard():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "GPP",
                        "declared_hard_sparring_days": ["Mon", "Fri"],
                        "declared_support_work_days": ["Wednesday"],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Mon"]["sparring_day_class"] == "primary_hard"
    assert by_day["Mon"]["effective_load"] == "hard"
    assert by_day["Fri"]["sparring_day_class"] == "primary_hard"
    assert by_day["Fri"]["effective_load"] == "hard"
    assert by_day["Wed"]["sparring_day_class"] == "none"


def test_extract_weekly_schedule_final_week_deload_stays_managed_not_primary():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "declared_hard_sparring_days": ["Monday", "Wednesday", "Friday"],
                        "hard_sparring_plan": [
                            {
                                "day": "Monday",
                                "hard_day_class": "primary_hard",
                                "effective_load": "hard",
                                "status": "hard_as_planned",
                                "reason_codes": [],
                            },
                            {
                                "day": "Wednesday",
                                "hard_day_class": "managed_hard",
                                "effective_load": "reduced",
                                "status": "deload_suggested",
                                "reason_codes": ["fight_week_taper", "final_week_sparring_cap"],
                                "coach_note": "No second hard spar in taper.",
                            },
                        ],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Mon"]["sparring_day_class"] == "primary_hard"
    assert by_day["Mon"]["effective_load"] == "hard"
    assert by_day["Wed"]["sparring_day_class"] == "managed_hard"
    assert by_day["Wed"]["effective_load"] == "reduced"
    assert by_day["Wed"]["status"] == "deload_suggested"
    assert by_day["Wed"]["reason_codes"] == ["fight_week_taper", "final_week_sparring_cap"]
    assert by_day["Wed"]["coach_note"] == "No second hard spar in taper."


def test_extract_weekly_schedule_multi_week_brief_keeps_all_weeks_addressable():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "GPP",
                        "declared_hard_sparring_days": ["Monday"],
                        "hard_sparring_plan": [
                            {"day": "Monday", "effective_load": "hard", "status": "hard_as_planned"}
                        ],
                    },
                    {
                        "phase": "SPP",
                        "declared_hard_sparring_days": ["Wednesday"],
                        "hard_sparring_plan": [
                            {"day": "Wednesday", "effective_load": "hard", "status": "hard_as_planned"}
                        ],
                    },
                    {
                        "phase": "TAPER",
                        "declared_hard_sparring_days": ["Friday"],
                        "hard_sparring_plan": [
                            {
                                "day": "Friday",
                                "effective_load": "technical",
                                "status": "convert_to_technical_suggested",
                            }
                        ],
                    },
                ]
            }
        }
    )

    assert schedule is not None
    assert schedule["week_count"] == 3


def test_extract_weekly_schedule_week_index_returns_correct_phase_and_week():
    planning_brief = {
        "weekly_role_map": {
            "weeks": [
                {"phase": "GPP", "hard_sparring_plan": []},
                {"phase": "SPP", "hard_sparring_plan": []},
                {"phase": "TAPER", "hard_sparring_plan": []},
            ]
        }
    }

    assert extract_weekly_schedule(planning_brief, week_index=0)["phase"] == "GPP"
    assert extract_weekly_schedule(planning_brief, week_index=1)["phase"] == "SPP"
    assert extract_weekly_schedule(planning_brief, week_index=2)["phase"] == "TAPER"


def test_extract_weekly_schedule_taper_technical_plan_displays_technical_class():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "declared_hard_sparring_days": ["Monday"],
                        "hard_sparring_plan": [
                            {
                                "day": "Monday",
                                "effective_load": "technical",
                                "status": "convert_to_technical_suggested",
                            }
                        ],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Mon"]["sparring_day_class"] == "technical"
    assert by_day["Mon"]["effective_load"] == "technical"


def test_extract_weekly_schedule_taper_missing_plan_does_not_fallback_to_declared_days():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "declared_hard_sparring_days": ["Monday", "Wednesday"],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Mon"]["sparring_day_class"] == "none"
    assert by_day["Mon"]["effective_load"] == "none"
    assert by_day["Mon"]["status"] == "missing_effective_sparring_plan"
    assert by_day["Wed"]["sparring_day_class"] == "none"
    assert by_day["Wed"]["effective_load"] == "none"
    assert by_day["Wed"]["status"] == "missing_effective_sparring_plan"


def test_weekly_day_entry_accepts_technical_sparring_class():
    entry = WeeklyDayEntry(
        weekday="Mon",
        sparring_day_class="technical",
        effective_load="technical",
        status="convert_to_technical_suggested",
    )

    assert entry.sparring_day_class == "technical"
