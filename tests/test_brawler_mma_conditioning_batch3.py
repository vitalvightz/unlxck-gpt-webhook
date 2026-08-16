import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import normalize_athlete_equipment_list, normalize_equipment_list

BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED = {
    "MMA Pocket Power Cluster": ("ATP-PCr", {"GPP", "SPP"}, ("partner", "thai_pads"), 6, 75, 8, 8),
    "Exchange-Sprawl-Return Burst": ("ATP-PCr", {"SPP"}, ("partner", "thai_pads"), 6, 75, 7, 8),
    "Clinch-Break Strike Burst": ("ATP-PCr", {"SPP"}, ("partner", "thai_pads"), 5, 75, 7, 8),
    "Ground-and-Pound Position Burst": ("ATP-PCr", {"GPP", "SPP"}, ("grappler_dummy",), 4, 75, 8, 8),
    "Pocket Strike-Shot Intervals": ("glycolytic", {"GPP", "SPP"}, ("partner", "thai_pads"), 30, 50, 6, 8),
    "Frame-Break-Reengage Intervals": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 35, 50, 6, 8),
    "Cage Pocket Exchange Intervals": ("glycolytic", {"SPP"}, ("partner", "cage"), 40, 55, 5, 7),
    "MMA Close-Exchange Flow": ("aerobic", {"GPP", "SPP"}, ("partner", "thai_pads"), 180, 60, 3, 6),
    "MMA Brawler Decision Rounds": ("aerobic", {"SPP"}, ("partner", "thai_pads"), 120, 60, 4, 6),
}
LEGACY = {"Alleyway Sprawl", "Sprint, Sprawl & Knee Conditioning Complex", "Ground-and-Pound Bursts"}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice():
    return {x["name"]: x for x in _bank() if {"mma", "brawler"}.issubset(x.get("tags", []))}


def test_exact_mma_brawler_rebuild_and_legacy_removal():
    entries = _slice()
    assert set(entries) == set(EXPECTED)
    assert LEGACY.isdisjoint(x["name"] for x in _bank())
    for name, expected in EXPECTED.items():
        item = entries[name]
        system, phases, equipment, work, rest, rounds, rpe = expected
        assert (item["system"], set(item["phases"]), tuple(item["equipment"])) == (system, phases, equipment)
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (work, rest, rounds, rpe)
        assert {"mma", "brawler"}.issubset(item["tags"])
    assert Counter(x["system"] for x in entries.values()) == {"ATP-PCr": 4, "glycolytic": 3, "aerobic": 2}


def test_energy_system_doses_are_coherent():
    entries = _slice().values()
    alactic = [x for x in entries if x["system"] == "ATP-PCr"]
    assert all(3 <= x["work_sec"] <= 7 and 60 <= x["rest_sec"] <= 90 and 6 <= x["rounds"] <= 8 for x in alactic)
    assert all(x["rpe"] == 8 and x["lactate_load"] == "low" for x in alactic)
    glycolytic = [x for x in entries if x["system"] == "glycolytic"]
    assert all(25 <= x["work_sec"] <= 60 and 45 <= x["rest_sec"] <= 60 and 5 <= x["rounds"] <= 6 for x in glycolytic)
    assert all(x["rpe"] in {7, 8} and x["lactate_load"] == "high" for x in glycolytic)
    aerobic = [x for x in entries if x["system"] == "aerobic"]
    assert all(120 <= x["work_sec"] <= 180 and x["rest_sec"] == 60 and 3 <= x["rounds"] <= 4 for x in aerobic)
    assert all(x["rpe"] in {5, 6} and x["lactate_load"] == "low" and x["intensity"] == "moderate" for x in aerobic)


def test_identity_boundaries_and_representative_decisions():
    entries = _slice().values()
    text = " ".join(f"{x['name']} {x['modality']} {x['notes']} {x['equipment_note']}".lower() for x in entries)
    banned = ("sprint", "10 sprawls", "burpee", "reaction light", "reaction ball", "imaginary shot", "band-resisted", "weighted punch", "chain wrestling", "mat return", "scramble chain", "pummelling", "prolonged clinch", "cage cutting", "escape denial", "pinning")
    assert all(term not in text for term in banned)
    assert "genuine committed shot" in text and "appropriate takedown defence" in text
    assert "pre-sprawl" in text and "responses are not pre-called" in text
    drift_tags = {"pressure_fighter", "wrestler", "scrambler", "clinch_fighter"}
    assert all(drift_tags.isdisjoint(x["tags"]) for x in entries)
    assert all("restore stance" in x["notes"].lower() or "stable posture" in x["notes"].lower() for x in entries)


def test_cage_and_ground_position_boundaries_are_explicit():
    cage = _slice()["Cage Pocket Exchange Intervals"]
    cage_text = f"{cage['notes']} {cage['equipment_note']}".lower()
    assert "not driving the partner backwards" in cage_text
    assert all(term not in cage_text for term in ("cutting", "pinning", "escape denial", "deny escape", "trap"))
    ground = _slice()["Ground-and-Pound Position Burst"]
    ground_text = f"{ground['notes']} {ground['equipment_note']}".lower()
    assert "already-secured" in ground_text and "maintain base and posture" in ground_text
    assert "do not chase position" in ground_text and "uncontrolled" in ground_text


def test_equipment_mechanics_uniqueness_and_phase_reachability():
    bank = _bank()
    entries = _slice().values()
    valid_equipment = {token for x in bank for token in x.get("equipment", [])}
    assert len([x["name"] for x in bank]) == len(set(x["name"] for x in bank))
    for item in entries:
        assert set(item["equipment"]) <= valid_equipment
        assert {t for t in item["tags"] if t.startswith("mech_")} == set(item["mechanical_risk_tags"])
    for phase in ("GPP", "SPP"):
        reached = [x for x in entries if phase in x["phases"]]
        assert {x["system"] for x in reached} == {"ATP-PCr", "glycolytic", "aerobic"}


def test_existing_selector_surfaces_rebuild_for_gpp_and_spp():
    flags = {"sport": "mma", "style_technical": ["mma"], "style_tactical": ["Brawler"], "key_goals": ["conditioning"], "weaknesses": ["gas_tank"], "fatigue": "low", "equipment": ["partner", "thai pads", "grappler dummy", "cage"], "training_frequency": 5, "days_available": 5, "days_until_fight": 35, "time_to_fight_days": 35, "injuries": [], "restrictions": []}
    for phase in ("GPP", "SPP"):
        result = conditioning.generate_conditioning_block({**flags, "phase": phase})
        selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
        assert set(selected) & set(EXPECTED), (phase, selected)


def test_representative_equipment_profiles_reach_the_slice():
    entries = _slice()
    profiles = (["partner", "thai pads"], ["partner", "cage"], ["grappler dummy"])
    reached = set()
    for profile in profiles:
        access = set(normalize_athlete_equipment_list(profile))
        reached |= {name for name, item in entries.items() if set(normalize_equipment_list(item["equipment"])) <= access}
    assert reached == set(EXPECTED)
