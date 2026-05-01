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


def test_extract_weekly_schedule_multi_week_brief_keeps_all_weeks_addressable():
    planning_brief = {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "GPP",
                    "declared_hard_sparring_days": ["Monday"],
                    "hard_sparring_plan": [
                        {
                            "day": "Monday",
                            "hard_day_class": "primary_hard",
                            "effective_load": "hard",
                            "status": "hard_as_planned",
                        }
                    ],
                },
                {
                    "phase": "SPP",
                    "declared_hard_sparring_days": ["Wednesday"],
                    "hard_sparring_plan": [
                        {
                            "day": "Wednesday",
                            "hard_day_class": "secondary_hard",
                            "effective_load": "hard",
                            "status": "hard_as_planned",
                        }
                    ],
                },
                {
                    "phase": "TAPER",
                    "declared_hard_sparring_days": ["Friday"],
                    "hard_sparring_plan": [
                        {
                            "day": "Friday",
                            "hard_day_class": "primary_hard",
                            "effective_load": "technical",
                            "status": "convert_to_technical_suggested",
                        }
                    ],
                },
            ]
        }
    }

    week_zero = extract_weekly_schedule(planning_brief, week_index=0)
    week_one = extract_weekly_schedule(planning_brief, week_index=1)
    week_two = extract_weekly_schedule(planning_brief, week_index=2)

    assert week_zero is not None
    assert week_zero["week_count"] == 3
    assert week_zero["week_index"] == 0
    assert week_zero["phase"] == "GPP"

    assert week_one is not None
    assert week_one["week_count"] == 3
    assert week_one["week_index"] == 1
    assert week_one["phase"] == "SPP"

    assert week_two is not None
    assert week_two["week_count"] == 3
    assert week_two["week_index"] == 2
    assert week_two["phase"] == "TAPER"


def test_extract_weekly_schedule_legacy_declared_hard_days_become_primary_hard_in_non_taper_week():
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


def test_extract_weekly_schedule_final_week_convert_to_technical_stays_visible():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "declared_hard_sparring_days": ["Wednesday"],
                        "hard_sparring_plan": [
                            {
                                "day": "Wednesday",
                                "hard_day_class": "primary_hard",
                                "effective_load": "technical",
                                "status": "convert_to_technical_suggested",
                                "reason_codes": ["fight_week_taper", "final_week_sparring_cap"],
                                "coach_note": "Convert this to technical rounds only.",
                            },
                        ],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Wed"]["sparring_day_class"] == "technical"
    assert by_day["Wed"]["effective_load"] == "technical"
    assert by_day["Wed"]["status"] == "convert_to_technical_suggested"
    assert by_day["Wed"]["reason_codes"] == ["fight_week_taper", "final_week_sparring_cap"]
    assert by_day["Wed"]["coach_note"] == "Convert this to technical rounds only."


def test_extract_weekly_schedule_final_week_deload_stays_managed_not_primary():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "declared_hard_sparring_days": ["Wednesday"],
                        "hard_sparring_plan": [
                            {
                                "day": "Wednesday",
                                "hard_day_class": "primary_hard",
                                "effective_load": "reduced",
                                "status": "deload_suggested",
                                "reason_codes": ["fight_week_taper", "final_week_sparring_cap"],
                                "coach_note": "Keep the rounds controlled.",
                            },
                        ],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Wed"]["sparring_day_class"] == "managed_hard"
    assert by_day["Wed"]["effective_load"] == "reduced"
    assert by_day["Wed"]["status"] == "deload_suggested"


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
    assert by_day["Mon"]["reason_codes"] == ["missing_effective_sparring_plan"]
    assert by_day["Wed"]["sparring_day_class"] == "none"
    assert by_day["Wed"]["status"] == "missing_effective_sparring_plan"

def test_extract_weekly_schedule_protected_late_week_uses_session_roles_and_d0_override():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "final_week_sparring_cap": {"active": True},
                        "declared_hard_sparring_days": ["Tuesday", "Thursday"],
                        "hard_sparring_plan": [
                            {
                                "day": "Tuesday",
                                "hard_day_class": "primary_hard",
                                "effective_load": "hard",
                                "status": "hard_as_planned",
                            }
                        ],
                        "session_roles": [
                            {
                                "role_key": "hard_sparring_day",
                                "scheduled_day_hint": "Tuesday",
                                "scheduled_countdown_label": "D-4",
                                "countdown_display_label": "D-4 Tue",
                            },
                            {
                                "role_key": "hard_sparring_day",
                                "scheduled_day_hint": "Thursday",
                                "scheduled_countdown_label": "D-2",
                                "countdown_display_label": "D-2 Thu",
                            },
                            {
                                "role_key": "fight_day_protocol_payload",
                                "scheduled_day_hint": "Saturday",
                                "scheduled_countdown_label": "D-0",
                                "countdown_display_label": "D-0 Sat",
                            },
                        ],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}

    assert by_day["Tue"]["countdown_label"] == "D-4"
    assert by_day["Tue"]["sparring_day_class"] == "primary_hard"
    assert by_day["Tue"]["effective_load"] == "hard"

    assert by_day["Thu"]["countdown_label"] == "D-2"
    assert by_day["Thu"]["sparring_day_class"] == "technical"
    assert by_day["Thu"]["effective_load"] == "technical"
    assert by_day["Thu"]["status"] == "convert_to_technical_suggested"

    assert by_day["Sat"]["countdown_label"] == "D-0"
    assert by_day["Sat"]["status"] == "fight_day_protocol"
    assert by_day["Sat"]["reason_codes"] == ["fight_day_protocol"]
