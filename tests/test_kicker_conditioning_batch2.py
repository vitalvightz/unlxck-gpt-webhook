import json
from collections import Counter
from pathlib import Path

from fightcamp.training_context import normalize_athlete_equipment_list, normalize_equipment_list


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

EXPECTED_KICKER_BATCH_2 = {
    "Teep Range Reset": ("aerobic", 180, 60, 3, 6),
    "Kick & Exit Flow": ("aerobic", 180, 60, 3, 6),
    "Switch-Side Rhythm": ("aerobic", 120, 60, 3, 6),
    "Rear-Kick Power Singles": ("ATP-PCr", 5, 60, 8, 8),
    "Reactive Body-Kick Burst": ("ATP-PCr", 6, 60, 8, 8),
    "Low-Kick Exit Burst": ("ATP-PCr", 6, 60, 8, 8),
    "Check-Return Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Interception Kick Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Dutch Target Call": ("glycolytic", 120, 60, 4, 8),
    "Body-Kick Repeatability": ("glycolytic", 45, 45, 6, 8),
    "Switch-Kick Repeatability": ("glycolytic", 45, 45, 6, 8),
    "Low-High Decision Rounds": ("glycolytic", 120, 60, 4, 8),
    "Kick-Punch Reposition": ("glycolytic", 60, 60, 6, 8),
    "Long-to-Clinch Transition": ("glycolytic", 120, 60, 4, 8),
    "Kick Recoil Quality Rounds": ("glycolytic", 120, 60, 4, 7),
    "Pressure-Kicker Rounds": ("glycolytic", 180, 60, 3, 8),
}

REMOVED_CORE_DRILLS = {
    "Band-Resisted Low Kick Power Complex",
    "Band-Resisted Calf Kick Complex",
    "Cartwheel Kick",
    "Hammer Kick",
    "Crescent Kick Precision",
    "Ax Kick Precision Drill",
    "Flying Knee Drill",
    "Jumping Roundhouse",
    "Scoop Kick Counter",
    "Capoeira Kick Flow",
}


def _bank_by_name() -> dict[str, dict]:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    return {item["name"]: item for item in data}


def test_kicker_batch_2_has_the_approved_behaviour_led_doses():
    by_name = _bank_by_name()

    assert Counter(dose[0] for dose in EXPECTED_KICKER_BATCH_2.values()) == {
        "aerobic": 3,
        "ATP-PCr": 5,
        "glycolytic": 8,
    }
    for name, (system, work_sec, rest_sec, rounds, rpe) in EXPECTED_KICKER_BATCH_2.items():
        item = by_name[name]
        assert "kicker" in item["tags"]
        assert (item["system"], item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (
            system,
            work_sec,
            rest_sec,
            rounds,
            rpe,
        )


def test_kicker_batch_2_removes_niche_and_resisted_core_drills():
    by_name = _bank_by_name()

    assert REMOVED_CORE_DRILLS.isdisjoint(by_name)


def test_kicker_batch_2_carries_reaction_recovery_and_technical_stop_rules():
    by_name = _bank_by_name()

    assert "No target means no kick" in by_name["Reactive Body-Kick Burst"]["notes"]
    assert "exit the opponent’s return line" in by_name["Low-Kick Exit Burst"]["notes"]
    assert "ready to defend another entry" in by_name["Interception Kick Burst"]["notes"]
    assert "Reduce output" in by_name["Body-Kick Repeatability"]["notes"]
    assert "Stop the set" in by_name["Kick Recoil Quality Rounds"]["notes"]


def _reachable_kicker_batch(equipment: list[str]) -> dict[str, set[str]]:
    access = set(normalize_athlete_equipment_list(equipment))
    by_system: dict[str, set[str]] = {"aerobic": set(), "ATP-PCr": set(), "glycolytic": set()}
    for name in EXPECTED_KICKER_BATCH_2:
        item = _bank_by_name()[name]
        required = set(normalize_equipment_list(item.get("equipment", [])))
        if required.issubset(access):
            by_system[item["system"]].add(name)
    return by_system


def test_kicker_batch_2_equipment_reachability_matches_realistic_profiles():
    solo_bag_profiles = [
        ["punching bag"],
        ["bodyweight", "punching bag"],
        ["heavy bag"],
        ["banana bag"],
    ]
    for equipment in solo_bag_profiles:
        reachable = _reachable_kicker_batch(equipment)
        assert "Switch-Side Rhythm" in reachable["aerobic"]
        assert "Rear-Kick Power Singles" in reachable["ATP-PCr"]
        assert "Body-Kick Repeatability" in reachable["glycolytic"]

    partner_reachable = _reachable_kicker_batch(["partner", "thai pads"])
    assert all(partner_reachable[system] for system in ("aerobic", "ATP-PCr", "glycolytic"))

    minimal_reachable = _reachable_kicker_batch([])
    assert minimal_reachable == {
        "aerobic": {"Teep Range Reset"},
        "ATP-PCr": set(),
        "glycolytic": set(),
    }
