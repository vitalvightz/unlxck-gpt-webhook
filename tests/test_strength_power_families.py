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
    assert "lower_body_jump" in profile["base_categories"]
    assert "lower_body_explosive_anchor" in profile["base_categories"]
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


def test_lower_body_explosive_anchor_is_required_only_when_requested():
    exercises = [
        {"name": "Back Squat", "equipment": "barbell", "tags": ["quad_dominant"]},
        {"name": "Bench Press", "equipment": "barbell", "tags": ["upper_body"]},
        {"name": "Split Squat", "equipment": "dumbbell", "tags": ["unilateral"]},
    ]

    assert "lower_body_explosive_anchor" not in missing_base_categories(exercises)
    assert "lower_body_explosive_anchor" in missing_base_categories(
        exercises,
        require_lower_body_explosive_anchor=True,
    )


def test_olympic_lift_satisfies_lower_body_explosive_anchor():
    exercise = {
        "name": "Hang Power Clean",
        "movement": "olympic",
        "method": "power",
        "equipment": "barbell",
        "tags": ["explosive", "triple_extension", "mech_ballistic", "mech_lower_hip_hinge"],
    }
    profile = classify_strength_item(exercise)

    assert "lower_body_olympic" in profile["base_categories"]
    assert "lower_body_explosive_anchor" in profile["base_categories"]
    assert "lower_body_explosive_anchor" not in missing_base_categories(
        [exercise],
        require_lower_body_explosive_anchor=True,
    )


def test_kettlebell_swing_satisfies_lower_body_explosive_anchor():
    exercise = {
        "name": "Kettlebell Swing",
        "movement": "hinge",
        "method": "power",
        "equipment": "kettlebell",
        "tags": ["explosive", "rate_of_force", "mech_ballistic", "mech_lower_hip_hinge"],
    }
    profile = classify_strength_item(exercise)

    assert "lower_body_hip_ballistic" in profile["base_categories"]
    assert "lower_body_explosive_anchor" in profile["base_categories"]
    assert "lower_body_explosive_anchor" not in missing_base_categories(
        [exercise],
        require_lower_body_explosive_anchor=True,
    )


def test_upper_body_plyometric_does_not_satisfy_lower_body_explosive_anchor():
    profile = classify_strength_item(
        {
            "name": "Clap Push-Up",
            "movement": "horizontal_push",
            "method": "plyometric",
            "equipment": "bodyweight",
            "tags": ["explosive", "mech_upper_press", "mech_ballistic"],
        }
    )

    assert "upper_body_ballistic" in profile["base_categories"]
    assert "lower_body_explosive_anchor" not in profile["base_categories"]
