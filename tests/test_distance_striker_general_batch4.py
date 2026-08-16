import json
from collections import Counter
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
SPORT_TAGS = {"boxing", "kickboxing", "muay_thai", "mma"}
EXPECTED_DOSES = {
    "Range Movement Flow": ("aerobic", 180, 60, 3, 5),
    "Range Reset Flow": ("aerobic", 120, 60, 4, 6),
    "Entry-Exit Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Range Intercept Burst": ("ATP-PCr", 6, 75, 7, 8),
    "Lateral Escape Burst": ("ATP-PCr", 5, 70, 8, 8),
    "Range Recovery Intervals": ("glycolytic", 60, 45, 6, 8),
    "Score-Reposition Rounds": ("glycolytic", 120, 60, 4, 8),
    "Movement Economy Rounds": ("aerobic", 180, 60, 3, 6),
    "Reactive Distance Rounds": ("glycolytic", 90, 45, 5, 8),
    "Pressure Escape and Reset": ("glycolytic", 60, 45, 6, 8),
}
REJECTED_LEGACY = {"Matrix Shuffle", "Phantom Step", "Sniper’s Retreat", "Ring Generalship", "Telescope Drill", "Outfighter’s Crucible", "Pendulum Step", "Band-Resisted Jab Endurance Complex", "Sniper’s Load", "Range Master", "Elusive Rhythms"}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _general_slice():
    return {item["name"]: item for item in _bank() if "distance_striker" in item.get("tags", []) and SPORT_TAGS.isdisjoint(item.get("tags", []))}


def test_batch_4_is_the_small_cross_sport_core():
    entries = _general_slice()
    assert set(entries) == set(EXPECTED_DOSES)
    assert Counter(d[0] for d in EXPECTED_DOSES.values()) == {"aerobic": 3, "ATP-PCr": 3, "glycolytic": 4}
    for name, dose in EXPECTED_DOSES.items():
        item = entries[name]
        assert (item["system"], item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == dose
        assert set(item["mechanical_risk_tags"]).issubset(item["tags"])


def test_batch_4_rejects_generic_conditioning_and_sport_specific_weapons():
    entries = _general_slice()
    names = {item["name"] for item in _bank()}
    assert REJECTED_LEGACY.isdisjoint(names)
    banned_equipment = {"agility_ladder", "sled", "kettlebell", "medicine_ball", "bands", "dumbbells"}
    banned_language = {"teep", "round kick", "sprawl", "cage", "slip", "pull", "clinch"}
    for item in entries.values():
        assert banned_equipment.isdisjoint(item["equipment"])
        text = f'{item["name"]} {item["notes"]}'.lower()
        assert all(term not in text for term in banned_language)


def test_batch_4_doses_preserve_energy_system_integrity_and_equipment_access():
    entries = _general_slice()
    aerobic = [item for item in entries.values() if item["system"] == "aerobic"]
    assert all(120 <= item["work_sec"] <= 180 and item["rest_sec"] == 60 and item["rpe"] <= 6 and item["lactate_load"] == "low" for item in aerobic)
    assert entries["Movement Economy Rounds"]["movement_cost"] == "moderate"
    alactic = [item for item in entries.values() if item["system"] == "ATP-PCr"]
    assert all(4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 75 and 6 <= item["rounds"] <= 8 and item["lactate_load"] == "low" and "Stop and reset" in item["notes"] for item in alactic)
    glycolytic = [item for item in entries.values() if item["system"] == "glycolytic"]
    assert all(45 <= item["work_sec"] <= 180 and 30 <= item["rest_sec"] <= 60 and 7 <= item["rpe"] <= 8 and item["lactate_load"] == "high" for item in glycolytic)
    for equipment in ({"bodyweight"}, {"partner"}):
        assert {item["system"] for item in entries.values() if set(item["equipment"]).issubset(equipment)} == {"aerobic", "ATP-PCr", "glycolytic"}
