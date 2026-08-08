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
    _is_app_owned_visible_role,
    _late_fight_active_role_count,
    _late_fight_allocation_plan,
    _uses_late_fight_stage2_payload,
)
import fightcamp.stage2_payload_late_fight as late_fight_module
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
    # D-13..D-8 is a six-day window, so it renders six dated days — not a padded
    # seven-day Mon-Sun grid, which used to invent a seventh day the window
    # never covered.
    assert len(labelled) == 6, "the week must render exactly its countdown window"
    assert sorted((day["d_day"] for day in labelled), reverse=True) == [13, 12, 11, 10, 9, 8]
    assert all(day["calendar_date"] for day in labelled)
    unlabelled = [day for day in schedule["days"] if not isinstance(day["d_day"], int)]
    # D-13..D-8 off the Friday fight is Sat 13 Jun .. Thu 18 Jun, so Friday is
    # the one weekday the window does not reach.
    assert [day["weekday"] for day in unlabelled] == ["Fri"], "out-of-window slots stay blank"


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


def _true_weekday_d_days(start: int, end: int, fight_date: str) -> dict[str, int]:
    """Ground truth: the weekday each D-day in a window actually falls on."""
    from datetime import date as _date, timedelta as _td

    fight = _date.fromisoformat(fight_date)
    return {(fight - _td(days=d)).strftime("%a"): d for d in range(start, end - 1, -1)}


def _declared_windows_and_schedules(days_until_fight: int, *, fight_date: str):
    """Pair each role-map week's *declared* countdown window with what it renders.

    The declared window must come from the role map — a late-fight week ships
    ``countdown_span``, so ``schedule["original_countdown_range"]`` is empty and
    ``schedule["countdown_range"]`` is derived from the rendered days. Reading the
    window off the schedule would compare the render against itself.
    """
    athlete = _athlete(days_until_fight, fight_date=fight_date)
    role_map = _build_late_fight_weekly_role_map(days_until_fight, athlete, None, phase="TAPER")
    role_map = apply_fight_day_override_to_weekly_role_map(role_map, athlete)
    brief = {"weekly_role_map": role_map, "athlete_model": athlete, "fight_date": fight_date}
    paired = []
    for week_index, week in enumerate(role_map.get("weeks", [])):
        span = week.get("countdown_span") or {}
        start, end = span.get("start_day"), span.get("end_day")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        schedule = extract_weekly_schedule(brief, week_index=week_index, fight_date=fight_date)
        assert schedule is not None
        paired.append(((start, end), schedule))
    assert paired, "late-fight role map must declare countdown windows"
    return paired


@pytest.mark.parametrize("days_until_fight", [21, 20, 17, 14, 9, 7, 4, 3])
def test_every_late_fight_week_renders_its_own_countdown_window(days_until_fight):
    # The defect: a late-fight week is a countdown *segment* (D-20..D-14, D-7..D-7,
    # D-4..D-2 …), but the calendar was rebuilt as the Mon-Sun week around the
    # segment's end day. Every earlier weekday came out a week late — a declared
    # hard-sparring day locked at D-18 rendered as D-11, inside the D-17 ban.
    for (start, end), schedule in _declared_windows_and_schedules(
        days_until_fight, fight_date=FIGHT_FRIDAY
    ):
        truth = _true_weekday_d_days(start, end, FIGHT_FRIDAY)
        reported = {
            day["weekday"]: day["d_day"]
            for day in schedule["days"]
            if isinstance(day["d_day"], int)
        }
        # Only the 8-day D-21..D-14 bridge overflows the seven weekday slots; it
        # drops the plan-creation day rather than a day still to be trained.
        for weekday, d_day in reported.items():
            assert truth.get(weekday) == d_day, (
                f"week D-{start}..D-{end} put {weekday} at D-{d_day}, truly D-{truth.get(weekday)}"
            )
        assert set(reported) <= set(truth), (
            f"week D-{start}..D-{end} rendered days outside its window: "
            f"{sorted(set(reported) - set(truth))}"
        )


@pytest.mark.parametrize("days_until_fight", [21, 20, 14, 7, 3])
def test_late_fight_weeks_never_render_days_after_the_fight(days_until_fight):
    # The Mon-Sun rebuild ran past D-0 for the final segments, emitting negative
    # D-days (post-fight) and even stamping a sparring card on one.
    schedules = _late_fight_schedules(days_until_fight, fight_date=FIGHT_FRIDAY)
    for schedule in schedules:
        for day in schedule["days"]:
            if isinstance(day["d_day"], int):
                assert day["d_day"] >= 0, f"rendered post-fight day {day['weekday']} D-{day['d_day']}"
                assert day["is_after_fight_day"] is False


def test_a_declared_sparring_day_is_not_duplicated_across_weeks():
    # hard_sparring_plan is keyed by weekday name, so before the fix one declared
    # Saturday was stamped into every week that had a Saturday slot — four weeks,
    # each at a different (or missing) D-day.
    schedules = _late_fight_schedules(21, fight_date=FIGHT_FRIDAY)
    placements: list[tuple[str, int | None]] = [
        (day["weekday"], day["d_day"])
        for schedule in schedules
        for day in schedule["days"]
        if day["sparring_day_class"] not in ("", "none")
    ]
    assert placements, "declared sparring days must still render"
    assert len(placements) == len(set(placements)), f"duplicate sparring placements: {placements}"
    assert all(isinstance(d_day, int) for _, d_day in placements), (
        f"a sparring day rendered without a D-day: {placements}"
    )


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
    # Availability must never shrink a week below the countdown window it covers
    # (late-fight windows run 1-8 days, so "seven days" is not the contract —
    # "exactly the declared window" is).
    schedules = _late_fight_schedules(21, fight_date=FIGHT_FRIDAY, training_days=training_days)
    for schedule in schedules:
        labelled = [day for day in schedule["days"] if isinstance(day["d_day"], int)]
        declared = schedule["original_countdown_range"] or schedule["countdown_range"]
        expected = min(declared[0] - declared[1] + 1, 7)
        assert len(labelled) == expected, (
            f"week {schedule['week_index']} covers D-{declared[0]}..D-{declared[1]} "
            f"but rendered {len(labelled)} days"
        )


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


# ── System invariant: no active window ever resolves to zero sessions ─────────
#
# Required roles are mandatory; the budget caps may only limit optional roles.
# This sweep is the durable, fail-loud guard against the whole class of bug
# (caps silently dropping required roles → empty window → plan starts late),
# not just the coach-owned-sparring trigger that first surfaced it.

def _all_days_boxer(days_until_fight: int):
    return {
        "sport": "boxing", "status": "professional", "rounds_format": "3x3",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "hard_sparring_days": ["tuesday", "thursday"], "fatigue": "moderate",
        "weight_cut_pct": 0.0, "weight_cut_risk": False, "readiness_flags": [],
        "key_goals": ["recovery", "strength"], "weaknesses": ["gas_tank"],
        "injuries": [], "fight_date": FIGHT_FRIDAY, "days_until_fight": days_until_fight,
        "plan_creation_weekday": "friday",
    }


def _sparse_boxer(days_until_fight: int):
    return {
        "sport": "boxing", "status": "amateur", "rounds_format": "3x3",
        "training_days": ["wednesday"], "hard_sparring_days": [], "fatigue": "low",
        "weight_cut_pct": 0.0, "weight_cut_risk": False, "readiness_flags": [],
        "key_goals": ["conditioning_endurance"], "weaknesses": ["gas_tank"],
        "injuries": [], "fight_date": FIGHT_FRIDAY, "days_until_fight": days_until_fight,
        "plan_creation_weekday": "friday",
    }


_PROFILE_BUILDERS = {
    "pro_pressure_mon_thu": lambda d: _pro_pressure_boxer(d, FIGHT_FRIDAY),
    "all_days": _all_days_boxer,
    "sparse_wed": _sparse_boxer,
}


@pytest.mark.parametrize("profile", ["pro_pressure_mon_thu", "all_days"])
@pytest.mark.parametrize("days_until_fight", list(range(1, 22)))
def test_active_window_keeps_required_app_work_when_legal_days_exist(profile, days_until_fight):
    athlete = _PROFILE_BUILDERS[profile](days_until_fight)
    roles = _late_fight_allocation_plan(days_until_fight, athlete).get("session_roles", [])
    assert roles, f"{profile} D-{days_until_fight} resolved to an empty active window"
    app_owned = [r for r in roles if _is_app_owned_visible_role(r.get("role_key"))]
    assert app_owned, f"{profile} D-{days_until_fight} placed no app-owned session"


@pytest.mark.parametrize("days_until_fight", list(range(1, 22)))
def test_sparse_availability_never_manufactures_an_unavailable_app_day(days_until_fight):
    athlete = _sparse_boxer(days_until_fight)
    roles = _late_fight_allocation_plan(days_until_fight, athlete).get("session_roles", [])
    for role in roles:
        if not _is_app_owned_visible_role(role.get("role_key")):
            continue
        weekday = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip().lower()
        assert weekday == "wednesday"


def test_caps_relax_to_keep_required_roles_when_required_meets_cap():
    # Bridge D-21: required app-owned roles (strength + freshness) == max_active
    # cap of 2, and a coach-owned hard spar also sits in the window. The cap must
    # not drop the required app-owned roles. (Generalises the coach-owned fix
    # into the "caps only limit optional" invariant.)
    athlete = _pro_pressure_boxer(21, FIGHT_FRIDAY)
    roles = _late_fight_allocation_plan(21, athlete).get("session_roles", [])
    role_keys = {r.get("role_key") for r in roles}
    assert {"strength_touch_day", "fight_week_freshness_day"} <= role_keys
    # The app-owned active count still honours the cap (coach sparring excluded).
    assert _late_fight_active_role_count(roles) <= 2


def test_empty_active_window_fails_loud(monkeypatch, caplog):
    # If placement is genuinely impossible (every subset fails assignment), the
    # allocator must log a warning rather than silently shipping an empty window.
    monkeypatch.setattr(late_fight_module, "_late_fight_best_assignment", lambda *a, **k: None)
    athlete = _pro_pressure_boxer(21, FIGHT_FRIDAY)
    with caplog.at_level("WARNING"):
        result = _late_fight_allocation_plan(21, athlete)
    assert result.get("session_roles") == []
    assert any("late_fight_allocation_empty_active_window" in rec.message for rec in caplog.records)


def test_d22_and_d21_are_adjacent_but_route_differently():
    # 26 Jun → 21 (late-fight), 27 Jun → 22 (normal). Locks the boundary so a
    # future refactor cannot silently move the camp/late-fight split.
    fight_26 = _parse_fight_datetime("2026-06-26")
    fight_27 = _parse_fight_datetime("2026-06-27")
    assert _compute_days_until_fight("2026-06-26", fight_26, now_utc=PLAN_TODAY) == 21
    assert _compute_days_until_fight("2026-06-27", fight_27, now_utc=PLAN_TODAY) == 22
    assert _uses_late_fight_stage2_payload(21) is True
    assert _uses_late_fight_stage2_payload(22) is False



def test_d21_shared_weekday_uses_rendered_d14_sparring_verdict():
    # A Friday plan created at D-21 and a Friday fight make D-21 and D-14
    # share the same weekday. The calendar drops D-21 because eight countdown
    # days cannot fit seven weekday slots. The visible Friday must therefore
    # carry D-14's technical verdict, never D-21's hard verdict.
    athlete = _athlete(21, fight_date=FIGHT_FRIDAY)
    athlete["hard_sparring_days"] = ["friday"]
    athlete["training_days"] = ["monday", "tuesday", "wednesday", "thursday", "friday"]

    role_map = _build_late_fight_weekly_role_map(21, athlete, None, phase="TAPER")
    role_map = apply_fight_day_override_to_weekly_role_map(role_map, athlete)
    bridge = role_map["weeks"][0]
    assert bridge["countdown_span"] == {"start_day": 21, "end_day": 14}

    friday_entries = [
        entry
        for entry in bridge["hard_sparring_plan"]
        if str(entry.get("day") or "").strip().lower() == "friday"
    ]
    assert len(friday_entries) == 1
    assert friday_entries[0]["d_day"] == 14
    assert friday_entries[0]["effective_load"] == "technical"
    assert friday_entries[0]["status"] == "convert_to_technical_suggested"
    assert "d17_hard_sparring_ban" in friday_entries[0]["reason_codes"]
    assert not any(
        entry.get("d_day") == 21 and entry.get("effective_load") == "hard"
        for entry in bridge["hard_sparring_plan"]
    )

    brief = {"weekly_role_map": role_map, "athlete_model": athlete, "fight_date": FIGHT_FRIDAY}
    schedule = extract_weekly_schedule(brief, week_index=0, fight_date=FIGHT_FRIDAY)
    assert schedule is not None
    friday = next(day for day in schedule["days"] if day["weekday"] == "Fri")
    assert friday["d_day"] == 14
    assert friday["effective_load"] == "technical"
    assert friday["status"] == "convert_to_technical_suggested"
    assert "d17_hard_sparring_ban" in friday["reason_codes"]
