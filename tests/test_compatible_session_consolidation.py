"""PR2: dose-preserving normal-camp alactic/Strength appointment composition."""

from __future__ import annotations

from copy import deepcopy

from fightcamp.goal_preservation import _other_stimuli
from fightcamp.physical_session_frequency import dated_appointments
from fightcamp.render_authority import authoritative_render_for_role
from fightcamp.session_composition import consolidate_compatible_physical_sessions


def _strength(*, day="Monday", cap=6, pressure=0):
    members = [
        {
            "slot_id": "strength-pull",
            "name": "Trap Bar Deadlift",
            "slot_group": "strength_slots",
            "source_phase": "SPP",
            "exercise_key": "trap-bar-deadlift",
            "base_prescription": "3 x 5 @ RPE 7",
        },
        {
            "slot_id": "strength-press",
            "name": "Landmine Press",
            "slot_group": "strength_slots",
            "source_phase": "SPP",
            "exercise_key": "landmine-press",
            "base_prescription": "3 x 4 @ RPE 7",
        },
    ]
    return {
        "category": "strength",
        "role_key": "primary_strength_day",
        "session_index": 1,
        "scheduled_day_hint": day,
        "selected_exercise_assignments": members,
        "effective_strength_prescriptions": [
            {
                "slot_id": m["slot_id"], "name": m["name"],
                "effective_prescription": "2 x 4 @ RPE 6",
            }
            for m in members
        ],
        "strength_composition_policy": {
            "effective_exercise_cap": cap,
            "pressure": pressure,
            "selected_count": 2,
            "selected_names": [m["name"] for m in members],
        },
    }


def _alactic(*, day="Wednesday", work=5, rounds=4):
    return {
        "category": "conditioning",
        "role_key": "alactic_speed_day",
        "preferred_system": "alactic",
        "session_index": 2,
        "scheduled_day_hint": day,
        "selected_exercise_assignments": [{
            "slot_id": "alactic-burst",
            "name": "Max-Power Bag Burst",
            "exercise_key": "max-power-bag-burst",
            "slot_group": "conditioning_slots",
            "source_phase": "SPP",
            "work_sec": work,
            "rounds": rounds,
            "effective_rounds": rounds,
            "rest_sec": 90,
            "rpe": 8,
            "effective_prescription": f"{work}s work, 90s rest x {rounds} rounds",
            "mechanical_risk_tags": ["mech_ballistic", "mech_upper_press"],
        }],
    }


def _map(*roles, contacts=()):
    return {
        "weeks": [{
            "week_index": 1,
            "phase": "SPP",
            "calendar_days": [
                {"weekday": day, "d_day": 30 - idx}
                for idx, day in enumerate([
                    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
                ])
            ],
            "declared_training_days": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
            ],
            "hard_sparring_plan": list(contacts),
            "session_roles": list(roles),
        }]
    }


def test_eligible_speed_and_strength_really_become_one_workout_with_all_doses():
    original = _map(_strength(), _alactic())
    before = deepcopy(original)
    assert len(dated_appointments(original)) == 2

    result = consolidate_compatible_physical_sessions(original)

    week = result["weeks"][0]
    assert len(dated_appointments(result)) == 1
    assert [r["role_key"] for r in week["session_roles"]] == ["primary_strength_day"]
    role = week["session_roles"][0]
    members = role["selected_exercise_assignments"]
    assert [m["name"] for m in members] == [
        "Max-Power Bag Burst", "Trap Bar Deadlift", "Landmine Press",
    ]
    assert members[0]["effective_prescription"] == (
        before["weeks"][0]["session_roles"][1]["selected_exercise_assignments"][0]["effective_prescription"]
    )
    assert role["effective_strength_prescriptions"] == (
        before["weeks"][0]["session_roles"][0]["effective_strength_prescriptions"]
    )
    assert role["strength_composition_policy"]["selected_count"] == 3
    assert len(result["session_consolidation_audit"]) == 1
    render = authoritative_render_for_role(role, week=week)
    assert render is not None
    lines = "\n".join(render["body_lines"])
    assert lines.count("- Max-Power Bag Burst — 5s work, 90s rest x 4 rounds") == 1
    assert "- Trap Bar Deadlift — 2 x 4 @ RPE 6" in lines
    assert "- Landmine Press — 2 x 4 @ RPE 6" in lines


def test_consolidated_alactic_member_keeps_conditioning_speed_goal_evidence():
    source = _alactic()
    selected = {
        "name": "Max-Power Bag Burst",
        "prescription": "5s work, 90s rest x 4 rounds",
        "movement_patterns": ["speed", "explosive", "mech_ballistic"],
        "selection_metadata": {
            "work_sec": 5, "rest_sec": 90, "rounds": 4, "rpe": 8,
            "duration": "5s work, 90s rest x 4 rounds",
            "tags": ["speed", "explosive", "mech_ballistic"],
        },
    }
    pools = {"SPP": {"conditioning_slots": [{
        "slot_id": "alactic-burst", "role": "alactic", "selected": selected,
    }]}}
    original_stimuli = _other_stimuli(source, pools, "SPP", {})
    assert any("speed_quality" in item["intents"] for item in original_stimuli)

    result = _map(_strength(), source)
    consolidate_compatible_physical_sessions(result)
    combined = result["weeks"][0]["session_roles"][0]
    combined_stimuli = _other_stimuli(combined, pools, "SPP", {})
    assert combined_stimuli == original_stimuli


def test_fight_pace_rounds_are_not_misclassified_as_alactic_micro_work():
    original = _map(_strength(), _alactic(work=180, rounds=4))
    consolidate_compatible_physical_sessions(original)
    assert len(dated_appointments(original)) == 2
    assert not original.get("session_consolidation_audit")


def test_never_move_speed_to_strength_day_next_to_hard_sparring():
    original = _map(
        _strength(), _alactic(),
        contacts=[{"day": "Tuesday", "effective_load": "hard", "status": "hard_as_planned"}],
    )
    consolidate_compatible_physical_sessions(original)
    assert len(dated_appointments(original)) == 2
    assert not original.get("session_consolidation_audit")


def test_combination_does_not_exceed_existing_strength_exercise_capacity():
    original = _map(_strength(cap=2), _alactic())
    consolidate_compatible_physical_sessions(original)
    assert len(dated_appointments(original)) == 2
    assert not original.get("session_consolidation_audit")


def test_combination_does_not_bypass_readiness_pressure():
    original = _map(_strength(pressure=1), _alactic())
    consolidate_compatible_physical_sessions(original)
    assert len(dated_appointments(original)) == 2
    assert not original.get("session_consolidation_audit")


def test_preserves_technical_coach_session_while_merging_compatible_app_work():
    coach = {
        "role_key": "light_combat_day", "category": "technical", "session_index": 3,
        "scheduled_day_hint": "Wednesday", "coach_owned": True,
        "declared_day_locked": True,
    }
    original = _map(_strength(), _alactic(), coach)
    consolidate_compatible_physical_sessions(original)
    assert coach["role_key"] in [r["role_key"] for r in original["weeks"][0]["session_roles"]]
    assert len(dated_appointments(original)) == 2  # Strength + coach boxing.


def _short_technical_footwork():
    return {
        "category": "conditioning",
        "role_key": "technical_footwork_touch_day",
        "preferred_system": "technical_footwork",
        "session_index": 2,
        "scheduled_day_hint": "Wednesday",
        "selected_exercise_assignments": [{
            "slot_id": "spp_technical_footwork_1_step_back_pivot_reset",
            "name": "Step-Back Pivot Reset",
            "exercise_key": "step-back-pivot-reset",
            "slot_group": "conditioning_slots",
            "source_phase": "SPP",
            "work_sec": 75,
            "rounds": 2,
            "rest_sec": 60,
            "rpe": 4,
            "effective_prescription": "2 x 75 sec technical sets, 60 sec reset",
        }],
    }


def test_short_technical_footwork_can_share_strength_without_losing_real_dose():
    original = _map(_strength(), _short_technical_footwork())
    before_member = deepcopy(original["weeks"][0]["session_roles"][1]["selected_exercise_assignments"][0])

    consolidate_compatible_physical_sessions(original)

    assert len(dated_appointments(original)) == 1
    host = original["weeks"][0]["session_roles"][0]
    assert host["athlete_facing_label"] == "Strength + footwork"
    member = host["selected_exercise_assignments"][0]
    assert member["slot_id"] == before_member["slot_id"]
    assert member["effective_prescription"] == before_member["effective_prescription"]
    render = authoritative_render_for_role(host, week=original["weeks"][0])
    assert render is not None
    assert any("Step-Back Pivot Reset" in line for line in render["body_lines"])
    assert original["session_consolidation_audit"][0]["embedded_quality"] == "footwork"


def test_technical_footwork_intent_is_preserved_as_footwork_not_aerobic():
    source = _short_technical_footwork()
    selected = {
        "name": "Step-Back Pivot Reset",
        "prescription": "2 x 75 sec technical sets, 60 sec reset",
        "movement_patterns": ["footwork"],
        "selection_metadata": {
            "tags": ["footwork", "technical"],
            "work_sec": 75, "rounds": 2, "rest_sec": 60,
            "rpe": 4, "total_minutes": 2.5,
            "duration": "2 x 75 sec technical sets, 60 sec reset",
        },
    }
    pools = {"SPP": {"conditioning_slots": [{
        "slot_id": "spp_technical_footwork_1_step_back_pivot_reset",
        "role": "technical_footwork", "selected": selected,
    }]}}
    before = _other_stimuli(source, pools, "SPP", {})
    assert any("footwork_practice" in s["intents"] for s in before)
    original = _map(_strength(), source)
    consolidate_compatible_physical_sessions(original)
    merged = original["weeks"][0]["session_roles"][0]
    after = _other_stimuli(merged, pools, "SPP", {})
    assert after == before
    assert not any("energy_system_training" in s["intents"] for s in after)


def test_full_aerobic_footwork_session_remains_separate():
    role = _short_technical_footwork()
    role.update(role_key="aerobic_support_day", preferred_system="aerobic")
    member = role["selected_exercise_assignments"][0]
    member.update(
        slot_id="spp_aerobic_1_pressure_footwork_flow",
        name="Pressure Footwork Flow",
        work_sec=180, rounds=3, rest_sec=45, rpe=6,
        effective_prescription="180s work, 45s rest x 3 rounds",
    )
    plan = _map(_strength(), role)
    consolidate_compatible_physical_sessions(plan)
    assert len(dated_appointments(plan)) == 2
    assert not plan.get("session_consolidation_audit")


def test_short_reactive_coordination_alactic_block_uses_same_compatibility_path():
    role = _alactic()
    role["role_key"] = "alactic_coordination_day"
    role["selected_exercise_assignments"][0]["name"] = "Reactive Angle Burst"
    plan = _map(_strength(), role)
    consolidate_compatible_physical_sessions(plan)
    assert len(dated_appointments(plan)) == 1
    assert plan["weeks"][0]["session_roles"][0]["selected_exercise_assignments"][0]["name"] == "Reactive Angle Burst"


def test_strenuous_technical_footwork_is_not_embedded_as_a_warmup():
    source = _short_technical_footwork()
    source["selected_exercise_assignments"][0].update(
        work_sec=90, rounds=4, rpe=8, rest_sec=30,
    )
    plan = _map(_strength(), source)
    consolidate_compatible_physical_sessions(plan)
    assert len(dated_appointments(plan)) == 2
