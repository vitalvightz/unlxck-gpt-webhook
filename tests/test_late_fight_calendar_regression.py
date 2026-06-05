"""Regression guards for the fight-camp calendar / countdown spine.

Root cause these tests lock down
-------------------------------
``days_until_fight <= 21`` routes a plan through the *late-fight* payload path
(``_PAYLOAD_MODE_MAP`` / ``_is_countdown_continuation_start``), while ``>= 22``
takes the *normal camp* path. A fight on 26 Jun 2026 (plan made 5 Jun) is D-21
→ late-fight; 27 Jun is D-22 → normal camp. That is the exact 21/22 boundary.

The two pipelines used to ship *different* calendar contracts:

* normal-camp weeks  → ``calendar_days`` + list ``countdown_range``
* late-fight weeks   → ``countdown_span`` = ``{"start_day", "end_day"}`` dict

``extract_weekly_schedule`` (which feeds the live ``/weekly-schedule`` calendar)
only understood ``calendar_days``/``countdown_range``. So every camp of 21 days
or fewer rendered a blank/inconsistent day grid — the source of the "started at
D-13" / "ended at D-4" reports — while longer camps (the majority, ~7/10) looked
fine. The fix teaches the extractor the ``countdown_span`` contract so the
calendar is always built from the fight date, gap-free and including D-0.

These tests prove the bug cannot randomly reappear.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fightcamp.fight_day_override import apply_fight_day_override_to_weekly_role_map
from fightcamp.input_parsing import _compute_days_until_fight, _parse_fight_datetime
from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_session_sequence,
    _build_late_fight_weekly_role_map,
    _days_out_payload_mode,
    _late_fight_active_role_count,
    _late_fight_allocation_plan,
    _uses_late_fight_stage2_payload,
)
from fightcamp.weekly_schedule_view import (
    _resolve_week_anchor_d_day,
    extract_weekly_schedule,
)


FIGHT_FRIDAY = "2026-06-26"  # Friday → D-21 when "today" is 2026-06-05
PLAN_TODAY = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)


def _athlete(days_until_fight: int, *, fight_date: str, training_days=None):
    return {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "training_days": training_days
        if training_days is not None
        else ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "fatigue": "low",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "fight_date": fight_date,
        "days_until_fight": days_until_fight,
        "plan_creation_weekday": "friday",
    }


def _late_fight_schedules(days_until_fight: int, *, fight_date: str, training_days=None):
    athlete = _athlete(days_until_fight, fight_date=fight_date, training_days=training_days)
    role_map = _build_late_fight_weekly_role_map(days_until_fight, athlete, None, phase="TAPER")
    role_map = apply_fight_day_override_to_weekly_role_map(role_map, athlete)
    brief = {"weekly_role_map": role_map, "athlete_model": athlete, "fight_date": fight_date}
    schedules = []
    for week_index in range(len(role_map.get("weeks", []))):
        schedule = extract_weekly_schedule(brief, week_index=week_index, fight_date=fight_date)
        assert schedule is not None
        schedules.append(schedule)
    return schedules


def _all_d_days(schedules):
    return [
        day["d_day"]
        for schedule in schedules
        for day in schedule["days"]
        if isinstance(day["d_day"], int)
    ]


# ── The 21 / 22 boundary that splits the two pipelines ────────────────────────

def test_d21_routes_late_fight_and_d22_routes_normal_camp():
    assert _uses_late_fight_stage2_payload(21) is True
    assert _days_out_payload_mode(21) == "bridge_compression_payload"
    assert _uses_late_fight_stage2_payload(22) is False
    assert _days_out_payload_mode(22) == "camp_payload"


# ── The exact contract fix: countdown_span must be understood ─────────────────

def test_extract_weekly_schedule_understands_countdown_span_contract():
    # A late-fight week ships countdown_span (dict), NOT a list countdown_range.
    schedule = extract_weekly_schedule(
        {
            "fight_date": FIGHT_FRIDAY,
            "weekly_role_map": {
                "weeks": [
                    {
                        "phase": "TAPER",
                        "countdown_span": {"start_day": 6, "end_day": 0},
                        "payload_mode": "late_fight_transition_payload",
                        "hard_sparring_plan": [],
                    }
                ]
            },
        }
    )

    assert schedule is not None
    # Calendar is built from the fight date — not blank.
    assert any(isinstance(day["d_day"], int) for day in schedule["days"])
    fight_day = next(day for day in schedule["days"] if day["d_day"] == 0)
    assert fight_day["is_fight_day"] is True
    assert fight_day["calendar_date"] == FIGHT_FRIDAY


def test_resolve_week_anchor_d_day_handles_both_contracts():
    assert _resolve_week_anchor_d_day({"countdown_range": [21, 14]}) == 14
    assert _resolve_week_anchor_d_day({"countdown_span": {"start_day": 21, "end_day": 14}}) == 14
    assert _resolve_week_anchor_d_day({"countdown_span": {"start_day": 0, "end_day": 0}}) == 0
    assert _resolve_week_anchor_d_day({}) is None


def test_countdown_span_week_is_no_longer_blank():
    week = {
        "phase": "TAPER",
        "countdown_span": {"start_day": 13, "end_day": 8},
        "payload_mode": "pre_fight_compressed_payload",
        "hard_sparring_plan": [],
    }
    schedule = extract_weekly_schedule(
        {"fight_date": FIGHT_FRIDAY, "weekly_role_map": {"weeks": [week]}}
    )
    assert schedule is not None
    labelled = [day for day in schedule["days"] if isinstance(day["d_day"], int)]
    assert len(labelled) == 7, "every day in the rendered week must carry a D-day"
    assert all(day["calendar_date"] for day in schedule["days"])


# ── End-to-end late-fight camps now render a real countdown incl. D-0 ─────────

# Camps whose countdown spans multiple days build a paged weekly grid. The
# continuation window is 3..21 days out — these all carry a D-0 segment.
@pytest.mark.parametrize("days_until_fight", [21, 14, 7, 4, 3])
def test_late_fight_camp_renders_calendar_with_fight_day(days_until_fight):
    schedules = _late_fight_schedules(days_until_fight, fight_date=FIGHT_FRIDAY)
    d_days = _all_d_days(schedules)
    assert d_days, "late-fight calendar must not be blank"
    # The fight day (D-0) is present and dated on the actual fight date.
    assert 0 in d_days
    fight_day = next(
        day
        for schedule in schedules
        for day in schedule["days"]
        if day["d_day"] == 0
    )
    assert fight_day["is_fight_day"] is True
    assert fight_day["calendar_date"] == FIGHT_FRIDAY


def test_fight_tomorrow_grid_is_empty_but_graceful():
    # D-1/D-2 are single-session modes with no multi-day grid by design; the
    # extractor must return None rather than crash or invent a calendar.
    athlete = _athlete(1, fight_date="2026-06-06")
    role_map = _build_late_fight_weekly_role_map(1, athlete, None, phase="TAPER")
    role_map = apply_fight_day_override_to_weekly_role_map(role_map, athlete)
    brief = {"weekly_role_map": role_map, "athlete_model": athlete, "fight_date": "2026-06-06"}
    assert extract_weekly_schedule(brief, week_index=0, fight_date="2026-06-06") is None


def test_late_fight_21_day_camp_does_not_start_at_d13():
    # The reported bug: a D-21 plan visibly "started at D-13". The calendar must
    # reach deep into the camp, well past D-13, not begin there.
    schedules = _late_fight_schedules(21, fight_date=FIGHT_FRIDAY)
    d_days = _all_d_days(schedules)
    assert max(d_days) >= 14, f"calendar should cover the early camp, got max D-{max(d_days)}"


def test_late_fight_camp_never_renders_a_blank_week():
    schedules = _late_fight_schedules(21, fight_date=FIGHT_FRIDAY)
    for schedule in schedules:
        labelled = [day for day in schedule["days"] if isinstance(day["d_day"], int)]
        assert labelled, "no late-fight week may render an empty day grid"


def test_late_fight_calendar_is_timezone_safe_dates():
    # Dates are pure calendar arithmetic off the fight date — no clock drift.
    schedules = _late_fight_schedules(7, fight_date=FIGHT_FRIDAY)
    for schedule in schedules:
        for day in schedule["days"]:
            if day["d_day"] == 0:
                assert day["calendar_date"] == FIGHT_FRIDAY


# ── Sparse availability must not collapse the calendar spine ──────────────────

@pytest.mark.parametrize(
    "training_days",
    [
        ["monday", "wednesday", "friday"],
        ["tuesday", "thursday", "saturday"],
        ["wednesday"],
        [],
    ],
)
def test_sparse_availability_keeps_full_calendar(training_days):
    # The calendar is the source of truth: rest/no-session days are still shown.
    schedules = _late_fight_schedules(21, fight_date=FIGHT_FRIDAY, training_days=training_days)
    for schedule in schedules:
        labelled = [day for day in schedule["days"] if isinstance(day["d_day"], int)]
        assert len(labelled) == 7, "all seven weekdays render regardless of availability"


# ── Timezone-safe days_until_fight (calendar-day difference) ──────────────────

@pytest.mark.parametrize("hour", [0, 6, 12, 23])
def test_days_until_fight_is_calendar_day_difference_not_clock_sensitive(hour):
    fight = _parse_fight_datetime(FIGHT_FRIDAY)
    now = datetime(2026, 6, 5, hour, 30, tzinfo=timezone.utc)
    assert _compute_days_until_fight(FIGHT_FRIDAY, fight, now_utc=now) == 21


def test_fight_tomorrow_is_one_day_out():
    fight = _parse_fight_datetime("2026-06-06")
    assert _compute_days_until_fight("2026-06-06", fight, now_utc=PLAN_TODAY) == 1


# ── The plan body must not start at D-13: bridge-window allocation ────────────
#
# Second, distinct root cause behind "the plan starts a week late": in the
# D-21..D-18 bridge window the athlete has a *required* coach-owned
# `hard_sparring_day` plus the app's required strength + freshness = 3 roles,
# but `max_active_roles` is 2. The coach-owned sparring placeholder wrongly
# counted against the app's active-role budget, so the allocator dropped every
# role and the whole D-21..D-18 window rendered empty — the first real session
# fell to D-13. The budget must count only app-owned sessions.

def _pro_pressure_boxer(days_until_fight: int, fight_date: str):
    return {
        "sport": "boxing",
        "status": "professional",
        "rounds_format": "3x3",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": ["monday", "thursday"],
        "fatigue": "moderate",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "key_goals": ["recovery", "strength"],
        "weaknesses": ["gas_tank"],
        "injuries": [],
        "fight_date": fight_date,
        "days_until_fight": days_until_fight,
        "plan_creation_weekday": "friday",
    }


def test_active_role_count_excludes_coach_owned_sparring():
    roles = [
        {"role_key": "hard_sparring_day"},      # coach-owned → not counted
        {"role_key": "strength_touch_day"},     # app-owned   → counted
        {"role_key": "fight_week_freshness_day"},  # app-owned → counted
    ]
    assert _late_fight_active_role_count(roles) == 2


@pytest.mark.parametrize("days_until_fight", [21, 20, 19, 18])
def test_bridge_window_allocation_is_not_empty(days_until_fight):
    # Every day in the D-21..D-18 bridge window must place at least the app's
    # required strength + freshness sessions (previously dropped to nothing).
    athlete = _pro_pressure_boxer(days_until_fight, FIGHT_FRIDAY)
    roles = _late_fight_allocation_plan(days_until_fight, athlete).get("session_roles", [])
    role_keys = {role.get("role_key") for role in roles}
    assert "strength_touch_day" in role_keys, f"D-{days_until_fight} dropped the strength touch"
    assert "fight_week_freshness_day" in role_keys, f"D-{days_until_fight} dropped freshness"
    assert all(
        isinstance(role.get("countdown_offset"), int) for role in roles
    ), "every placed role must carry a countdown offset"


def test_d21_pressure_boxer_plan_starts_at_d21_not_d13():
    # The exact reported case: 26 Jun fight, pro pressure boxer, Mon/Thu hard
    # sparring, made on a Friday (D-21). The visible plan must open at D-21.
    athlete = _pro_pressure_boxer(21, FIGHT_FRIDAY)
    sequence = _build_late_fight_session_sequence(21, athlete)
    offsets = [role.get("countdown_offset") for role in sequence if isinstance(role.get("countdown_offset"), int)]
    assert offsets, "late-fight session sequence must not be empty"
    assert max(offsets) == 21, f"plan should open at D-21, opened at D-{max(offsets)}"


def test_d22_and_d21_are_adjacent_but_route_differently():
    # 26 Jun → 21 (late-fight), 27 Jun → 22 (normal). Locks the boundary so a
    # future refactor cannot silently move the camp/late-fight split.
    fight_26 = _parse_fight_datetime("2026-06-26")
    fight_27 = _parse_fight_datetime("2026-06-27")
    assert _compute_days_until_fight("2026-06-26", fight_26, now_utc=PLAN_TODAY) == 21
    assert _compute_days_until_fight("2026-06-27", fight_27, now_utc=PLAN_TODAY) == 22
    assert _uses_late_fight_stage2_payload(21) is True
    assert _uses_late_fight_stage2_payload(22) is False
