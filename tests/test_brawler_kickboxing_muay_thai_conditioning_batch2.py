import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment

BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED = {
    "Pocket Punch-Kick Cluster": ("ATP-PCr", {"GPP", "SPP"}, ("heavy_bag",), 6, 75, 8, 8),
    "Cover-Hook-Kick Burst": ("ATP-PCr", {"GPP", "SPP"}, ("partner", "thai_pads"), 6, 75, 8, 8),
    "Check-Return Pocket Burst": ("ATP-PCr", {"SPP"}, ("partner", "thai_pads"), 5, 75, 8, 8),
    "Pocket Knee Reentry Burst": ("ATP-PCr", {"SPP"}, ("partner", "thai_pads"), 7, 75, 6, 8),
    "Punch-Kick Exchange Intervals": ("glycolytic", {"GPP", "SPP"}, ("heavy_bag",), 25, 45, 6, 8),
    "Guard-and-Low-Kick Answer": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 25, 45, 6, 8),
    "Pocket Body-Head-Leg Intervals": ("glycolytic", {"GPP", "SPP"}, ("partner", "thai_pads"), 35, 50, 5, 7),
    "Close-Range Exchange Rounds": ("aerobic", {"GPP", "SPP"}, ("partner", "thai_pads"), 180, 60, 3, 6),
    "Inside Decision Rounds — Kickboxing / Muay Thai": ("aerobic", {"SPP"}, ("partner", "thai_pads"), 120, 60, 4, 6),
}
PROTECTED_TESTS = (
    "test_brawler_boxing_conditioning_batch1.py",
    "test_counter_striker_kickboxing_muay_thai_conditioning.py",
    "test_pressure_fighter_conditioning_batch3.py",
)

def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))

def _slice():
    return {x["name"]: x for x in _bank() if "brawler" in x.get("tags", []) and {"kickboxing", "muay_thai"} & set(x.get("tags", []))}

def test_exact_approved_slice_and_metadata():
    entries = _slice()
    assert set(entries) == set(EXPECTED)
    for name, expected in EXPECTED.items():
        item = entries[name]
        system, phases, equipment, work, rest, rounds, rpe = expected
        assert (item["system"], set(item["phases"]), tuple(item["equipment"])) == (system, phases, equipment)
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (work, rest, rounds, rpe)
        assert "brawler" in item["tags"] and {"kickboxing", "muay_thai"} & set(item["tags"])
    assert Counter(x["system"] for x in entries.values()) == {"ATP-PCr": 4, "glycolytic": 3, "aerobic": 2}
    assert Counter(s for x in entries.values() for s in {"kickboxing", "muay_thai"} & set(x["tags"])) == {"muay_thai": 9, "kickboxing": 8}

def test_energy_system_doses_are_coherent():
    entries = _slice().values()
    alactic = [x for x in entries if x["system"] == "ATP-PCr"]
    assert all(4 <= x["work_sec"] <= 7 and 60 <= x["rest_sec"] <= 90 and 6 <= x["rounds"] <= 8 and x["rpe"] == 8 and x["lactate_load"] == "low" for x in alactic)
    glycolytic = [x for x in entries if x["system"] == "glycolytic"]
    assert all(20 <= x["work_sec"] <= 60 and 40 <= x["rest_sec"] <= 60 and x["rpe"] in {7, 8} and x["lactate_load"] == "high" for x in glycolytic)
    aerobic = [x for x in entries if x["system"] == "aerobic"]
    assert all(120 <= x["work_sec"] <= 180 and x["rest_sec"] == 60 and x["rpe"] in {5, 6} and x["lactate_load"] == "low" for x in aerobic)

def test_exchange_identity_boundaries_and_recovery_are_explicit():
    text = " ".join(f"{x['name']} {x['notes']}".lower() for x in _slice().values())
    banned = ("walk them down", "deny exits", "trap them", "cut off the ring", "keep advancing", "long-range", "kick power", "pummelling", "sustained collar", "prolonged clinch control", "pull-counter")
    assert all(term not in text for term in banned)
    for item in _slice().values():
        notes = item["notes"].lower()
        assert "stance" in notes and "guard" in notes
        assert "recoil" in notes or item["name"] == "Pocket Knee Reentry Burst"
        assert not {"pressure_fighter", "kicker", "clinch_fighter", "counter_striker"} & set(item["tags"])

def test_equipment_mechanics_and_phase_reachability_follow_conventions():
    valid = set(known_equipment)
    entries = _slice().values()
    for item in entries:
        assert set(item["equipment"]) <= valid
        mechanical = {tag for tag in item["tags"] if tag.startswith("mech_")}
        assert set(item["mechanical_risk_tags"]) == mechanical
    for phase in ("GPP", "SPP"):
        reached = [x for x in entries if phase in x["phases"]]
        assert reached and {x["system"] for x in reached} == {"ATP-PCr", "glycolytic", "aerobic"}

def test_existing_selector_surfaces_slice_for_both_sports_and_phases():
    names = set(EXPECTED)
    for sport, technical in (("kickboxing", "kickboxing"), ("muay_thai", "muay thai")):
        flags = {"sport": sport, "style_technical": [technical], "style_tactical": ["Brawler"], "key_goals": ["conditioning"], "weaknesses": ["gas_tank"], "fatigue": "low", "equipment": ["heavy_bag", "partner", "thai_pads"], "training_frequency": 5, "days_available": 5, "days_until_fight": 35, "time_to_fight_days": 35, "injuries": [], "restrictions": []}
        for phase in ("GPP", "SPP"):
            result = conditioning.generate_conditioning_block({**flags, "phase": phase})
            selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
            assert set(selected) & names, (sport, phase, selected)
