import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

EXPECTED = {
    "MMA Kick Recoil Flow": ("aerobic", (180, 60, 3, 6), {"GPP", "SPP"}, ("heavy_bag",)),
    "Bilateral MMA Kick Flow": ("aerobic", (150, 60, 3, 6), {"GPP", "SPP"}, ("heavy_bag",)),
    "Cage-Space Kick Flow": ("aerobic", (150, 60, 3, 6), {"GPP", "SPP"}, ("partner", "thai_pads")),
    "Rear-Kick Power Singles": ("ATP-PCr", (5, 60, 8, 8), {"GPP", "SPP"}, ("heavy_bag",)),
    "Low-Kick Exit Burst": ("ATP-PCr", (6, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Kick-Level-Change Ready Reset": ("ATP-PCr", (6, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Entry-Safe Low-Kick Burst": ("ATP-PCr", (6, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Intercept-and-Frame Kick Burst": ("ATP-PCr", (6, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Low-Kick Repeatability": ("glycolytic", (45, 45, 6, 8), {"GPP", "SPP"}, ("heavy_bag",)),
    "Kick-or-Defend Decision Rounds": ("glycolytic", (60, 45, 5, 8), {"SPP"}, ("partner", "thai_pads")),
    "Cage-Space Kick Rounds": ("glycolytic", (90, 60, 4, 8), {"SPP"}, ("partner", "thai_pads")),
    "Kick-Exit Anti-Entry Rounds": ("glycolytic", (60, 45, 6, 8), {"SPP"}, ("partner", "thai_pads")),
}
LEGACY = {
    "Interception Kick Burst", "Kick-Punch Reposition",
    "Kick Recoil Quality Rounds", "Switch-Kick Power Bursts",
}
DRIFT_TAGS = {"distance_striker", "counter_striker", "pressure_fighter", "wrestler", "brawler", "clinch_fighter"}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice():
    return {item["name"]: item for item in _bank() if {"kicker", "mma"} <= set(item.get("tags", []))}


def test_exact_mma_kicker_slice_and_metadata():
    entries = _slice()
    assert set(entries) == set(EXPECTED)
    assert Counter(item["system"] for item in entries.values()) == {"aerobic": 3, "ATP-PCr": 5, "glycolytic": 4}
    for name, (system, dose, phases, equipment) in EXPECTED.items():
        item = entries[name]
        assert {"kicker", "mma"} <= set(item["tags"])
        assert item["system"] == system
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == dose
        assert set(item["phases"]) == phases
        assert tuple(item["equipment"]) == equipment


def test_gpp_and_spp_progression_and_doses_are_coherent():
    entries = _slice()
    gpp = {name for name, item in entries.items() if "GPP" in item["phases"]}
    assert gpp == {
        "MMA Kick Recoil Flow", "Bilateral MMA Kick Flow", "Cage-Space Kick Flow",
        "Rear-Kick Power Singles", "Low-Kick Repeatability",
    }
    assert all("SPP" in item["phases"] for item in entries.values())
    assert {item["system"] for item in entries.values() if "GPP" in item["phases"]} == {"aerobic", "ATP-PCr", "glycolytic"}
    assert {item["system"] for item in entries.values() if "SPP" in item["phases"]} == {"aerobic", "ATP-PCr", "glycolytic"}
    for item in entries.values():
        if item["system"] == "aerobic":
            assert 120 <= item["work_sec"] <= 180 and item["rest_sec"] == 60
            assert item["rpe"] in {5, 6} and item["lactate_load"] == "low"
        elif item["system"] == "ATP-PCr":
            assert 4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 90
            assert 6 <= item["rounds"] <= 8 and item["rpe"] == 8 and item["lactate_load"] == "low"
        else:
            assert 30 <= item["work_sec"] <= 120 and item["rest_sec"] < item["work_sec"] * 2
            assert item["rpe"] in {7, 8} and item["lactate_load"] == "high"


def test_mma_threats_decisions_and_quality_rules_are_explicit():
    entries = _slice()
    spp_blob = " ".join(item["notes"].lower() for item in entries.values() if "SPP" in item["phases"])
    assert "level-change" in spp_blob
    assert "forward" in spp_blob
    assert "limited-space" in spp_blob
    assert "not kicking is a correct repetition" in entries["Kick-or-Defend Decision Rounds"]["notes"].lower()
    assert "no safe window means no kick" in entries["Entry-Safe Low-Kick Burst"]["notes"].lower()
    for name in ("MMA Kick Recoil Flow", "Bilateral MMA Kick Flow", "Cage-Space Kick Flow", "Low-Kick Repeatability", "Kick-or-Defend Decision Rounds", "Cage-Space Kick Rounds", "Kick-Exit Anti-Entry Rounds"):
        notes = entries[name]["notes"].lower()
        assert ("reduce" in notes or "stop" in notes) and "stance" in notes


def test_legacy_and_archetype_drift_are_absent():
    assert LEGACY.isdisjoint({item["name"] for item in _bank()})
    for item in _slice().values():
        assert DRIFT_TAGS.isdisjoint(item["tags"]), item["name"]
        blob = f'{item["name"]} {item["modality"]} {item["notes"]}'.lower()
        assert "cage cutting" not in blob and "walk down" not in blob and "punch combination" not in blob.replace("no punch combination", "")
        assert "chain wrestling" not in blob and "mat return" not in blob and "takedown completion" not in blob
    intercept = _slice()["Intercept-and-Frame Kick Burst"]
    intercept_blob = f'{intercept["modality"]} {intercept["notes"]}'.lower()
    assert "front kick" in intercept_blob
    assert "side kick" not in intercept_blob and "back kick" not in intercept_blob


def test_equipment_and_mechanical_tags_follow_runtime_conventions():
    valid = set(known_equipment)
    for item in _slice().values():
        assert set(item["equipment"]) <= valid
        mechanical = [tag for tag in item["tags"] if tag.startswith("mech_")]
        assert len(mechanical) == len(set(mechanical))
        assert mechanical == item["mechanical_risk_tags"]
        assert len(item["mechanical_risk_tags"]) == len(set(item["mechanical_risk_tags"]))


def test_existing_selector_surfaces_mma_kicker_in_gpp_and_spp():
    flags = {
        "sport": "mma", "style_technical": ["mma"], "style_tactical": ["Kicker"],
        "key_goals": ["conditioning"], "weaknesses": ["gas_tank"], "fatigue": "low",
        "equipment": ["heavy bag", "partner", "thai pads"], "training_frequency": 5,
        "days_available": 5, "days_until_fight": 35, "time_to_fight_days": 35,
        "injuries": [], "restrictions": [],
    }
    for phase in ("GPP", "SPP"):
        conditioning._style_conditioning_bank_cache = None
        result = conditioning.generate_conditioning_block({**flags, "phase": phase})
        selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
        assert set(selected) & set(EXPECTED), (phase, selected)
