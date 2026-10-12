"""F11: tactical watch bank exhaustion; F12: silent strength goal removal.

Pipeline tests run the real Stage 1 entry point with a frozen clock and a
fixed seed; they make no model call.
"""
from __future__ import annotations

import collections
import datetime as dt

import pytest

from fightcamp import camp_week_fillers_impl, gap_fill_inserts, input_parsing, tactical_watch_library
from fightcamp.goal_preservation import validate_goal_preservation
from fightcamp.main import generate_plan_sync
from fightcamp.tactical_watch_library import (
    TacticalWatchBankExhausted,
    ordered_phase_bank,
    select_tactical_watch,
)

_NOW = dt.datetime(2026, 1, 4, 12)
_CACHE: dict[tuple, dict] = {}


def _plan(sport, days, *, hard=("Tuesday",), goals=("strength", "conditioning"), weak=("gas_tank",)):
    key = (sport, days, hard, goals, weak)
    if key not in _CACHE:
        fields = {
            "Full name": "Regression", "Age": "24", "Weight (kg)": "70", "Target Weight (kg)": "70",
            "Height (cm)": "175", "Stance": "Orthodox", "Fighting Style (Technical)": sport,
            "Professional Status": "amateur", "Current Record": "0-0", "Rounds x Minutes": "3x3",
            "Weekly Training Frequency": "4", "Fatigue Level": "low",
            "Equipment Access": "barbell, dumbbells, bodyweight",
            "Training Availability": "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday",
            "Hard Sparring Days": ", ".join(hard), "What are your key performance goals?": ", ".join(goals),
            "Primary goal": goals[0], "Where do you feel weakest right now?": ", ".join(weak),
            "Primary weak area": weak[0], "Athlete Time Zone": "UTC",
            "When is your next fight?": (_NOW.date() + dt.timedelta(days=days)).isoformat(),
        }
        mp = pytest.MonkeyPatch()
        mp.setattr(input_parsing, "_utc_now", lambda: _NOW)
        try:
            _CACHE[key] = generate_plan_sync(
                {"data": {"fields": [{"label": k, "value": v} for k, v in fields.items()]}, "random_seed": 7}
            )
        finally:
            mp.undo()
    return _CACHE[key]


def _weeks(result):
    return result["planning_brief"]["weekly_role_map"]["weeks"]


def _watch_keys(result):
    return [role.get("tactical_watch_key") for week in _weeks(result) for role in week["session_roles"]
            if role.get("role_key") == "tactical_watch"]


# ---------------------------------------------------------------------------
# F11 - tactical watch exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport,days", [("wrestling", 35), ("wrestling", 42), ("wrestling", 70),
                                        ("muay thai", 56), ("muay thai", 84)])
def test_previously_crashing_camps_complete_with_a_watch_every_week(sport, days):
    keys = _watch_keys(_plan(sport, days))
    assert keys and all(keys)


@pytest.mark.parametrize("sport,days", [("boxing", 56), ("mma", 84), ("kickboxing", 84), ("bjj", 70)])
def test_sports_with_enough_watches_never_repeat(sport, days):
    assert not [k for k, n in collections.Counter(_watch_keys(_plan(sport, days))).items() if n > 1]


def test_exhausted_bank_reuses_least_recently_used_deterministically():
    bank = ordered_phase_bank("wrestling", "TAPER")
    assert bank
    used = {watch.key for watch in bank}
    picks = [select_tactical_watch("wrestling", "TAPER", used, allow_reuse=True).key for _ in range(len(bank) + 1)]
    assert picks == [w.key for w in bank] + [bank[0].key]
    again = {watch.key for watch in bank}
    assert [select_tactical_watch("wrestling", "TAPER", again, allow_reuse=True).key
            for _ in range(len(bank) + 1)] == picks


def test_reuse_is_opt_in():
    used = {watch.key for watch in ordered_phase_bank("wrestling", "TAPER")}
    with pytest.raises(TacticalWatchBankExhausted):
        select_tactical_watch("wrestling", "TAPER", used)


def test_an_empty_bank_records_a_skip_instead_of_failing(monkeypatch):
    monkeypatch.setattr(tactical_watch_library, "ordered_phase_bank", lambda *a, **k: ())
    with pytest.raises(TacticalWatchBankExhausted):
        select_tactical_watch("wrestling", "GPP", set(), allow_reuse=True)
    week = {"calendar_days": [{"weekday": "monday", "d_day": 30}], "declared_training_days": ["monday"],
            "session_roles": [{"role_key": "tactical_watch", "scheduled_day_hint": "Monday"}]}
    assert camp_week_fillers_impl._ensure_tactical_watch(week, {"sport": "wrestling"}, "GPP", set(), {}) is False
    assert week["tactical_watch_skipped"] == {"reason_code": "tactical_watch_bank_empty", "phase": "GPP"}


def test_gap_fill_paths_skip_instead_of_failing_on_an_empty_bank(monkeypatch):
    monkeypatch.setattr(tactical_watch_library, "ordered_phase_bank", lambda *a, **k: ())
    athlete = {"sport": "wrestling", "days_until_fight": 20}
    assert gap_fill_inserts._build_insert_role("tactical_watch", athlete, 10, usage_ledger={}) is None
    role = {"role_key": "tactical_watch"}
    assert gap_fill_inserts._apply_bank_watch(role, athlete, phase="SPP", used_watch_keys=set()) is False
    assert role["tactical_watch_skipped"]["reason_code"] == "tactical_watch_bank_empty"
    sequence = [{"role_key": "technical_shadow_rhythm", "countdown_offset": d} for d in (12, 5)]
    assert gap_fill_inserts._ensure_weekly_tactical_watches(sequence, athlete, {}, {}) == []


# ---------------------------------------------------------------------------
# F12 - strength retained, explicitly deferred inside the hard-sparring window
# ---------------------------------------------------------------------------


def _strength_case(days):
    result = _plan("boxing", days, hard=("Thursday",), goals=("strength", "speed"), weak=("strength",))
    brief = result["planning_brief"]
    return brief, next(e for e in brief["goal_preservation"] if e["goal"] == "strength")


@pytest.mark.parametrize("days", [21, 20, 14, 10])
def test_strength_survives_intake(days):
    brief, _ = _strength_case(days)
    snapshot = brief["athlete_snapshot"]
    assert "strength" in snapshot["key_goals"] and "strength" in snapshot["weaknesses"]
    assert brief["priority_focus"]["primary_goal"] == "strength"


def test_d21_is_still_a_strength_build():
    _, strength = _strength_case(21)
    assert strength["state"] == "build"
    assert "hard_sparring_strength_limit" not in strength["reason_codes"]


@pytest.mark.parametrize("days", [20, 14, 10])
def test_inside_the_window_strength_is_an_explicit_cited_deferral(days):
    brief, strength = _strength_case(days)
    assert "hard_sparring_strength_limit" in strength["reason_codes"]
    if not strength["satisfied"]:
        assert strength["state"] == "defer"
        assert strength["constraints"][0]["reason_code"] == "hard_sparring_strength_limit"
        assert strength["constraints"][0]["days_until_fight"] == days
    assert not any(e["goal"] == "strength" for e in validate_goal_preservation(brief))
    assert not any((role.get("priority_microdose") or {}).get("goal") == "strength"
                   for week in _weeks({"planning_brief": brief}) for role in week["session_roles"])


@pytest.mark.parametrize("days,expected", [
    (21, {17: "hard", 10: "technical", 3: "technical"}),
    (20, {16: "hard", 9: "technical", 2: "technical"}),
    (14, {10: "technical", 3: "technical"}),
])
def test_sparring_cutoff_is_unchanged(days, expected):
    """Values match origin/Main for the same athlete."""
    brief, _ = _strength_case(days)
    plan = {entry["d_day"]: entry["effective_load"] for week in _weeks({"planning_brief": brief})
            for entry in week.get("hard_sparring_plan") or []}
    assert plan == expected
