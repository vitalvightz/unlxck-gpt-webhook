import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp import conditioning, strength


def test_style_taper_bodyweight_drill_is_eligible_with_empty_athlete_equipment(monkeypatch):
    style_taper_bank = [
        {
            "name": "Bodyweight Taper Burst",
            "phases": ["TAPER"],
            "placement": "conditioning",
            "system": "alactic",
            "tags": ["pressure_fighter", "sharpness"],
            "equipment": ["bodyweight"],
            "load": "Fast and crisp",
            "rest": "60 sec",
            "timing": "6 x 8 sec",
            "purpose": "Keep sharp without fatigue.",
            "red_flags": "None",
        },
        {
            "name": "Med Ball Taper Slam",
            "phases": ["TAPER"],
            "placement": "conditioning",
            "system": "alactic",
            "tags": ["pressure_fighter", "sharpness"],
            "equipment": ["medicine_ball"],
            "load": "Explosive",
            "rest": "75 sec",
            "timing": "5 x 10 sec",
            "purpose": "Power touch.",
            "red_flags": "None",
        },
    ]

    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])

    def fake_load_bank(path, source="", enforce_conditioning_systems=False):
        if source == "style_taper_conditioning.json":
            return style_taper_bank
        return []

    monkeypatch.setattr(conditioning, "_load_bank", fake_load_bank)

    _, selected_names, _, _, _, _ = conditioning.generate_conditioning_block(
        {
            "phase": "TAPER",
            "fatigue": "low",
            "style_tactical": ["pressure fighter"],
            "style_technical": ["boxing"],
            "key_goals": [],
            "weaknesses": [],
            "injuries": [],
            "equipment": [],
            "training_frequency": 2,
        }
    )

    assert "Bodyweight Taper Burst" in selected_names
    assert "Med Ball Taper Slam" not in selected_names


def test_bodyweight_strength_drill_remains_selectable_when_athlete_does_not_list_bodyweight(monkeypatch):
    exercise_bank = [
        {
            "name": "Bodyweight Speed Push-Up",
            "tags": ["speed", "explosive", "upper_body_push"],
            "phases": ["SPP", "TAPER", "GPP"],
            "equipment": ["bodyweight"],
            "movement": "push",
            "prescription": {"SPP": "4 x 5"},
        },
        {
            "name": "Medicine Ball Rotational Throw",
            "tags": ["explosive", "rotation"],
            "phases": ["SPP", "TAPER", "GPP"],
            "equipment": ["medicine_ball"],
            "movement": "rotation",
            "prescription": {"SPP": "4 x 3/side"},
        },
    ]

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())

    block = strength.generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "low",
            "fight_format": "mma",
            "style_tactical": ["pressure fighter"],
            "key_goals": [],
            "training_days": ["Mon", "Wed"],
            "training_frequency": 2,
            "equipment": [],
            "injuries": [],
            "prev_exercises": [],
            "recent_exercises": [],
            "restrictions": [],
            "ignore_restrictions": False,
            "random_seed": 7,
        },
        weaknesses=[],
        mindset_cue=None,
    )

    selected_names = {exercise["name"] for exercise in block["exercises"]}
    assert "Bodyweight Speed Push-Up" in selected_names
    assert "Medicine Ball Rotational Throw" not in selected_names
