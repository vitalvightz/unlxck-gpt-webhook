"""F08: scheduled physical sessions with no eligible member; F14: low-load
support days carrying high-cost work.

Pipeline tests run the real Stage 1 entry point with a frozen clock and a
fixed seed; they make no model call.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from fightcamp import input_parsing
from fightcamp.calendar_context import role_d_day
from fightcamp.goal_preservation import collect_goal_evidence
from fightcamp.main import generate_plan_sync
from fightcamp.session_composition import (
    EMPTY_PHYSICAL_SESSION_REASON,
    _meets_low_load_support_contract,
    suppress_unfilled_physical_roles,
)

_NOW = dt.datetime(2026, 1, 4, 12)
_REPO = Path(__file__).resolve().parents[1]
_FULL_GYM = ("barbell", "dumbbells", "kettlebells", "medicine_ball", "heavy_bag", "bodyweight",
             "pull_up_bar", "bands", "bench", "skipping_rope")
_SHOULDER = [{"area": "Right shoulder", "severity": "low", "trend": "improving", "injury_type": "pain",
              "timeframe": "last_month"}]
_SCENARIOS = {
    # Known case: D-15 glycolytic with a declared hard day.
    "boxer21": {},
    "boxer21_freq6": {"frequency": 6},
    "boxer21_bodyweight": {"equipment": ("bodyweight",)},
    "kick10_late": {"days": 10, "sport": "kickboxing", "goals": ("speed",)},
    "bjj35_shoulder_rehab_friendly": {"days": 35, "sport": "bjj", "goals": ("strength",), "target": "68",
                                      "guided": _SHOULDER},
    "bjj35_shoulder_mobility": {"days": 35, "sport": "bjj", "goals": ("strength", "mobility"), "target": "68",
                                "hard": ("Tuesday", "Thursday"), "guided": _SHOULDER},
}
_CACHE: dict[str, dict] = {}


def _plan(key):
    if key not in _CACHE:
        kw = {"days": 21, "sport": "boxing", "goals": ("speed", "conditioning"), "frequency": 4,
              "equipment": _FULL_GYM, "hard": ("Thursday",), "target": "65", "guided": None, **_SCENARIOS[key]}
        fields = {
            "Full name": "Regression", "Age": "24", "Weight (kg)": "68", "Target Weight (kg)": kw["target"],
            "Height (cm)": "175", "Stance": "Orthodox", "Fighting Style (Technical)": kw["sport"],
            "Professional Status": "amateur", "Current Record": "0-0", "Rounds x Minutes": "3x3",
            "Weekly Training Frequency": str(kw["frequency"]), "Fatigue Level": "low",
            "Equipment Access": ", ".join(kw["equipment"]),
            "Training Availability": "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday",
            "Hard Sparring Days": ", ".join(kw["hard"]),
            "What are your key performance goals?": ", ".join(kw["goals"]), "Primary goal": kw["goals"][0],
            "Where do you feel weakest right now?": "trunk_strength", "Primary weak area": "trunk_strength",
            "When is your next fight?": (_NOW.date() + dt.timedelta(days=kw["days"])).isoformat(),
            "Athlete Time Zone": "UTC",
        }
        data = {"data": {"fields": [{"label": k, "value": v} for k, v in fields.items()]}, "random_seed": 7}
        if kw["guided"]:
            data["guided_injuries"] = kw["guided"]
        mp = pytest.MonkeyPatch()
        mp.setattr(input_parsing, "_utc_now", lambda: _NOW)
        try:
            _CACHE[key] = generate_plan_sync(data)
        finally:
            mp.undo()
    return _CACHE[key]["planning_brief"]


def _surfaces(brief):
    """(week, roles, suppressed) on the brief's authoritative calendar."""
    if "late_fight_session_sequence" in brief:
        return [({}, brief["late_fight_session_sequence"], brief["late_fight_plan_spec"].get("suppressed_roles") or [])]
    return [(w, w["session_roles"], w.get("suppressed_roles") or []) for w in brief["weekly_role_map"]["weeks"]]


def _empty_suppressions(brief):
    return [s for _, _, rows in _surfaces(brief) for s in rows if s.get("reason_code") == EMPTY_PHYSICAL_SESSION_REASON]


@pytest.mark.parametrize("key", sorted(_SCENARIOS))
def test_no_completed_plan_ships_an_empty_strength_or_conditioning_session(key):
    brief = _plan(key)
    empty = [(r["role_key"], role_d_day(w, r)) for w, roles, _ in _surfaces(brief) for r in roles
             if r.get("category") in {"strength", "conditioning"} and not r.get("selected_exercise_assignments")]
    assert empty == []


def test_known_d15_glycolytic_session_is_a_recorded_suppression():
    rows = _empty_suppressions(_plan("boxer21"))
    assert [(s["role_key"], s["preferred_system"], s["original_d_day"]) for s in rows] == [
        ("fight_pace_repeatability_day", "glycolytic", 15)
    ]
    assert rows[0]["reason"] and rows[0]["authority"] == "session_composition"


def test_late_fight_plan_suppresses_only_on_its_authoritative_sequence():
    brief = _plan("kick10_late")
    assert all(s["category"] in {"strength", "conditioning"} for s in _empty_suppressions(brief))
    # The stale weekly mirror is not rewritten into false "no eligible" claims.
    assert not any(s.get("reason_code") == EMPTY_PHYSICAL_SESSION_REASON
                   for w in brief["weekly_role_map"]["weeks"] for s in w.get("suppressed_roles") or [])


@pytest.mark.parametrize("key", sorted(_SCENARIOS))
def test_suppressed_sessions_carry_no_goal_evidence(key):
    brief = _plan(key)
    removed = {(s["role_key"], s["original_d_day"]) for s in _empty_suppressions(brief)}
    assert not {(e.get("role_key"), e.get("d_day")) for e in collect_goal_evidence(brief)} & removed


def test_recovery_and_zero_load_support_roles_are_untouched():
    brief = _plan("boxer21")
    keys = {r["role_key"] for _, roles, _ in _surfaces(brief) for r in roles}
    assert {"fight_week_freshness_day", "tactical_watch", "fight_visualization"} <= keys
    assert all(s["category"] in {"strength", "conditioning"} for s in _empty_suppressions(brief))


def test_no_new_sessions_are_added():
    brief = _plan("boxer21_freq6")
    for week, roles, _ in _surfaces(brief):
        declared = {d.lower() for d in week.get("declared_training_days") or []}
        assert all(str(r.get("scheduled_day_hint") or "").lower() in declared | {""} for r in roles
                   if r.get("category") in {"strength", "conditioning"})


# ---------------------------------------------------------------------------
# F14 - low-load support days
# ---------------------------------------------------------------------------

def _bank(name):
    rows = json.loads((_REPO / "data/conditioning_bank.json").read_text())
    return next(row for row in rows if row["name"] == name)


_LOW_LOAD_ROLE = {
    "governance": {"authority": "unused_day_low_load_support_upgrade"},
    "blocked_systems": ["glycolytic", "ATP-PCr"],
    "blocked_intensities": ["high", "max"],
    "blocked_tags": ["mech_cns_high", "high_cns", "sprint", "plyometric", "high_impact_lower", "mech_landing_impact"],
}


def test_the_kettlebell_swing_emom_breaks_the_low_load_contract():
    assert not _meets_low_load_support_contract(_LOW_LOAD_ROLE, _bank("Kettlebell Swings (EMOM Aerobic)"))


def test_zone_two_shadowboxing_meets_the_low_load_contract():
    assert _meets_low_load_support_contract(_LOW_LOAD_ROLE, _bank("Tempo Shadowboxing"))


@pytest.mark.parametrize("key", ["bjj35_shoulder_rehab_friendly", "bjj35_shoulder_mobility"])
def test_low_load_support_days_hold_only_low_load_work_or_are_suppressed(key):
    brief = _plan(key)
    support = [(w, r) for w, roles, _ in _surfaces(brief) for r in roles
               if (r.get("governance") or {}).get("authority") == "unused_day_low_load_support_upgrade"]
    assert support, "scenario must exercise a converted low-load day"
    for _, role in support:
        names = [m["name"] for m in role["selected_exercise_assignments"]]
        assert names and "Kettlebell Swings (EMOM Aerobic)" not in names
        for name in names:
            assert _meets_low_load_support_contract(role, _bank(name))
    # Week-one converted days have nothing eligible: removed, not filled.
    assert any(s["role_key"].startswith("converted_") for s in _empty_suppressions(brief))


def test_dedicated_rehab_roles_are_not_rewritten():
    brief = _plan("bjj35_shoulder_rehab_friendly")
    rehab = [r for _, roles, _ in _surfaces(brief) for r in roles if r["role_key"] == "mobility_rehab"]
    assert any(r.get("selected_exercise_assignments") for r in rehab)


# ---------------------------------------------------------------------------
# Suppression pass on hand-built briefs
# ---------------------------------------------------------------------------

def _week(*roles):
    return {"week_index": 1, "calendar_days": [{"weekday": "monday", "d_day": 20}], "session_roles": list(roles)}


def test_pass_removes_empty_strength_and_conditioning_and_keeps_everything_else():
    keep = [
        {"role_key": "primary_strength_day", "category": "strength", "selected_exercise_assignments": [{"name": "Squat"}]},
        {"role_key": "fight_week_freshness_day", "category": "recovery"},
        {"role_key": "hard_sparring_day", "category": "sparring"},
        {"role_key": "tactical_watch", "category": "support_insert"},
    ]
    drop = [
        {"role_key": "strength_touch_day", "category": "strength", "selected_exercise_assignments": []},
        {"role_key": "fight_pace_repeatability_day", "category": "conditioning", "preferred_system": "glycolytic",
         "scheduled_day_hint": "Monday"},
    ]
    brief = {"weekly_role_map": {"weeks": [_week(*keep, *drop)]}}
    suppress_unfilled_physical_roles(brief)
    week = brief["weekly_role_map"]["weeks"][0]
    assert week["session_roles"] == keep
    assert [(s["role_key"], s["reason_code"], s["original_d_day"]) for s in week["suppressed_roles"]] == [
        ("strength_touch_day", EMPTY_PHYSICAL_SESSION_REASON, None),
        ("fight_pace_repeatability_day", EMPTY_PHYSICAL_SESSION_REASON, 20),
    ]


def test_pass_acts_on_the_late_fight_sequence_and_leaves_the_mirror():
    mirror = {"weeks": [_week({"role_key": "neural_primer_day", "category": "strength"})]}
    sequence = [{"role_key": "neural_primer_day", "category": "strength", "scheduled_countdown_label": "D-7"},
                {"role_key": "strength_touch_day", "category": "strength",
                 "selected_exercise_assignments": [{"name": "Band-Resisted Punch"}]}]
    brief = {"weekly_role_map": mirror, "late_fight_session_sequence": sequence, "late_fight_plan_spec": {}}
    suppress_unfilled_physical_roles(brief)
    assert [r["role_key"] for r in sequence] == ["strength_touch_day"]
    assert [s["role_key"] for s in brief["late_fight_plan_spec"]["suppressed_roles"]] == ["neural_primer_day"]
    assert len(mirror["weeks"][0]["session_roles"]) == 1
