from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.camp_week_fillers import _splice_late_fight_tail
from fightcamp.late_fight_tail import build_finished_late_fight_tail
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.session_composition import attach_late_fight_assignments, compose_normal_strength_assignments
from fightcamp.stage2_payload import _build_late_fight_allowed_exercises_by_day


def _slot(name, priority, quality="anchor_loaded"):
    return {
        "slot_id": f"slot-{priority}", "session_index": 1, "priority": priority, "purpose": name,
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


def test_spliced_role_resolves_exact_selected_source_phase_not_containing_week():
    pools = {
        "GPP": {"strength_slots": [_slot("GPP Trap Bar Deadlift", 1)]},
        "SPP": {"strength_slots": [_slot("SPP Barbell Thruster", 1)]},
        "TAPER": {"strength_slots": [_slot("Taper High Pull", 1)]},
    }
    role = {"role_key": "strength_touch_day", "category": "strength",
            "scheduled_countdown_label": "D-10", "scheduled_day_hint": "tuesday",
            "late_fight_tail_owned": True}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role]}, candidate_pools=pools,
    )
    attach_late_fight_assignments([role], assignments)
    assert role["selected_exercise_assignments"][0]["source_phase"] == "GPP"

    # The role deliberately lives in an SPP week. Resolution must still use the
    # exact GPP assignment selected by the shared late-fight authority.
    role_map = {"weeks": [{"phase": "SPP", "calendar_days": [{"weekday": "tuesday", "d_day": 10}],
                           "session_roles": [role]}]}
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(weekly_role_map=role_map, candidate_pools=pools)
    assert [item["name"] for item in role["effective_strength_prescriptions"]] == [
        "GPP Trap Bar Deadlift"]


def test_d7_neural_assignment_uses_exact_source_and_excludes_alternatives():
    pools = {
        "GPP": {"strength_slots": [_slot("GPP Speed Isometric", 1)]},
        "SPP": {"strength_slots": [_slot("SPP Speed High Pull", 1), _slot("SPP Speed Row", 2)]},
        "TAPER": {"strength_slots": [_slot("Taper Speed Shuffle", 1)]},
    }
    role = {"role_key": "neural_primer_day", "category": "strength",
            "scheduled_countdown_label": "D-7", "scheduled_day_hint": "tuesday",
            "late_fight_tail_owned": True}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role]}, candidate_pools=pools,
    )
    attach_late_fight_assignments([role], assignments)
    role_map = {"weeks": [{"phase": "TAPER", "calendar_days": [{"weekday": "tuesday", "d_day": 7}],
                           "session_roles": [role]}]}
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(weekly_role_map=role_map, candidate_pools=pools)
    selected = role["selected_exercise_assignments"]
    resolved = role["effective_strength_prescriptions"]
    assert len(selected) == len(resolved) == 1
    assert resolved[0]["name"] == selected[0]["name"]


def test_d30_spliced_tail_matches_direct_late_fight_assignment_authority():
    athlete = {"days_until_fight": 30, "plan_creation_weekday": "monday", "sport": "mma",
               "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"]}
    pools = {
        "GPP": {"strength_slots": [_slot("GPP Barbell Thruster", 1), _slot("GPP High Pull", 2)]},
        "SPP": {"strength_slots": [_slot("SPP Rotational Slam", 1), _slot("SPP Speed Row", 2)]},
        "TAPER": {"strength_slots": [_slot("Taper Skater Hop", 1)]},
    }
    role_map = {"weeks": [
        {"phase": "SPP", "calendar_days": [{"weekday": "wednesday", "d_day": 13}],
         "session_roles": [], "intentionally_unused_days": []},
        {"phase": "TAPER", "calendar_days": [
            {"weekday": "monday", "d_day": day} for day in range(12, -1, -1)],
         "session_roles": [], "intentionally_unused_days": []},
    ]}
    assert _splice_late_fight_tail(role_map, athlete)
    spliced_roles = [role for week in role_map["weeks"] for role in week["session_roles"]
                     if role.get("late_fight_tail_owned")]
    direct_roles = build_finished_late_fight_tail(30, athlete)["session_sequence"]

    _, spliced_by_day = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": spliced_roles}, candidate_pools=pools)
    _, direct_by_day = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": direct_roles}, candidate_pools=pools)
    assert spliced_by_day == direct_by_day

    attach_late_fight_assignments(spliced_roles, spliced_by_day)
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(weekly_role_map=role_map, candidate_pools=pools)
    selected_strength = [assignment for role in spliced_roles
                         for assignment in role.get("selected_exercise_assignments", [])
                         if assignment.get("slot_group") == "strength_slots"]
    resolved_strength = [item for role in spliced_roles
                         for item in role.get("effective_strength_prescriptions", [])]
    assert selected_strength
    assert {(item["slot_id"], item["name"]) for item in resolved_strength} == {
        (item["slot_id"], item["name"]) for item in selected_strength}
