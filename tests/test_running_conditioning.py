"""Running conditioning contracts: real doses, safe selection, and no fake equipment."""

import json
from pathlib import Path

import pytest

from fightcamp.bank_schema import (
    conditioning_dose_shape, has_meaningful_fulfillment_authority,
    is_late_fight_metadata_safe, D13_TO_D8,
)
from fightcamp.conditioning_boxing import (
    _boxing_aerobic_preference_rank, _boxing_aerobic_priority_adjustment,
)
from fightcamp.config import conditioning_dose_active_work_seconds

BANK = {row["name"]: row for row in json.loads(Path("data/conditioning_bank.json").read_text())}
RUNS = (
    "5K Steady Run", "One-Mile Timed Run", "Continuous Tempo Run",
    "Running Fartlek (1:2)", "Running Aerobic Intervals (6x4min)",
    "800m Running Repeats (8x)", "Short Hill Sprints (5x10s)",
    "Long Hill Intervals (12x2min)", "Descending Sprint Ladder (80-60-40m)",
    "Boxing Round Running Intervals (10-10-10)",
)


@pytest.mark.parametrize("name", RUNS)
def test_running_workouts_have_real_equipment_free_doses(name):
    item = BANK[name]
    assert item["equipment"] == []
    assert item["modality"] == "run"
    assert item["rpe"] > 0
    assert conditioning_dose_shape(item, source="conditioning_bank.json")
    assert has_meaningful_fulfillment_authority(
        item, source_kind="conditioning", source="conditioning_bank.json"
    )


@pytest.mark.parametrize("name", [
    "5K Steady Run", "One-Mile Timed Run",
    "800m Running Repeats (8x)", "Descending Sprint Ladder (80-60-40m)",
])
def test_distance_running_never_invents_timed_work(name):
    item = BANK[name]
    assert conditioning_dose_shape(item) == "distance"
    assert conditioning_dose_active_work_seconds(item) is None


def test_distance_dose_rejects_missing_or_invalid_distance():
    assert conditioning_dose_shape({"distance_m": -5000}) is None
    assert conditioning_dose_shape({"distance_m": 800, "rounds": 0}) is None
    assert conditioning_dose_shape({"distance_m": 800}) == "distance"


def test_hill_work_and_existing_legacy_doses_are_authorised():
    hill = BANK["Tempo Hill Runs"]
    assert (hill["work_sec"], hill["rounds"], hill["rest_sec"]) == (20, 6, 60)
    assert conditioning_dose_shape(hill) == "interval"
    assert has_meaningful_fulfillment_authority(
        hill, source_kind="conditioning", source="conditioning_bank.json"
    )
    assert (BANK["Hill Sprint Repeats"]["rounds"], BANK["Hill Sprint Repeats"]["work_sec"]) == (8, 8)


def test_no_equipment_does_not_authorise_a_physical_ladder():
    for name in ("Agility Ladder Sprints", "Agility Ladder (Recovery)"):
        assert BANK[name]["equipment"] == ["agility_ladder"]
    assert not has_meaningful_fulfillment_authority(
        BANK["Agility Ladder (Recovery)"],
        source_kind="conditioning", source="conditioning_bank.json",
    )


def test_running_priority_depends_on_lower_limb_safety():
    run = BANK["Nasal Jog"]
    args = dict(weaknesses=[], goals=["conditioning"], restrictions=None, equipment_access_set=set())
    assert _boxing_aerobic_preference_rank(run, injuries=[], **args) == 2
    assert _boxing_aerobic_priority_adjustment(run, injuries=[], **args) > 0
    assert _boxing_aerobic_preference_rank(run, injuries=["Achilles pain"], **args) == 5
    assert _boxing_aerobic_priority_adjustment(run, injuries=["Achilles pain"], **args) < 0


@pytest.mark.parametrize("name", [
    "800m Running Repeats (8x)", "Short Hill Sprints (5x10s)",
    "Long Hill Intervals (12x2min)", "Descending Sprint Ladder (80-60-40m)",
    "Boxing Round Running Intervals (10-10-10)",
])
def test_hard_running_is_not_accidentally_taper_cleared(name):
    result = is_late_fight_metadata_safe(BANK[name], "conditioning_bank.json", D13_TO_D8)
    assert not result["safe"]


def test_tempo_has_no_fabricated_total_minutes():
    for name in ("5K Steady Run", "One-Mile Timed Run", "800m Running Repeats (8x)"):
        assert "total_minutes" not in BANK[name]


def test_no_machine_boxer_keeps_an_outdoor_run_in_the_aerobic_shortlist():
    from fightcamp.conditioning import generate_conditioning_block

    flags = {
        "phase": "GPP", "sport": "boxing", "style_technical": ["boxing"],
        "style_tactical": ["counter_striker"], "key_goals": ["conditioning"],
        "primary_goal": "conditioning", "weaknesses": ["endurance"],
        "equipment": [], "injuries": [], "fatigue": "low",
        "training_frequency": 4, "days_until_fight": 49,
        "hard_sparring_days": [], "support_work_days": ["Wednesday"],
        "rounds_format": "3 x 3",
    }
    *_, candidates = generate_conditioning_block(flags)
    names = {item["drill"]["name"] for item in candidates.get("aerobic", [])}
    assert names & {"Nasal Jog", "5K Steady Run", "Continuous Tempo Run"}, names


@pytest.mark.parametrize("name", [
    "5K Steady Run", "One-Mile Timed Run", "Continuous Tempo Run",
    "Running Fartlek (1:2)", "Running Aerobic Intervals (6x4min)",
    "800m Running Repeats (8x)", "Long Hill Intervals (12x2min)",
    "Boxing Round Running Intervals (10-10-10)",
])
def test_endurance_running_has_actual_conditioning_priority_hits(name):
    from fightcamp.conditioning import _conditioning_collision_safe_priority_bonus
    from fightcamp.priority_profile import build_priority_profile
    from fightcamp.tag_maps import GOAL_PRIORITY_TAG_MAP, WEAKNESS_PRIORITY_TAG_MAP

    tags = set(BANK[name]["tags"])
    assert {"conditioning", "work_capacity"} <= tags
    profile = build_priority_profile({
        "key_goals": ["conditioning"], "primary_goal": "conditioning",
        "weak_areas": ["gas_tank"], "primary_weak_area": "gas_tank",
    })
    goals = list(tags & set(GOAL_PRIORITY_TAG_MAP["conditioning"]))
    weaknesses = list(tags & set(WEAKNESS_PRIORITY_TAG_MAP["gas_tank"]))
    assert _conditioning_collision_safe_priority_bonus(
        goals, weaknesses, profile, drill=BANK[name],
    ) >= 5.0


@pytest.mark.parametrize("name", ["Short Hill Sprints (5x10s)", "Descending Sprint Ladder (80-60-40m)"])
def test_short_running_sprints_score_for_speed_not_fake_endurance(name):
    from fightcamp.conditioning import _conditioning_collision_safe_priority_bonus
    from fightcamp.priority_profile import build_priority_profile
    from fightcamp.tag_maps import GOAL_PRIORITY_TAG_MAP, WEAKNESS_PRIORITY_TAG_MAP

    tags = set(BANK[name]["tags"])
    assert {"speed", "acceleration", "explosive"} <= tags
    assert not tags & {"work_capacity", "glycolytic", "aerobic"}
    profile = build_priority_profile({
        "key_goals": ["speed"], "primary_goal": "speed",
        "weak_areas": ["speed"], "primary_weak_area": "speed",
    })
    goals = list(tags & set(GOAL_PRIORITY_TAG_MAP["speed"]))
    weaknesses = list(tags & set(WEAKNESS_PRIORITY_TAG_MAP["speed"]))
    assert _conditioning_collision_safe_priority_bonus(
        goals, weaknesses, profile, drill=BANK[name],
    ) >= 5.0


def test_original_standalone_protocol_headroom_is_unchanged():
    from fightcamp.conditioning_boxing import can_add_hard_conditioning

    assert not can_add_hard_conditioning(
        {"fatigue": "low", "hard_sparring_days": ["Monday", "Friday"]}
    )
    assert can_add_hard_conditioning(
        {"fatigue": "low", "hard_sparring_days": ["Monday"]}
    )
    assert not can_add_hard_conditioning(
        {"fatigue": "moderate", "hard_sparring_days": []}
    )
    assert can_add_hard_conditioning(
        {"fatigue": "low", "hard_sparring_days": ["Monday", "Friday"]},
        {"effective_hard_sparring_days": []},
    )


def test_two_hard_sparring_days_do_not_blanket_exclude_high_rpe(monkeypatch):
    from fightcamp import conditioning

    # Constrain the candidate bank so this checks the eligibility rule, not
    # whether a specific entry happens to land in the top-five shortlist.
    selected = [
        BANK["5K Steady Run"],
        BANK["Long Hill Intervals (12x2min)"],
    ]
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: selected)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    flags = {
        "phase": "GPP", "sport": "boxing", "style_technical": ["boxing"],
        "style_tactical": ["counter_striker"], "key_goals": ["conditioning"],
        "primary_goal": "conditioning", "weaknesses": ["endurance"],
        "equipment": [], "injuries": [], "fatigue": "low",
        "training_frequency": 4, "days_until_fight": 49,
        "hard_sparring_days": ["Monday", "Friday"],
        "support_work_days": ["Wednesday"], "rounds_format": "3 x 3",
    }
    *_, reservoir = conditioning.generate_conditioning_block(flags)
    names = {item["drill"]["name"] for item in reservoir.get("aerobic", [])}
    assert {"5K Steady Run", "Long Hill Intervals (12x2min)"} <= names


def test_heavy_bag_preference_preserves_original_bonus_and_three_contact_limit():
    from fightcamp.conditioning_preferences import striking_heavy_bag_preference

    bag = {"name": "Heavy Bag Rounds", "equipment": ["heavy_bag"], "rpe": 9}
    params = dict(phase="SPP", system="glycolytic", fatigue="low",
                  days_until_fight=35, equipment_access_set={"heavy_bag"},
                  injuries=[], sport="boxing")
    assert striking_heavy_bag_preference(bag, hard_sparring_days=["Monday"], **params) == 3.0
    assert striking_heavy_bag_preference(
        bag, hard_sparring_days=["Monday", "Friday"], **params
    ) == 3.0
    assert striking_heavy_bag_preference(
        bag, hard_sparring_days=["Monday", "Wednesday", "Friday"], **params
    ) == 0.0
    assert striking_heavy_bag_preference(
        bag, hard_sparring_days=["Monday", "Friday"],
        **{**params, "fatigue": "high"},
    ) == 0.0


def test_distance_run_survives_stage2_serialization_and_composition_without_fake_seconds():
    from fightcamp.stage2_payload import _serialize_conditioning_option
    from fightcamp.session_composition import compose_normal_conditioning_assignments

    drill = BANK["5K Steady Run"]
    option = _serialize_conditioning_option(drill, "aerobic", "easy base run")
    assert option["selection_metadata"]["distance_m"] == 5000
    role = {
        "category": "conditioning", "role_key": "aerobic_support_day",
        "preferred_system": "aerobic", "scheduled_day_hint": "Wednesday",
    }
    weekly = {"weeks": [{"phase": "GPP", "session_roles": [role]}]}
    slot = {"slot_id": "gpp-running", "role": "aerobic", "selected": option, "alternates": []}
    compose_normal_conditioning_assignments(
        weekly_role_map=weekly, candidate_pools={"GPP": {"conditioning_slots": [slot]}}
    )
    policy = role["conditioning_composition_policy"]
    assert policy["distance_dose_unmeasured"] is True
    assert policy["conditioning_workload_met"] is None
    assert policy["conditioning_active_work_seconds"] == 0
    assert policy["workload_limited"] is False
    assert role["selected_exercise_assignments"][0]["effective_prescription"] == drill["duration"]


def test_actual_assigned_distance_work_evidences_conditioning_without_fake_duration():
    from fightcamp.stage2_payload import _serialize_conditioning_option
    from fightcamp.goal_preservation import _other_stimuli

    for name in ("5K Steady Run", "800m Running Repeats (8x)"):
        drill = BANK[name]
        system = drill["system"]
        option = _serialize_conditioning_option(drill, system, "conditioned running")
        slot = {"slot_id": "running-dose", "role": system, "selected": option}
        role = {
            "category": "conditioning", "preferred_system": system,
            "selected_exercise_assignments": [{
                "slot_group": "conditioning_slots", "source_phase": "GPP",
                "slot_id": "running-dose", "name": name,
                "effective_prescription": drill["duration"],
            }],
        }
        pools = {"GPP": {"conditioning_slots": [slot]}}
        stimuli = _other_stimuli(role, pools, "GPP", {})
        assert len(stimuli) == 1
        assert "energy_system_training" in stimuli[0]["intents"]
        assert stimuli[0]["distance_m"] == drill["distance_m"]
        assert "total_minutes" not in stimuli[0]  # Unknown pace != zero duration.


def test_short_distance_does_not_pretend_to_be_aerobic_development():
    from fightcamp.stage2_payload import _serialize_conditioning_option
    from fightcamp.goal_preservation import _other_stimuli
    drill = dict(BANK["5K Steady Run"], name="Short run", distance_m=100)
    option = _serialize_conditioning_option(drill, "aerobic", "")
    role = {"category": "conditioning", "preferred_system": "aerobic",
            "selected_exercise_assignments": [{"slot_group": "conditioning_slots",
                "source_phase": "GPP", "slot_id": "short", "name": "Short run"}]}
    pool = {"GPP": {"conditioning_slots": [{"slot_id": "short", "role": "aerobic", "selected": option}]}}
    assert not _other_stimuli(role, pool, "GPP", {})


def test_short_hill_running_has_true_alactic_work_recovery_structure():
    from fightcamp.conditioning import _alactic_structure_ok
    drill = BANK["Short Hill Sprints (5x10s)"]
    assert drill["work_sec"] == 10
    assert drill["rest_sec"] >= 120
    assert _alactic_structure_ok(drill)


def test_distance_sprint_ladder_does_not_falsely_claim_timed_alactic_work():
    from fightcamp.conditioning import _alactic_structure_ok
    drill = BANK["Descending Sprint Ladder (80-60-40m)"]
    assert drill["system"] == "glycolytic"
    assert drill["distance_segments_m"] == [80, 80, 60, 60, 40, 40]
    assert not _alactic_structure_ok(drill)
    assert "work_sec" not in drill
