from __future__ import annotations

import json
from pathlib import Path

from fightcamp import strength
from fightcamp.strength import generate_strength_block


REPO_ROOT = Path(__file__).resolve().parents[1]
EXERCISE_BANK = REPO_ROOT / "data" / "exercise_bank.json"


def _quality_profile() -> dict:
    return {
        "quality_class": "support_only",
        "anchor_capable": False,
        "support_only": True,
        "base_categories": ["support"],
    }


def test_boxing_support_strength_entries_exist_with_cluster_contracts():
    data = json.loads(EXERCISE_BANK.read_text(encoding="utf-8"))
    items = {item["name"]: item for item in data}

    expected = {
        "Pressure Split-Stance Pallof Rebuild": "boxing__strength_general__balance__pressure_fighter",
        "Counter Band Retract Guard Hold": "boxing__power__trunk_strength__counter_striker",
        "Distance Lateral Stick-and-Reset": "boxing__speed__footwork__distance_striker",
    }

    assert expected.keys() <= items.keys()
    for name, cluster_id in expected.items():
        item = items[name]
        assert item["category"] == "boxing_support"
        assert item["cluster_ids"] == [cluster_id]
        assert item["coverage_categories"] == ["strength_support"]
        assert "boxing" in item["tags"]
        assert "strength_support" in item["tags"]


def test_mma_support_strength_entries_exist_with_cluster_contracts():
    data = json.loads(EXERCISE_BANK.read_text(encoding="utf-8"))
    items = {item["name"]: item for item in data}

    expected = {
        "Hybrid Split-Stance Pallof Shot Hold": "mma__style_completion__coordination_proprioception__hybrid",
        "Hybrid Shot Entry Stick-and-Rebuild": "mma__style_completion__coordination_proprioception__hybrid",
        "Hybrid Shotput Sprawl Catch-and-Freeze": "mma__style_completion__coordination_proprioception__hybrid",
        "Grappler Hand-Fight Chest-Supported Row": "mma__style_completion__gas_tank__grappler",
        "Grappler Split-Stance Anti-Rotation Drag Hold": "mma__style_completion__gas_tank__grappler",
        "Grappler Re-Shot Stick March": "mma__style_completion__gas_tank__grappler",
    }

    assert expected.keys() <= items.keys()
    for name, cluster_id in expected.items():
        item = items[name]
        assert item["category"] == "mma_support"
        assert item["cluster_ids"] == [cluster_id]
        assert item["coverage_categories"] == ["strength_support"]
        assert "mma" in item["tags"]
        assert "strength_support" in item["tags"]


def test_boxing_cluster_support_beats_generic_single_leg_when_profile_matches(monkeypatch):
    exercise_bank = [
        {
            "name": "Generic Single-Leg Balance",
            "phases": ["SPP"],
            "tags": ["balance", "core", "single_leg", "strength_support"],
            "equipment": ["bands"],
            "movement": "lunge",
            "method": "strength",
        },
        {
            "name": "Pressure Split-Stance Pallof Rebuild",
            "phases": ["SPP"],
            "tags": [
                "boxing",
                "pressure_fighter",
                "anti_rotation",
                "balance",
                "stance_control",
                "core",
                "strength_support",
            ],
            "equipment": ["bands"],
            "movement": "isometric",
            "method": "strength",
            "cluster_ids": ["boxing__strength_general__balance__pressure_fighter"],
            "coverage_categories": ["strength_support"],
        },
    ]

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "score_exercise", lambda **_kwargs: (5.0, {"final_score": 5.0}))
    monkeypatch.setattr(strength, "strength_quality_adjustment", lambda _ex, phase=None: (0.0, _quality_profile()))

    result = generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "low",
            "equipment": ["bands"],
            "fight_format": "boxing",
            "training_days": ["Mon"],
            "training_frequency": 1,
            "raw_key_goals": ["Strength"],
            "raw_weaknesses": ["Balance"],
            "raw_style_tactical": ["Pressure"],
            "raw_style_technical": ["Boxer"],
        }
    )

    assert result["exercises"][0]["name"] == "Pressure Split-Stance Pallof Rebuild"
    assert result["why_log"][0]["reasons"]["cluster_hits"] == 1


def test_mma_cluster_support_surfaces_for_hybrid_profile(monkeypatch):
    exercise_bank = [
        {
            "name": "Generic Reactive Split-Stance Hold",
            "phases": ["SPP"],
            "tags": ["coordination", "reactive", "core", "strength_support"],
            "equipment": ["bands"],
            "movement": "isometric",
            "method": "strength",
        },
        {
            "name": "Hybrid Split-Stance Pallof Shot Hold",
            "phases": ["SPP"],
            "tags": [
                "mma",
                "hybrid",
                "coordination",
                "reactive",
                "anti_rotation",
                "core",
                "strength_support",
            ],
            "equipment": ["bands"],
            "movement": "isometric",
            "method": "strength",
            "cluster_ids": ["mma__style_completion__coordination_proprioception__hybrid"],
            "coverage_categories": ["strength_support"],
        },
    ]

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "score_exercise", lambda **_kwargs: (5.0, {"final_score": 5.0}))
    monkeypatch.setattr(strength, "strength_quality_adjustment", lambda _ex, phase=None: (0.0, _quality_profile()))

    result = generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "low",
            "equipment": ["bands"],
            "fight_format": "mma",
            "training_days": ["Mon"],
            "training_frequency": 1,
            "raw_key_goals": ["Skill Refinement"],
            "raw_weaknesses": ["Coordination / Proprioception"],
            "raw_style_tactical": ["Hybrid"],
            "raw_style_technical": ["MMA"],
        }
    )

    assert result["exercises"][0]["name"] == "Hybrid Split-Stance Pallof Shot Hold"
    assert result["why_log"][0]["reasons"]["cluster_hits"] == 1
    assert all(ex.get("category") != "boxing_support" for ex in result["exercises"])


def test_mma_with_boxing_technical_style_can_use_boxing_support(monkeypatch):
    exercise_bank = [
        {
            "name": "Generic Reactive Split-Stance Hold",
            "phases": ["SPP"],
            "tags": ["coordination", "reactive", "core", "strength_support"],
            "equipment": ["bands"],
            "movement": "isometric",
            "method": "strength",
        },
        {
            "name": "Distance Lateral Stick-and-Reset",
            "category": "boxing_support",
            "phases": ["SPP"],
            "tags": [
                "boxing",
                "distance_striker",
                "footwork",
                "balance",
                "reactive",
                "strength_support",
            ],
            "equipment": ["bands"],
            "movement": "lunge",
            "method": "strength",
            "cluster_ids": ["boxing__speed__footwork__distance_striker"],
            "coverage_categories": ["strength_support"],
        },
    ]

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "score_exercise", lambda **_kwargs: (5.0, {"final_score": 5.0}))
    monkeypatch.setattr(strength, "strength_quality_adjustment", lambda _ex, phase=None: (0.0, _quality_profile()))

    result = generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "low",
            "equipment": ["bands"],
            "fight_format": "mma",
            "training_days": ["Mon"],
            "training_frequency": 1,
            "raw_key_goals": ["Speed"],
            "raw_weaknesses": ["Footwork"],
            "raw_style_tactical": ["Distance"],
            "raw_style_technical": ["MMA", "Boxer"],
        }
    )

    assert result["exercises"][0]["name"] == "Distance Lateral Stick-and-Reset"