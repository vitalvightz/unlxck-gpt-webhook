from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp import conditioning
from fightcamp.style_taper_governance import (
    D7,
    D6_TO_D5,
    D4_TO_D2,
    D1,
    style_taper_window_for_days,
)


BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_taper_conditioning.json"


def _load_bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _base_flags(**overrides) -> dict:
    flags = {
        "phase": "TAPER",
        "fatigue": "low",
        "sport": "boxing",
        "fight_format": "boxing",
        "style_tactical": ["counter_striker"],
        "style_technical": ["boxing"],
        "key_goals": [],
        "weaknesses": [],
        "injuries": [],
        "restrictions": [],
        "equipment": ["bodyweight", "mat", "partner", "focus_mitts", "thai_pad"],
        "training_frequency": 1,
        "days_available": 1,
        "days_until_fight": 4,
    }
    flags.update(overrides)
    return flags


def _patch_to_isolate_style_taper(monkeypatch) -> None:
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(
        conditioning,
        "allocate_sessions",
        lambda *_args, **_kwargs: {"strength": 0, "conditioning": 1, "recovery": 0},
    )
    monkeypatch.setattr(
        conditioning,
        "calculate_exercise_numbers",
        lambda *_args, **_kwargs: {"strength": 0, "conditioning": 1},
    )


def test_style_taper_runtime_loader_rejects_specialized_governance_violation(tmp_path):
    invalid = {
        "name": "Unsafe D1 primer",
        "description": "Probe",
        "equipment": ["bodyweight"],
        "phases": ["TAPER"],
        "system": "alactic",
        "modality": "probe",
        "duration": "2x4s with 120s rest",
        "intensity": "technical crisp",
        "tags": ["boxing", "counter_striker", "sharpness"],
        "work_sec": 4,
        "rest_sec": 120,
        "rounds": 2,
        "total_minutes": 3.0,
        "rpe_max": 8,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "execution_intent": "technical_crisp",
        "contact_level": "none",
        "late_windows": [D1],
    }
    path = tmp_path / "style_taper_conditioning.json"
    path.write_text(json.dumps([invalid]), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsafe style taper entry"):
        conditioning._load_bank(
            path,
            source="style_taper_conditioning.json",
            enforce_conditioning_systems=True,
        )


def test_style_taper_fallback_never_crosses_sport_boundary():
    bank = _load_bank()
    filtered = conditioning._filter_style_taper_bank_for_context(
        bank,
        sport="boxing",
        styles={"submission_hunter"},
    )

    assert filtered
    assert all("boxing" in set(item.get("tags", [])) for item in filtered)
    assert not any("submission_hunter" in set(item.get("tags", [])) for item in filtered)


@pytest.mark.parametrize(
    ("sport", "technical", "style", "days_until_fight", "expected_window", "equipment"),
    [
        ("boxing", "boxing", "counter_striker", 4, D4_TO_D2, ["bodyweight"]),
        ("mma", "mma", "scrambler", 3, D4_TO_D2, ["bodyweight", "mat"]),
        ("bjj", "bjj", "submission_hunter", 1, D1, ["bodyweight", "mat"]),
        ("wrestling", "wrestling", "wrestler", 5, D6_TO_D5, ["bodyweight", "mat", "partner"]),
        ("muay_thai", "muay_thai", "clinch_fighter", 7, D7, ["bodyweight", "partner"]),
    ],
)
def test_generated_taper_plan_preserves_sport_style_and_day_window(
    monkeypatch,
    sport,
    technical,
    style,
    days_until_fight,
    expected_window,
    equipment,
):
    _patch_to_isolate_style_taper(monkeypatch)
    bank_by_name = {item["name"]: item for item in _load_bank()}

    _output, _names, _why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(
            sport=sport,
            fight_format=sport,
            style_technical=[technical],
            style_tactical=[style],
            days_until_fight=days_until_fight,
            equipment=equipment,
        )
    )

    selected = [
        drill
        for drills in grouped.values()
        for drill in drills
        if drill.get("name") in bank_by_name
    ]
    assert selected, f"Expected a Style Taper drill for {sport}/{style} at D-{days_until_fight}"

    for drill in selected:
        source = bank_by_name[drill["name"]]
        tags = set(source.get("tags", []))
        assert sport in tags
        assert style in tags
        assert expected_window in source.get("late_windows", [])
        assert style_taper_window_for_days(days_until_fight) == expected_window


def test_style_taper_is_withheld_when_sport_cannot_be_resolved(monkeypatch):
    _patch_to_isolate_style_taper(monkeypatch)
    bank_names = {item["name"] for item in _load_bank()}

    _output, _names, _why_log, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _base_flags(
            sport="",
            fight_format="",
            style_technical=[],
            style_tactical=["counter_striker"],
            days_until_fight=4,
            equipment=["bodyweight"],
        )
    )

    selected_names = {
        drill.get("name")
        for drills in grouped.values()
        for drill in drills
        if drill.get("name")
    }
    assert selected_names.isdisjoint(bank_names)
