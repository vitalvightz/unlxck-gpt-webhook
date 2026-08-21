import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.training_context import normalize_athlete_equipment_list, normalize_equipment_list
from fightcamp.strength import normalize_exercise_movement, generate_strength_block




def test_equipment_alias_split():
    assert set(normalize_equipment_list("Med Balls / Bands")) == {"medicine_ball", "bands"}
    assert set(normalize_equipment_list(["Med Balls / Bands"])) == {"medicine_ball", "bands"}


def test_band_equipment_aliases_normalize_to_bands():
    assert normalize_equipment_list("band") == ["bands"]
    assert normalize_equipment_list("resistance_band") == ["bands"]
    assert normalize_equipment_list("mini_band") == ["bands"]
    assert normalize_equipment_list("banded") == ["bands"]


def test_exercise_equipment_aliases_reach_canonical_intake_tokens():
    assert normalize_equipment_list("weighted_vest") == ["weight_vest"]
    assert normalize_equipment_list("stability_ball") == ["swiss_ball"]
    assert normalize_equipment_list("cable_machine") == ["cable"]
    assert normalize_equipment_list("weight_plate") == ["plate"]


def test_box_equipment_aliases_reach_canonical_intake_token():
    for alias in ("plyo_box", "plyo box", "plyometric box", "jump box"):
        assert normalize_equipment_list(alias) == ["box"]
    assert normalize_equipment_list("bench") == ["bench"]
    assert normalize_equipment_list("step") == ["step"]


def test_normalize_equipment_list_does_not_inject_bodyweight():
    assert normalize_equipment_list(["medicine_ball"]) == ["medicine_ball"]


def test_normalize_athlete_equipment_list_injects_bodyweight():
    assert normalize_athlete_equipment_list([]) == ["bodyweight"]


def test_normalize_exercise_movement_fallback():
    exercise = {"name": "Test Movement", "category": "hinge", "tags": ["pull"]}
    assert normalize_exercise_movement(exercise) == "hinge"
    assert exercise["movement"] == "hinge"


def test_lower_body_plyometrics_use_power_movement_families():
    cases = {
        "Ballistic Box Jump (Min Ground Contact)": "vertical_jump",
        "Single-Leg Box Jump": "vertical_jump",
        "Alternating Skater Hops": "lateral_reactive",
        "Lateral Box Push-Off": "lateral_reactive",
        "Single-Leg 45° Bound": "horizontal_jump",
        "Side Hop-to-Stabilize": "lateral_reactive",
    }
    for name, expected in cases.items():
        exercise = {"name": name, "method": "plyometric", "tags": ["mech_lower_jump"]}
        assert normalize_exercise_movement(exercise) == expected


def test_explicit_upper_body_movement_wins_over_plyometric_method():
    exercise = {
        "name": "Clap Push-Up",
        "movement": "horizontal_push",
        "method": "plyometric",
        "tags": ["explosive", "mech_upper_press", "mech_ballistic"],
    }
    assert normalize_exercise_movement(exercise) == "horizontal_push"


def test_mechanical_upper_press_does_not_become_vertical_jump():
    exercise = {
        "name": "Explosive Push-Up",
        "movement": "compound",
        "method": "plyometric",
        "tags": ["mech_upper_press", "mech_ballistic"],
    }
    assert normalize_exercise_movement(exercise) == "horizontal_push"


def test_directional_metadata_routes_lower_body_plyometrics():
    assert normalize_exercise_movement(
        {
            "name": "Reaction Hop",
            "movement": "horizontal",
            "method": "plyometric",
            "tags": ["mech_lower_jump"],
        }
    ) == "horizontal_jump"
    assert normalize_exercise_movement(
        {
            "name": "Reactive Shuffle",
            "movement": "frontal",
            "method": "plyometric",
            "tags": ["mech_lower_jump"],
        }
    ) == "lateral_reactive"
    assert normalize_exercise_movement(
        {
            "name": "Rotational Hop",
            "movement": "transverse",
            "method": "plyometric",
            "tags": ["mech_lower_jump", "mech_trunk_rotation"],
        }
    ) == "rotation"


def test_movement_keyword_ab_does_not_match_inside_words():
    assert normalize_exercise_movement({"name": "Cable Fly (High to Low)"}) == "push"
    assert normalize_exercise_movement({"name": "Four-way manual neck isometric"}) == "neck"


def test_no_legacy_token_in_data():
    repo_root = Path(__file__).resolve().parents[1]
    forbidden = "med balls / bands"
    forbidden_combo = '"medicine_ball", "bands"'
    for path in repo_root.rglob("*.json"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8").lower()
        assert forbidden not in text, f"Legacy token found in {path}"
        assert forbidden_combo not in text, f"Combined equipment found in {path}"


def test_boxer_avoids_grappling_terms():
    flags = {
        "phase": "GPP",
        "fight_format": "boxing",
        "style_tactical": ["clinch fighter"],
        "training_days": ["mon", "wed", "fri"],
        "training_frequency": 3,
        "random_seed": 0,
        "equipment": [
            "plate",
            "wrist_roller",
            "pullup_bar",
            "dumbbells",
            "bands",
            "kettlebell",
            "medicine_ball",
            "sled",
            "landmine",
            "sledgehammer",
        ],
        "key_goals": [],
    }
    block = generate_strength_block(flags=flags, weaknesses=[], mindset_cue=None)
    tags = {t for ex in block["exercises"] for t in ex.get("tags", [])}
    banned = {"wrestler", "bjj", "grappler"}
    assert not any(term in tags for term in banned)


def test_dedupe_against_general_bank():
    flags = {
        "phase": "SPP",
        "fight_format": "mma",
        "style_tactical": ["clinch fighter"],
        "training_days": ["mon", "wed"],
        "training_frequency": 2,
        "random_seed": 0,
        "equipment": ["pullup_bar", "dumbbells", "bands", "kettlebell", "landmine"],
        "key_goals": [],
    }
    block = generate_strength_block(flags=flags, weaknesses=["pull"], mindset_cue=None)
    names = [ex["name"] for ex in block["exercises"]]
    assert names.count("Weighted Pull-Up") <= 1


def test_novelty_with_cornerstone():
    # Non-cornerstone should not repeat
    clinch_flags = {
        "fight_format": "mma",
        "style_tactical": ["clinch fighter"],
        "training_days": ["mon", "wed"],
        "training_frequency": 2,
        "random_seed": 0,
        "equipment": ["plate", "wrist_roller", "dumbbells", "pullup_bar"],
        "key_goals": [],
    }
    gpp = generate_strength_block(flags={**clinch_flags, "phase": "GPP"}, weaknesses=[], mindset_cue=None)
    gpp_names = [ex["name"] for ex in gpp["exercises"]]
    gpp_moves = {ex.get("movement") for ex in gpp["exercises"] if ex.get("movement")}
    assert "Plate Pinch Holds" in gpp_names
    spp = generate_strength_block(
        flags={**clinch_flags, "phase": "SPP", "prev_exercises": gpp_names, "recent_exercises": list(gpp_moves)},
        weaknesses=[],
        mindset_cue=None,
    )
    spp_names = [ex["name"] for ex in spp["exercises"]]
    assert "Plate Pinch Holds" not in spp_names

    # Cornerstone can repeat
    counter_flags = {
        "fight_format": "mma",
        "style_tactical": ["counter striker"],
        "training_days": ["mon", "wed"],
        "training_frequency": 2,
        "random_seed": 0,
        "equipment": ["bands", "landmine"],
        "key_goals": [],
    }
    gpp2 = generate_strength_block(flags={**counter_flags, "phase": "GPP"}, weaknesses=[], mindset_cue=None)
    gpp2_names = [ex["name"] for ex in gpp2["exercises"]]
    gpp2_moves = {ex.get("movement") for ex in gpp2["exercises"] if ex.get("movement")}
    assert "Pallof Press" in gpp2_names
    spp2 = generate_strength_block(
        flags={**counter_flags, "phase": "SPP", "prev_exercises": gpp2_names, "recent_exercises": list(gpp2_moves)},
        weaknesses=[],
        mindset_cue=None,
    )
    spp2_names = [ex["name"] for ex in spp2["exercises"]]
    assert "Pallof Press" in spp2_names
