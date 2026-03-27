from fightcamp.conditioning import generate_conditioning_block
from fightcamp.injury_guard import derive_constraint_sensitivity
from fightcamp.strength import generate_strength_block


def _hip_flexor_injury(*, trend: str, functional_impact: str) -> dict:
    return {
        "injury_type": "unspecified",
        "canonical_location": "hip_flexor",
        "severity": "moderate",
        "trend": trend,
        "functional_impact": functional_impact,
        "aggravators": [
            "deep hip flexion",
            "hard rotation",
            "heavy hinging",
            "fast direction changes",
            "prolonged stance/load",
        ],
        "notes": "pain spikes when driving the knee up, after sparring, or when loading the stance",
        "original_phrase": "Hip / groin",
    }


def _boxing_flags(parsed_injuries: list[dict], *, fatigue: str = "high") -> dict:
    return {
        "phase": "SPP",
        "fatigue": fatigue,
        "fight_format": "boxing",
        "sport": "boxing",
        "style_technical": ["boxing"],
        "style_tactical": ["distance_striker"],
        "key_goals": ["power", "strength", "conditioning", "mobility", "weight_cut"],
        "weaknesses": ["conditioning", "power", "mobility", "trunk_strength"],
        "training_days": ["Mon", "Tue", "Thu", "Sat"],
        "training_frequency": 4,
        "days_until_fight": 17,
        "hard_sparring_days": ["Tue", "Thu"],
        "weight_cut_risk": True,
        "weight_cut_pct": 5.8,
        "equipment": [
            "bodyweight",
            "bands",
            "dumbbell",
            "medicine_ball",
            "heavy_bag",
            "bench",
            "rower",
            "assault_bike",
        ],
        "injuries": ["hip flexor issue"],
        "parsed_injuries": parsed_injuries,
        "random_seed": 11,
    }


def test_constraint_sensitivity_state_distinguishes_improving_vs_critical():
    improving = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )
    worsening = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )

    assert improving.state == "constrained"
    assert worsening.state == "critical"
    assert worsening.score > improving.score


def test_constrained_boxing_profile_stays_strict_without_flattening():
    flags = _boxing_flags(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")]
    )

    strength = generate_strength_block(flags=flags)
    strength_names = [exercise["name"] for exercise in strength["exercises"]]
    assert "Band-Resisted Punch" in strength_names
    assert "Band-Resisted Straight Punch" in strength_names
    assert "Banded Row (Speed Focus)" in strength_names
    assert not any("Split Squat" in name for name in strength_names)
    assert not any("Russian Twist" in name or "Rotational" in name for name in strength_names)
    assert sum("Lunge" in name or "Bound" in name for name in strength_names) <= 1

    _, conditioning_names, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert "Distance Angle Exit Shadow Tempo" in conditioning_names
    assert "Assault Bike Capacity Builder" in conditioning_names
    assert not any("Exit-and-Reenter" in name for name in conditioning_names)
    assert grouped_drills["aerobic"][0]["name"] == "Distance Angle Exit Shadow Tempo"


def test_critical_boxing_profile_becomes_much_simpler():
    flags = _boxing_flags(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")]
    )

    strength = generate_strength_block(flags=flags)
    strength_names = [exercise["name"] for exercise in strength["exercises"]]
    assert "Lateral Bound-to-Slip" not in strength_names
    assert "Jump Lunge (Alternating)" not in strength_names
    assert "Dynamic Plank-to-Punch" in strength_names

    _, conditioning_names, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert grouped_drills["aerobic"][0]["name"] == "Swimming (Freestyle Laps)"
    assert "Distance Angle Exit Shadow Tempo" not in conditioning_names
    assert not any("Exit-and-Reenter" in name for name in conditioning_names)
    assert "Explosive Boxing Burst Intervals" not in conditioning_names


def test_healthy_boxing_control_keeps_sport_specific_outputs():
    flags = _boxing_flags([], fatigue="low")
    flags["injuries"] = []
    flags.pop("parsed_injuries")
    flags["weight_cut_risk"] = False
    flags["weight_cut_pct"] = 0.0
    flags["hard_sparring_days"] = ["Tue"]

    strength = generate_strength_block(flags=flags)
    strength_names = [exercise["name"] for exercise in strength["exercises"]]
    assert "Lateral Bound-to-Slip" in strength_names
    assert "Jump Lunge (Alternating)" in strength_names

    _, conditioning_names, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert "Distance Exit-and-Reenter Bag Repeats" in conditioning_names
    assert grouped_drills["alactic"][0]["name"] == "Explosive Boxing Burst Intervals"
