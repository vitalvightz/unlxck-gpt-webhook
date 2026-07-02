"""Tests for low-cost fillers on normal-camp SPP/TAPER weeks."""

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import (
    LOW_COST_RECOVERY_INSERTS,
    PHYSICAL_INSERTS,
    ZERO_COST_INSERTS,
)
from fightcamp.weekly_plan_render import _session_body


def _calendar(day_to_d):
    return [{"weekday": weekday, "d_day": d_day} for weekday, d_day in day_to_d.items()]


def _role(role_key, weekday, category="conditioning"):
    return {"role_key": role_key, "category": category, "scheduled_day_hint": weekday}


def _week(
    phase,
    session_roles,
    *,
    calendar_days=None,
    unused=None,
    training_days=None,
    **extra,
):
    week = {
        "phase": phase,
        "session_roles": session_roles,
        "calendar_days": calendar_days or [],
        "intentionally_unused_days": unused or [],
        "declared_training_days": training_days or [],
    }
    week.update(extra)
    return week


def _fillers(week):
    return [
        role
        for role in week["session_roles"]
        if isinstance(role, dict) and role.get("camp_week_filler")
    ]


def _spp_week_with_unused_days():
    return _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Monday"), _role("primary_strength_day", "Thursday", "strength")],
        calendar_days=_calendar({"monday": 30, "wednesday": 28, "thursday": 27, "friday": 26}),
        unused=[
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        training_days=["Monday", "Wednesday", "Thursday", "Friday"],
    )


def test_spp_unused_days_get_fillers_and_leave_unused_list():
    week = _spp_week_with_unused_days()
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})

    fillers = _fillers(week)
    assert len(fillers) == 2
    assert {f["scheduled_day_hint"] for f in fillers} == {"Wednesday", "Friday"}
    assert all(f["category"] == "support_insert" for f in fillers)
    assert all(f.get("converted_from_unused_day") for f in fillers)
    assert week["intentionally_unused_days"] == []


def test_spp_cap_is_two_fillers():
    week = _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Monday")],
        calendar_days=_calendar({"monday": 30, "tuesday": 29, "wednesday": 28, "thursday": 27}),
        unused=[
            {"day": "Tuesday", "role": "off_day"},
            {"day": "Wednesday", "role": "off_day"},
            {"day": "Thursday", "role": "off_day"},
        ],
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    assert len(_fillers(week)) == 2
    # The third unused day stays intentionally unused.
    assert len(week["intentionally_unused_days"]) == 1


def test_taper_cap_is_one_filler():
    week = _week(
        "TAPER",
        [_role("alactic_sharpness_day", "Monday")],
        calendar_days=_calendar({"monday": 6, "wednesday": 4, "friday": 2}),
        unused=[
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "recovery_only_day"},
        ],
        training_days=["Monday", "Wednesday", "Friday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    assert len(_fillers(week)) == 1


def test_gpp_weeks_are_untouched():
    week = _week(
        "GPP",
        [_role("aerobic_base_day", "Monday")],
        calendar_days=_calendar({"monday": 45, "wednesday": 43}),
        unused=[{"day": "Wednesday", "role": "off_day"}],
        training_days=["Monday", "Wednesday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    assert _fillers(week) == []
    assert week["intentionally_unused_days"]


def test_compressed_week_is_never_filled():
    week = _spp_week_with_unused_days()
    week["intentional_compression"] = {"active": True, "reason_codes": ["high_fatigue"]}
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    assert _fillers(week) == []
    assert len(week["intentionally_unused_days"]) == 2


def test_inactive_compression_record_does_not_block_fillers():
    # The role map always attaches an intentional_compression dict; only
    # ``active: True`` means the week was deliberately left small.
    week = _spp_week_with_unused_days()
    week["intentional_compression"] = {"active": False, "reason_codes": ["two_hard_spar_days"]}
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    assert _fillers(week)


def test_short_day_tokens_match_full_name_calendar_days():
    # Real role maps use short tokens ("Wed") on roles/unused days but full
    # names ("wednesday") on calendar_days.
    week = _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Mon")],
        calendar_days=_calendar({"monday": 16, "wednesday": 14}),
        unused=[{"day": "Wed", "role": "recovery_only_day"}],
        training_days=["Mon", "Wed"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low", "hard_sparring_days": ["Tue", "Thu"]})
    fillers = _fillers(week)
    assert any(f["scheduled_day_hint"] == "Wed" for f in fillers)
    assert week["intentionally_unused_days"] == []


def test_safety_annotated_unused_day_is_skipped():
    week = _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Monday")],
        calendar_days=_calendar({"monday": 30, "wednesday": 28}),
        unused=[
            {
                "day": "Wednesday",
                "role": "recovery_only_day",
                "low_aerobic_cap_skipped": True,
                "low_aerobic_cap_reason": "cut severity blocked the upgrade",
            }
        ],
        training_days=["Monday", "Wednesday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    # The annotated day is never filled and stays intentionally unused; only the
    # shared-day fallback on an existing session day remains possible.
    assert all(f["scheduled_day_hint"] != "Wednesday" for f in _fillers(week))
    assert week["intentionally_unused_days"]


def test_high_fatigue_restricts_fillers_to_zero_cost_and_recovery():
    week = _spp_week_with_unused_days()
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "high"})
    fillers = _fillers(week)
    assert fillers
    for filler in fillers:
        assert filler["role_key"] in ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS


def test_hard_sparring_day_filler_is_never_physical():
    week = _week(
        "SPP",
        [_role("hard_sparring_day", "Tuesday", "sparring")],
        calendar_days=_calendar({"tuesday": 29}),
        training_days=["Tuesday"],
    )
    apply_camp_week_fillers(
        {"weeks": [week]},
        {"fatigue": "low", "hard_sparring_days": ["Tuesday"]},
    )
    for filler in _fillers(week):
        assert filler["role_key"] not in PHYSICAL_INSERTS


def test_shared_day_fallback_adds_at_most_one_filler():
    week = _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Monday"), _role("primary_strength_day", "Thursday", "strength")],
        calendar_days=_calendar({"monday": 30, "thursday": 27}),
        training_days=["Monday", "Thursday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    fillers = _fillers(week)
    assert len(fillers) == 1
    assert fillers[0]["scheduled_day_hint"] in {"Monday", "Thursday"}


def test_day_without_calendar_d_day_is_skipped():
    week = _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Monday")],
        calendar_days=_calendar({"monday": 30}),
        unused=[{"day": "Wednesday", "role": "off_day"}],
        training_days=["Monday", "Wednesday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    # Wednesday has no calendar entry, so it is left intentionally unused, and
    # the shared-day fallback may still use Monday.
    assert week["intentionally_unused_days"] == [{"day": "Wednesday", "role": "off_day"}]
    for filler in _fillers(week):
        assert filler["scheduled_day_hint"] == "Monday"


def test_fight_day_gets_no_filler():
    week = _week(
        "TAPER",
        [_role("fight_week_freshness_day", "Wednesday", "recovery")],
        calendar_days=_calendar({"wednesday": 2, "saturday": 0}),
        unused=[{"day": "Saturday", "role": "off_day"}],
        training_days=["Wednesday", "Saturday"],
    )
    apply_camp_week_fillers({"weeks": [week]}, {"fatigue": "low"})
    for filler in _fillers(week):
        assert filler["scheduled_day_hint"] != "Saturday"


def test_at_most_one_physical_filler_per_week():
    week = _week(
        "SPP",
        [_role("fight_pace_repeatability_day", "Monday")],
        calendar_days=_calendar({"monday": 30, "wednesday": 28, "friday": 26}),
        unused=[
            {"day": "Wednesday", "role": "off_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        training_days=["Monday", "Wednesday", "Friday"],
    )
    # A footwork weakness biases selection toward physical inserts, exercising
    # the per-week physical cap.
    apply_camp_week_fillers(
        {"weeks": [week]},
        {"fatigue": "low", "weaknesses": ["footwork"]},
    )
    physical = [f for f in _fillers(week) if f["role_key"] in PHYSICAL_INSERTS]
    assert len(physical) <= 1


def test_session_body_renders_support_insert_display_text():
    role = {
        "category": "support_insert",
        "role_key": "tactical_cue_card",
        "display_text": "Write one fight cue only: entry, exit, counter.",
    }
    body = _session_body(role, "SPP", [], {}, is_primary_strength=False)
    assert body == ["- Write one fight cue only: entry, exit, counter."]


def test_session_body_support_insert_without_text_falls_back():
    role = {"category": "support_insert", "role_key": "tactical_cue_card"}
    body = _session_body(role, "SPP", [], {}, is_primary_strength=False)
    assert body == ["- Coach-led session aligned with this week's focus."]
