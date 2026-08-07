from fightcamp.stage2_payload_late_fight import (
    _late_fight_countdown_context,
    can_render_late_taper_day,
)


def test_fight_week_app_work_still_respects_declared_availability():
    assert not can_render_late_taper_day(
        countdown_offset=5,
        weekday="sunday",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    )


def test_fight_day_remains_legal_outside_normal_training_availability():
    assert can_render_late_taper_day(
        countdown_offset=0,
        weekday="saturday",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    )


def test_countdown_context_does_not_remap_weekdays_to_nearest_available_day():
    context = _late_fight_countdown_context(
        14,
        {
            "days_until_fight": 14,
            "plan_creation_weekday": "friday",
            "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        },
    )

    raw_map = context["raw_countdown_weekday_map"]
    resolved_map = context["countdown_weekday_map"]

    assert raw_map["D-12"] == "sunday"
    assert "D-12" not in resolved_map
    assert raw_map["D-9"] == "wednesday"
    assert resolved_map["D-9"] == "wednesday"
