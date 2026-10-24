"""Capacity is evidence-based; goal recovery still uses the canonical owners."""
from copy import deepcopy
import datetime as dt

import pytest

from fightcamp.stage2_role_map import (
    _readiness_compression_floor,
)


@pytest.mark.parametrize("record, expected", [
    ({"severity": "low"}, 0),
    ({"severity": "moderate", "severity_source": "fallback_default"}, 0),
    ({"severity": "moderate", "severity_source": "guided_card"}, 1),
    ({"severity": "high"}, 1),
    ({"severity": "low", "training_impact": "not_limiting"}, 0),
    ({"severity": "low", "notes": "[training_impact:limiting]"}, 1),
    ({"severity": "high", "notes": "[training_impact:cant_train]"}, 1),
    ({"severity": "severe", "training_impact": "not_limiting"}, 1),
    ({"severity": "low", "training_impact": "not_limiting", "medical_hold": True}, 1),
])
def test_session_compression_uses_existing_impact_and_severity(record, expected):
    athlete = {"injuries": ["Sometimes my left knee hurts"], "parsed_injuries": [record],
               "readiness_flags": ["injury_management"]}
    before = deepcopy(athlete)
    assert _readiness_compression_floor(athlete) == expected
    # Budget classification never removes movement-specific injury metadata.
    assert athlete == before


@pytest.mark.parametrize("safety", [
    {"injury_mode": "medical_hold"}, {"injury_mode": "restricted_rehab_only"},
    {"readiness_flags": ["red_flag_injury"]}, {"readiness_flags": ["severe_injury"]},
])
def test_independent_safety_overrides_still_compress(safety):
    assert _readiness_compression_floor(safety) >= 1


def test_unknown_raw_symptoms_do_not_delete_a_session():
    athlete = {"injuries": ["Sometimes my left knee hurts"], "readiness_flags": ["injury_management"]}
    assert _readiness_compression_floor(athlete) == 0
    assert _readiness_compression_floor({**athlete, "fatigue": "high"}) == 1


@pytest.mark.parametrize("dated", [False, True])
def test_sam_like_intake_retains_primary_strength_and_contact_locks(monkeypatch, dated):
    from api.models import PlanRequest
    from fightcamp.main import generate_plan_sync
    import fightcamp.goal_preservation as goals
    from planner_clock import pin_planner_clock
    from test_late_primer_e2e_vito_b import _VITO_B

    intake = deepcopy(_VITO_B)
    intake.update(
        fight_date="2026-12-28" if dated else "", no_scheduled_fight=not dated,
        injuries="Sometimes my left knee hurts", guided_injury=None, guided_injuries=[],
        primary_goal="strength", key_goals=["strength", "power", "conditioning"],
        weak_areas=["footwork"], primary_weak_area="footwork", support_work_days=[],
        hard_sparring_days=["Wednesday", "Sunday"],
        training_availability=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"],
        weekly_training_frequency=4,
    )
    pin_planner_clock(monkeypatch, dt.datetime(2026, 10, 13, 10))
    captured = []
    original = goals.reconcile_goal_preservation

    def observe(brief):
        result = original(brief)
        captured.append(deepcopy(result))
        return result

    monkeypatch.setattr(goals, "reconcile_goal_preservation", observe)
    payload = PlanRequest(**intake).to_payload()
    payload["random_seed"] = 7
    result = generate_plan_sync(payload)
    assert result["planning_brief"]
    block = captured[0]
    weeks = block["weekly_role_map"]["weeks"]
    if dated:
        weeks = [w for w in weeks if min(d["d_day"] for d in w["calendar_days"]) > 20]
    else:
        assert len(weeks) == 4
        primary = next(g for g in block["goal_preservation"] if g["goal"] == "strength")
        assert primary["satisfied"] and primary["state"] == "build"
    assert weeks
    for week in weeks:
        from fightcamp.physical_session_frequency import appointment_budget_exceeded
        if not dated:
            assert not appointment_budget_exceeded({"weeks": [week]}, 4)
        roles = week["session_roles"]
        assert all(r.get("scheduled_day_hint") in intake["training_availability"]
                   for r in roles if r.get("scheduled_day_hint"))
        assert {r.get("scheduled_day_hint") for r in roles if r["role_key"] == "hard_sparring_day"} == {"Wednesday", "Sunday"}
        assert any(r["category"] == "strength" and r.get("selected_exercise_assignments") for r in roles)
        assert not any("injury_management" in r.get("compression_reason_codes", []) for r in week["suppressed_roles"])


@pytest.mark.parametrize("goal", ["strength", "power", "speed", "conditioning"])
def test_build_goal_attempts_maintenance_recovery_before_deferral(monkeypatch, goal):
    # Isolate reconciliation order: the same repair owner must receive the
    # maintenance obligation, not merely be asked to build a second time.
    import fightcamp.goal_preservation as goals
    from test_goal_preservation import _brief

    brief = _brief(roles=[])
    brief["athlete_snapshot"].update(primary_goal=goal, key_goals=[goal])
    brief["priority_focus"] = {"primary_goal": goal}
    attempts = []
    constraint = {"reason_code": "calendar_capacity", "authority": "calendar_policy"}
    monkeypatch.setattr(goals, "_deferral_constraints", lambda *args: [constraint])
    monkeypatch.setattr(goals, "collect_goal_evidence", lambda brief: [])

    def repair(brief, entry, **kwargs):
        attempts.append(entry["state"])
        return [{"result": "calendar_forbidden"}]

    monkeypatch.setattr(goals, "_restore_goal_roles", repair)
    goals.reconcile_goal_preservation(brief)
    assert attempts == ["build", "maintain"]
    entry = brief["goal_preservation"][0]
    assert entry["state"] == "defer" and not entry["satisfied"]
    assert entry["constraints"] == [constraint]


@pytest.mark.parametrize("goal", ["strength", "power", "speed", "conditioning"])
def test_primary_maintenance_recovery_is_used_when_build_is_infeasible(monkeypatch, goal):
    import fightcamp.goal_preservation as goals
    from test_goal_preservation import _brief

    brief = _brief(roles=[])
    brief["athlete_snapshot"].update(primary_goal=goal, key_goals=[goal])
    brief["priority_focus"] = {"primary_goal": goal}
    repaired = []
    witness = {"name": "Existing safe candidate"}
    constraint = {"reason_code": "calendar_capacity", "authority": "calendar_policy"}
    monkeypatch.setattr(goals, "_deferral_constraints", lambda *args: [constraint])
    monkeypatch.setattr(goals, "collect_goal_evidence", lambda brief: [])

    def coverage(entry, brief, evidence):
        if repaired and entry["state"] == "maintain":
            return [witness], []
        return [], [{"min_d_day": 14, "max_d_day": 20}]

    def repair(brief, entry, **kwargs):
        if entry["state"] == "maintain":
            repaired.append(goal)
        return [{"result": "restored" if repaired else "calendar_forbidden"}]

    monkeypatch.setattr(goals, "_coverage", coverage)
    monkeypatch.setattr(goals, "_restore_goal_roles", repair)
    goals.reconcile_goal_preservation(brief)
    entry = brief["goal_preservation"][0]
    assert repaired == [goal]
    assert entry["state"] == "maintain" and entry["satisfied"]
    assert entry["evidence"] == [witness]
    assert entry["constraints"] == [constraint]


def test_goal_repair_cannot_add_an_appointment_over_requested_budget():
    from test_goal_preservation import _brief, _role
    from fightcamp.goal_preservation import _restore_goal_roles, classify_goal_preservation

    occupied = {"role_key": "aerobic_base_day", "category": "conditioning",
                "preferred_system": "aerobic", "session_index": 1,
                "scheduled_day_hint": "Thursday", "scheduled_countdown_label": "D-15"}
    brief = _brief(roles=[occupied])
    brief["athlete_snapshot"].update(primary_goal="strength", key_goals=["strength"], training_frequency=1)
    brief["priority_focus"] = {"primary_goal": "strength"}
    week = brief["weekly_role_map"]["weeks"][0]
    week["calendar_days"] = [{"weekday": "monday", "d_day": 18}, {"weekday": "thursday", "d_day": 15}]
    week["goal_repair_candidates"] = [_role()]
    entry = {**classify_goal_preservation(brief["athlete_snapshot"])[0], "state": "maintain"}
    audit = _restore_goal_roles(brief, entry, enforce_session_budget=True)
    week = brief["weekly_role_map"]["weeks"][0]
    assert len(week["session_roles"]) == 1
    assert any(a["result"] == "session_cap" for a in audit)
