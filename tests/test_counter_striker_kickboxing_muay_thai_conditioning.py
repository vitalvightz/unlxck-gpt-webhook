import json
from collections import Counter
from pathlib import Path


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED_DOSES = {
    "Counter Kick Matrix": ("aerobic", 180, 60, 3, 5),
    "Teep Intercept Flow": ("aerobic", 150, 60, 3, 5),
    "Kick Defence Reset Flow": ("aerobic", 120, 60, 3, 6),
    "Check-Return Kick Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Pull-Kick Counter Burst": ("ATP-PCr", 6, 75, 6, 8),
    "Intercept & Counter Mitts": ("ATP-PCr", 7, 60, 8, 8),
    "Reactive Counter Choice — Kickboxing": ("ATP-PCr", 7, 75, 6, 8),
    "Check-Return Intervals — Kickboxing": ("glycolytic", 45, 30, 6, 7),
    "Defend-Counter-Reposition Intervals — Kickboxing": ("glycolytic", 60, 45, 5, 8),
    "Random Attack Counter Rounds — Kickboxing": ("glycolytic", 120, 60, 4, 8),
    "Counter Knee Matrix": ("glycolytic", 90, 45, 4, 8),
}
AUDIT = {
    "Counter Kick Matrix": "MODIFY",
    "Intercept & Counter Mitts": "MODIFY",
    "Counter Knee Matrix": "MODIFY",
    "Counter Sniper Drill": "REPLACE",
    "Kick Defense March": "REMOVE",
}
REPLACEMENTS = {
    "Counter Sniper Drill": "Reactive Counter Choice — Kickboxing",
}


def _bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _slice() -> dict[str, dict]:
    return {
        item["name"]: item
        for item in _bank()
        if "counter_striker" in item.get("tags", [])
        and {"kickboxing", "muay_thai"} & set(item.get("tags", []))
    }


def test_surviving_slice_is_compact_and_deliberately_dosed():
    entries = _slice()
    assert set(entries) == set(EXPECTED_DOSES)
    assert Counter(item["system"] for item in entries.values()) == {
        "aerobic": 3,
        "ATP-PCr": 4,
        "glycolytic": 4,
    }
    for name, dose in EXPECTED_DOSES.items():
        item = entries[name]
        assert (
            item["system"], item["work_sec"], item["rest_sec"],
            item["rounds"], item["rpe"],
        ) == dose
        assert set(item["mechanical_risk_tags"]).issubset(item["tags"])


def test_every_original_survivor_has_an_explicit_audit_outcome():
    active_names = {item["name"] for item in _bank()}
    assert set(AUDIT) == {
        "Counter Sniper Drill", "Counter Kick Matrix", "Intercept & Counter Mitts",
        "Counter Knee Matrix", "Kick Defense March",
    }
    assert {name for name, result in AUDIT.items() if result == "MODIFY"} <= active_names
    assert {name for name, result in AUDIT.items() if result in {"REPLACE", "REMOVE"}}.isdisjoint(active_names)
    assert set(REPLACEMENTS.values()) <= active_names


def test_doses_match_each_energy_system_and_phase_coverage_is_meaningful():
    entries = list(_slice().values())
    aerobic = [item for item in entries if item["system"] == "aerobic"]
    assert all(120 <= x["work_sec"] <= 180 and x["rest_sec"] == 60 and 5 <= x["rpe"] <= 6 and x["lactate_load"] == "low" for x in aerobic)
    alactic = [item for item in entries if item["system"] == "ATP-PCr"]
    assert all(3 <= x["work_sec"] <= 7 and 60 <= x["rest_sec"] <= 75 and 6 <= x["rounds"] <= 8 and x["rpe"] == 8 and x["lactate_load"] == "low" for x in alactic)
    glycolytic = [item for item in entries if item["system"] == "glycolytic"]
    assert all(45 <= x["work_sec"] <= 180 and 30 <= x["rest_sec"] <= 60 and 7 <= x["rpe"] <= 8 and x["lactate_load"] == "high" for x in glycolytic)
    gpp = [item for item in entries if "GPP" in item["phases"]]
    assert Counter(item["system"] for item in gpp) == {"aerobic": 3, "ATP-PCr": 3}
    assert all("SPP" in item["phases"] for item in entries)


def test_drills_are_opponent_led_and_finish_with_recovered_defence():
    for item in _slice().values():
        notes = item["notes"].lower()
        assert any(word in notes for word in ("cue", "feeds")), item["name"]
        assert any(word in notes for word in ("read", "perceive")), item["name"]
        assert any(word in notes for word in ("defend", "check", "parry", "pull", "intercept", "cover", "frame", "evade")), item["name"]
        assert any(word in notes for word in ("counter", "return", "teep")), item["name"]
        assert "recover stance" in notes, item["name"]


def test_slice_has_kickboxing_and_muay_thai_depth_without_clinch_drift():
    entries = _slice()
    assert all("counter_striker" in item["tags"] for item in entries.values())
    assert all({"kickboxing", "muay_thai"} & set(item["tags"]) for item in entries.values())
    assert sum("muay_thai" in item["tags"] for item in entries.values()) >= 4
    knee = entries["Counter Knee Matrix"]
    assert "muay_thai" in knee["tags"] and "kickboxing" not in knee["tags"]
    assert "prolonged clinch" in knee["notes"].lower()


def test_equipment_requires_a_real_cue_source_and_uses_supported_tokens():
    approved = {"partner", "thai_pads", "focus_mitts"}
    for item in _slice().values():
        assert set(item["equipment"]) <= approved
        assert "partner" in item["equipment"], f'{item["name"]} has no opponent cue source'
