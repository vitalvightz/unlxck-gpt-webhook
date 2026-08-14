from fightcamp.strength_session_quality import classify_strength_item, missing_base_categories


def test_bodyweight_jump_is_power_not_loaded_strength():
    profile = classify_strength_item(
        {
            "name": "Jump Squat",
            "method": "power",
            "equipment": "bodyweight",
            "tags": ["explosive", "mech_lower_jump", "triple_extension"],
        }
    )

    assert profile["quality_class"] == "anchor_power"
    assert "lower_body_power" in profile["base_categories"]
    assert "lower_body_loaded" not in profile["base_categories"]


def test_single_leg_hyphen_counts_as_unilateral():
    profile = classify_strength_item(
        {
            "name": "Single-Leg Box Jump",
            "method": "plyometric",
            "equipment": "bodyweight",
            "tags": ["plyometric", "mech_lower_jump"],
        }
    )

    assert "unilateral" in profile["base_categories"]


def test_rotational_power_is_not_demoted_to_support():
    profile = classify_strength_item(
        {
            "name": "Woodchopper (Cable)",
            "method": "power",
            "equipment": "cable",
            "tags": ["core", "explosive", "rotational", "mech_trunk_rotation"],
        }
    )

    assert profile["quality_class"] == "anchor_power"
    assert "rotational_power" in profile["base_categories"]


def test_lower_body_power_is_a_required_strength_family():
    exercises = [
        {"name": "Back Squat", "equipment": "barbell", "tags": ["quad_dominant"]},
        {"name": "Bench Press", "equipment": "barbell", "tags": ["upper_body"]},
        {"name": "Split Squat", "equipment": "dumbbell", "tags": ["unilateral"]},
    ]

    assert "lower_body_power" in missing_base_categories(exercises)
