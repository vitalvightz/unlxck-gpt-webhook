import json
from pathlib import Path

from fightcamp.strength import normalize_exercise_movement
from fightcamp.training_context import normalize_equipment_list


EXERCISES = json.loads(Path("data/exercise_bank.json").read_text(encoding="utf-8"))
CONDITIONING = json.loads(Path("data/conditioning_bank.json").read_text(encoding="utf-8"))
STYLE_TAPER_CONDITIONING = json.loads(
    Path("data/style_taper_conditioning.json").read_text(encoding="utf-8")
)
EXERCISES_BY_NAME = {entry["name"]: entry for entry in EXERCISES}
CONDITIONING_BY_NAME = {entry["name"]: entry for entry in CONDITIONING}
STYLE_TAPER_BY_NAME = {entry["name"]: entry for entry in STYLE_TAPER_CONDITIONING}


def test_box_gated_taper_drills_use_canonical_intake_token():
    for name in ("Box Squat Low Height - Grappler", "Low Box Step-Up - Clinch Fighter"):
        assert normalize_equipment_list(STYLE_TAPER_BY_NAME[name]["equipment"]) == ["box"]


def test_directional_and_upper_body_plyometrics_follow_bank_metadata():
    expected = {
        "Clap Push-Up": "horizontal_push",
        "Explosive Push-Up (Clap-to-Tap)": "horizontal_push",
        "Box Jump": "vertical_jump",
        "Single-Leg Bounding": "horizontal_jump",
        "Alternating Skater Hops": "lateral_reactive",
        "Band-Resisted Reaction Hop": "horizontal_jump",
        "Single-Leg Reactive Shuffle": "lateral_reactive",
        "Single-Leg Rotational Hop to Balance": "rotation",
    }

    for name, movement in expected.items():
        item = EXERCISES_BY_NAME[name].copy()
        assert item["movement"] == movement
        assert normalize_exercise_movement(item) == movement


def test_conditioning_finishers_do_not_compete_in_strength_selection():
    moved_names = {
        "5-10-15 Ladder (Box Jumps/Push-Ups/KB Swings)",
        "EMOM: 5 Squat Cleans + 5 Burpees",
    }

    assert moved_names.isdisjoint(EXERCISES_BY_NAME)
    assert moved_names.issubset(CONDITIONING_BY_NAME)
    for name in moved_names:
        assert CONDITIONING_BY_NAME[name]["system"] == "glycolytic"
        assert CONDITIONING_BY_NAME[name]["block_if_fight_within_days"] == 21


def test_trap_bar_jump_variants_are_consolidated():
    trap_bar_jump_names = {
        name for name in EXERCISES_BY_NAME if name.lower().startswith("trap bar jump")
    }

    assert trap_bar_jump_names == {"Trap Bar Jump"}
    assert "light load" in EXERCISES_BY_NAME["Trap Bar Jump"]["notes"].lower()


def test_non_landing_core_exercises_have_non_landing_costs():
    for name in ("Chop Holds (Anti-Rotation)", "Woodchopper (Cable)"):
        item = EXERCISES_BY_NAME[name]
        assert item["impact_cost"] == "low"
        assert item["landing_cost"] == "none"
        assert item["low_impact"] is True
        assert "mech_landing_impact" not in item["mechanical_risk_tags"]
        assert "mech_lower_jump" not in item["mechanical_risk_tags"]


def test_bodyweight_jump_squat_uses_moderate_cns_metadata():
    item = EXERCISES_BY_NAME["Jump Squat"]

    assert item["cns_load"] == "moderate"
    assert "mech_cns_high" not in item["tags"]
    assert "mech_cns_high" not in item["mechanical_risk_tags"]
