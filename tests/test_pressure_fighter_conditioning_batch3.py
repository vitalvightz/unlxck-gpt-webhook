import json
from collections import Counter
from pathlib import Path

from fightcamp.training_context import normalize_athlete_equipment_list, normalize_equipment_list


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

APPROVED_DRILLS = {
    "Pressure Footwork Flow": ("aerobic", 180, 45, 3, 5),
    "Ring-Cut Flow": ("aerobic", 180, 45, 3, 5),
    "Jab-to-Pressure Flow": ("aerobic", 180, 60, 3, 6),
    "Max-Power Bag Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Explosive Cutoff Burst": ("ATP-PCr", 5, 55, 8, 8),
    "Entry-and-Score Burst": ("ATP-PCr", 6, 60, 8, 8),
    "Escape-Recatch Burst": ("ATP-PCr", 6, 60, 8, 8),
    "Corner Trap Burst": ("ATP-PCr", 7, 60, 8, 8),
    "Ring-Cutting Intervals": ("glycolytic", 120, 60, 4, 8),
    "Pressure Combination Rounds": ("glycolytic", 120, 60, 4, 8),
    "Body-Head Pressure Intervals": ("glycolytic", 60, 45, 6, 8),
    "Cutoff-Reposition Intervals": ("glycolytic", 60, 45, 6, 8),
    "Pocket Repeatability Rounds": ("glycolytic", 45, 30, 8, 8),
    "Pressure Reset Intervals": ("glycolytic", 60, 45, 6, 7),
    "Rope/Corner Pressure Rounds": ("glycolytic", 180, 60, 3, 8),
    "Pressure Decision Rounds": ("glycolytic", 120, 60, 4, 8),
}

SUPERSEDED_LEGACY_DRILLS = {
    "Pressure Cooker", "Brawler's Gauntlet", "Ring-Cut Sprint",
    "Strongman Clinch & Sprawl Complex", "Rotational Power & Med Ball Complex",
    "Battle Rope & DB Punch Complex", "Puncher's Circuit", "Rope & Smash",
    "Last 10 Seconds", "Titan's Test", "Trap Bar Loaded Carry Complex",
    "Barbell Smash & Dash", "Tire Flip Fury", "Sled Dragger's Delight",
    "Sledgehammer Showdown", "Battle Rope & Bag Combo", "Trap Bar Tackle",
    "Barbell Bully", "Tire Slam & Jam", "Sled Push Punishment", "Clinch Grinder",
    "Cage Bully", "Dirty Boxer’s Feast", "Trap Bar Carry & Uppercut Complex",
    "KB Swing & Marching Knee Complex", "Wall & Maul", "Tire Dominator",
    "Chain Gang", "Knee Harvest", "Pitbull Protocol", "Crowbar Clinch",
    "Smother Squad", "Dump Truck", "Muay Dump", "Octopus Guard", "Brick Wall",
    "Chain Reactor", "Grim Reaper",
}

# Existing cross-style drills outside the rebuilt core remain untouched and tagged.
RETAINED_CROSS_STYLE_DRILLS = {
    "Forward-Blast Heavy Bag Intervals", "Overhand Right Bursts", "Forward Lunge Strikes",
    "Liver Hook Bursts", "Swarm Entry Sprints", "Ground-and-Pound Bursts",
    "Corner Knee Bursts", "Uppercut Barrage", "Cage Cutting Footwork",
    "Brawler's Forward Shadow", "Pressure Fighter's Cutoff Circuit",
    "Pressure Fighter's Cutoff Shadow", "Pressure Fighter's Shadowboxing Riddle",
}


def _bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _by_name() -> dict[str, dict]:
    return {item["name"]: item for item in _bank()}


def test_approved_pressure_fighter_drills_replace_the_legacy_core():
    by_name = _by_name()
    assert set(APPROVED_DRILLS).issubset(by_name)
    assert SUPERSEDED_LEGACY_DRILLS.isdisjoint(by_name)
    assert RETAINED_CROSS_STYLE_DRILLS.issubset(by_name)
    assert all("pressure_fighter" in by_name[name]["tags"] for name in APPROVED_DRILLS)
    assert all("pressure_fighter" in by_name[name]["tags"] for name in RETAINED_CROSS_STYLE_DRILLS)


def test_pressure_fighter_batch_has_deliberate_energy_system_dosing():
    by_name = _by_name()
    assert Counter(dose[0] for dose in APPROVED_DRILLS.values()) == {
        "aerobic": 3, "ATP-PCr": 5, "glycolytic": 8,
    }
    for name, expected in APPROVED_DRILLS.items():
        item = by_name[name]
        actual = (item["system"], item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"])
        assert actual == expected

    alactic = [by_name[name] for name, dose in APPROVED_DRILLS.items() if dose[0] == "ATP-PCr"]
    assert all(3 <= item["work_sec"] <= 8 and item["rest_sec"] >= 7 * item["work_sec"] for item in alactic)
    assert all(item["rounds"] >= 6 and item["lactate_load"] == "low" for item in alactic)

    aerobic = [by_name[name] for name, dose in APPROVED_DRILLS.items() if dose[0] == "aerobic"]
    assert all(item["work_sec"] >= 180 and item["rpe"] <= 6 for item in aerobic)
    assert all(item["intensity"] == "moderate" and item["lactate_load"] == "low" for item in aerobic)

    glycolytic = [by_name[name] for name, dose in APPROVED_DRILLS.items() if dose[0] == "glycolytic"]
    assert all(45 <= item["work_sec"] <= 180 and 30 <= item["rest_sec"] <= 60 for item in glycolytic)
    assert all(item["rounds"] >= 3 and item["rpe"] in {7, 8} for item in glycolytic)


def test_pressure_fighter_notes_enforce_technical_quality():
    notes = [_by_name()[name]["notes"].lower() for name in APPROVED_DRILLS]
    quality_rules = (
        "stop", "reset", "reduce output", "lower the pace", "no forced attack",
        "do not cross", "never cross", "regain stance", "recover stance", "cut the route",
    )
    assert sum(any(rule in note for rule in quality_rules) for note in notes) >= 12
    assert all(any(rule in note for rule in quality_rules) for note in notes)


def _reachable(equipment: list[str]) -> dict[str, set[str]]:
    access = set(normalize_athlete_equipment_list(equipment))
    result = {"aerobic": set(), "ATP-PCr": set(), "glycolytic": set()}
    for name in APPROVED_DRILLS:
        item = _by_name()[name]
        required = set(normalize_equipment_list(item["equipment"]))
        if required.issubset(access):
            result[item["system"]].add(name)
    return result


def test_pressure_fighter_equipment_profiles_reach_each_system():
    for profile in (["bodyweight"], ["heavy bag"], ["partner"]):
        assert all(_reachable(list(profile))[system] for system in ("aerobic", "ATP-PCr", "glycolytic"))
    assert "Pressure Footwork Flow" in _reachable([])["aerobic"]
