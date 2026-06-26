from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.stage2_planning_brief import _compress_short_camp_priorities


def _base_flags(**overrides):
    flags = {
        "phase": "SPP",
        "fatigue": "low",
        "sport": "boxing",
        "fight_format": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "injuries": [],
        "equipment": ["bodyweight"],
        "training_frequency": 3,
        "days_available": 3,
        "days_until_fight": 28,
    }
    flags.update(overrides)
    return flags


def _small_conditioning_bank():
    return [
        {
            "name": "Fight Pace Repeat A",
            "phases": ["SPP"],
            "system": "glycolytic",
            "tags": ["conditioning", "glycolytic"],
            "equipment": [],
            "duration": "4 x 2 min, 1 min rest",
            "rpe": 7,
        },
        {
            "name": "Fight Pace Repeat B",
            "phases": ["SPP"],
            "system": "glycolytic",
            "tags": ["conditioning", "glycolytic"],
            "equipment": [],
            "duration": "4 x 90 sec, 1 min rest",
            "rpe": 7,
        },
        {
            "name": "Reactive Shuffle Speed",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["speed", "footwork", "reactive", "low_impact"],
            "equipment": [],
            "duration": "4 x 6 sec, 90 sec rest",
            "notes": "Short full-rest footwork speed. Stop before fatigue.",
            "work_sec": 6,
            "rest_sec": 90,
            "rounds": 4,
            "rpe": 7,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
        {
            "name": "Split Step Footwork Pop",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["footwork", "acceleration", "low_impact"],
            "equipment": [],
            "duration": "4 x 5 sec, 90 sec rest",
            "notes": "Sharp technical footwork pop. Stop before fatigue.",
            "work_sec": 5,
            "rest_sec": 90,
            "rounds": 4,
            "rpe": 7,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
        {
            "name": "Easy Bike Flush",
            "phases": ["SPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery"],
            "equipment": [],
            "duration": "20 min",
            "rpe": 5,
        },
    ]


def _patch_small_bank(monkeypatch, *, total_drills=3):
    monkeypatch.setattr(conditioning, "get_conditioning_bank", _small_conditioning_bank)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": total_drills})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": total_drills})
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: {"boxing": {"SPP": {"glycolytic": 1.0, "alactic": 1.0, "aerobic": 1.0}}})


def test_speed_goal_renders_second_alactic_exposure(monkeypatch):
    _patch_small_bank(monkeypatch)

    output, _names, why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(key_goals=["speed"])
    )

    assert len(grouped.get("alactic", [])) == 2
    assert any({"speed", "footwork", "reactive"} & set(drill.get("tags", [])) for drill in grouped["alactic"])
    assert "Speed Dose:" in output
    assert any(
        "speed_goal_alactic_microdose" in entry.get("reasons", {}).get("reason_codes", [])
        for entry in why_log
    )


def test_non_speed_baseline_keeps_one_alactic_primary(monkeypatch):
    _patch_small_bank(monkeypatch)

    output, _names, why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(key_goals=["conditioning"])
    )

    assert len(grouped.get("alactic", [])) == 1
    assert "Speed Dose:" not in output
    assert not any(
        "speed_goal_alactic_microdose" in entry.get("reasons", {}).get("reason_codes", [])
        for entry in why_log
    )


def test_high_fatigue_suppresses_second_speed_exposure(monkeypatch):
    _patch_small_bank(monkeypatch)

    output, _names, _why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(key_goals=["speed"], fatigue="high")
    )

    assert len(grouped.get("alactic", [])) == 1
    assert "Speed Dose:" not in output


def test_taper_speed_goal_respects_single_alactic_cap(monkeypatch):
    _patch_small_bank(monkeypatch)

    output, _names, _why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(phase="TAPER", key_goals=["speed"], days_until_fight=7)
    )

    assert len(grouped.get("alactic", [])) <= 1
    assert "Speed Dose:" not in output


def test_lower_limb_injury_downgrades_away_from_acceleration_speed(monkeypatch):
    bank = [
        {
            "name": "Hard Sprint Acceleration",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["speed", "acceleration", "mech_max_velocity"],
            "equipment": [],
            "duration": "4 x 8 sec, 120 sec rest",
        },
        {
            "name": "Rhythm Footwork Pop",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["footwork", "coordination", "low_impact"],
            "equipment": [],
            "duration": "4 x 6 sec, 90 sec rest",
        },
        *_small_conditioning_bank()[:2],
    ]
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: bank)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 3})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 3})
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: {"boxing": {"SPP": {"glycolytic": 1.0, "alactic": 1.0}}})

    _output, names, _why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(key_goals=["speed"], injuries=["hamstring strain"])
    )

    assert "Hard Sprint Acceleration" not in names
    assert any(drill.get("name") == "Rhythm Footwork Pop" for drill in grouped.get("alactic", []))


def test_speed_tagging_regression_entries_are_additive():
    root = Path(__file__).resolve().parents[1]
    conditioning_bank = json.loads((root / "data" / "conditioning_bank.json").read_text(encoding="utf-8"))
    exercise_bank = json.loads((root / "data" / "exercise_bank.json").read_text(encoding="utf-8"))

    conditioning_by_name = {item["name"]: set(item.get("tags", [])) for item in conditioning_bank}
    exercise_by_name = {item["name"]: set(item.get("tags", [])) for item in exercise_bank}

    assert {"speed", "footwork", "reactive"} <= conditioning_by_name["Mini Hurdle Quick Steps"]
    assert {"speed", "footwork", "reactive"} <= conditioning_by_name["Reactive Shuffle Repeats"]
    assert {"speed", "acceleration"} <= exercise_by_name["Sprint Acceleration (10-20m)"]
    assert "reactive" in exercise_by_name["Reactive Band Taps (Partner)"]
    assert "footwork" in exercise_by_name["Pivot-and-freeze lead foot"]
    assert "footwork" in exercise_by_name["Line step-and-stick forward/back"]
    assert {"speed", "footwork"} <= exercise_by_name["Boxing Shuffle Drill (Ladder)"]


def test_short_camp_speed_goal_has_distinct_planning_objective():
    compressed = _compress_short_camp_priorities(
        {
            "days_until_fight": 6,
            "key_goals": ["speed"],
            "primary_goal": "speed",
            "weaknesses": [],
            "readiness_flags": [],
        }
    )

    labels = [entry["label"] for entry in compressed["primary_targets"]]
    assert "speed / footwork sharpness" in labels
    assert "power expression" not in labels
