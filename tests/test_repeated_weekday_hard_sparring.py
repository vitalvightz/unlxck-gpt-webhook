"""A declared hard-sparring weekday that repeats inside one planner week.

Plans can take a session on the generation day, so a 23-day camp becomes
D-22..D-0 and the first planner week spans eight days (D-22..D-15) with two
Fridays. The weekday-keyed sparring plan resolved "Friday" to D-15 only; with a
reduced-contact request D-15 sits inside the D-17 cutoff, so the athlete's
declared Friday sparring on the generation day vanished and a recovery flush
took its place. Each occurrence must be resolved on its own date.
"""
from __future__ import annotations

import datetime

import pytest

from api.structured_plan_deterministic_fallback import build_deterministic_structured_plan
from fightcamp import input_parsing, stage2_planning_brief
from fightcamp.sparring_dose_planner import repeated_weekday_hard_sparring_entries
from support import _build_request

_GENERATED_AT = datetime.datetime(2026, 9, 25, 18, 54)  # Friday, D-22


def _generate(hard_sparring_days: list[str], support_work_days: list[str]) -> dict:
    generate_plan_sync = pytest.importorskip("fightcamp.main").generate_plan_sync
    patch = pytest.MonkeyPatch()
    # Both clocks: days_until_fight and the plan-creation weekday.
    patch.setattr(input_parsing, "_utc_now", lambda: _GENERATED_AT)
    patch.setattr(stage2_planning_brief, "_utc_now", lambda: _GENERATED_AT)
    try:
        payload = _build_request(
            {
                "fight_date": "2026-10-17",
                "hard_sparring_days": hard_sparring_days,
                "support_work_days": support_work_days,
                "technical_skill_days": [],
                "training_availability": ["Monday", "Tuesday", "Thursday", "Friday", "Sunday"],
                "weekly_training_frequency": 4,
                "reduced_contact_requested": True,
                "fatigue_level": "low",
                "injuries": "",
                "key_goals": ["skill_refinement", "speed"],
                "weak_areas": ["power", "trunk_strength"],
                "athlete": {"weight_kg": 76.0, "target_weight_kg": 72.0},
            }
        ).to_payload()
        payload["include_generation_day"] = True
        payload["random_seed"] = 1
        return generate_plan_sync(payload)["planning_brief"]
    finally:
        patch.undo()


@pytest.fixture(scope="module")
def brief() -> dict:
    return _generate(["Friday", "Sunday"], [])


@pytest.fixture(scope="module")
def light_brief() -> dict:
    return _generate(["Sunday"], ["Friday"])


def _structured_days(brief: dict) -> dict[int, dict]:
    plan = build_deterministic_structured_plan(brief)
    assert plan is not None
    days: dict[int, dict] = {}
    for week in plan["weeks"]:
        for day in week["days"]:
            label = str(day.get("countdown_label") or "")
            if label.startswith("D-"):
                days[int(label[2:])] = day
    return days


def _contact(day: dict) -> str:
    card = day.get("today_card") or {}
    return f"{card.get('headline') or ''} {card.get('coach_led_contact') or ''}"


def test_generation_day_friday_keeps_declared_hard_sparring(brief):
    first_week = brief["weekly_role_map"]["weeks"][0]
    assert first_week["countdown_range"] == [22, 15]
    repeated = first_week["repeated_weekday_hard_sparring"]
    assert [(e["day"], e["scheduled_d_day"], e["effective_load"]) for e in repeated] == [
        ("Friday", 22, "hard")
    ]
    pinned = [
        role for role in first_week["session_roles"]
        if role["role_key"] == "hard_sparring_day" and role.get("scheduled_d_day") == 22
    ]
    assert len(pinned) == 1
    assert pinned[0]["scheduled_countdown_label"] == "D-22"


def test_structured_plan_renders_both_first_week_hard_days(brief):
    days = _structured_days(brief)
    assert "Hard sparring" in _contact(days[22])
    assert "recovery" not in " ".join(s["title"].lower() for s in days[22].get("sessions") or [])
    assert "Hard sparring" in _contact(days[20])
    assert days[20]["day_type"] == "high"
    # The later Friday is still inside the elevated-risk cutoff.
    assert "Hard sparring" not in _contact(days[15])


def test_later_occurrence_is_not_duplicated_as_hard_contact(brief):
    first_week = brief["weekly_role_map"]["weeks"][0]
    friday = next(e for e in first_week["hard_sparring_plan"] if e["day"] == "Friday")
    assert friday["d_day"] == 15
    assert friday["effective_load"] == "technical"


def test_generation_day_friday_keeps_declared_light_combat(light_brief):
    first_week = light_brief["weekly_role_map"]["weeks"][0]
    light_ddays = sorted(
        role.get("scheduled_d_day") or int(role["scheduled_countdown_label"][2:])
        for role in first_week["session_roles"]
        if role["role_key"] == "light_combat_day"
    )
    assert light_ddays == [15, 22]
    days = _structured_days(light_brief)
    assert "light_combat_day" in days[22]["planning_day_role_keys"]
    # App S&C must not take the declared light day's slot.
    assert not any("strength" in key for key in days[22]["planning_day_role_keys"])
    assert "Technical" in _contact(days[22])


def test_late_weeks_keep_declared_weekdays_on_their_real_dates(light_brief):
    days = _structured_days(light_brief)
    # 2026-10-17 is a Saturday, so D-8 and D-1 are Fridays, D-13 and D-6 Sundays.
    for d_day in (8, 1):
        assert "light_combat_day" in days[d_day]["planning_day_role_keys"]
    for d_day in (13, 6):
        assert "hard_sparring_day" in days[d_day]["planning_day_role_keys"]


def test_seven_day_week_has_no_repeated_occurrences():
    week = {
        "fight_weekday": "saturday",
        "projected_days_until_fight_end": 7,
        "span_days": 7,
        "declared_hard_sparring_days": ["Friday", "Sunday"],
    }
    assert repeated_weekday_hard_sparring_entries(week=week, athlete_snapshot={}) == []


def test_degenerate_multi_year_week_is_not_expanded():
    # A far-future fight date yields a "week" thousands of days long; resolving
    # every repeat there ran the dose planner thousands of times and timed out.
    week = {
        "fight_weekday": "saturday",
        "projected_days_until_fight_end": 7,
        "span_days": 11595,
        "declared_hard_sparring_days": ["Friday", "Sunday"],
    }
    assert repeated_weekday_hard_sparring_entries(week=week, athlete_snapshot={}) == []
