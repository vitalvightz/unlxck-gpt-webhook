import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

EXPECTED = {
    "Kick Recoil Flow": ({"kickboxing", "muay_thai"}, "aerobic", (180, 60, 3, 6), {"GPP", "SPP"}, ("heavy_bag",)),
    "Teep Range Reset": ({"muay_thai"}, "aerobic", (180, 60, 3, 6), {"GPP", "SPP"}, ("bodyweight",)),
    "Kick & Exit Flow": ({"kickboxing", "muay_thai"}, "aerobic", (180, 60, 3, 6), {"GPP", "SPP"}, ("partner", "thai_pads")),
    "Bilateral Round-Kick Flow": ({"kickboxing", "muay_thai"}, "aerobic", (120, 60, 3, 6), {"GPP", "SPP"}, ("heavy_bag",)),
    "Rear-Kick Power Singles": ({"kickboxing", "muay_thai", "mma"}, "ATP-PCr", (5, 60, 8, 8), {"GPP", "SPP"}, ("heavy_bag",)),
    "Low-Kick Exit Burst": ({"kickboxing", "muay_thai", "mma"}, "ATP-PCr", (6, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Reactive Body-Kick Burst": ({"kickboxing", "muay_thai"}, "ATP-PCr", (6, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Check-Return Burst": ({"kickboxing", "muay_thai"}, "ATP-PCr", (5, 60, 8, 8), {"SPP"}, ("partner", "thai_pads")),
    "Body-Kick Repeatability": ({"kickboxing", "muay_thai"}, "glycolytic", (45, 45, 6, 8), {"GPP", "SPP"}, ("heavy_bag",)),
    "Switch-Kick Repeatability": ({"muay_thai"}, "glycolytic", (45, 45, 6, 8), {"SPP"}, ("partner", "thai_pads")),
    "Target-Choice Kick Rounds": ({"kickboxing", "muay_thai"}, "glycolytic", (120, 60, 4, 8), {"SPP"}, ("partner", "thai_pads")),
    "Range-Adaptive Kick Rounds": ({"kickboxing", "muay_thai"}, "glycolytic", (180, 60, 3, 8), {"SPP"}, ("partner", "thai_pads")),
}

SUPERSEDED_FOR_KICKBOXING_MUAY_THAI = {
    "Switch-Side Rhythm", "Interception Kick Burst", "Dutch Target Call",
    "Low-High Decision Rounds", "Kick-Punch Reposition", "Long-to-Clinch Transition",
    "Kick Recoil Quality Rounds", "Pressure-Kicker Rounds", "Switch-Kick Power Bursts",
    "Kicker's Switch Stance March",
}
FORBIDDEN_DRIFT = {"pressure_fighter", "distance_striker", "counter_striker", "brawler", "clinch_fighter", "clinch"}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice():
    return {item["name"]: item for item in _bank() if "kicker" in item.get("tags", []) and ({"kickboxing", "muay_thai"} & set(item["tags"]))}


def test_exact_kickboxing_muay_thai_kicker_slice_and_metadata():
    entries = _slice()
    assert set(entries) == set(EXPECTED)
    assert Counter(item["system"] for item in entries.values()) == {"aerobic": 4, "ATP-PCr": 4, "glycolytic": 4}
    for name, (sports, system, dose, phases, equipment) in EXPECTED.items():
        item = entries[name]
        assert set(item["tags"]) & {"kickboxing", "muay_thai", "mma"} == sports
        assert item["system"] == system
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == dose
        assert set(item["phases"]) == phases
        assert tuple(item["equipment"]) == equipment


def test_gpp_and_spp_architecture_is_meaningful():
    entries = _slice()
    required_gpp = {"Kick Recoil Flow", "Teep Range Reset", "Kick & Exit Flow", "Bilateral Round-Kick Flow", "Rear-Kick Power Singles", "Body-Kick Repeatability"}
    assert {name for name, item in entries.items() if "GPP" in item["phases"]} == required_gpp
    assert all("SPP" in item["phases"] for item in entries.values())
    assert {item["system"] for item in entries.values() if "GPP" in item["phases"]} == {"aerobic", "ATP-PCr", "glycolytic"}
    assert {item["system"] for item in entries.values() if "SPP" in item["phases"]} == {"aerobic", "ATP-PCr", "glycolytic"}


def test_doses_quality_rules_and_representative_decisions_are_coherent():
    for item in _slice().values():
        if item["system"] == "aerobic":
            assert 120 <= item["work_sec"] <= 180 and item["rest_sec"] == 60 and item["rpe"] in {5, 6}
            assert item["lactate_load"] == "low"
        elif item["system"] == "ATP-PCr":
            assert 4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 90 and 6 <= item["rounds"] <= 8
            assert item["rpe"] == 8 and item["lactate_load"] == "low"
        else:
            assert 30 <= item["work_sec"] <= 180 and item["rest_sec"] < item["work_sec"] * 2 and item["rpe"] in {7, 8}
        if item["system"] != "ATP-PCr":
            notes = item["notes"].lower()
            assert ("reduce" in notes or "stop" in notes) and "stance" in notes
    for name in ("Reactive Body-Kick Burst", "Check-Return Burst", "Target-Choice Kick Rounds", "Range-Adaptive Kick Rounds"):
        assert _slice()[name]["equipment"] == ["partner", "thai_pads"]
    assert "No target means no kick" in _slice()["Reactive Body-Kick Burst"]["notes"]


def test_legacy_and_tactical_overlap_are_removed():
    assert not {
        item["name"] for item in _bank()
        if item["name"] in SUPERSEDED_FOR_KICKBOXING_MUAY_THAI
        and ({"kickboxing", "muay_thai"} & set(item.get("tags", [])))
    }
    for item in _slice().values():
        assert FORBIDDEN_DRIFT.isdisjoint(item["tags"]), item["name"]
        blob = f'{item["name"]} {item["modality"]} {item["notes"]}'.lower()
        assert "jab-cross" not in blob and "clinch" not in blob and "walk-down" not in blob and "trapping" not in blob


def test_equipment_and_mechanical_tags_follow_runtime_conventions():
    valid = set(known_equipment)
    for item in _slice().values():
        assert set(item["equipment"]) <= valid
        mechanical = [tag for tag in item["tags"] if tag.startswith("mech_")]
        assert len(mechanical) == len(set(mechanical))
        assert set(mechanical) == set(item["mechanical_risk_tags"])
        assert len(item["mechanical_risk_tags"]) == len(set(item["mechanical_risk_tags"]))


def test_existing_selector_surfaces_kicker_for_both_sports_and_phases():
    expected = set(EXPECTED)
    for sport in ("kickboxing", "muay_thai"):
        flags = {
            "sport": sport, "style_technical": [sport], "style_tactical": ["Kicker"],
            "key_goals": ["conditioning"], "weaknesses": ["gas_tank"], "fatigue": "low",
            "equipment": ["heavy bag", "partner", "thai pads"], "training_frequency": 5,
            "days_available": 5, "days_until_fight": 35, "time_to_fight_days": 35,
            "injuries": [], "restrictions": [],
        }
        for phase in ("GPP", "SPP"):
            conditioning._style_conditioning_bank_cache = None
            result = conditioning.generate_conditioning_block({**flags, "phase": phase})
            selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
            assert set(selected) & expected, (sport, phase, selected)


def test_deferred_mma_kicker_coverage_is_preserved_without_leaking_into_batch_1():
    by_name = {item["name"]: item for item in _bank()}
    mma_only_legacy = {
        "Interception Kick Burst",
        "Kick-Punch Reposition",
        "Kick Recoil Quality Rounds",
        "Switch-Kick Power Bursts",
    }
    for name in mma_only_legacy:
        sports = set(by_name[name]["tags"]) & {"kickboxing", "muay_thai", "mma"}
        assert sports == {"mma"}, name

    # These approved Batch-1 concepts already served all three sports, so their
    # existing MMA reachability remains on the shared record pending Batch 2.
    for name in ("Rear-Kick Power Singles", "Low-Kick Exit Burst"):
        assert "mma" in by_name[name]["tags"]

    assert set(_slice()) == set(EXPECTED)
