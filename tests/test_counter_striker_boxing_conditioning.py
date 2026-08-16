import json
from collections import Counter
from pathlib import Path


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_conditioning_bank.json"
EXPECTED_DOSES = {
    "Read & Counter Flow": ("aerobic", 180, 60, 3, 5),
    "Counter Shadow Flow": ("aerobic", 180, 60, 3, 5),
    "Defensive Position Flow": ("aerobic", 120, 60, 3, 6),
    "Slip-Cross Burst": ("ATP-PCr", 5, 60, 8, 8),
    "Pull-Straight Burst": ("ATP-PCr", 5, 75, 6, 8),
    "Check-Hook Pivot Burst": ("ATP-PCr", 6, 75, 6, 8),
    "Intercepting Straight Burst": ("ATP-PCr", 4, 60, 8, 8),
    "Reactive Counter Choice": ("ATP-PCr", 7, 75, 6, 8),
    "Parry-Return Intervals": ("glycolytic", 45, 30, 6, 7),
    "Defend-Counter-Exit Intervals": ("glycolytic", 60, 45, 5, 8),
    "Random Attack Counter Rounds": ("glycolytic", 120, 60, 4, 8),
    "Counter Quality Rounds": ("glycolytic", 180, 60, 3, 8),
}
EXPECTED_PHASES = {
    "Read & Counter Flow": {"GPP", "SPP"},
    "Counter Shadow Flow": {"GPP", "SPP"},
    "Defensive Position Flow": {"GPP", "SPP"},
    "Slip-Cross Burst": {"GPP", "SPP"},
    "Pull-Straight Burst": {"GPP", "SPP"},
    "Intercepting Straight Burst": {"GPP", "SPP"},
    "Check-Hook Pivot Burst": {"SPP"},
    "Reactive Counter Choice": {"SPP"},
    "Parry-Return Intervals": {"SPP"},
    "Defend-Counter-Exit Intervals": {"SPP"},
    "Random Attack Counter Rounds": {"SPP"},
    "Counter Quality Rounds": {"SPP"},
}
REMOVED_LEGACY = {
    "Pull Counter Matrix",
    "Sniper's Timing",
    "Counter Striker's Shell Defense Drill",
    "Pull-Counter Springs",
    "Counter Striker's Retreat Drill",
    "Counter Striker's Parry Drill",
    "Tempo Shadowboxing (Slow Reps)",
}
PRESERVED_OTHER_SLICES = {
    "Intercept & Counter Mitts",
    "Slip-Counter Springs",
    "Long-Distance Shadowboxing",
    "Shadow Flow Rounds",
}


def _bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _boxing_counter_slice() -> dict[str, dict]:
    return {
        item["name"]: item
        for item in _bank()
        if {"boxing", "counter_striker"}.issubset(item.get("tags", []))
    }


def test_boxing_counter_striker_slice_is_compact_and_deliberately_dosed():
    entries = _boxing_counter_slice()
    assert set(entries) == set(EXPECTED_DOSES)
    assert Counter(dose[0] for dose in EXPECTED_DOSES.values()) == {
        "aerobic": 3,
        "ATP-PCr": 5,
        "glycolytic": 4,
    }
    for name, expected in EXPECTED_DOSES.items():
        item = entries[name]
        assert (
            item["system"], item["work_sec"], item["rest_sec"],
            item["rounds"], item["rpe"],
        ) == expected
        assert set(item["mechanical_risk_tags"]).issubset(item["tags"])


def test_energy_systems_follow_counter_striker_dose_rules():
    entries = _boxing_counter_slice().values()
    aerobic = [item for item in entries if item["system"] == "aerobic"]
    assert all(
        120 <= item["work_sec"] <= 180
        and item["rest_sec"] == 60
        and 5 <= item["rpe"] <= 6
        and item["lactate_load"] == "low"
        for item in aerobic
    )
    alactic = [item for item in entries if item["system"] == "ATP-PCr"]
    assert all(
        3 <= item["work_sec"] <= 7
        and 60 <= item["rest_sec"] <= 75
        and 6 <= item["rounds"] <= 8
        and item["rpe"] == 8
        and item["lactate_load"] == "low"
        for item in alactic
    )
    glycolytic = [item for item in entries if item["system"] == "glycolytic"]
    assert all(
        45 <= item["work_sec"] <= 180
        and 30 <= item["rest_sec"] <= 60
        and 7 <= item["rpe"] <= 8
        and item["lactate_load"] == "high"
        for item in glycolytic
    )


def test_slice_has_deliberate_gpp_and_spp_phase_coverage():
    entries = _boxing_counter_slice()
    assert set(entries) == set(EXPECTED_PHASES)
    for name, phases in EXPECTED_PHASES.items():
        assert set(entries[name]["phases"]) == phases

    gpp_entries = [item for item in entries.values() if "GPP" in item["phases"]]
    assert len(gpp_entries) == 6
    assert Counter(item["system"] for item in gpp_entries) == {
        "aerobic": 3,
        "ATP-PCr": 3,
    }
    assert all("SPP" in item["phases"] for item in entries.values())


def test_solo_imagined_cues_are_not_tagged_as_external_reactivity():
    shadow_flow = _boxing_counter_slice()["Counter Shadow Flow"]
    assert "mech_reactive" not in shadow_flow["tags"]
    assert "mech_reactive" not in shadow_flow["mechanical_risk_tags"]


def test_every_drill_has_an_attack_cue_counter_and_reset_or_exit():
    for item in _boxing_counter_slice().values():
        notes = item["notes"].lower()
        assert any(cue in notes for cue in ("cue", "attacks", "feeds")), item["name"]
        assert any(response in notes for response in ("counter", "return", "stop-hit")), item["name"]
        assert any(finish in notes for finish in ("reset", "reposition", "regain", "recover", "exit")), item["name"]


def test_legacy_overlap_is_removed_without_deleting_other_rebuilt_slices():
    by_name = {item["name"]: item for item in _bank()}
    assert REMOVED_LEGACY.isdisjoint(by_name)
    assert PRESERVED_OTHER_SLICES.issubset(by_name)
    for name in PRESERVED_OTHER_SLICES:
        assert not {"boxing", "counter_striker"}.issubset(by_name[name]["tags"])


def test_slice_uses_realistic_accessible_equipment_only():
    entries = _boxing_counter_slice().values()
    approved = {"bodyweight", "partner", "focus_mitts", "partner_mitts"}
    assert all(set(item["equipment"]).issubset(approved) for item in entries)
    assert any(item["equipment"] == ["bodyweight"] for item in entries)
    assert any(set(item["equipment"]) & {"partner", "focus_mitts", "partner_mitts"} for item in entries)
