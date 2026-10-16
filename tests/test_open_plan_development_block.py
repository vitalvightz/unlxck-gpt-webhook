"""Open (undated) plans get the dated planner's intelligence without periodisation.

An open plan used to stop at a candidate pool plus prose rules: no role map, no
closed membership, no effective dose, no realised-load checks and no goal
verdict, and it built GPP/SPP/TAPER pools as if for a 12-week camp. It now runs
one four-week development block through the canonical owners, on a calendar
placed clear of any fight, and hands the finalizer only its weekday projection.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re

import pytest

from api.models import PlanRequest
from fightcamp.main import generate_plan_sync
from fightcamp.stage2_payload import OPEN_BLOCK_HORIZON_DAYS, OPEN_BLOCK_WEEKS
from planner_clock import pin_planner_clock
from test_late_primer_e2e_vito_b import _VITO_B

_NOW = dt.datetime(2026, 10, 13, 10)
_VARIANTS = {
    "kickboxing": {},
    "boxing": {"athlete": {"technical_style": ["boxing"]}},
    "high_fatigue": {"fatigue_level": "high"},
    "limiting_knee": {"injuries": "", "guided_injury": None, "guided_injuries": [
        {"area": "Left knee", "severity": "moderate", "trend": "stable", "injury_type": "pain", "timeframe": "last_month"}]},
    "no_sparring": {"hard_sparring_days": [], "support_work_days": []},
    "mma_two_hard_power": {
        "athlete": {"technical_style": ["mma"]},
        "injuries": "", "guided_injury": None, "guided_injuries": [],
        "key_goals": ["power", "speed", "strength"],
        "primary_goal": "power", "weak_areas": ["power", "trunk_strength"],
        "primary_weak_area": "power", "goal_weakness_collision_tags": ["power"],
        "hard_sparring_days": ["Tuesday", "Thursday"],
        "support_work_days": ["Friday"],
        "training_availability": ["Monday", "Tuesday", "Thursday", "Friday", "Saturday"],
        "weekly_training_frequency": 6,
    },
    "three_days": {"training_availability": ["Monday", "Wednesday", "Friday"], "weekly_training_frequency": 3,
                   "hard_sparring_days": ["Wednesday"], "support_work_days": []},
}
_CACHE: dict[str, dict] = {}


def _result(variant: str) -> dict:
    if variant not in _CACHE:
        intake = copy.deepcopy(_VITO_B)
        intake.update(fight_date="", no_scheduled_fight=True)
        for field, value in _VARIANTS[variant].items():
            if field == "athlete":
                intake["athlete"].update(value)
            else:
                intake[field] = value
        payload = PlanRequest(**intake).to_payload()
        payload["random_seed"] = 7
        payload["_triage_resume_override"] = {"approved": True, "allowed_modes": ["needs_review", "restricted_rehab_only"]}
        mp = pytest.MonkeyPatch()
        pin_planner_clock(mp, _NOW)
        try:
            _CACHE[variant] = generate_plan_sync(payload)
        finally:
            mp.undo()
    return _CACHE[variant]


def _spec(variant: str) -> dict:
    return _result(variant)["planning_brief"]["open_plan_spec"]


def _stage1_names(brief: dict) -> set[str]:
    names = set()
    for pool in brief["candidate_pools"].values():
        for group in ("strength_slots", "conditioning_slots", "rehab_slots"):
            for slot in pool.get(group) or []:
                for option in [slot.get("selected") or {}, *(slot.get("alternates") or [])]:
                    if option.get("name"):
                        names.add(option["name"])
    return names


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_open_plan_carries_a_deterministic_four_week_session_plan(variant):
    brief = _result(variant)["planning_brief"]
    assert brief["payload_variant"] == "open_ongoing_stage2_payload"
    plan = brief["open_plan_spec"]["weekly_session_plan"]
    assert plan["authority"] == "deterministic_open_development_block"
    assert len(plan["weeks"]) == OPEN_BLOCK_WEEKS
    physical = [
        session for week in plan["weeks"] for session in week["sessions"]
        if session.get("category") in {"strength", "conditioning"}
    ]
    assert physical, variant
    names = _stage1_names(brief)
    for session in physical:
        # Closed membership: every exercise is a Stage 1 candidate with a dose.
        assert session["exercises"], session
        for exercise in session["exercises"]:
            assert exercise["name"] in names, exercise
            assert exercise["prescription"], exercise


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_open_plan_has_no_periodisation_or_countdown(variant):
    brief = _result(variant)["planning_brief"]
    spec = brief["open_plan_spec"]
    text = json.dumps({"plan": spec["weekly_session_plan"], "goals": spec["goal_coverage"]})
    assert not re.search(r"\bD-\d", text)
    # One development pool, never a taper pool.
    assert list(brief["candidate_pools"]) == ["GPP"]
    countdown_roles = {"fight_day_protocol", "strength_touch_day", "neural_primer_day",
                       "alactic_sharpness_day", "fight_week_freshness_day", "light_fight_pace_touch_day"}
    for week in spec["weekly_session_plan"]["weeks"]:
        assert not {session["role_key"] for session in week["sessions"]} & countdown_roles


def test_open_plan_goals_are_judged_from_the_block_membership():
    coverage = {entry["goal"]: entry for entry in _spec("kickboxing")["goal_coverage"]}
    assert set(coverage) == {"speed", "power"}
    for goal in ("speed", "power"):
        assert coverage[goal]["satisfied"] is True, coverage[goal]
        assert coverage[goal]["evidence"], goal
        for item in coverage[goal]["evidence"]:
            assert 1 <= item["week"] <= OPEN_BLOCK_WEEKS and item["weekday"]


def test_open_plan_finalizer_gets_the_session_plan_and_closed_membership_rules():
    result = _result("kickboxing")
    rules = " ".join(result["planning_brief"]["open_plan_spec"]["render_rules"])
    assert "weekly_session_plan" in rules and "never add, replace or substitute" in rules
    assert "weekly_session_plan" in (result.get("stage2_handoff_text") or "")


def test_open_plan_keeps_coach_owned_contact_days():
    week = _spec("kickboxing")["weekly_session_plan"]["weeks"][0]
    by_role = {session["role_key"]: session["weekday"] for session in week["sessions"]}
    assert by_role.get("hard_sparring_day") == "Thursday"
    assert by_role.get("light_combat_day") == "Monday"


def test_dated_camps_never_carry_the_open_block_horizon():
    from fightcamp.stage2_payload import _open_block_athlete_view

    view = _open_block_athlete_view({"training_days": ["monday"]})
    assert view["days_until_fight"] - 7 * OPEN_BLOCK_WEEKS == view["open_block_horizon_days"] == OPEN_BLOCK_HORIZON_DAYS
    # The horizon is far beyond every countdown band (D-17 inward).
    assert OPEN_BLOCK_HORIZON_DAYS > 17


def test_open_block_consolidates_with_the_existing_owner_before_projection(monkeypatch):
    from collections import Counter
    import fightcamp.goal_preservation as goals
    import fightcamp.stage2_payload as payload
    from test_compatible_session_consolidation import _alactic, _map, _strength

    role_map = _map(_strength(), _alactic())
    block = {"weekly_role_map": role_map, "goal_preservation": []}
    before = [payload._open_block_session(role) for role in role_map["weeks"][0]["session_roles"]]
    monkeypatch.setattr(payload, "_build_planning_brief", lambda **kwargs: block)
    monkeypatch.setattr(goals, "reconcile_goal_preservation", lambda brief: brief)
    refresh = goals.refresh_goal_evidence_after_composition
    refreshed = []

    def observe_refresh(brief):
        # The source role is already gone when the existing evidence mechanism runs.
        refreshed.append(copy.deepcopy(brief["weekly_role_map"]))
        return refresh(brief)

    monkeypatch.setattr(goals, "refresh_goal_evidence_after_composition", observe_refresh)
    result = payload._attach_open_development_block(
        {"open_plan_spec": {"plan_type": "open_ongoing_system"}},
        athlete_model={}, restrictions=[], phase_briefs={"GPP": {}},
        candidate_pools={"GPP": {"strength_slots": []}}, omission_ledger={},
        rewrite_guidance={}, plan_input=None, computed_support=None,
    )
    sessions = result["open_plan_spec"]["weekly_session_plan"]["weeks"][0]["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["weekday"] == "Monday"
    assert sessions[0]["role_key"] == "primary_strength_day"
    assert Counter((e["name"], e["prescription"]) for s in before for e in s["exercises"]) == Counter(
        (e["name"], e["prescription"]) for e in sessions[0]["exercises"]
    )
    assert len(refreshed) == 1
    assert refreshed[0]["session_consolidation_audit"]
    assert len(refreshed[0]["weeks"][0]["session_roles"]) == 1


def test_open_goal_evidence_names_the_final_projected_membership():
    spec = _spec("kickboxing")
    members = {
        (week["week"], session["weekday"], exercise["name"])
        for week in spec["weekly_session_plan"]["weeks"] for session in week["sessions"]
        for exercise in session.get("exercises") or []
    }
    for goal in spec["goal_coverage"]:
        assert goal["satisfied"]
        assert all((item["week"], item["weekday"], item["name"]) in members for item in goal["evidence"])


def test_two_hard_power_open_block_never_turns_a_microdose_into_full_strength():
    """Production-like MMA schedule across all four weeks, no model calls."""
    spec = _spec("mma_two_hard_power")
    assert len(spec["weekly_session_plan"]["weeks"]) == 4
    for week in spec["weekly_session_plan"]["weeks"]:
        sessions = week["sessions"]
        assert {"Tuesday", "Thursday"} <= {
            item["weekday"] for item in sessions if item["role_key"] == "hard_sparring_day"
        }
        assert all(
            item["weekday"] in {"Monday", "Tuesday", "Thursday", "Friday", "Saturday"}
            for item in sessions
        )
        meaningful_strength = [
            item for item in sessions if item.get("category") == "strength"
        ]
        assert meaningful_strength, week
        for session in meaningful_strength:
            if session.get("weekday") != "Monday":
                continue
            # A pre-hard Monday power touch must never contain the full bank
            # strength circuit, independent of whether this seed selected one.
            assert len(session.get("exercises") or []) <= 1
            for exercise in session.get("exercises") or []:
                dose = str(exercise.get("prescription") or "")
                assert dose.startswith(("1 x 1", "1 x 2", "2 x 1", "2 x 2")), exercise
