"""Regression tests for conditioning dose-metadata and equipment-model fixes.

These guard four narrow corrections:

1. ``Treadmill Hill Sprints (Glycolytic)`` encodes ``6x20s, 1:40 rest`` as
   20s work / 100s rest / 6 rounds, with the bank's elapsed-session convention
   ``(6*20 + 5*100)/60 = 10.33`` minutes -- not a 1:40 work:rest ratio.
2. ``SkiErg Recovery Flow`` is continuous recovery work and must not carry a
   ``rest_sec`` (which only ever means genuine recovery between work bouts).
3. ``Jump Rope (Recovery Pace)`` is continuous 15-minute recovery work and must
   not carry a ``rest_sec`` either.
4. ``weight_belt`` is a real equipment token, and ``Pool Running (Weight Belt)``
   requires both ``pool`` and ``weight_belt`` -- so it is gated exactly like the
   conditioning selector gates any equipment-bearing drill.
"""

from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import (
    EQUIP_ALIASES,
    known_equipment,
    normalize_athlete_equipment_list,
    normalize_equipment_list,
)

_BANK = {
    entry["name"]: entry
    for entry in json.loads(
        Path("data/conditioning_bank.json").read_text(encoding="utf-8")
    )
}


def _selector_equipment_eligible(drill: dict, athlete_equipment: list[str]) -> bool:
    """Mirror the conditioning selector's equipment gate exactly.

    The selector computes ``drill_equipment = normalize_equipment_list(...)`` and
    ``equipment_access_set = set(normalize_athlete_equipment_list(...))`` and then
    keeps a drill only when ``not drill_equipment or
    drill_equipment.issubset(equipment_access_set)``.
    """
    required = set(normalize_equipment_list(drill.get("equipment", [])))
    access = set(normalize_athlete_equipment_list(athlete_equipment))
    return not required or required.issubset(access)


# --- 1. Treadmill Hill Sprints dose correction -----------------------------


def test_treadmill_hill_sprints_encodes_20s_work_100s_rest_six_rounds():
    drill = _BANK["Treadmill Hill Sprints (Glycolytic)"]
    assert drill["work_sec"] == 20
    assert drill["rest_sec"] == 100  # 1:40 == 100 seconds, not a 1:40 ratio
    assert drill["rounds"] == 6
    assert drill["total_minutes"] == 10.33


def test_treadmill_hill_sprints_total_minutes_matches_elapsed_convention():
    drill = _BANK["Treadmill Hill Sprints (Glycolytic)"]
    work_sec = drill["work_sec"]
    rest_sec = drill["rest_sec"]
    rounds = drill["rounds"]
    elapsed = (rounds * work_sec + (rounds - 1) * rest_sec) / 60
    assert round(elapsed, 2) == drill["total_minutes"]


def test_treadmill_hill_sprints_preserves_glycolytic_purpose():
    drill = _BANK["Treadmill Hill Sprints (Glycolytic)"]
    assert drill["system"] == "glycolytic"
    assert drill["phases"] == ["GPP"]
    assert drill["lactate_load"] == "high"
    assert drill["rpe"] == 9


# --- 2 & 3. Continuous recovery drills must not misuse rest_sec ------------


def test_skierg_recovery_flow_does_not_misuse_rest_sec():
    drill = _BANK["SkiErg Recovery Flow"]
    assert "rest_sec" not in drill
    # Session length stays represented by duration / total_minutes.
    assert drill["total_minutes"] == 25
    assert drill["duration"] == "25min easy"
    # No invented work/rest interval structure.
    assert "work_sec" not in drill
    assert "rounds" not in drill


def test_jump_rope_recovery_pace_does_not_misuse_rest_sec():
    drill = _BANK["Jump Rope (Recovery Pace)"]
    assert "rest_sec" not in drill
    assert drill["total_minutes"] == 15
    assert "work_sec" not in drill
    assert "rounds" not in drill


# --- 4. weight_belt equipment token + Pool Running (Weight Belt) gating -----


def test_weight_belt_is_a_known_equipment_token():
    assert "weight_belt" in known_equipment


def test_weight_belt_aliases_normalize_to_canonical_token():
    for alias in ("weight belt", "weighted belt"):
        assert EQUIP_ALIASES[alias] == "weight_belt"
        assert normalize_equipment_list([alias]) == ["weight_belt"]


def test_pool_running_weight_belt_requires_pool_and_weight_belt():
    drill = _BANK["Pool Running (Weight Belt)"]
    assert set(normalize_equipment_list(drill["equipment"])) == {"pool", "weight_belt"}


def test_pool_running_weight_belt_is_blocked_without_weight_belt():
    drill = _BANK["Pool Running (Weight Belt)"]
    assert not _selector_equipment_eligible(drill, ["pool"])


def test_pool_running_weight_belt_is_available_with_pool_and_weight_belt():
    drill = _BANK["Pool Running (Weight Belt)"]
    assert _selector_equipment_eligible(drill, ["pool", "weight_belt"])


def test_existing_pool_only_conditioning_still_behaves_normally():
    # Pool-only drills must remain reachable for an athlete with only pool
    # access, unaffected by the new weight_belt requirement above.
    pool_only = _BANK["Pool Running (No Impact)"]
    assert set(normalize_equipment_list(pool_only["equipment"])) == {"pool"}
    assert _selector_equipment_eligible(pool_only, ["pool"])
    # And the weight-belt drill must NOT leak in for that same athlete.
    assert not _selector_equipment_eligible(
        _BANK["Pool Running (Weight Belt)"], ["pool"]
    )


# --- 4b. End-to-end selector gating through generate_conditioning_block -----


def _pool_gating_flags(equipment: list[str]) -> dict:
    return {
        "phase": "GPP",
        "sport": "boxing",
        "style_technical": ["boxing"],
        "style_tactical": ["Counter Striker"],
        "key_goals": ["conditioning", "recovery"],
        "weaknesses": ["gas_tank"],
        "fatigue": "low",
        "injuries": [],
        "equipment": equipment,
        "training_frequency": 3,
    }


def _patch_pool_bank(monkeypatch) -> None:
    """Feed the real selector a tiny GPP-aerobic bank containing the weight-belt
    drill plus a universally available aerobic fallback, so the only variable is
    equipment access."""
    bank = [
        {
            "name": "Pool Running (Weight Belt)",
            "placement": "conditioning",
            "system": "aerobic",
            "phases": ["GPP"],
            "tags": ["aerobic", "conditioning", "zero_impact"],
            "equipment": ["pool", "weight_belt"],
            "total_minutes": 35,
            "duration": "35min continuous",
            "rpe": 6,
            "intensity": "zone 2",
        },
        {
            "name": "Bodyweight Aerobic Shadow",
            "placement": "conditioning",
            "system": "aerobic",
            "phases": ["GPP"],
            "tags": ["aerobic", "conditioning"],
            "equipment": ["bodyweight"],
            "total_minutes": 20,
            "duration": "20min continuous",
            "rpe": 5,
            "intensity": "zone 2",
        },
    ]
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: bank)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "select_coordination_drill", lambda *a, **k: None)
    monkeypatch.setattr(conditioning, "_load_bank", lambda *a, **k: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *a, **k: {"conditioning": 2})
    monkeypatch.setattr(
        conditioning, "calculate_exercise_numbers", lambda *a, **k: {"conditioning": 2}
    )


def test_selector_blocks_pool_running_weight_belt_without_belt(monkeypatch):
    _patch_pool_bank(monkeypatch)
    _text, selected_names, _why, _grouped, _missing, _reservoir = (
        conditioning.generate_conditioning_block(_pool_gating_flags(["pool"]))
    )
    assert "Pool Running (Weight Belt)" not in selected_names


def test_selector_allows_pool_running_weight_belt_with_pool_and_belt(monkeypatch):
    _patch_pool_bank(monkeypatch)
    _text, selected_names, _why, _grouped, _missing, _reservoir = (
        conditioning.generate_conditioning_block(
            _pool_gating_flags(["pool", "weight_belt"])
        )
    )
    assert "Pool Running (Weight Belt)" in selected_names
