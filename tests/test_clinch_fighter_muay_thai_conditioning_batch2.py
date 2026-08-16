import hashlib
import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED = {
    "Clinch Position Flow": ("aerobic", {"GPP", "SPP"}, ("partner",), 180, 60, 3, 5),
    "Posture-Control Knee Flow": ("aerobic", {"GPP", "SPP"}, ("partner", "thai_pads"), 180, 60, 3, 5),
    "Reactive Clinch Position Rounds": ("aerobic", {"SPP"}, ("partner", "thai_pads"), 120, 60, 4, 6),
    "Posture-Break Knee Burst": ("ATP-PCr", {"GPP", "SPP"}, ("partner", "thai_pads"), 6, 75, 8, 8),
    "Turn-and-Knee Burst": ("ATP-PCr", {"SPP"}, ("partner", "thai_pads"), 6, 75, 6, 8),
    "Frame-Reconnect Burst": ("ATP-PCr", {"GPP", "SPP"}, ("partner",), 5, 75, 8, 8),
    "Clinch Reposition Intervals": ("glycolytic", {"GPP", "SPP"}, ("partner",), 30, 45, 6, 8),
    "Knee-and-Recover Intervals": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 35, 45, 6, 8),
    "Grip-Fight-to-Score Intervals": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 30, 45, 6, 8),
    "Clinch Decision Rounds": ("glycolytic", {"SPP"}, ("partner", "thai_pads"), 60, 45, 5, 8),
}
LEGACY = {
    "Clinch Hold & Knee Complex", "Max Knee & Sprawl Complex", "Wall Pressure & Elbow Complex",
    "Dutch Clinch Drill", "Elbow Alley", "Clinch Gas Tank", "Clinch Finisher",
    "Clinch Knee Storm Intervals", "Clinch-to-Strike Transition Drill", "Thai Plum Explosion Drill",
    "Neck Snap Drill", "Knee Strike Bursts", "Dump Explosions", "Strike-to-Clinch Drill",
    "Hip Slam Drill", "Corner Knee Bursts", "Clinch Marching Rounds",
    "Clinch Fighter's Neck Endurance", "Clinch Fighter's Frame Endurance",
}
PRESERVED_HASHES = {
    ("boxing", "clinch_fighter"): "e5dab2bd52fedd4eb7ff47206c92fc7114162b3db382b3fe60a3b8c47d5f8daa",
    ("muay_thai", "brawler"): "0de248a0ea8e4b420e1bb71d2809017d0e61abcf2ef4b1091505c0fd8f0cfcec",
    ("muay_thai", "pressure_fighter"): "78d027c8185c83f4c5516fb5faddb9f0d70a7aaede9e308b904e18ace56f35b3",
    ("muay_thai", "counter_striker"): "d0c679f5df1ca69d68dbdc58cd44f57b984de79c3ed373a1a44fda18a1713828",
    ("muay_thai", "distance_striker"): "c16b1172f6d123ccceaa3c8612fcd30f3d093a96c8433337e1b4c6423a281cb1",
}


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice(sport="muay_thai", style="clinch_fighter"):
    return [item for item in _bank() if {sport, style} <= set(item.get("tags", []))]


def test_slice_has_exact_approved_names_and_doses():
    entries = {item["name"]: item for item in _slice()}
    assert set(entries) == set(EXPECTED)
    assert set(entries).isdisjoint(LEGACY)
    for name, (system, phases, equipment, work, rest, rounds, rpe) in EXPECTED.items():
        item = entries[name]
        assert {"clinch_fighter", "muay_thai"} <= set(item["tags"])
        assert (item["system"], set(item["phases"]), tuple(item["equipment"])) == (system, phases, equipment)
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (work, rest, rounds, rpe)


def test_energy_system_doses_are_coherent():
    entries = _slice()
    assert Counter(item["system"] for item in entries) == {"ATP-PCr": 3, "glycolytic": 4, "aerobic": 3}
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


def test_positional_resistance_and_archetype_boundaries_are_explicit():
    entries = _slice()
    assert all("partner" in item["equipment"] for item in entries)
    assert all(not ({"brawler", "pressure_fighter", "wrestler", "boxing", "mma"} & set(item["tags"])) for item in entries)
    text = " ".join(item["notes"].lower() for item in entries)
    banned = ("sprawl", "takedown", "double leg", "single leg", "chain wrestling", "mat return", "hip throw",
              "yank", "snap neck", "neck crank", "slam", "non-stop knee", "knee storm", "knee barrage")
    assert all(term not in text for term in banned)
    assert all("resist" in (item["notes"] + " " + item["equipment_note"]).lower() for item in entries)
    knee_entries = [item for item in entries if "knee" in item["notes"].lower()]
    assert all("controlled knee" in item["notes"].lower() and "thai_pads" in item["equipment"] for item in knee_entries)
    assert all(any(word in item["notes"].lower() for word in ("position", "posture", "control", "reconnect")) for item in entries)


def test_decision_rounds_are_distinct_and_knee_exposure_is_consistent():
    entries = {item["name"]: item for item in _slice()}
    reactive = entries["Reactive Clinch Position Rounds"]
    dense = entries["Clinch Decision Rounds"]
    assert (reactive["system"], reactive["work_sec"], reactive["rest_sec"], reactive["rpe"]) == ("aerobic", 120, 60, 6)
    assert (dense["system"], dense["work_sec"], dense["rest_sec"], dense["rounds"], dense["rpe"]) == ("glycolytic", 60, 45, 5, 8)
    assert "increases positional resistance" in dense["notes"].lower()
    assert "maintain decision quality" in dense["notes"].lower()

    knee_entries = [item for item in entries.values() if "controlled knee" in item["notes"].lower()]
    assert knee_entries
    assert all("mech_lower_hip_hinge" in item["tags"] for item in knee_entries)
    assert all("mech_lower_hip_hinge" in item["mechanical_risk_tags"] for item in knee_entries)


def test_partner_only_equipment_notes_do_not_refer_to_unlisted_pads():
    partner_only = [item for item in _slice() if item["equipment"] == ["partner"]]
    assert partner_only
    assert all("thai pad" not in item["equipment_note"].lower() for item in partner_only)


def test_phase_equipment_and_mechanical_metadata_follow_conventions():
    entries = _slice()
    valid_equipment = set(known_equipment)
    for item in entries:
        assert set(item["equipment"]) <= valid_equipment
        assert {tag for tag in item["tags"] if tag.startswith("mech_")} == set(item["mechanical_risk_tags"])
    for phase in ("GPP", "SPP"):
        reached = [item for item in entries if phase in item["phases"]]
        assert reached and {item["system"] for item in reached} == {"ATP-PCr", "glycolytic", "aerobic"}


def test_existing_selector_surfaces_slice_in_gpp_and_spp():
    flags = {
        "sport": "muay_thai", "style_technical": ["muay thai"],
        "style_tactical": ["Clinch Fighter"], "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"], "fatigue": "low", "equipment": ["partner", "thai_pads"],
        "training_frequency": 5, "days_available": 5, "days_until_fight": 35,
        "time_to_fight_days": 35, "injuries": [], "restrictions": [],
    }
    expected = set(EXPECTED)
    for phase in ("GPP", "SPP"):
        conditioning._style_conditioning_bank_cache = None
        result = conditioning.generate_conditioning_block({**flags, "phase": phase})
        selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
        assert set(selected) & expected


def test_boxing_clinch_and_other_rebuilt_muay_thai_styles_are_protected():
    for (sport, style), expected_hash in PRESERVED_HASHES.items():
        payload = json.dumps(_slice(sport, style), sort_keys=True, separators=(",", ":")).encode()
        assert hashlib.sha256(payload).hexdigest() == expected_hash
