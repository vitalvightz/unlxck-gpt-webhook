"""Tests for the fight-day (D-0) override guard.

Covers:
- The shared helper that clamps the final week of a weekly role map.
- Integration through the normal-camp ``_build_weekly_role_map`` so a declared
  hard-sparring weekday that lands on the fight date renders as the fight-day
  protocol, not as a coach-led boxing session.
- Anti-hardcode regression: the same weekday one week earlier is NOT
  suppressed.
- Multiple fight weekdays (Friday / Saturday / Wednesday) all clamp correctly.
"""

from __future__ import annotations

import pytest

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
