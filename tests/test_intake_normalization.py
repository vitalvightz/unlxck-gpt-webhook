from fightcamp.intake_normalization import (
    normalize_intake_profile,
    normalized_profile_from_flags,
    normalized_profile_from_state,
)


def test_normalize_intake_profile_maps_aliases_and_preserves_raw_values():
    profile = normalize_intake_profile(
        goals=["Conditioning", "Recovery", "Striking", "Conditioning"],
        weaknesses=["conditioning", "Footwork", "Rotation", "Unknown Weakness"],
        technical_styles=["Boxer", "Muay Thai/K1", "Brazilian Jiu Jitsu"],
        tactical_styles=["Grappling", "Counter"],
    )

    assert profile.raw_goal_values == ["Conditioning", "Recovery", "Striking", "Conditioning"]
    assert profile.raw_weakness_values == ["conditioning", "Footwork", "Rotation", "Unknown Weakness"]
    assert profile.raw_technical_styles == ["Boxer", "Muay Thai/K1", "Brazilian Jiu Jitsu"]
    assert profile.raw_tactical_styles == ["Grappling", "Counter"]

    assert profile.goal_keys == ["repeatability_endurance"]
    assert profile.goal_secondary == ["striking"]
    assert profile.support_flags == ["recovery_support"]
    assert profile.weakness_keys == ["gas_tank", "footwork", "trunk_strength"]
    assert profile.weakness_secondary == [
        "aerobic_repeatability",
        "fight_repeatability",
        "lateral_movement",
        "coordination_proprioception",
        "core_stability",
        "rotation",
        "unknown_weakness",
    ]
    assert profile.technical_style_keys == ["boxing", "muay_thai", "bjj"]
    assert profile.tactical_style_keys == ["grappler", "counter_striker"]
    assert profile.tactical_style_secondary == ["submission_hunter", "scrambler"]
    assert profile.style_secondary == ["submission_hunter", "scrambler"]


def test_normalized_profile_from_state_prefers_explicit_normalized_fields():
    profile = normalized_profile_from_state(
        raw_goals=["Power", "Weight Cut"],
        raw_weaknesses=["Speed"],
        raw_technical_styles=["Wrestler"],
        raw_tactical_styles=["Pressure"],
        normalized_fields={
            "goal_keys": ["speed"],
            "goal_secondary": ["grappling"],
            "support_flags": ["weight_cut_support"],
            "weakness_keys": ["balance"],
            "weakness_secondary": ["base"],
            "technical_style_keys": ["mma"],
            "tactical_style_keys": ["hybrid"],
            "tactical_style_secondary": ["scrambler"],
            "style_secondary": ["scrambler"],
        },
    )

    assert profile.raw_goal_values == ["Power", "Weight Cut"]
    assert profile.raw_weakness_values == ["Speed"]
    assert profile.raw_technical_styles == ["Wrestler"]
    assert profile.raw_tactical_styles == ["Pressure"]
    assert profile.goal_keys == ["speed"]
    assert profile.goal_secondary == ["grappling"]
    assert profile.support_flags == ["weight_cut_support"]
    assert profile.weakness_keys == ["balance"]
    assert profile.weakness_secondary == ["base"]
    assert profile.technical_style_keys == ["mma"]
    assert profile.tactical_style_keys == ["hybrid"]
    assert profile.tactical_style_secondary == ["scrambler"]
    assert profile.style_secondary == ["scrambler"]


def test_normalized_profile_from_flags_prefers_raw_fields_over_legacy_keys():
    profile = normalized_profile_from_flags(
        {
            "raw_key_goals": ["Conditioning"],
            "key_goals": ["Power"],
            "raw_weaknesses": ["conditioning"],
            "weaknesses": ["Footwork"],
            "raw_style_technical": ["Boxer"],
            "style_technical": ["Wrestler"],
            "raw_style_tactical": ["Grappling"],
            "style_tactical": ["Counter"],
        }
    )

    assert profile.raw_goal_values == ["Conditioning"]
    assert profile.raw_weakness_values == ["conditioning"]
    assert profile.raw_technical_styles == ["Boxer"]
    assert profile.raw_tactical_styles == ["Grappling"]
    assert profile.goal_keys == ["repeatability_endurance"]
    assert profile.weakness_keys == ["gas_tank"]
    assert profile.technical_style_keys == ["boxing"]
    assert profile.tactical_style_keys == ["grappler"]