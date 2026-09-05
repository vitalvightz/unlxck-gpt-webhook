from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.camp_week_fillers import _splice_late_fight_tail
from fightcamp.late_fight_tail import build_finished_late_fight_tail
from fightcamp.late_fight_phase_eligibility import (
    phase_scoped_candidate_pools,
    scheduled_phase_for_role,
)
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.session_composition import attach_late_fight_assignments, compose_normal_strength_assignments
from fightcamp.stage2_payload import _build_late_fight_allowed_exercises_by_day
from fightcamp.stage2_payload_late_fight import _countdown_weekday_map


def _slot(name, priority, quality="anchor_loaded"):
    return {
        "slot_id": f"slot-{priority}", "session_index": 1, "priority": priority, "purpose": name,
        "quality_class": quality, "anchor_capable": quality != "support_isometric",
        "support_only": quality == "support_isometric",
        "selected": {"name": name, "prescription": "3 x 5 @ RPE 7", "quality_class": quality},
    }


def _conditioning_slot(name, priority, system="alactic", late_windows=None):
    return {
        "slot_id": f"conditioning-slot-{priority}-{name}",
        "session_index": 1,
        "priority": priority,
        "purpose": name,
        "role": system,
        "selected": {
            "name": name,
            "role": system,
            **(
                {"selection_metadata": {"late_windows": late_windows}}
                if late_windows is not None
                else {}
            ),
        },
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
    slots = [_slot("First SPP Touch", 1), _slot("Second SPP Touch", 2)]
    role = {"role_key": "strength_touch_day", "category": "strength",
            "scheduled_countdown_label": "D-10"}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "phase": "SPP"},
        candidate_pools={"SPP": {"strength_slots": slots}},
    )
    assert [item["name"] for item in assignments["D-10"]] == ["First SPP Touch"]


def test_stage1_phase_days_map_d7_to_spp_before_d5_taper():
    athlete_model = {
        "phase_weeks": {
            "days": {"GPP": 19, "SPP": 2, "TAPER": 5},
        }
    }
    assert scheduled_phase_for_role(
        {"scheduled_countdown_label": "D-7", "phase": "TAPER"},
        athlete_model=athlete_model,
    ) == "SPP"
    assert scheduled_phase_for_role(
        {"scheduled_countdown_label": "D-5", "phase": "SPP"},
        athlete_model=athlete_model,
    ) == "TAPER"


def test_phase_scope_fails_closed_when_phase_is_unresolved():
    pools = {
        "GPP": {"strength_slots": [_slot("GPP Lift", 1)]},
        "SPP": {"strength_slots": [_slot("SPP Lift", 1)]},
        "TAPER": {"strength_slots": [_slot("Taper Lift", 1)]},
    }
    assert phase_scoped_candidate_pools(pools, "") == {}
    assert phase_scoped_candidate_pools(pools, "unknown") == {}


def test_late_fight_selector_stays_inside_authoritative_stage1_phase():
    athlete_model = {
        "phase_weeks": {
            "days": {"GPP": 14, "SPP": 7, "TAPER": 5},
        }
    }
    pools = {
        "GPP": {"strength_slots": [_slot("GPP Trap Bar Deadlift", 1)]},
        "SPP": {"strength_slots": [_slot("SPP Barbell Thruster", 1)]},
        "TAPER": {"strength_slots": [_slot("Taper High Pull", 1)]},
    }
    role = {"role_key": "strength_touch_day", "category": "strength",
            "scheduled_countdown_label": "D-10", "scheduled_day_hint": "tuesday",
            "phase": "GPP", "late_fight_tail_owned": True}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={
            "visible_session_sequence": [role],
            "phase": "GPP",
            "athlete_model": athlete_model,
        },
        candidate_pools=pools,
    )
    attach_late_fight_assignments([role], assignments)
    assert role["selected_exercise_assignments"][0]["source_phase"] == "SPP"

    role_map = {"weeks": [{"phase": "SPP", "calendar_days": [{"weekday": "tuesday", "d_day": 10}],
                           "session_roles": [role]}]}
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(weekly_role_map=role_map, candidate_pools=pools)
    assert [item["name"] for item in role["effective_strength_prescriptions"]] == [
        "SPP Barbell Thruster"]


def test_d7_neural_assignment_cannot_reach_gpp_hang_power_clean():
    athlete_model = {
        "phase_weeks": {
            "days": {"GPP": 19, "SPP": 2, "TAPER": 5},
        }
    }
    pools = {
        "GPP": {"strength_slots": [_slot("Hang Power Clean", 1)]},
        "SPP": {"strength_slots": [_slot("SPP Speed High Pull", 1), _slot("SPP Speed Row", 2)]},
        "TAPER": {"strength_slots": [_slot("Taper Speed Shuffle", 1)]},
    }
    role = {"role_key": "neural_primer_day", "category": "strength",
            "scheduled_countdown_label": "D-7", "scheduled_day_hint": "tuesday",
            "phase": "TAPER", "late_fight_tail_owned": True}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={
            "visible_session_sequence": [role],
            "phase": "TAPER",
            "athlete_model": athlete_model,
        },
        candidate_pools=pools,
    )
    attach_late_fight_assignments([role], assignments)
    selected = role["selected_exercise_assignments"]
    assert len(selected) == 1
    assert selected[0]["source_phase"] == "SPP"
    assert selected[0]["name"] == "SPP Speed High Pull"
    assert selected[0]["name"] != "Hang Power Clean"


def test_d2_alactic_assignment_cannot_reach_gpp_broad_jump_repeats():
    athlete_model = {
        "phase_weeks": {
            "days": {"GPP": 19, "SPP": 2, "TAPER": 5},
        }
    }
    pools = {
        "GPP": {"conditioning_slots": [_conditioning_slot("Broad Jump Repeats", 1)]},
        "SPP": {"conditioning_slots": [_conditioning_slot("SPP Alactic Burst", 1)]},
        "TAPER": {"conditioning_slots": [
            _conditioning_slot("Taper D2 Alactic Burst", 1, late_windows=["d4_to_d2"])
        ]},
    }
    role = {
        "role_key": "alactic_sharpness_day",
        "category": "conditioning",
        "preferred_system": "alactic",
        "scheduled_countdown_label": "D-2",
        "scheduled_day_hint": "sunday",
        "phase": "GPP",
        "late_fight_tail_owned": True,
    }
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={
            "visible_session_sequence": [role],
            "phase": "GPP",
            "athlete_model": athlete_model,
        },
        candidate_pools=pools,
    )
    attach_late_fight_assignments([role], assignments)
    selected = role["selected_exercise_assignments"]
    assert len(selected) == 1
    assert selected[0]["source_phase"] == "TAPER"
    assert selected[0]["name"] == "Taper D2 Alactic Burst"
    assert selected[0]["name"] != "Broad Jump Repeats"


def _sharpness_role(d_day, weekday="wednesday"):
    return {
        "role_key": "alactic_sharpness_day",
        "category": "conditioning",
        "preferred_system": "alactic",
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_day_hint": weekday,
        "phase": "TAPER",
        "late_fight_tail_owned": True,
    }


def _taper_athlete():
    return {"phase_weeks": {"days": {"GPP": 0, "SPP": 0, "TAPER": 13}}}


def test_d4_excludes_reactive_shuffle_before_late_tail_selection():
    role = _sharpness_role(4)
    reactive = _conditioning_slot(
        "Reactive Shuffle Repeats", 1, late_windows=["d13_to_d8", "d7", "d6_to_d5"]
    )

    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "athlete_model": _taper_athlete()},
        candidate_pools={"TAPER": {"conditioning_slots": [reactive]}},
    )
    attach_late_fight_assignments([role], assignments)

    assert assignments["D-4"] == []
    assert role["selected_exercise_assignments"] == []


def test_d4_excludes_bank_candidate_with_missing_late_windows():
    role = _sharpness_role(4)
    missing_windows = _conditioning_slot("Low Box Jump (Fast Reset)", 1)

    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "athlete_model": _taper_athlete()},
        candidate_pools={"TAPER": {"conditioning_slots": [missing_windows]}},
    )

    assert assignments["D-4"] == []


def test_d6_keeps_reactive_shuffle_eligible():
    reactive = _conditioning_slot(
        "Reactive Shuffle Repeats", 1, late_windows=["d13_to_d8", "d7", "d6_to_d5"]
    )
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [_sharpness_role(6, "monday")],
              "athlete_model": _taper_athlete()},
        candidate_pools={"TAPER": {"conditioning_slots": [reactive]}},
    )

    assert [item["name"] for item in assignments["D-6"]] == ["Reactive Shuffle Repeats"]


def test_late_window_illegal_top_candidate_falls_through_to_next_legal_candidate():
    slots = [
        _conditioning_slot("Reactive Shuffle Repeats", 1, late_windows=["d6_to_d5"]),
        _conditioning_slot("Legal D4 Sharpness", 2, late_windows=["d4_to_d2"]),
    ]
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [_sharpness_role(4)],
              "athlete_model": _taper_athlete()},
        candidate_pools={"TAPER": {"conditioning_slots": slots}},
    )

    assert [item["name"] for item in assignments["D-4"]] == ["Legal D4 Sharpness"]


def test_wrong_phase_candidate_is_excluded_even_when_late_window_matches():
    pools = {
        "SPP": {"conditioning_slots": [
            _conditioning_slot("Wrong Phase D4 Drill", 1, late_windows=["d4_to_d2"])
        ]},
        "TAPER": {"conditioning_slots": [
            _conditioning_slot("Taper D4 Drill", 2, late_windows=["d4_to_d2"])
        ]},
    }
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [_sharpness_role(4)],
              "athlete_model": _taper_athlete()},
        candidate_pools=pools,
    )

    assert [item["name"] for item in assignments["D-4"]] == ["Taper D4 Drill"]


def test_sunday_fight_week_d4_sharpness_assignment_uses_its_actual_window():
    # 2026-10-04 is Sunday: D-7 Sunday, D-6 Monday and D-4 Wednesday.
    countdown_map = _countdown_weekday_map("saturday", 29)
    assert {label: countdown_map[label] for label in ("D-7", "D-6", "D-4")} == {
        "D-7": "sunday",
        "D-6": "monday",
        "D-4": "wednesday",
    }
    role = _sharpness_role(4, "wednesday")
    slots = [
        _conditioning_slot("Reactive Shuffle Repeats", 1, late_windows=["d6_to_d5"]),
        _conditioning_slot("Wednesday Sharpness", 2, late_windows=["d4_to_d2"]),
    ]
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "athlete_model": {
            **_taper_athlete(), "fight_date": "2026-10-04",
        }},
        candidate_pools={"TAPER": {"conditioning_slots": slots}},
    )

    assert role["scheduled_day_hint"] == "wednesday"
    assert [item["name"] for item in assignments["D-4"]] == ["Wednesday Sharpness"]


def test_d30_spliced_tail_matches_direct_late_fight_assignment_authority():
    athlete = {"days_until_fight": 30, "plan_creation_weekday": "monday", "sport": "mma",
               "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
               "phase_weeks": {"days": {"GPP": 13, "SPP": 4, "TAPER": 13}}}
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

    spec_context = {"athlete_model": athlete}
    _, spliced_by_day = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": spliced_roles, **spec_context}, candidate_pools=pools)
    _, direct_by_day = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": direct_roles, **spec_context}, candidate_pools=pools)
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
