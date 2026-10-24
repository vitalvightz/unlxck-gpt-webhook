"""Real persisted readiness -> intake -> allocation -> membership -> goal verdict."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest

from api.models import PlanRequest
from api.services.sparring_readiness_snapshot import annotate_payload_with_sparring_readiness
from fightcamp.goal_preservation import validate_goal_preservation
from fightcamp.main import generate_plan_sync
from planner_clock import pin_planner_clock
from tests.support import FakeStore


@pytest.mark.parametrize("dated", [False, True])
@pytest.mark.parametrize("symptom", ["Sometimes my left knee hurts", "Sometimes my right shoulder hurts", ""])
@pytest.mark.parametrize("coached_days", [[], ["Tuesday", "Friday"]])
def test_persisted_readiness_preserves_app_budget_with_coached_days(monkeypatch, dated, symptom, coached_days, frequency=4):
    import fightcamp.goal_preservation as goals

    intake = json.loads((Path(__file__).parent / "fixtures/injury_readiness/sam_like.json").read_text())
    intake.update(injuries=symptom, support_work_days=coached_days, weekly_training_frequency=frequency,
                  no_scheduled_fight=not dated, fight_date="2026-12-05" if dated else "")
    store = FakeStore()
    if symptom:
        # The production tracker's legacy default, not an independently graded
        # moderate injury. Snapshot annotation must retain its provenance.
        store.create_injury_flag("athlete", {"source": "intake", "severity": "moderate", "status": "open",
                                            "description": symptom, "body_area": symptom})
    pin_planner_clock(monkeypatch, datetime(2026, 10, 24, 15, 6))
    payload = annotate_payload_with_sparring_readiness(
        PlanRequest(**intake).to_payload(), store=store, athlete_id="athlete", training_day="2026-10-24")
    payload["random_seed"] = 7
    captured = []
    original = goals.reconcile_goal_preservation

    def observe(brief):
        result = original(brief)
        captured.append(deepcopy(result))
        return result

    monkeypatch.setattr(goals, "reconcile_goal_preservation", observe)
    result = generate_plan_sync(payload)
    final = result["planning_brief"]
    assert final["athlete_snapshot"]["triage_summary"]["mode"] == "full_plan"
    assert not final["athlete_snapshot"]["injury_restrictions"]
    model = final["athlete_snapshot"]
    block = captured[0]
    weeks = block["weekly_role_map"]["weeks"]
    normal = [w for w in weeks if min(d["d_day"] for d in w["calendar_days"]) > 20]
    assert normal
    candidates = {option.get("name") for pool in block["candidate_pools"].values()
                  for group in ("strength_slots", "conditioning_slots", "rehab_slots")
                  for slot in pool.get(group) or []
                  for option in [slot.get("selected") or {}, *(slot.get("alternates") or [])]}
    for week in normal:
        roles = week["session_roles"]
        assert {r["scheduled_day_hint"].lower() for r in roles if r["role_key"] == "hard_sparring_day"} == {"wednesday", "sunday"}
        assert all(r.get("scheduled_day_hint", "").lower() in {d.lower() for d in intake["training_availability"]}
                   for r in roles if r.get("scheduled_day_hint"))
        assert not any("injury_management" in r.get("compression_reason_codes", []) for r in week["suppressed_roles"])
        strength = [r for r in roles if r["category"] == "strength"]
        if coached_days:
            assert {r["scheduled_day_hint"].lower() for r in roles if r["role_key"] == "light_combat_day"} == {"tuesday", "friday"}
        if frequency == 4:
            assert any(r["category"] == "conditioning" for r in roles)
            assert strength and all(r.get("selected_exercise_assignments") for r in strength)
            assert all(member["name"] in candidates for r in strength for member in r["selected_exercise_assignments"])
            assert not any("guidance" in member["name"].lower() for r in strength for member in r["selected_exercise_assignments"])
    if dated:
        assert any(r["category"] == "recovery" for w in weeks for r in w["session_roles"])
    if coached_days and symptom and not dated:
        assert any(r["role_key"] in {"mobility_rehab", "joint_prep"}
                   for w in normal for r in w["session_roles"])
    assert all(e["scope"] == "contact" for e in model["readiness_evidence"])
    if not dated:
        primary = next(g for g in final["open_plan_spec"]["goal_coverage"] if g["goal"] == "strength")
        assert primary["satisfied"]
        if frequency == 4:
            assert primary["state"] == "build" and primary["evidence"]
            members = {(w["week"], s["weekday"], ex["name"])
                       for w in final["open_plan_spec"]["weekly_session_plan"]["weeks"]
                       for s in w["sessions"] for ex in s.get("exercises", [])}
            assert all((e["week"], e["weekday"], e["name"]) in members for e in primary["evidence"])
    assert not [e for e in validate_goal_preservation(final) if e.get("goal") == "strength"]
    if not dated:
        forged = deepcopy(final)
        goal = next(g for g in forged["open_plan_spec"]["goal_coverage"] if g["goal"] == "strength")
        goal.update(state="defer", satisfied=False, evidence=[], constraints=[])
        assert any(e.get("goal") == "strength" for e in validate_goal_preservation(forged))



def test_three_session_app_budget_preserves_lawful_goal_recovery(monkeypatch):
    test_persisted_readiness_preserves_app_budget_with_coached_days(
        monkeypatch, dated=False, symptom="", coached_days=[], frequency=3,
    )
