from __future__ import annotations

import json
from pathlib import Path

from fightcamp import strength
from fightcamp.injury_filtering import injury_match_details


ROOT = Path(__file__).resolve().parents[1]

LEGACY_STYLE_STRENGTH_NAMES = {
    "Plate Pinch Holds",
    "Wrist Roller Extensions",
    "Barbell Thruster",
    "Turkish Get-Up",
    "Bulgarian Split Squat",
    "Walking Lunges",
    "Weighted Pull-Up",
    "Kettlebell Swing",
    "Barbell Landmine Twist",
    "Pallof Press",
    "Overhead Med Ball Slam",
    "Farmer’s Carry",
    "Weighted Sled Push",
    "Jumping Lunge",
    "Sledgehammer Slam",
    "Medicine Ball Slam",
    "Counter-Striker Split-Line Punch Isometric Hold",
    "Pressure-Fighter Staggered Body-Shot Med-Ball Throw",
    "Clinch Towel/Gi Row Isometric Hold",
}

# These legacy entries were intentionally retired as semantic duplicates of the
# canonical main-bank movement shown here. Keeping the mapping explicit makes a
# future deletion a conscious decision instead of a silent migration side effect.
INTENTIONALLY_RETIRED = {
    "Plate Pinch Holds": "Plate Pinch Carry",
    "Walking Lunges": "Bulgarian Split Squat",
    "Farmer’s Carry": "Farmers Walk (Fat Grip)",
    "Jumping Lunge": "Jump Lunge (Alternating)",
    "Clinch Towel/Gi Row Isometric Hold": "Towel Pull-Up",
}

EXPECTED_EXACT_INJURY_MAPPINGS = {
    "elbow": {"Wrist Roller Extensions"},
    "hip_flexor": {"Bulgarian Split Squat"},
    "knee": {"Bulgarian Split Squat"},
    "quad": {"Bulgarian Split Squat"},
    "shoulder": {"Pallof Press"},
}

EXPECTED_RETIRED_INJURY_REPLACEMENTS = {
    "forearm": {"Plate Pinch Carry", "Farmers Walk (Fat Grip)"},
    "hand": {"Plate Pinch Carry", "Farmers Walk (Fat Grip)"},
    "hip_flexor": {"Bulgarian Split Squat", "Jump Lunge (Alternating)"},
    "knee": {"Bulgarian Split Squat", "Jump Lunge (Alternating)"},
    "quad": {"Bulgarian Split Squat", "Jump Lunge (Alternating)"},
}


def _exercise_bank() -> list[dict]:
    return json.loads((ROOT / "data" / "exercise_bank.json").read_text(encoding="utf-8"))


def _injury_map() -> dict[str, list[str]]:
    return json.loads((ROOT / "data" / "injury_exclusion_map.json").read_text(encoding="utf-8"))


def test_every_legacy_style_strength_entry_has_an_explicit_resolution() -> None:
    bank_names = {item["name"] for item in _exercise_bank()}
    retired_names = set(INTENTIONALLY_RETIRED)
    surviving_names = LEGACY_STYLE_STRENGTH_NAMES - retired_names

    assert surviving_names <= bank_names
    assert retired_names.isdisjoint(bank_names)
    assert surviving_names | retired_names == LEGACY_STYLE_STRENGTH_NAMES

    missing_replacements = {
        legacy_name: replacement
        for legacy_name, replacement in INTENTIONALLY_RETIRED.items()
        if replacement not in bank_names
    }
    assert not missing_replacements, f"Retired style exercises lack canonical replacements: {missing_replacements}"


def test_style_strength_retirement_preserves_injury_resolution() -> None:
    injury_map = _injury_map()

    for region, exercise_names in EXPECTED_EXACT_INJURY_MAPPINGS.items():
        refs = set(injury_map[region])
        for exercise_name in exercise_names:
            assert f"exercise_bank:{exercise_name}" in refs

    for region, replacement_names in EXPECTED_RETIRED_INJURY_REPLACEMENTS.items():
        refs = set(injury_map[region])
        for replacement_name in replacement_names:
            assert f"exercise_bank:{replacement_name}" in refs

    all_refs = {ref for refs in injury_map.values() for ref in refs}
    assert not any(ref.startswith("style_specific_exercises:") for ref in all_refs)


def test_surviving_overhead_med_ball_slam_remains_injury_guarded() -> None:
    exercise = next(item for item in _exercise_bank() if item["name"] == "Overhead Med Ball Slam")

    for region in ("chest", "shoulder"):
        reasons = injury_match_details(exercise, [region])
        assert reasons, f"Overhead Med Ball Slam lost {region} injury protection during bank migration"


def _style_candidate(name: str, *, counter_specific: bool) -> dict:
    tags = [
        "anti_rotation",
        "core",
        "isometric",
        "low_impact",
        "low_eccentric",
        "cns_freshness",
    ]
    if counter_specific:
        tags.append("counter_striker")
    return {
        "name": name,
        "category": "core",
        "phases": ["SPP"],
        "method": "strength",
        "movement": "anti_rotation",
        "type": "isometric",
        "tags": tags,
        "equipment": "bands",
        "movement_cost": "low",
        "impact_cost": "low",
        "eccentric_cost": "low",
        "landing_cost": "none",
        "cns_load": "low",
        "soreness_risk": "low",
        "low_impact": True,
        "low_eccentric": True,
        "cns_freshness": True,
        "cut_buckets_allowed": ["none", "low", "moderate"],
    }


def test_tactical_style_changes_strength_selection_without_protected_injection(monkeypatch) -> None:
    neutral = _style_candidate("Neutral Anti-Rotation Hold", counter_specific=False)
    counter = _style_candidate("Counter Anti-Rotation Hold", counter_specific=True)

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: [neutral, counter])
    monkeypatch.setattr(strength, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})

    base_flags = {
        "phase": "SPP",
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_technical": ["boxing"],
        "equipment": ["bands"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": [],
        "weaknesses": [],
        "injuries": [],
    }

    unstyled = strength.generate_strength_block(flags={**base_flags, "style_tactical": []})
    styled = strength.generate_strength_block(
        flags={**base_flags, "style_tactical": ["counter_striker"]}
    )

    assert unstyled["exercises"][0]["name"] == "Neutral Anti-Rotation Hold"
    assert styled["exercises"][0]["name"] == "Counter Anti-Rotation Hold"
    assert not hasattr(strength, "get_style_exercises")
    assert not hasattr(strength, "_style_exercises_cache")
