import hashlib
import json
from collections import Counter
from pathlib import Path

from fightcamp.training_context import normalize_athlete_equipment_list, normalize_equipment_list


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

APPROVED_DRILLS = {
    "Long-Range Movement Flow": ("aerobic", 180, 60, 3, 5),
    "Teep Range-Control Flow": ("aerobic", 180, 60, 3, 5),
    "Long-Weapon Exit Flow": ("aerobic", 180, 60, 3, 6),
    "Teep Intercept Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Kick-and-Exit Burst": ("ATP-PCr", 6, 65, 8, 8),
    "Jab-Kick Entry Burst": ("ATP-PCr", 6, 60, 8, 8),
    "Rear-Kick Reposition Burst": ("ATP-PCr", 5, 70, 7, 8),
    "Reactive Long-Weapon Burst": ("ATP-PCr", 7, 75, 6, 8),
    "Teep Volume & Position": ("glycolytic", 60, 45, 6, 7),
    "Kick-Exit Intervals": ("glycolytic", 60, 45, 6, 8),
    "Long Combination Rounds": ("glycolytic", 120, 60, 4, 8),
    "Range-Recovery Intervals": ("glycolytic", 60, 45, 6, 8),
    "Jab-Teep Control Rounds": ("glycolytic", 120, 60, 4, 8),
    "Kick-Reposition Rounds": ("glycolytic", 120, 60, 4, 8),
    "Pressure-Escape Distance Rounds": ("glycolytic", 90, 60, 5, 8),
    "Long-Range Decision Rounds": ("glycolytic", 120, 60, 4, 8),
}

SUPERSEDED_LEGACY_DRILLS = {
    "Telescope Drill", "Pendulum Step", "Teep & Retreat", "Switch-Kick Endurance Drill",
    "Teep-and-Clinch Gauntlet", "Switch-Kick Acceleration", "MT Teep Acceleration Drill",
    "Switch-Kick Plyos", "Long Guard Snap", "Axe Kick Acceleration",
    "Spinning Back Kick Accelerations", "Teep Maintenance Drill", "Kicker's Range Management",
    "Distance Striker's Angle Drill", "Distance Striker's Teep Maintenance",
    "Distance Striker's Math Dodge",
}


def _bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice() -> list[dict]:
    return [item for item in _bank() if "distance_striker" in item.get("tags", []) and {"kickboxing", "muay_thai"} & set(item.get("tags", []))]


def _by_name() -> dict[str, dict]:
    return {item["name"]: item for item in _bank()}


def test_approved_names_replace_only_the_legacy_slice():
    by_name = _by_name()
    assert set(APPROVED_DRILLS).issubset(by_name)
    assert SUPERSEDED_LEGACY_DRILLS.isdisjoint(by_name)
    assert {item["name"] for item in _slice()} == set(APPROVED_DRILLS)

    unrelated = [
        item
        for item in _bank()
        if item not in _slice()
        and not (
            "distance_striker" in item.get("tags", [])
            and {"boxing", "kickboxing", "muay_thai", "mma"}.isdisjoint(item.get("tags", []))
        )
    ]
    canonical = json.dumps(unrelated, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == "d020108e7acf96acc7aba3a9577bc52ce461af67e0610078ab9bb4abb70ca08d"


def test_metadata_and_energy_system_doses_are_coherent():
    by_name = _by_name()
    assert Counter(dose[0] for dose in APPROVED_DRILLS.values()) == {"aerobic": 3, "ATP-PCr": 5, "glycolytic": 8}
    required = {"name", "equipment", "phases", "system", "modality", "duration", "intensity", "tags", "notes", "work_sec", "rest_sec", "rounds", "rpe", "impact_cost", "lactate_load", "movement_cost", "mechanical_risk_tags"}
    for name, dose in APPROVED_DRILLS.items():
        item = by_name[name]
        assert required.issubset(item)
        assert {"distance_striker", "kickboxing", "muay_thai"}.issubset(item["tags"])
        assert (item["system"], item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == dose

    aerobic = [by_name[n] for n, d in APPROVED_DRILLS.items() if d[0] == "aerobic"]
    assert all(x["work_sec"] >= 180 and x["rpe"] <= 6 and x["lactate_load"] == "low" for x in aerobic)
    alactic = [by_name[n] for n, d in APPROVED_DRILLS.items() if d[0] == "ATP-PCr"]
    assert all(4 <= x["work_sec"] <= 7 and 55 <= x["rest_sec"] <= 75 and 6 <= x["rounds"] <= 8 and x["lactate_load"] == "low" for x in alactic)
    glycolytic = [by_name[n] for n, d in APPROVED_DRILLS.items() if d[0] == "glycolytic"]
    assert all(60 <= x["work_sec"] <= 120 and 45 <= x["rest_sec"] <= 60 and x["rounds"] >= 4 for x in glycolytic)


def test_intercept_is_partner_led_and_alactic_bursts_are_risk_tagged():
    by_name = _by_name()
    intercept = by_name["Teep Intercept Burst"]
    assert intercept["equipment"] == ["partner", "thai_pads"]
    assert "advances unpredictably" in intercept["notes"]
    assert "only when the entry is genuinely there" in intercept["notes"]

    reactive = {"Teep Intercept Burst", "Jab-Kick Entry Burst", "Reactive Long-Weapon Burst"}
    for name, dose in APPROVED_DRILLS.items():
        if dose[0] != "ATP-PCr":
            continue
        item = by_name[name]
        assert {"mech_ballistic", "mech_acceleration"}.issubset(item["mechanical_risk_tags"])
        assert set(item["mechanical_risk_tags"]).issubset(item["tags"])
        if name in reactive:
            assert "mech_reactive" in item["mechanical_risk_tags"]


def test_notes_enforce_distance_and_technical_quality():
    quality = ("stance", "range", "recoil", "balance", "exit", "retreat")
    for item in _slice():
        note = item["notes"].lower()
        assert any(term in note for term in quality)
        assert any(term in note for term in ("stop", "reset", "reduce output", "lower the pace", "no ", "do not"))


def _reachable(equipment: list[str]) -> set[str]:
    access = set(normalize_athlete_equipment_list(equipment))
    return {item["system"] for item in _slice() if set(normalize_equipment_list(item["equipment"])).issubset(access)}


def test_realistic_equipment_profiles_reach_every_system():
    for profile in (["bodyweight"], ["heavy bag"], ["partner", "thai pads"]):
        assert _reachable(list(profile)) == {"aerobic", "ATP-PCr", "glycolytic"}
