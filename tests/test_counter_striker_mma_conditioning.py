import json
from collections import Counter
from pathlib import Path

from fightcamp.conditioning import generate_conditioning_block


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED_DOSES = {
    "MMA Read & Counter Flow": ("aerobic", 180, 60, 3, 5),
    "Strike-Shot Transition Flow": ("aerobic", 150, 60, 3, 6),
    "Cage Counter Movement Flow": ("aerobic", 180, 60, 3, 5),
    "Sprawl-Counter Burst": ("ATP-PCr", 5, 75, 6, 8),
    "Intercepting Knee Entry Burst": ("ATP-PCr", 5, 75, 6, 8),
    "Level-Change Uppercut Burst": ("ATP-PCr", 4, 60, 8, 8),
    "Stuff-Shot Counter Exit": ("ATP-PCr", 6, 75, 6, 8),
    "Reactive MMA Counter Choice": ("ATP-PCr", 7, 75, 6, 8),
    "Strike-or-Shot Counter Intervals": ("glycolytic", 60, 45, 5, 8),
    "Cage Defend-Counter-Escape": ("glycolytic", 75, 45, 4, 8),
    "Failed Shot Punish & Reset": ("glycolytic", 45, 30, 6, 7),
    "MMA Counter Decision Rounds": ("glycolytic", 120, 60, 4, 8),
}
REMOVED_LEGACY = {
    "Clinch Counter Chaos",
    "Frame & Counter Knee Complex",
    "Slip-Counter Springs",
}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice():
    return {
        item["name"]: item
        for item in _bank()
        if {"mma", "counter_striker"}.issubset(item.get("tags", []))
    }


def test_mma_counter_slice_is_compact_complete_and_deliberately_dosed():
    entries = _slice()
    assert set(entries) == set(EXPECTED_DOSES)
    assert Counter(item["system"] for item in entries.values()) == {
        "aerobic": 3, "ATP-PCr": 5, "glycolytic": 4,
    }
    for name, expected in EXPECTED_DOSES.items():
        item = entries[name]
        assert (item["system"], item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == expected
        assert set(item["mechanical_risk_tags"]) == {
            tag for tag in item["tags"] if tag.startswith("mech_")
        }
        assert item["duration"] == f'{item["rounds"]} x {item["work_sec"]} sec, {item["rest_sec"]} sec rest'


def test_energy_systems_and_phases_match_the_intended_load():
    entries = list(_slice().values())
    aerobic = [item for item in entries if item["system"] == "aerobic"]
    assert all(150 <= item["work_sec"] <= 180 and item["rest_sec"] == 60 and 5 <= item["rpe"] <= 6 and item["lactate_load"] == "low" for item in aerobic)
    alactic = [item for item in entries if item["system"] == "ATP-PCr"]
    assert all(4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 75 and item["rpe"] == 8 and item["lactate_load"] == "low" for item in alactic)
    glycolytic = [item for item in entries if item["system"] == "glycolytic"]
    assert all(45 <= item["work_sec"] <= 120 and 30 <= item["rest_sec"] <= 60 and 7 <= item["rpe"] <= 8 and item["lactate_load"] == "high" for item in glycolytic)
    assert Counter(item["system"] for item in entries if "GPP" in item["phases"]) == {"aerobic": 3, "ATP-PCr": 4}
    assert all("SPP" in item["phases"] for item in entries)


def test_every_drill_is_opponent_led_and_ends_in_defensive_recovery():
    for item in _slice().values():
        notes = item["notes"].lower()
        assert "partner" in notes or "holder" in notes
        assert "read" in notes
        assert any(word in notes for word in ("defend", "defence", "intercept", "frame", "sprawl", "stuffs"))
        assert any(word in notes for word in ("counter", "uppercut", "knee"))
        assert any(word in notes for word in ("reset", "recover", "restores", "restored", "regains"))


def test_realistic_equipment_and_legacy_cleanup():
    approved = {"partner", "thai_pads", "focus_mitts", "wall"}
    assert all(set(item["equipment"]) <= approved and "partner" in item["equipment"] for item in _slice().values())
    assert REMOVED_LEGACY.isdisjoint(item["name"] for item in _bank())


def _flags(phase, equipment, **overrides):
    flags = {
        "phase": phase, "fatigue": "low", "style_technical": ["mma"],
        "style_tactical": ["counter_striker"], "key_goals": ["conditioning"],
        "weaknesses": ["conditioning"], "injuries": [], "equipment": equipment,
        "training_frequency": 4, "sport": "mma", "fight_format": "mma",
        "days_until_fight": 35,
    }
    flags.update(overrides)
    return flags


def test_existing_selector_can_reach_rebuilt_mma_drills_and_respects_equipment():
    equipment = ["partner", "thai_pads", "focus_mitts", "wall"]
    representative_by_phase = {
        "GPP": "Strike-Shot Transition Flow",
        "SPP": "Strike-or-Shot Counter Intervals",
    }
    for phase, expected_name in representative_by_phase.items():
        result = generate_conditioning_block(_flags(
            phase,
            equipment,
            preferred_exercise_names=[expected_name],
        ))
        selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
        assert selected == [expected_name]

    result = generate_conditioning_block(_flags(
        "SPP",
        [],
        preferred_exercise_names=["Strike-or-Shot Counter Intervals"],
    ))
    selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
    assert set(selected).isdisjoint(EXPECTED_DOSES)


def test_declared_systems_expose_the_right_prescription_candidates():
    entries = _slice()
    assert all(entries[name]["work_sec"] <= 7 and entries[name]["rest_sec"] >= 60 for name in EXPECTED_DOSES if EXPECTED_DOSES[name][0] == "ATP-PCr")
    assert all(entries[name]["work_sec"] >= 45 and entries[name]["rest_sec"] <= 60 for name in EXPECTED_DOSES if EXPECTED_DOSES[name][0] == "glycolytic")


def test_lower_and_upper_restrictions_have_mechanical_tags_to_filter_against():
    entries = _slice()
    lower_risk = {name for name, item in entries.items() if {"mech_lower_hip_hinge", "mech_lower_lunge", "mech_landing_impact"} & set(item["mechanical_risk_tags"])}
    upper_risk = {name for name, item in entries.items() if "mech_upper_press" in item["mechanical_risk_tags"]}
    assert {"Sprawl-Counter Burst", "Intercepting Knee Entry Burst", "Stuff-Shot Counter Exit"} <= lower_risk
    assert {"Level-Change Uppercut Burst", "Strike-or-Shot Counter Intervals"} <= upper_risk
