import hashlib
import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED = {
    "MMA Clinch Position Flow": ("aerobic", {"GPP", "SPP"}, ("partner",), 180, 60, 3, 5),
    "Cage Position Flow": ("aerobic", {"GPP", "SPP"}, ("partner",), 180, 60, 3, 5),
    "Reactive MMA Clinch Rounds": ("aerobic", {"SPP"}, ("partner", "thai_pads"), 120, 60, 4, 6),
    "Underhook Position Burst": ("ATP-PCr", {"GPP", "SPP"}, ("partner",), 6, 75, 8, 8),
    "Cage Turn Burst": ("ATP-PCr", {"SPP"}, ("partner",), 6, 75, 7, 8),
    "Level-Change Stuff-and-Recover Burst": ("ATP-PCr", {"SPP"}, ("partner",), 7, 75, 7, 8),
    "Cage Position Intervals": ("glycolytic", {"GPP", "SPP"}, ("partner",), 35, 45, 6, 8),
    "Clinch Strike-Control Intervals": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 35, 45, 6, 8),
    "Pummel-to-Attack Intervals": ("glycolytic", {"GPP", "SPP"}, ("partner", "thai_pads"), 35, 45, 6, 8),
    "MMA Clinch Decision Rounds": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 60, 45, 5, 8),
}
LEGACY = {
    "Cage Clinch Gauntlet", "Greco-Roman Grinder", "Max Knee & Sprawl Complex",
    "Wall Pressure & Elbow Complex", "Judo Clinch Transition", "Clinch & Sprawl Reaction Complex",
    "Elbow Alley", "Collar Tie Counter", "Clinch Gas Tank", "Band-Resisted Whizzer & Sprawl Complex",
    "Clinch Finisher", "Clinch Knee Storm Intervals", "Clinch-to-Strike Transition Drill",
    "Neck Snap Drill", "Knee Strike Bursts", "Strike-to-Clinch Drill",
}
PRESERVED_HASHES = {
    ("boxing", "clinch_fighter"): "a8c2cacfaf4b81155c1048bad4bb3b17ffd90c600991fd2750ffe05cdb36b4a9",
    ("muay_thai", "clinch_fighter"): "dde054e5f0fa8eddd77a08dc34dac94feade2515368db25bb6408c18de389358",
    ("mma", "brawler"): "cb8a9c25186201b904ed9dee351a54a942bd97250d01b15998fc67ca45999d76",
    ("mma", "pressure_fighter"): "655b2724c48bd2fed2d849e0c0e605b15631ac441001b4c642c25b0c11d470c1",
    ("mma", "counter_striker"): "7b0b5b305792afcc281ab6aa01b27e47984254cedda23923e738a4507be98d6b",
    ("mma", "distance_striker"): "de7cfb86eceb0fedab845908a2ad2de4894bf3836ba8f395aa30d3f58461cc04",
}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice(sport="mma", style="clinch_fighter"):
    return [item for item in _bank() if {sport, style} <= set(item.get("tags", []))]


def test_exact_mma_clinch_rebuild_names_metadata_and_system_distribution():
    entries = {item["name"]: item for item in _slice()}
    assert set(entries) == set(EXPECTED)
    assert set(entries).isdisjoint(LEGACY)
    assert Counter(item["system"] for item in entries.values()) == {
        "ATP-PCr": 3, "glycolytic": 4, "aerobic": 3,
    }
    for name, expected in EXPECTED.items():
        item = entries[name]
        system, phases, equipment, work, rest, rounds, rpe = expected
        assert {"mma", "clinch_fighter"} <= set(item["tags"])
        assert (item["system"], set(item["phases"]), tuple(item["equipment"])) == (system, phases, equipment)
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (work, rest, rounds, rpe)


def test_energy_doses_and_phase_reachability_are_coherent():
    entries = _slice()
    for item in entries:
        if item["system"] == "ATP-PCr":
            assert 4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 90
            assert 6 <= item["rounds"] <= 8 and item["rpe"] == 8 and item["lactate_load"] == "low"
        elif item["system"] == "glycolytic":
            assert 20 <= item["work_sec"] <= 60 and item["rest_sec"] < 2 * item["work_sec"]
            assert item["rpe"] in {7, 8} and item["lactate_load"] == "high"
        else:
            assert 120 <= item["work_sec"] <= 180 and item["rest_sec"] == 60
            assert item["rpe"] in {5, 6} and item["lactate_load"] == "low"
    for phase in ("GPP", "SPP"):
        reached = [item for item in entries if phase in item["phases"]]
        assert {item["system"] for item in reached} == {"ATP-PCr", "glycolytic", "aerobic"}


def test_standing_connection_cage_level_change_and_partner_rules_are_explicit():
    entries = {item["name"]: item for item in _slice()}
    assert all("partner" in item["equipment"] for item in entries.values())
    assert all(not ({"wrestler", "scrambler", "brawler", "pressure_fighter", "muay_thai"} & set(item["tags"])) for item in entries.values())
    text = " ".join(f"{item['name']} {item['modality']} {item['notes']} {item['equipment_note']}".lower() for item in entries.values())
    assert all(term in text for term in ("standing connection", "underhook", "head position", "level-change", "recover standing control"))
    cage_names = {name for name in EXPECTED if "Cage" in name} | {"MMA Clinch Decision Rounds"}
    assert len(cage_names) == 4
    assert all("padded wall or cage simulation" in entries[name]["equipment_note"].lower() for name in cage_names)
    assert all(term not in text for term in ("thai plum", "neck snap", "knee storm", "elbow combination", "mat return", "reshot", "ground control"))
    assert "do not finish takedowns" in text and "not takedown completion" in text


def test_equipment_tokens_and_mechanical_risk_tags_follow_bank_conventions():
    bank = _bank()
    valid_equipment = set(known_equipment)
    assert len([item["name"] for item in bank]) == len({item["name"] for item in bank})
    for item in _slice():
        assert set(item["equipment"]) <= valid_equipment
        assert {tag for tag in item["tags"] if tag.startswith("mech_")} == set(item["mechanical_risk_tags"])


def test_reactive_and_fatigue_decision_rounds_are_meaningfully_distinct():
    entries = {item["name"]: item for item in _slice()}
    reactive = entries["Reactive MMA Clinch Rounds"]
    dense = entries["MMA Clinch Decision Rounds"]
    assert (reactive["system"], reactive["work_sec"], reactive["rest_sec"], reactive["rpe"]) == ("aerobic", 120, 60, 6)
    assert (dense["system"], dense["work_sec"], dense["rest_sec"], dense["rpe"]) == ("glycolytic", 60, 45, 8)
    assert "sustainable" in reactive["notes"].lower()
    assert "higher live resistance" in dense["notes"].lower() and "under fatigue" in dense["notes"].lower()


def test_existing_selector_surfaces_mma_clinch_fighter_in_gpp_and_spp():
    # Conditioning selection now prefers the best physiological match for the
    # slot, so a style drill no longer owns a system slot by default. This test
    # covers bank *reachability* — sport, style, equipment, phase and safety
    # filtering — so it names the slice explicitly; an explicitly requested
    # exercise is a coach instruction and is never displaced on target grounds.
    flags = {
        "sport": "mma", "style_technical": ["mma"], "style_tactical": ["Clinch Fighter"],
        "key_goals": ["conditioning"], "weaknesses": ["gas_tank"], "fatigue": "low",
        "equipment": ["partner", "thai pads"], "training_frequency": 5,
        "days_available": 5, "days_until_fight": 35, "time_to_fight_days": 35,
        "injuries": [], "restrictions": [], "preferred_exercise_names": sorted(EXPECTED),
    }
    for phase in ("GPP", "SPP"):
        conditioning._style_conditioning_bank_cache = None
        result = conditioning.generate_conditioning_block({**flags, "phase": phase})
        selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
        assert set(selected) & set(EXPECTED), (phase, selected)


def test_protected_clinch_and_rebuilt_tactical_slices_are_byte_for_byte_unchanged():
    for (sport, style), expected_hash in PRESERVED_HASHES.items():
        payload = json.dumps(_slice(sport, style), sort_keys=True, separators=(",", ":")).encode()
        assert hashlib.sha256(payload).hexdigest() == expected_hash
