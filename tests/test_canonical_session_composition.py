from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.session_composition import compose_normal_strength_assignments
from fightcamp.stage2_payload import _build_late_fight_allowed_exercises_by_day


def _slot(name, priority, quality="anchor_loaded"):
    return {
        "slot_id": f"slot-{priority}", "session_index": 1, "priority": priority,
        "quality_class": quality, "anchor_capable": quality != "support_isometric",
        "support_only": quality == "support_isometric",
        "selected": {"name": name, "prescription": "3 x 5 @ RPE 7", "quality_class": quality},
    }


def _map(role, d_day=10):
    return {"weeks": [{"phase": "SPP", "calendar_days": [{"weekday": "tuesday", "d_day": d_day}],
                        "session_roles": [{**role, "scheduled_day_hint": "tuesday"}]}]}


def test_resolver_requires_explicit_selection_not_shared_session_index():
    names = ["Barbell Thruster", "Med-Ball Rotational Slam", "Banded Row (Speed Focus)",
             "High Pull", "Alternating Skater Hops", "Single-Leg Reactive Shuffle"]
    slots = [_slot(name, index) for index, name in enumerate(names, 1)]
    role_map = _map({"role_key": "primary_strength_day", "category": "strength"})
    apply_late_camp_role_morph(role_map)

    apply_effective_strength_prescriptions(weekly_role_map=role_map,
                                           candidate_pools={"SPP": {"strength_slots": slots}})
    assert "effective_strength_prescriptions" not in role_map["weeks"][0]["session_roles"][0]

    role = role_map["weeks"][0]["session_roles"][0]
    role["selected_exercise_assignments"] = [
        {"slot_id": slots[1]["slot_id"], "name": names[1], "source_phase": "SPP", "slot_group": "strength_slots"}
    ]
    apply_effective_strength_prescriptions(weekly_role_map=role_map,
                                           candidate_pools={"SPP": {"strength_slots": slots}})
    assert [item["name"] for item in role["effective_strength_prescriptions"]] == [names[1]]


def test_normal_full_strength_composition_preserves_anchor_secondary_and_support():
    slots = [_slot("Trap Bar Deadlift", 1), _slot("Landmine Press", 2),
             _slot("Pallof Press", 3, "support_isometric")]
    role_map = _map({"role_key": "primary_strength_day", "category": "strength"}, 17)
    apply_late_camp_role_morph(role_map)
    compose_normal_strength_assignments(weekly_role_map=role_map,
                                        candidate_pools={"SPP": {"strength_slots": slots}})
    apply_effective_strength_prescriptions(weekly_role_map=role_map,
                                           candidate_pools={"SPP": {"strength_slots": slots}})
    role = role_map["weeks"][0]["session_roles"][0]
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Trap Bar Deadlift", "Landmine Press", "Pallof Press"]
    assert [item["name"] for item in role["effective_strength_prescriptions"]] == [
        "Trap Bar Deadlift", "Landmine Press", "Pallof Press"]


def test_late_fight_selector_selects_one_fallback_candidate_for_reduced_touch():
    slots = [_slot("Barbell Thruster", 1), _slot("High Pull", 2), _slot("Skater Hop", 3)]
    role = {"role_key": "strength_touch_day", "category": "strength",
            "scheduled_countdown_label": "D-10"}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role]},
        candidate_pools={"SPP": {"strength_slots": slots}},
    )
    assert [item["name"] for item in assignments["D-10"]] == ["Barbell Thruster"]
