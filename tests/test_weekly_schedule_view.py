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


def test_extract_weekly_schedule_empty_late_plan_marks_declared_hard_days_technical_only():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "payload_mode": "late_fight_session_payload",
                        "declared_hard_sparring_days": ["Tuesday", "Thursday"],
                        "hard_sparring_plan": [],
                        "effective_hard_sparring_days": [],
                        "intentional_compression": {
                            "active": True,
                            "reason_codes": ["late_fight_session_payload"],
                        },
                    }
                ]
            }
        }
    )

    assert schedule is not None
    by_day = {day["weekday"]: day for day in schedule["days"]}
    for weekday in ("Tue", "Thu"):
        assert by_day[weekday]["sparring_day_class"] == "technical"
        assert by_day[weekday]["effective_load"] == "technical"
        assert by_day[weekday]["status"] == "convert_to_technical_suggested"
        assert by_day[weekday]["reason_codes"] == ["d17_hard_sparring_ban"]


def test_weekly_schedule_view_exposes_d_day_labels_from_calendar_days():
    from fightcamp.weekly_schedule_view import extract_weekly_schedule

    planning_brief = {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "projected_days_until_fight_start": 20,
                    "projected_days_until_fight_end": 14,
                    "calendar_days": [
                        {
                            "weekday": "monday",
                            "d_day": 18,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        },
                        {
                            "weekday": "tuesday",
                            "d_day": 17,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        },
                        {
                            "weekday": "wednesday",
                            "d_day": 16,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        },
                    ],
                    "hard_sparring_plan": [],
                    "declared_hard_sparring_days": [],
                }
            ]
        }
    }

    schedule = extract_weekly_schedule(planning_brief, week_index=0)

    assert schedule is not None
    assert schedule["days"][0]["weekday"] == "Mon"
    assert schedule["days"][0]["d_day"] == 18
    assert schedule["days"][0]["day_label"] == "D-18"
    assert schedule["days"][2]["day_label"] == "D-16"
    assert schedule["countdown_range"] == [18, 16]
    assert schedule["week_countdown_label"] == "D-18 → D-16"
    assert schedule["week_label_with_countdown"] == "Week 1 — SPP (D-18 → D-16)"
    assert schedule["days"][0]["weekday_with_label"] == "Mon (D-18)"


def test_weekly_schedule_view_builds_countdown_range_when_missing_from_week():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "GPP",
                        "calendar_days": [
                            {"weekday": "monday", "d_day": 37},
                            {"weekday": "tuesday", "d_day": 36},
                            {"weekday": "wednesday", "d_day": 35},
                        ],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    assert schedule["countdown_range"] == [37, 35]
    assert schedule["week_countdown_label"] == "D-37 → D-35"


def test_protected_week_does_not_apply_d17_ban_to_d37_declared_hard_day():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "countdown",
                        "calendar_days": [
                            {"weekday": "monday", "d_day": 37},
                            {"weekday": "tuesday", "d_day": 36},
                        ],
                        "hard_sparring_plan": [],
                        "declared_hard_sparring_days": ["monday"],
                        "effective_hard_sparring_days": [],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    monday = schedule["days"][0]
    assert monday["weekday"] == "Mon"
    assert monday["d_day"] == 37
    assert monday["effective_load"] == "none"
    assert monday["status"] == ""
    assert monday["reason_codes"] == []


def test_extract_weekly_schedule_calendar_days_are_normalized_to_monday_to_sunday_with_placeholders():
    schedule = extract_weekly_schedule(
        {
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "SPP",
                        "calendar_days": [
                            {"weekday": "Friday", "d_day": 15, "calendar_date": "2026-05-15"},
                            {"weekday": "Monday", "d_day": 19, "calendar_date": "2026-05-11"},
                            {"weekday": "Wednesday", "d_day": 17, "calendar_date": "2026-05-13"},
                        ],
                        "hard_sparring_plan": [{"day": "Wednesday", "status": "convert_to_technical_suggested"}],
                    }
                ]
            }
        }
    )

    assert schedule is not None
    assert [day["weekday"] for day in schedule["days"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    by_day = {day["weekday"]: day for day in schedule["days"]}
    assert by_day["Mon"]["calendar_date"] == "2026-05-11"
    assert by_day["Wed"]["calendar_date"] == "2026-05-13"
    assert by_day["Fri"]["calendar_date"] == "2026-05-15"
    assert by_day["Tue"]["calendar_date"] == "2026-05-12"
    assert by_day["Thu"]["calendar_date"] == "2026-05-14"
    assert by_day["Sat"]["calendar_date"] == "2026-05-16"
    assert by_day["Sun"]["calendar_date"] == "2026-05-17"
    assert by_day["Tue"]["d_day"] == 18
    assert by_day["Thu"]["d_day"] == 16
    assert by_day["Sat"]["d_day"] == 14
    assert by_day["Sun"]["d_day"] == 13
    assert by_day["Tue"]["day_label"] == "D-18"
    assert by_day["Sun"]["weekday_with_label"] == "Sun (D-13)"
    assert by_day["Sat"]["sparring_day_class"] == "none"
