import json
from collections import Counter
from pathlib import Path


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

EXPECTED_DOSES = {
    "Open-Space Movement Flow": ("aerobic", 180, 60, 3, 5),
    "Cage-Aware Range Flow": ("aerobic", 180, 60, 3, 6),
    "Level-Change Respect Flow": ("aerobic", 120, 60, 3, 5),
    "Intercept-and-Exit Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Strike-Sprawl-Reset Burst": ("ATP-PCr", 6, 75, 8, 8),
    "Entry-Score-Angle Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Fence-Escape Burst": ("ATP-PCr", 7, 75, 6, 8),
    "Reactive Range Decision Burst": ("ATP-PCr", 6, 75, 8, 8),
    "Cage Escape Intervals": ("glycolytic", 60, 45, 6, 8),
    "Strike-Level-Change Decision Rounds": ("glycolytic", 120, 60, 4, 8),
    "In-Out MMA Striking Rounds": ("glycolytic", 120, 60, 4, 8),
    "Anti-Fence Range Rounds": ("glycolytic", 180, 60, 3, 7),
    "Failed-Entry Reset Intervals": ("glycolytic", 45, 45, 6, 8),
    "Intercept-Reposition Rounds": ("glycolytic", 60, 45, 6, 8),
    "Long-Range MMA Decision Rounds": ("glycolytic", 180, 60, 3, 8),
    "Range Recovery Under Pressure": ("glycolytic", 90, 60, 4, 8),
}


def _mma_distance_entries() -> dict[str, dict]:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    return {
        item["name"]: item
        for item in bank
        if {"distance_striker", "mma"}.issubset(item.get("tags", []))
    }


def test_batch_3_is_the_approved_mma_distance_striker_slice():
    entries = _mma_distance_entries()

    assert set(entries) == set(EXPECTED_DOSES)
    assert Counter(dose[0] for dose in EXPECTED_DOSES.values()) == {
        "aerobic": 3,
        "ATP-PCr": 5,
        "glycolytic": 8,
    }
    for name, dose in EXPECTED_DOSES.items():
        item = entries[name]
        assert (item["system"], item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == dose


def test_batch_3_removes_generic_mma_conditioning():
    bank_names = {
        item["name"] for item in json.loads(BANK_PATH.read_text(encoding="utf-8"))
    }

    assert {"Ghost Protocol", "Octagon Geometry", "Sniper’s Grip"}.isdisjoint(bank_names)


def test_batch_3_alactic_work_has_full_recovery_and_reactive_stop_rules():
    entries = _mma_distance_entries()

    for name, item in entries.items():
        if item["system"] != "ATP-PCr":
            continue
        assert 4 <= item["work_sec"] <= 7, name
        assert 60 <= item["rest_sec"] <= 75, name
        assert item["lactate_load"] == "low", name
        assert "Stop" in item["notes"], name
        if name != "Entry-Score-Angle Burst":
            assert "mech_reactive" in item["mechanical_risk_tags"], name


def test_batch_3_uses_partner_or_bodyweight_without_new_boundary_equipment():
    entries = _mma_distance_entries()

    assert {equipment for item in entries.values() for equipment in item["equipment"]} == {
        "bodyweight",
        "partner",
    }
    for name in {
        "Cage-Aware Range Flow",
        "Fence-Escape Burst",
        "Cage Escape Intervals",
        "Anti-Fence Range Rounds",
        "Long-Range MMA Decision Rounds",
    }:
        assert "marked boundary" in entries[name]["notes"]


def test_batch_3_decision_drills_do_not_reward_automatic_sprawls():
    entries = _mma_distance_entries()

    assert "Only sprawl" in entries["Level-Change Respect Flow"]["notes"]
    assert "Only sprawl" in entries["Strike-Sprawl-Reset Burst"]["notes"]
    assert "Do not force an action" in entries["Reactive Range Decision Burst"]["notes"]
    assert "without automatic sprawls" in entries["Long-Range MMA Decision Rounds"]["notes"]
