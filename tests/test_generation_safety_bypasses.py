"""Generation safety bypasses F05 and F06 (reports/generation_logic_integrity).

F05: foot and toe injuries did not exclude jumps, landings or sprint starts at
any severity, because the region rules lacked the impact/rebound/max-velocity
tags the ankle, knee and Achilles rules already carry.

F06: goal preservation's weekly microdose invented hard-coded exercises and
doses ("Reactive Start Burst", "Loaded Carry Touch", ...) and appended them to
closed sessions after injury, equipment, restriction and load checks had run.

The pipeline tests run the real Stage 1 entry point with a frozen clock and a
fixed seed; they make no model call.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from fightcamp import input_parsing
from fightcamp.calendar_context import role_d_day
from fightcamp.injury_guard import injury_decision
from fightcamp.main import generate_plan_sync

_REPO = Path(__file__).resolve().parents[1]
_NOW = dt.datetime(2026, 1, 4, 12)
_IMPACT_TAGS = {
    "mech_landing_impact",
    "mech_lower_jump",
    "mech_reactive_rebound",
    "mech_max_velocity",
}
_INVENTED = {
    "Reactive Start Burst",
    "Loaded Carry Touch",
    "Med-Ball Rotational Throw",
    "Reactive Footwork Walkthrough",
    "Targeted Mobility Touch",
}
_FULL_GYM = ("barbell", "dumbbells", "kettlebells", "medicine_ball", "heavy_bag", "bodyweight",
             "pull_up_bar", "bands", "bench", "skipping_rope")


def _bank() -> dict[str, dict]:
    rows = json.loads((_REPO / "data/exercise_bank.json").read_text())
    rows += json.loads((_REPO / "data/conditioning_bank.json").read_text())
    return {row["name"]: row for row in rows}


# ---------------------------------------------------------------------------
# F05 - foot and toe rules
# ---------------------------------------------------------------------------

_IMPACT_EXERCISES = ("Jump Squat", "Box Jump", "Sprint Acceleration (10-20m)")


@pytest.mark.parametrize("region", ["foot", "toe"])
@pytest.mark.parametrize("name", _IMPACT_EXERCISES)
@pytest.mark.parametrize("severity", ["moderate", "high"])
def test_foot_and_toe_exclude_jumps_landings_and_sprints(region, name, severity):
    injury = [{"region": region, "severity": severity, "original_phrase": f"right {region}"}]
    assert injury_decision(_bank()[name], injury, "SPP", "low").action == "exclude"


@pytest.mark.parametrize("region", ["foot", "toe"])
@pytest.mark.parametrize("name", _IMPACT_EXERCISES)
def test_low_severity_foot_pain_is_never_a_plain_allow(region, name):
    """Low severity follows the ankle's existing weighting (modify, not exclude).
    That boundary is pending clinical sign-off; it must never read as allow."""
    injury = [{"region": region, "severity": "low", "original_phrase": f"right {region}"}]
    assert injury_decision(_bank()[name], injury, "SPP", "low").action == "modify"


@pytest.mark.parametrize("name", _IMPACT_EXERCISES)
def test_a_foot_injury_without_a_stated_severity_excludes(name):
    """Stage 1 selection passes the injury region as text; with no severity the
    guard uses its moderate default, which now excludes impact work."""
    assert injury_decision(_bank()[name], ["right foot"], "SPP", "low").action == "exclude"


def test_the_ankle_rule_is_unchanged():
    injury = [{"region": "ankle", "severity": "low", "original_phrase": "left ankle"}]
    bank = _bank()
    assert injury_decision(bank["Jump Squat"], injury, "SPP", "low").action == "modify"
    assert injury_decision(bank["Sprint Acceleration (10-20m)"], injury, "SPP", "low").action == "allow"


# ---------------------------------------------------------------------------
# Real Stage 1 pipeline
# ---------------------------------------------------------------------------


def _payload(*, days=21, guided=None, equipment=_FULL_GYM, sport="boxing", goals=("speed", "conditioning"),
             weak=("trunk_strength",), hard=("Thursday",), target="65", resume=False):
    fight = (_NOW.date() + dt.timedelta(days=days)).isoformat()
    fields = {
        "Full name": "Safety Regression", "Age": "24", "Weight (kg)": "68", "Target Weight (kg)": target,
        "Height (cm)": "175", "Stance": "Orthodox", "Fighting Style (Technical)": sport,
        "Professional Status": "amateur", "Current Record": "0-0", "Rounds x Minutes": "3x3",
        "Weekly Training Frequency": "4", "Fatigue Level": "low", "Equipment Access": ", ".join(equipment),
        "Training Availability": "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday",
        "Hard Sparring Days": ", ".join(hard), "What are your key performance goals?": ", ".join(goals),
        "Primary goal": goals[0], "Where do you feel weakest right now?": ", ".join(weak),
        "Primary weak area": weak[0], "When is your next fight?": fight, "Athlete Time Zone": "UTC",
    }
    data = {"data": {"fields": [{"label": k, "value": v} for k, v in fields.items()]}, "random_seed": 7}
    if guided:
        data["guided_injuries"] = guided
    if resume:
        data["_triage_resume_override"] = {"approved": True, "allowed_modes": ["needs_review"]}
    return data


def _injury(area, severity, trend="stable", injury_type="pain"):
    return [{"area": area, "severity": severity, "trend": trend, "injury_type": injury_type,
             "timeframe": "last_week"}]


_CACHE: dict[str, dict] = {}


def _plan(key, **kwargs):
    if key not in _CACHE:
        mp = pytest.MonkeyPatch()
        mp.setattr(input_parsing, "_utc_now", lambda: _NOW)
        try:
            _CACHE[key] = generate_plan_sync(_payload(**kwargs))
        finally:
            mp.undo()
    return _CACHE[key]


_SCENARIOS = {
    "no_injury": {},
    "foot_low_stable": {"guided": _injury("Right foot", "low")},
    "foot_low_improving": {"guided": _injury("Right foot", "low", trend="improving")},
    "foot_high_resumed": {"guided": _injury("Right foot", "high", injury_type="pain"), "resume": True},
    "ankle_low_sprain": {"guided": _injury("Left ankle", "low", injury_type="sprain")},
    "knee_low": {"guided": _injury("Left knee", "low")},
    "achilles_low": {"guided": _injury("Achilles", "low")},
}


def _roles(result):
    for week in result["planning_brief"]["weekly_role_map"]["weeks"]:
        for role in week["session_roles"]:
            yield role


def _members(result):
    for role in _roles(result):
        for assignment in role.get("selected_exercise_assignments") or []:
            yield role, assignment


@pytest.mark.parametrize("key", ["foot_low_stable", "foot_low_improving", "foot_high_resumed"])
def test_foot_injury_plans_carry_no_landing_jump_or_sprint_work(key):
    result = _plan(key, **_SCENARIOS[key])
    assert result["planning_brief"]["athlete_snapshot"]["triage_summary"]["mode"] == "full_plan" or _SCENARIOS[key].get("resume")
    offenders = [
        (assignment["name"], sorted(set(assignment.get("mechanical_risk_tags") or []) & _IMPACT_TAGS))
        for _, assignment in _members(result)
        if set(assignment.get("mechanical_risk_tags") or []) & _IMPACT_TAGS
    ]
    names = {assignment["name"] for _, assignment in _members(result)}
    assert offenders == []
    assert not names & {"Jump Squat", "Box Jump", "Sprint Acceleration (10-20m)"}


@pytest.mark.parametrize("key", sorted(_SCENARIOS))
def test_no_invented_microdose_reaches_any_plan(key):
    result = _plan(key, **_SCENARIOS[key])
    names = {assignment["name"] for _, assignment in _members(result)}
    microdoses = {
        (role.get("priority_microdose") or {}).get("name")
        for role in _roles(result) if isinstance(role.get("priority_microdose"), dict)
    }
    assert not (names | microdoses) & _INVENTED


@pytest.mark.parametrize("key", ["foot_low_stable", "ankle_low_sprain", "knee_low", "achilles_low"])
def test_injured_athletes_receive_no_reactive_start_burst(key):
    result = _plan(key, **_SCENARIOS[key])
    assert "Reactive Start Burst" not in {assignment["name"] for _, assignment in _members(result)}


def _microdose_roles(result):
    return [role for role in _roles(result) if isinstance(role.get("priority_microdose"), dict)]


def test_bodyweight_only_athlete_gets_no_equipment_dependent_microdose():
    """S27: Loaded Carry Touch (2 x 20 m) used to be attached with no equipment."""
    result = _plan("s27_bodyweight", days=35, equipment=("bodyweight",), goals=("strength", "power"),
                   weak=("power",), target="68")
    pools = result["planning_brief"]["candidate_pools"]
    for role in _microdose_roles(result):
        microdose = role["priority_microdose"]
        assert microdose["name"] not in _INVENTED
        assert microdose["source"] == "phase_pool"
        slot = next(
            slot for pool in pools.values() if isinstance(pool, dict)
            for slot in pool.get("strength_slots") or [] if slot.get("slot_id") == microdose["slot_id"]
        )
        equipment = str(slot["selected"].get("equipment") or "").replace(",", " ").split()
        assert set(equipment) <= {"bodyweight", "none", ""}


def test_shoulder_injured_bjj_athlete_gets_no_carry_microdose():
    """S16: carries used to be the only member of two conditioning sessions."""
    result = _plan("s16_shoulder", days=35, sport="bjj", goals=("strength", "mobility"),
                   hard=("Tuesday", "Thursday"), target="68",
                   guided=_injury("Right shoulder", "low", trend="improving"))
    for role in _microdose_roles(result):
        assert role["category"] == "strength"
        assert role["priority_microdose"]["name"] not in _INVENTED
    for role in _roles(result):
        if role.get("category") in {"conditioning", "technical"}:
            assert "priority_microdose" not in role


@pytest.mark.parametrize("key", sorted(_SCENARIOS))
def test_microdoses_only_join_existing_strength_sessions_from_the_pool(key):
    result = _plan(key, **_SCENARIOS[key])
    for role in _microdose_roles(result):
        microdose = role["priority_microdose"]
        assert role["category"] == "strength"
        assert microdose["source"] == "phase_pool"
        members = [a for a in role["selected_exercise_assignments"] if a.get("slot_group") == "strength_slots"]
        assert len(members) >= 2, "host had composed membership before the microdose joined"
        priced = [p for p in role["effective_strength_prescriptions"] if p.get("slot_id") == microdose["slot_id"]]
        assert priced and priced[0]["dose_authority"] != "weekly_priority_exposure_floor"


def test_the_known_case_records_the_uncovered_week_instead_of_inventing():
    result = _plan("no_injury", **_SCENARIOS["no_injury"])
    speed = next(e for e in result["planning_brief"]["goal_preservation"] if e["goal"] == "speed")
    results = {attempt.get("result") for attempt in speed["repair_attempts"]}
    assert "floor_no_safe_candidate" in results or speed["satisfied"]
    assert "microdose_attached" not in results or all(
        r["priority_microdose"]["source"] == "phase_pool" for r in _microdose_roles(result)
    )


def test_known_case_sparring_cutoff_and_taper_are_unchanged():
    """D-17 stays hard; later declared Thursdays convert to technical."""
    result = _plan("no_injury", **_SCENARIOS["no_injury"])
    plan = {
        entry["d_day"]: entry["effective_load"]
        for week in result["planning_brief"]["weekly_role_map"]["weeks"]
        for entry in week.get("hard_sparring_plan") or []
    }
    assert plan == {17: "hard", 10: "technical", 3: "technical"}
    tail_days = [
        role_d_day(week, role)
        for week in result["planning_brief"]["weekly_role_map"]["weeks"]
        for role in week["session_roles"]
        if role.get("late_fight_tail_owned")
    ]
    assert tail_days and all(day is not None and day <= 13 for day in tail_days)
