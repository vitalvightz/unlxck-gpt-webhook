"""Synthetic intake through final membership, doses, markdown and real cards."""
from collections import defaultdict

import pytest

from fightcamp.calendar_context import role_d_day
from fightcamp.goal_preservation import _effective_map, dose_volume, validate_goal_preservation
from fightcamp.physical_session_frequency import appointment_budget_exceeded
from scripts.audit_training_intelligence import SCENARIOS, generate_scenario


@pytest.mark.parametrize("name", SCENARIOS)
def test_selected_objectives_reach_real_rendered_plans_or_causal_deferral(name):
    result = generate_scenario(name)
    brief, summary = result["brief"], result["summary"]
    assert summary["goal_findings"] == []
    assert summary["fidelity_findings"] == []
    assert not any(e["code"] in {"goal_preservation_render_mismatch", "late_camp_effective_prescription_exceeded"}
                   for e in summary["validator"]["errors"])
    blocks = defaultdict(list)
    for week in result["structured"]["weeks"]:
        for day in week["days"]:
            for session in day.get("sessions") or []:
                for block in session.get("blocks") or []:
                    blocks[(day["countdown_label"], block["display_name"])].append(block)
    for week in _effective_map(brief).get("weeks") or []:
        for role in week.get("session_roles") or []:
            day = role_d_day(week, role)
            if role.get("render_mandatory") is False or day is None or day <= 0:
                continue
            for member in role.get("selected_exercise_assignments") or []:
                visible = blocks.get((f"D-{day}", member["name"]))
                assert visible, (name, day, member["name"])
    for entry in brief["goal_preservation"]:
        if entry["state"] == "defer":
            assert entry["constraints"] and not entry["satisfied"]
        else:
            assert entry["satisfied"] and entry["evidence"]
        for witness in entry["evidence"]:
            if not witness.get("name") or not witness.get("d_day"):
                continue
            dose = witness["effective_prescription"]
            cards = blocks[(f"D-{witness['d_day']}", witness["name"])]
            volume = dose_volume(dose)
            # Complex/time/contrast work keeps its original units and sequence.
            # Simple repetition witnesses must have executable card quantities.
            if volume["sets"] and volume["unit"] == "reps":
                assert any(dose.rstrip(".") in str(b.get("execution_instructions") or "")
                           or (b.get("sets") == volume["sets"] and b.get("reps") == volume["amount"])
                           for b in cards), (name, witness, cards)
    assert validate_goal_preservation(brief) == []


@pytest.mark.parametrize("seed", [4, 17])
def test_strength_continuity_and_capacity_survive_different_selection_seeds(seed):
    result = generate_scenario("mma_27d", seed=seed)
    strength = next(e for e in result["brief"]["goal_preservation"] if e["goal"] == "strength")
    assert strength["state"] == "maintain" and strength["satisfied"]
    assert {e["week_index"] for e in strength["evidence"]} == {1, 2}
    week = result["brief"]["weekly_role_map"]["weeks"][1]
    assert not appointment_budget_exceeded({"weeks": [week]}, 5)


def test_another_athletes_generation_does_not_change_a_seeded_programme():
    before = generate_scenario("mma_27d")["summary"]["weeks"]
    generate_scenario("boxing", seed=17)
    assert generate_scenario("mma_27d")["summary"]["weeks"] == before
