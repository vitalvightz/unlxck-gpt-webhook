from __future__ import annotations

import copy
import json
from pathlib import Path

from fightcamp import strength
from fightcamp.late_selector_windows import D4_TO_D2


def _exercise_named(name: str) -> dict:
    for item in json.loads(Path("data/exercise_bank.json").read_text(encoding="utf-8")):
        if item["name"] == name:
            return item
    raise AssertionError(f"Missing exercise bank item: {name}")


def _safe_d3_primer() -> dict:
    return {
        "name": "D3 Safe Source Primer",
        "phases": ["TAPER"],
        "method": "power",
        "movement": "horizontal_push",
        "type": "bilateral",
        "tags": [
            "d3_safe_source_primer_score",
            "late_strength_touch",
            "neural_primer",
            "speed",
            "low_impact",
            "low_eccentric",
            "cns_freshness",
        ],
        "equipment": "bands",
        "late_windows": [D4_TO_D2],
        "phase_role": "late_strength_touch",
        "impact_cost": "low",
        "eccentric_cost": "low",
        "landing_cost": "none",
        "soreness_risk": "low",
        "cns_load": "low",
        "low_impact": True,
        "low_eccentric": True,
        "cns_freshness": True,
    }


def _quality_passthrough(exercise, phase=None):
    return 0.0, strength.classify_strength_item(exercise)


def test_d3_late_window_hard_blocks_sandbag_shouldering_bank_item():
    sandbag = _exercise_named("Sandbag Shouldering")

    result = strength._evaluate_strength_late_window(
        sandbag,
        window=D4_TO_D2,
        days_until_fight=3,
        cut_bucket="none",
    )

    assert result["blocked"] is True
    assert "late_strength_block_window_mismatch" in result["block_codes"]
    assert "late_strength_block_familiarity_required_late" in result["block_codes"]


def test_d3_strength_source_selection_cannot_emit_sandbag_shouldering(monkeypatch):
    sandbag = copy.deepcopy(_exercise_named("Sandbag Shouldering"))
    safe_primer = _safe_d3_primer()
    exercise_bank = [sandbag, safe_primer]
    score_map = {
        "explosive": 99.0,
        "d3_safe_source_primer_score": 1.0,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "strength_quality_adjustment", _quality_passthrough)
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]], "reason_codes": []},
        ),
    )

    result = strength.generate_strength_block(
        flags={
            "phase": "TAPER",
            "fatigue": "low",
            "fight_format": "boxing",
            "sport": "boxing",
            "style_tactical": [],
            "style_technical": ["boxing"],
            "equipment": ["bodyweight", "bands", "sandbag"],
            "training_days": ["Wed"],
            "training_frequency": 1,
            "days_available": 1,
            "key_goals": ["power"],
            "weaknesses": [],
            "injuries": [],
            "days_until_fight": 3,
        }
    )

    selected_names = [entry["name"] for entry in result["why_log"]]
    assert selected_names == ["D3 Safe Source Primer"]
    assert "Sandbag Shouldering" not in result["block"]
    assert all(ex["name"] != "Sandbag Shouldering" for ex in result["exercises"])

    late_blocks = result["late_window_diagnostics"]["blocked"]
    sandbag_blocks = [entry for entry in late_blocks if entry["name"] == "Sandbag Shouldering"]
    assert sandbag_blocks
    assert "late_strength_block_window_mismatch" in sandbag_blocks[0]["reason_codes"]
    assert "late_strength_block_familiarity_required_late" in sandbag_blocks[0]["reason_codes"]
