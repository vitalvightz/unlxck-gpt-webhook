"""Tests for the fight-day (D-0) override guard.

Covers:
- The shared helper that clamps the final week of a weekly role map.
- ``fight_date`` is the primary D-0 source; the offset fallback only fires
  when no fight date is available.
- Integration through the normal-camp ``_build_weekly_role_map`` so a declared
  hard-sparring weekday that lands on the fight date renders as the fight-day
  protocol, not as a coach-led boxing session.
- Anti-hardcode regression: the same weekday one week earlier is NOT
  suppressed.
- Multiple fight weekdays (Friday / Saturday / Wednesday) all clamp correctly.
- Saturday hard-sparring collision: declared spar days include Saturday and
  the fight is on Saturday.
- Deterministic rendered text proves the fight-day line is emitted verbatim.
"""

from __future__ import annotations

import pytest

from fightcamp.fight_date_utils import (
    fight_weekday_from_fight_date,
    resolve_fight_weekday,
)
from fightcamp.fight_day_override import (
    FIGHT_DAY_PROTOCOL_TEXT,
    apply_fight_day_override_to_weekly_role_map,
    compute_fight_weekday,
)


# ---------------------------------------------------------------------------
# compute_fight_weekday
# ---------------------------------------------------------------------------


class TestComputeFightWeekday:
    def test_monday_creation_plus_4_is_friday(self):
        athlete = {"plan_creation_weekday": "monday", "days_until_fight": 4}
        assert compute_fight_weekday(athlete) == "friday"

    @pytest.mark.parametrize(
        "creation, days, expected",
        [
            ("sunday", 26, "friday"),     # camp >21 days, fight on Friday
            ("monday", 26, "saturday"),   # camp >21 days, fight on Saturday
            ("monday", 23, "wednesday"),  # camp >21 days, fight on Wednesday
            ("wednesday", 30, "friday"),  # 30 days out
        ],
    )
    def test_long_camp_fight_weekdays(self, creation, days, expected):
        athlete = {"plan_creation_weekday": creation, "days_until_fight": days}
        assert compute_fight_weekday(athlete) == expected

    def test_returns_none_for_missing_weekday(self):
        assert compute_fight_weekday({"days_until_fight": 26}) is None

    def test_returns_none_for_missing_days(self):
        assert compute_fight_weekday({"plan_creation_weekday": "monday"}) is None

    def test_returns_none_for_non_dict(self):
        assert compute_fight_weekday(None) is None
        assert compute_fight_weekday("not a dict") is None


# ---------------------------------------------------------------------------
# apply_fight_day_override_to_weekly_role_map
# ---------------------------------------------------------------------------


def _weekly_role_map_with(week_session_roles: list[list[dict]]) -> dict:
    weeks = []
    for idx, roles in enumerate(week_session_roles, start=1):
        weeks.append(
            {
                "week_index": idx,
                "phase": "TAPER" if idx == len(week_session_roles) else "SPP",
                "session_roles": [dict(role) for role in roles],
                "calendar_days": [
                    {"weekday": "monday", "d_day": 4, "is_fight_day": False, "is_after_fight_day": False},
                    {"weekday": "wednesday", "d_day": 2, "is_fight_day": False, "is_after_fight_day": False},
                    {"weekday": "friday", "d_day": 0, "is_fight_day": True, "is_after_fight_day": False},
                ] if idx == len(week_session_roles) else [
                    {"weekday": "monday", "d_day": 11, "is_fight_day": False, "is_after_fight_day": False},
                    {"weekday": "wednesday", "d_day": 9, "is_fight_day": False, "is_after_fight_day": False},
                    {"weekday": "friday", "d_day": 7, "is_fight_day": False, "is_after_fight_day": False},
                ],
                "suppressed_roles": [],
                "declared_hard_sparring_days": ["monday", "wednesday", "friday"],
                "effective_hard_sparring_days": ["monday", "wednesday", "friday"],
            }
        )
    return {"weeks": weeks}


@pytest.mark.parametrize(
    "role_key",
    [
        "hard_sparring_day",
        "primary_strength_day",
        "fight_pace_repeatability_day",
        "aerobic_support_day",
        "neural_primer_day",
        "recovery_day",
    ],
)
def test_override_replaces_any_role_on_fight_weekday(role_key):
    """The override is unconditional on D-0 — no role survives."""
    week_role = {"role_key": role_key, "scheduled_day_hint": "friday", "category": "any"}
    weekly_role_map = _weekly_role_map_with([[week_role]])
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}  # Friday

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    final_week = result["weeks"][-1]
    assert len(final_week["session_roles"]) == 1
    fight_role = final_week["session_roles"][0]
    assert fight_role["role_key"] == "fight_day_protocol"
    assert fight_role["display_text"] == FIGHT_DAY_PROTOCOL_TEXT
    assert fight_role["scheduled_day_hint"] == "friday"


def test_override_appends_protocol_when_no_role_already_on_fight_day():
    """If no session role is hinted to the fight weekday, append a protocol slot."""
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "primary_strength_day", "scheduled_day_hint": "monday"}]]
    )
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}  # Friday

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)
    final_week = result["weeks"][-1]
    role_keys = [role["role_key"] for role in final_week["session_roles"]]
    assert "fight_day_protocol" in role_keys
    fight_role = next(r for r in final_week["session_roles"] if r["role_key"] == "fight_day_protocol")
    assert fight_role["scheduled_day_hint"] == "friday"
    assert fight_role["display_text"] == FIGHT_DAY_PROTOCOL_TEXT


def test_override_records_top_level_metadata():
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}]]
    )
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    assert result["fight_day_override"]["active"] is True
    assert result["fight_day_override"]["fight_weekday"] == "friday"
    assert result["fight_day_override"]["fight_day_text"] == FIGHT_DAY_PROTOCOL_TEXT


def test_override_drops_fight_day_from_effective_hard_sparring_days():
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}]]
    )
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    final_week = result["weeks"][-1]
    assert "friday" not in final_week["effective_hard_sparring_days"]
    assert "monday" in final_week["effective_hard_sparring_days"]


def test_override_scrubs_fight_day_even_when_not_declared_hard_sparring():
    """Metadata cleanup must be unconditional, not gated on declared spar days."""
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "primary_strength_day", "scheduled_day_hint": "friday"}]]
    )
    final_week = weekly_role_map["weeks"][-1]
    final_week["declared_hard_sparring_days"] = ["monday", "wednesday"]
    final_week["effective_hard_sparring_days"] = ["monday", "wednesday", "friday"]

    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}
    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    final_week = result["weeks"][-1]
    assert "friday" not in final_week["effective_hard_sparring_days"]


def test_override_filters_hard_sparring_plan_entries_for_fight_day():
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}]]
    )
    final_week = weekly_role_map["weeks"][-1]
    final_week["hard_sparring_plan"] = [
        {"day": "monday", "status": "hard_as_planned"},
        {"day": "friday", "status": "hard_as_planned"},
    ]
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    final_week = result["weeks"][-1]
    assert all(entry["day"] != "friday" for entry in final_week["hard_sparring_plan"])
    assert any(entry["day"] == "monday" for entry in final_week["hard_sparring_plan"])


def test_override_does_not_touch_earlier_weeks():
    """Anti-hardcode: same weekday in a prior week is not suppressed."""
    weekly_role_map = _weekly_role_map_with(
        [
            [{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}],
            [{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}],
        ]
    )
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    earlier_week = result["weeks"][0]
    assert earlier_week["session_roles"][0]["role_key"] == "hard_sparring_day"
    assert "fight_day_override" not in earlier_week
    final_week = result["weeks"][-1]
    assert final_week["session_roles"][0]["role_key"] == "fight_day_protocol"


@pytest.mark.parametrize(
    "creation_weekday, days_out, expected_fight_weekday",
    [
        ("sunday", 26, "friday"),
        ("sunday", 27, "saturday"),
        ("monday", 23, "wednesday"),
    ],
)
def test_override_fires_for_multiple_fight_weekdays(
    creation_weekday, days_out, expected_fight_weekday
):
    weekly_role_map = _weekly_role_map_with(
        [
            [
                {"role_key": "hard_sparring_day", "scheduled_day_hint": expected_fight_weekday},
                {"role_key": "primary_strength_day", "scheduled_day_hint": "tuesday"},
            ]
        ]
    )
    athlete_model = {
        "plan_creation_weekday": creation_weekday,
        "days_until_fight": days_out,
    }
    final_week = weekly_role_map["weeks"][-1]
    final_week["calendar_days"] = [
        {"weekday": "monday", "d_day": 4, "is_fight_day": False, "is_after_fight_day": False},
        {"weekday": expected_fight_weekday, "d_day": 0, "is_fight_day": True, "is_after_fight_day": False},
    ]

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)
    final_week = result["weeks"][-1]
    role_for_fight_day = next(
        role for role in final_week["session_roles"]
        if role["scheduled_day_hint"] == expected_fight_weekday
    )
    assert role_for_fight_day["role_key"] == "fight_day_protocol"
    assert role_for_fight_day["display_text"] == FIGHT_DAY_PROTOCOL_TEXT
    # Other days survive
    other_roles = [
        role for role in final_week["session_roles"]
        if role["scheduled_day_hint"] != expected_fight_weekday
    ]
    assert any(role["role_key"] == "primary_strength_day" for role in other_roles)


def test_override_no_op_when_fight_weekday_unknown():
    """Without plan_creation_weekday or days_until_fight the map is unchanged."""
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}]]
    )
    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, {})
    assert "fight_day_override" not in result
    assert result["weeks"][-1]["session_roles"][0]["role_key"] == "hard_sparring_day"


def test_override_records_displaced_role_in_suppressed():
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}]]
    )
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)

    suppressed = result["weeks"][-1]["suppressed_roles"]
    assert any(
        item.get("downgraded_from_role_key") == "hard_sparring_day"
        and item.get("replacement_role_key") == "fight_day_protocol"
        for item in suppressed
    )


def test_override_no_op_when_final_week_has_no_d0_calendar_day():
    weekly_role_map = _weekly_role_map_with(
        [[{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday"}]]
    )
    final_week = weekly_role_map["weeks"][-1]
    final_week["calendar_days"] = [
        {"weekday": "monday", "d_day": 8, "is_fight_day": False, "is_after_fight_day": False},
        {"weekday": "wednesday", "d_day": 7, "is_fight_day": False, "is_after_fight_day": False},
        {"weekday": "friday", "d_day": 5, "is_fight_day": False, "is_after_fight_day": False},
    ]
    athlete_model = {"plan_creation_weekday": "sunday", "days_until_fight": 26}

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)
    assert "fight_day_override" not in result
    assert result["weeks"][-1]["session_roles"][0]["role_key"] == "hard_sparring_day"


def test_normal_camp_taper_ending_d1_does_not_render_fight_day_protocol_inside_taper():
    """When taper week ends at D-1, do not inject fight_day_protocol into same weekday D-7."""
    weekly_role_map = _weekly_role_map_with(
        [
            [{"role_key": "hard_sparring_day", "scheduled_day_hint": "wednesday"}],
            [{"role_key": "hard_sparring_day", "scheduled_day_hint": "wednesday"}],
        ]
    )
    final_week = weekly_role_map["weeks"][-1]
    final_week["calendar_days"] = [
        {"weekday": "monday", "d_day": 8, "is_fight_day": False, "is_after_fight_day": False},
        {"weekday": "wednesday", "d_day": 7, "is_fight_day": False, "is_after_fight_day": False},
        {"weekday": "friday", "d_day": 5, "is_fight_day": False, "is_after_fight_day": False},
        {"weekday": "sunday", "d_day": 1, "is_fight_day": False, "is_after_fight_day": False},
    ]
    athlete_model = {"fight_date": "2026-06-10"}  # Wednesday

    result = apply_fight_day_override_to_weekly_role_map(weekly_role_map, athlete_model)
    result_final_week = result["weeks"][-1]

    assert "fight_day_override" not in result
    assert not any(
        role.get("role_key") == "fight_day_protocol"
        for role in result_final_week["session_roles"]
    )
    assert any(
        role.get("role_key") == "hard_sparring_day"
        and role.get("scheduled_day_hint") == "wednesday"
        for role in result_final_week["session_roles"]
    )


# ---------------------------------------------------------------------------
# Integration with the normal-camp _build_weekly_role_map
# ---------------------------------------------------------------------------


def _normal_camp_athlete_model(
    *, plan_creation_weekday: str, days_until_fight: int, hard_sparring_days: list[str]
) -> dict:
    return {
        "sport": "boxing",
        "plan_creation_weekday": plan_creation_weekday,
        "days_until_fight": days_until_fight,
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": hard_sparring_days,
        "support_work_days": ["tuesday"],
        "fatigue": "moderate",
        "readiness_flags": [],
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "injuries": [],
    }


def _minimal_progression(weeks: int) -> dict:
    progression_weeks = []
    for idx in range(weeks):
        is_last = idx == weeks - 1
        progression_weeks.append(
            {
                "week_index": idx + 1,
                "phase": "TAPER" if is_last else ("SPP" if idx else "GPP"),
                "stage_key": "fight_week" if is_last else "phase_block",
                "phase_week_index": 1,
                "phase_week_total": 1,
                "span_days": 7,
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic"],
                "must_keep": [],
                "resolved_rule_state": {},
                "intentionally_unused_days": [],
            }
        )
    return {"weeks": progression_weeks}


@pytest.mark.parametrize(
    "creation_weekday, days_out, fight_weekday",
    [
        ("sunday", 26, "friday"),
        ("sunday", 27, "saturday"),
        ("monday", 23, "wednesday"),
    ],
)
def test_normal_camp_final_week_clamps_fight_day(
    creation_weekday, days_out, fight_weekday
):
    from fightcamp.stage2_role_map import _build_weekly_role_map

    athlete_model = _normal_camp_athlete_model(
        plan_creation_weekday=creation_weekday,
        days_until_fight=days_out,
        hard_sparring_days=["monday", "wednesday", "friday"],
    )
    progression = _minimal_progression(weeks=4)
    limiter_profile = {"key": "general_fight_readiness"}

    weekly_role_map = _build_weekly_role_map(
        athlete_model,
        progression,
        limiter_profile,
        fight_week_override={"active": False},
    )

    assert weekly_role_map["fight_day_override"]["active"] is True
    assert weekly_role_map["fight_day_override"]["fight_weekday"] == fight_weekday

    final_week = weekly_role_map["weeks"][-1]
    fight_day_roles = [
        role for role in final_week["session_roles"]
        if role.get("scheduled_day_hint") == fight_weekday
    ]
    assert len(fight_day_roles) == 1
    assert fight_day_roles[0]["role_key"] == "fight_day_protocol"
    assert fight_day_roles[0]["display_text"] == FIGHT_DAY_PROTOCOL_TEXT

    # No hard_sparring_day role on the fight day in the final week
    assert not any(
        role.get("role_key") == "hard_sparring_day"
        and role.get("scheduled_day_hint") == fight_weekday
        for role in final_week["session_roles"]
    )


def test_fight_date_overrides_offset_arithmetic_when_both_present():
    """fight_date wins even if days_until_fight + plan_creation_weekday disagree."""
    # Offset alone would say Wednesday (sunday + 24 days mod 7 = wednesday)
    # but fight_date says Saturday — fight_date must win.
    assert resolve_fight_weekday(
        fight_date="2026-05-23",  # Saturday
        plan_creation_weekday="sunday",
        days_until_fight=24,
    ) == "saturday"


def test_compute_fight_weekday_prefers_fight_date_in_athlete_model():
    athlete = {
        "fight_date": "2026-05-23",  # Saturday
        "plan_creation_weekday": "sunday",
        "days_until_fight": 24,  # would yield wednesday under offset arithmetic
    }
    assert compute_fight_weekday(athlete) == "saturday"


def test_compute_fight_weekday_accepts_next_fight_date_alias():
    athlete = {"next_fight_date": "2026-05-22"}  # Friday
    assert compute_fight_weekday(athlete) == "friday"


def test_compute_fight_weekday_falls_back_when_fight_date_missing():
    athlete = {"plan_creation_weekday": "sunday", "days_until_fight": 26}
    assert compute_fight_weekday(athlete) == "friday"


def test_fight_weekday_from_fight_date_handles_iso_strings_and_dates():
    from datetime import date as _date, datetime as _datetime

    assert fight_weekday_from_fight_date("2026-05-22") == "friday"
    assert fight_weekday_from_fight_date(_date(2026, 5, 23)) == "saturday"
    assert fight_weekday_from_fight_date(_datetime(2026, 4, 29, 12, 0)) == "wednesday"
    assert fight_weekday_from_fight_date("not-a-date") is None
    assert fight_weekday_from_fight_date(None) is None


def test_saturday_hard_sparring_collision_is_clamped_to_protocol():
    """Declared hard sparring on Saturday + fight on Saturday → protocol."""
    from fightcamp.stage2_role_map import _build_weekly_role_map

    athlete_model = _normal_camp_athlete_model(
        plan_creation_weekday="sunday",
        days_until_fight=27,  # Saturday
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    athlete_model["training_days"] = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    ]
    athlete_model["fight_date"] = "2026-05-23"  # Saturday
    progression = _minimal_progression(weeks=4)

    weekly_role_map = _build_weekly_role_map(
        athlete_model,
        progression,
        {"key": "general_fight_readiness"},
        fight_week_override={"active": False},
    )

    final_week = weekly_role_map["weeks"][-1]
    saturday_roles = [
        role for role in final_week["session_roles"]
        if role.get("scheduled_day_hint") == "saturday"
    ]
    assert saturday_roles, "Saturday must surface as a slot on the fight week"
    assert all(role["role_key"] == "fight_day_protocol" for role in saturday_roles)
    assert all(role["role_key"] != "hard_sparring_day" for role in saturday_roles)
    # No Saturday hard sparring in metadata
    assert "saturday" not in final_week["effective_hard_sparring_days"]


def test_rendered_plan_text_contains_fight_day_protocol_line():
    """Deterministic rendered-text proof: 'Fight day (Friday): ...protocol' appears."""
    from types import SimpleNamespace

    from fightcamp.plan_pipeline_rendering import _sparring_adjustment_lines

    context = SimpleNamespace(
        plan_input=SimpleNamespace(
            hard_sparring_days=["monday", "wednesday", "friday"],
            support_work_days=["tuesday"],
            next_fight_date="2026-05-22",  # Friday
            days_until_fight=26,
            athlete_timezone="UTC",
        ),
    )

    lines = _sparring_adjustment_lines(context)
    text = "\n".join(lines)

    assert "Fight day (Friday)" in text
    assert FIGHT_DAY_PROTOCOL_TEXT in text
    # Sanity: the fight day must NOT render as a hard sparring / contact session
    # next to the Friday tag in this athlete-facing summary (current label plus the
    # legacy "Coach-led boxing session" wording).
    assert "Friday — Hard sparring" not in text
    assert "Friday — Coach-led boxing session" not in text


def test_rendered_plan_text_omits_fight_day_line_when_date_unknown():
    """Without a fight_date the renderer must NOT guess from the wall clock."""
    from types import SimpleNamespace

    from fightcamp.plan_pipeline_rendering import _sparring_adjustment_lines

    context = SimpleNamespace(
        plan_input=SimpleNamespace(
            hard_sparring_days=["monday"],
            support_work_days=[],
            next_fight_date="",
            days_until_fight=26,
            athlete_timezone="UTC",
        ),
    )

    lines = _sparring_adjustment_lines(context)
    text = "\n".join(lines)

    # No drift-prone fight-day line when fight_date is unavailable.
    assert "Fight day" not in text


def test_normal_camp_prior_week_keeps_hard_sparring_on_same_weekday():
    """Anti-hardcode regression at the integration level."""
    from fightcamp.stage2_role_map import _build_weekly_role_map

    # Friday fight in 4 weeks; declared hard sparring on Friday.
    athlete_model = _normal_camp_athlete_model(
        plan_creation_weekday="sunday",
        days_until_fight=26,
        hard_sparring_days=["monday", "wednesday", "friday"],
    )
    progression = _minimal_progression(weeks=4)

    weekly_role_map = _build_weekly_role_map(
        athlete_model,
        progression,
        {"key": "general_fight_readiness"},
        fight_week_override={"active": False},
    )

    # The first three weeks must still lock Friday as hard_sparring_day.
    for week in weekly_role_map["weeks"][:-1]:
        friday_roles = [
            role for role in week["session_roles"]
            if role.get("scheduled_day_hint") == "friday"
        ]
        if friday_roles:
            assert any(role.get("role_key") == "hard_sparring_day" for role in friday_roles), (
                "Earlier weeks must keep declared Friday hard sparring intact"
            )

    # The final week must NOT.
    final_week = weekly_role_map["weeks"][-1]
    friday_roles = [
        role for role in final_week["session_roles"]
        if role.get("scheduled_day_hint") == "friday"
    ]
    assert friday_roles, "Final week must still expose the fight day as a slot"
    assert all(role["role_key"] == "fight_day_protocol" for role in friday_roles)
