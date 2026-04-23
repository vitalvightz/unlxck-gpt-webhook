from fightcamp.weekly_schedule_view import extract_weekly_schedule


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


def test_extract_weekly_schedule_hides_final_week_capped_extra_hard_days_from_sparring_map():
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
    assert by_day["Wed"]["sparring_day_class"] == "none"
    assert by_day["Wed"]["effective_load"] == "none"
    assert by_day["Wed"]["status"] == "deload_suggested"
    assert by_day["Wed"]["reason_codes"] == ["fight_week_taper", "final_week_sparring_cap"]
    assert by_day["Wed"]["coach_note"] == "No second hard spar in taper."
