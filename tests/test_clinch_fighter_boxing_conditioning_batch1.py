import hashlib
import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED = {
    "Inside Position Flow": ("aerobic", {"GPP", "SPP"}, ("partner",), 180, 60, 3, 5),
    "Frame-Separate-Reset Flow": ("aerobic", {"GPP", "SPP"}, ("partner",), 120, 60, 3, 5),
    "Tie-Up Position Burst": ("ATP-PCr", {"GPP", "SPP"}, ("partner",), 5, 75, 8, 8),
    "Turn-and-Separate Burst": ("ATP-PCr", {"SPP"}, ("partner",), 6, 75, 6, 8),
    "Smother-Return Burst": ("ATP-PCr", {"SPP"}, ("partner_mitts",), 7, 75, 6, 8),
    "Inside Position Intervals": ("glycolytic", {"GPP", "SPP"}, ("partner",), 25, 45, 6, 8),
    "Control-Separate-Punch Intervals": ("glycolytic", {"SPP"}, ("partner_mitts",), 35, 45, 5, 8),
    "Reactive Clinch Decision Rounds": ("aerobic", {"SPP"}, ("partner_mitts",), 120, 60, 4, 6),
}
REMOVED_FROM_BOXING = {
    "Greco-Roman Grinder", "Rope-A-Dope Clinch", "Clinch & Sprawl Reaction Complex",
    "Collar Tie Counter", "Clinch Gas Tank", "Clinch-to-Strike Transition Drill",
    "Rope Clinch Frames", "Referee Break Counters", "Overhook Uppercut Drill",
    "Corner Mauling Circuit", "Slip-Clinch Reaction",
}
PRESERVED_BOXING_SLICE_HASHES = {
    "brawler": "5babae91985da17f1fa63ef1d611b71ccba32c9d002a82a1fb5debb684d193bc",
    "pressure_fighter": "de0dfdc245d903e5830bd90133199bb9b63f163e331c02a3fe94bc6e510688dd",
    "counter_striker": "8bbdb45bfaea8e9dc4a1a6db6c8c6f1fa92fd3ea437bf7a99bb45d2742b6d93e",
    "distance_striker": "800ab4b7e1248a3a5efc289a6ba6be2dcab8aa5a993c733fcea473248bf26951",
}


def _bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice(style: str = "clinch_fighter") -> dict[str, dict]:
    return {
        item["name"]: item for item in _bank()
        if {"boxing", style}.issubset(item.get("tags", []))
    }


def test_boxing_clinch_fighter_slice_has_exact_approved_rebuild():
    entries = _slice()
    assert set(entries) == set(EXPECTED)
    assert set(_slice()).isdisjoint(REMOVED_FROM_BOXING)
    for name, (system, phases, equipment, work, rest, rounds, rpe) in EXPECTED.items():
        item = entries[name]
        assert {"boxing", "clinch_fighter"}.issubset(item["tags"])
        assert (item["system"], set(item["phases"]), tuple(item["equipment"])) == (
            system, phases, equipment,
        )
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (
            work, rest, rounds, rpe,
        )


def test_energy_system_doses_are_deliberate_and_coherent():
    entries = list(_slice().values())
    assert Counter(item["system"] for item in entries) == {
        "ATP-PCr": 3, "glycolytic": 2, "aerobic": 3,
    }
    alactic = [item for item in entries if item["system"] == "ATP-PCr"]
    assert all(4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 90 for item in alactic)
    assert all(6 <= item["rounds"] <= 8 and item["rpe"] == 8 and item["lactate_load"] == "low" for item in alactic)
    glycolytic = [item for item in entries if item["system"] == "glycolytic"]
    assert all(20 <= item["work_sec"] <= 60 and item["rest_sec"] < 2 * item["work_sec"] for item in glycolytic)
    assert all(item["rpe"] in {7, 8} and item["lactate_load"] == "high" for item in glycolytic)
    aerobic = [item for item in entries if item["system"] == "aerobic"]
    assert all(120 <= item["work_sec"] <= 180 and item["rest_sec"] == 60 for item in aerobic)
    assert all(item["rpe"] in {5, 6} and item["lactate_load"] == "low" for item in aerobic)


def test_connection_is_partner_based_and_boxing_boundaries_are_explicit():
    entries = _slice().values()
    assert all(set(item["equipment"]) & {"partner", "partner_mitts"} for item in entries)
    assert all(not ({"wrestler", "brawler", "pressure_fighter", "muay_thai"} & set(item["tags"])) for item in entries)
    notes = " ".join(item["notes"].lower() for item in entries)
    assert all(term not in notes for term in ("knee strike", "elbow strike", "thai plum", "walk the opponent down", "ring cutting"))
    assert all(any(term in item["notes"].lower() for term in ("connection", "inside", "arm", "forearm", "smother")) for item in entries)
    assert all(any(term in item["notes"].lower() for term in ("separate", "release", "legal space")) for item in entries)
    assert all(any(term in item["notes"].lower() for term in ("stance", "guard")) for item in entries)


def test_equipment_mechanical_tags_and_phase_reachability_follow_conventions():
    valid_equipment = set(known_equipment) | {"focus_mitts", "partner_mitts"}
    entries = list(_slice().values())
    for item in entries:
        assert set(item["equipment"]).issubset(valid_equipment)
        mechanical = {tag for tag in item["tags"] if tag.startswith("mech_")}
        assert set(item["mechanical_risk_tags"]) == mechanical
    for phase in ("GPP", "SPP"):
        reached = [item for item in entries if phase in item["phases"]]
        assert reached
        assert {item["system"] for item in reached} == {"ATP-PCr", "glycolytic", "aerobic"}


def test_existing_selector_does_not_promote_support_to_clinch_fulfillment():
    # Conditioning selection now prefers the best physiological match for the
    # slot, so a style drill no longer owns a system slot by default. This test
    # covers bank *reachability* — sport, style, equipment, phase and safety
    # filtering — so it names the slice explicitly; an explicitly requested
    # exercise is a coach instruction and is never displaced on target grounds.
    flags = {
        "sport": "boxing", "style_technical": ["boxing"],
        "style_tactical": ["Clinch Fighter"], "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"], "fatigue": "low",
        "equipment": ["partner", "partner_mitts", "focus_mitts"],
        "training_frequency": 5, "days_available": 5, "days_until_fight": 35,
        "time_to_fight_days": 35, "injuries": [], "restrictions": [], "preferred_exercise_names": sorted(EXPECTED),
    }
    selected_by_phase = {}
    for phase in ("GPP", "SPP"):
        result = conditioning.generate_conditioning_block({**flags, "phase": phase})
        selected_by_phase[phase] = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]

    assert not selected_by_phase["GPP"]
    assert set(selected_by_phase["SPP"]) & {
        name for name, item in _slice().items() if item["meaningful_stress"] is True
    }


def test_rebuilt_boxing_archetype_blocks_remain_byte_for_byte_equivalent():
    for style, expected_hash in PRESERVED_BOXING_SLICE_HASHES.items():
        entries = list(_slice(style).values())
        payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        assert hashlib.sha256(payload).hexdigest() == expected_hash
