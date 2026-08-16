import json
from collections import Counter
from pathlib import Path

from fightcamp import conditioning
from fightcamp.training_context import known_equipment


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"

EXPECTED = {
    "Pocket Power Cluster": ("ATP-PCr", {"GPP", "SPP"}, ("heavy_bag",), 5, 75, 8, 8),
    "Cover-Return Burst": ("ATP-PCr", {"SPP"}, ("partner_mitts",), 6, 75, 8, 8),
    "Body-Head Power Burst": ("ATP-PCr", {"GPP", "SPP"}, ("focus_mitts",), 5, 75, 8, 8),
    "Exchange-Reentry Burst": ("ATP-PCr", {"SPP"}, ("partner_mitts",), 7, 75, 6, 8),
    "Pocket Combination Intervals": ("glycolytic", {"GPP", "SPP"}, ("heavy_bag",), 25, 45, 6, 8),
    "Guard-and-Answer Intervals": ("glycolytic", {"SPP"}, ("partner_mitts",), 25, 45, 6, 8),
    "Pocket Exchange Rounds": ("aerobic", {"GPP", "SPP"}, ("partner",), 180, 60, 3, 6),
    "Inside Decision Rounds": ("aerobic", {"SPP"}, ("partner_mitts",), 120, 60, 4, 6),
}

SUPERSEDED = {
    "Forward-Blast Heavy Bag Intervals", "Brawler's Body Shot Barrage",
    "Overhand Right Bursts", "Forward Lunge Strikes", "Liver Hook Bursts",
    "Swarm Entry Sprints", "Uppercut Barrage", "Brawler's Body Shot Guard",
}


def _bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice() -> dict[str, dict]:
    return {
        item["name"]: item for item in _bank()
        if {"boxing", "brawler"}.issubset(item.get("tags", []))
    }


def test_boxing_brawler_slice_has_only_the_approved_rebuild():
    entries = _slice()
    assert set(entries) == set(EXPECTED)
    assert SUPERSEDED.isdisjoint(item["name"] for item in _bank())
    for name, expected in EXPECTED.items():
        item = entries[name]
        system, phases, equipment, work, rest, rounds, rpe = expected
        assert (item["system"], set(item["phases"]), tuple(item["equipment"])) == (system, phases, equipment)
        assert (item["work_sec"], item["rest_sec"], item["rounds"], item["rpe"]) == (work, rest, rounds, rpe)
        assert {"boxing", "brawler"}.issubset(item["tags"])


def test_energy_system_doses_are_coherent():
    entries = _slice().values()
    assert Counter(item["system"] for item in entries) == {"ATP-PCr": 4, "glycolytic": 2, "aerobic": 2}
    alactic = [item for item in entries if item["system"] == "ATP-PCr"]
    assert all(4 <= item["work_sec"] <= 7 and 60 <= item["rest_sec"] <= 90 for item in alactic)
    assert all(6 <= item["rounds"] <= 8 and item["rpe"] == 8 and item["lactate_load"] == "low" for item in alactic)
    glycolytic = [item for item in entries if item["system"] == "glycolytic"]
    assert all(20 <= item["work_sec"] <= 60 and 40 <= item["rest_sec"] <= 45 for item in glycolytic)
    assert all(item["rpe"] in {7, 8} and item["lactate_load"] == "high" for item in glycolytic)
    aerobic = [item for item in entries if item["system"] == "aerobic"]
    assert all(120 <= item["work_sec"] <= 180 and item["rest_sec"] == 60 for item in aerobic)
    assert all(item["rpe"] in {5, 6} and item["intensity"] == "moderate" for item in aerobic)


def test_rebuild_is_reachable_in_gpp_and_spp_with_normal_boxing_equipment():
    entries = _slice().values()
    available = {"heavy_bag", "focus_mitts", "partner", "partner_mitts"}
    for phase in ("GPP", "SPP"):
        reached = [item for item in entries if phase in item["phases"] and set(item["equipment"]).issubset(available)]
        assert reached
        assert {item["system"] for item in reached} == {"ATP-PCr", "glycolytic", "aerobic"}


def test_existing_selector_surfaces_the_rebuilt_slice_in_gpp_and_spp():
    flags = {
        "sport": "boxing", "style_technical": ["boxing"], "style_tactical": ["Brawler"],
        "key_goals": ["conditioning"], "weaknesses": ["gas_tank"], "fatigue": "low",
        "equipment": ["heavy_bag", "focus_mitts", "partner", "partner_mitts"],
        "training_frequency": 5, "days_available": 5, "days_until_fight": 35,
        "time_to_fight_days": 35, "injuries": [], "restrictions": [],
    }
    for phase in ("GPP", "SPP"):
        result = conditioning.generate_conditioning_block({**flags, "phase": phase})
        selected = result[5]["__style_conditioning__"]["final_selected_style_conditioning_names"]
        assert set(selected) & set(EXPECTED)


def test_equipment_and_mechanical_metadata_follow_bank_conventions():
    valid_equipment = set(known_equipment) | {"focus_mitts", "partner_mitts"}
    for item in _slice().values():
        assert set(item["equipment"]).issubset(valid_equipment)
        mechanical = {tag for tag in item["tags"] if tag.startswith("mech_")}
        assert set(item["mechanical_risk_tags"]) == mechanical


def test_no_gimmick_resistance_or_pressure_fighter_behaviour_drift():
    text = " ".join(
        f"{item['name']} {item['notes']} {item['equipment_note']}".lower()
        for item in _slice().values()
    )
    banned = (
        "sprint", "band-resisted", "weighted punch", "burpee", "reaction ball", "light cue",
        "ring cut", "ring-cut", "deny exit", "denying exit", "trap the opponent", "pursuit",
        "walk down", "walking down", "forward-pressure recapture", "advance relentlessly",
    )
    assert all(term not in text for term in banned)
    assert all("pressure_fighter" not in item["tags"] for item in _slice().values())


def test_every_drill_preserves_a_specific_brawler_exchange_behaviour():
    behaviours = ("pocket", "compact", "body-head", "high guard", "short-range", "re-enter")
    for item in _slice().values():
        text = f"{item['name']} {item['notes']}".lower()
        assert any(behaviour in text for behaviour in behaviours), item["name"]


def test_boxing_brawler_names_are_unique_across_the_bank():
    names = [item["name"] for item in _bank()]
    assert len(names) == len(set(names))
