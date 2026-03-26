import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp import strength
from fightcamp.training_context import normalize_equipment_list
from fightcamp.strength import normalize_exercise_movement, normalize_style_tags, generate_strength_block


def test_style_tag_mapping():
    tags = ["style_brawler", "style_grappler", "counter_striker"]
    assert normalize_style_tags(tags) == {"brawler", "grappler", "counter_striker"}


def test_equipment_alias_split():
    assert set(normalize_equipment_list("Med Balls / Bands")) == {"medicine_ball", "bands"}
    assert set(normalize_equipment_list(["Med Balls / Bands"])) == {"medicine_ball", "bands"}


def test_normalize_exercise_movement_fallback():
    exercise = {"name": "Test Movement", "category": "hinge", "tags": ["pull"]}
    assert normalize_exercise_movement(exercise) == "hinge"
    assert exercise["movement"] == "hinge"


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


def test_novelty_with_cornerstone(monkeypatch):
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
    assert "Suitcase Carry Holds" in gpp_names
    spp = generate_strength_block(
        flags={**clinch_flags, "phase": "SPP", "prev_exercises": gpp_names, "recent_exercises": list(gpp_moves)},
        weaknesses=[],
        mindset_cue=None,
    )
    spp_names = [ex["name"] for ex in spp["exercises"]]
    assert "Suitcase Carry Holds" not in spp_names

    # Cornerstone can repeat when it still fits the next phase.
    exercise_bank = [
        {
            "name": "Weighted Pull-Up",
            "phases": ["GPP", "SPP"],
            "tags": ["pull", "compound", "upper_body"],
            "equipment": ["pullup_bar", "dumbbells"],
            "movement": "pull",
            "method": "strength",
        },
        {
            "name": "Pallof Press",
            "phases": ["GPP", "SPP"],
            "tags": ["anti_rotation", "core", "stability"],
            "equipment": ["bands"],
            "movement": "rotation",
            "method": "strength",
        },
    ]

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 2})
    score_map = {"Weighted Pull-Up": 6.0, "Pallof Press": 5.5}
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map["Weighted Pull-Up"] if "compound" in kwargs["exercise_tags"] else score_map["Pallof Press"],
            {"final_score": score_map["Weighted Pull-Up"] if "compound" in kwargs["exercise_tags"] else score_map["Pallof Press"]},
        ),
    )

    counter_flags = {
        "fight_format": "mma",
        "style_tactical": ["counter striker"],
        "training_days": ["mon", "wed"],
        "training_frequency": 2,
        "random_seed": 0,
        "equipment": ["bands", "pullup_bar", "dumbbells"],
        "key_goals": [],
    }
    gpp2 = generate_strength_block(flags={**counter_flags, "phase": "GPP"}, weaknesses=[], mindset_cue=None)
    gpp2_names = [ex["name"] for ex in gpp2["exercises"]]
    gpp2_moves = {ex.get("movement") for ex in gpp2["exercises"] if ex.get("movement")}
    assert "Weighted Pull-Up" in gpp2_names
    assert "Pallof Press" in gpp2_names
    spp2 = generate_strength_block(
        flags={**counter_flags, "phase": "SPP", "prev_exercises": gpp2_names, "recent_exercises": list(gpp2_moves)},
        weaknesses=[],
        mindset_cue=None,
    )
    spp2_names = [ex["name"] for ex in spp2["exercises"]]
    assert "Weighted Pull-Up" in spp2_names
    assert "Pallof Press" not in spp2_names
