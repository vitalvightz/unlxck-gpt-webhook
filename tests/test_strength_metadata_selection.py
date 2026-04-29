from __future__ import annotations

import json
from pathlib import Path

from fightcamp import strength
from fightcamp.late_selector_windows import D4_TO_D2, D7


def _flags(**overrides) -> dict:
    base = {
        "phase": "TAPER",
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "equipment": ["bodyweight", "bands"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": ["power"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": 3,
    }
    return {**base, **overrides}


def _selected_names(result: dict) -> list[str]:
    return [entry["name"] for entry in result["why_log"]]


def _quality_passthrough(exercise, phase=None):
    return 0.0, strength.classify_strength_item(exercise)


def _patch_minimal_strength_runtime(monkeypatch, exercise_bank: list[dict], score_map: dict[str, float]) -> None:
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
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


def test_late_strength_selection_prefers_explicit_low_cost_metadata(monkeypatch):
    exercise_bank = [
        {
            "name": "Dense Jump Primer",
            "phases": ["TAPER"],
            "method": "power",
            "movement": "lunge",
            "type": "unilateral",
            "tags": ["dense_jump", "explosive", "mech_landing_impact", "mech_lower_lunge"],
            "equipment": "bodyweight",
            "impact_cost": "high",
            "eccentric_cost": "high",
            "landing_cost": "high",
            "soreness_risk": "high",
            "cns_load": "high",
        },
        {
            "name": "Band Snap-Down Primer",
            "phases": ["TAPER"],
            "method": "power",
            "movement": "core",
            "type": "bilateral",
            "tags": ["band_snap", "explosive", "speed", "mech_ballistic"],
            "equipment": "bands",
            "late_windows": [D4_TO_D2],
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "none",
            "soreness_risk": "low",
            "cns_load": "low",
            "low_impact": True,
            "low_eccentric": True,
            "cns_freshness": True,
        },
    ]
    _patch_minimal_strength_runtime(monkeypatch, exercise_bank, {"dense_jump": 10.0, "band_snap": 9.5})

    result = strength.generate_strength_block(flags=_flags())

    assert _selected_names(result) == ["Band Snap-Down Primer"]
    selected_reasons = result["why_log"][0]["reasons"]["reason_codes"]
    assert "late_strength_boost_low_soreness" in selected_reasons
    assert "late_strength_boost_low_impact" in selected_reasons
    assert "late_strength_boost_low_eccentric" in selected_reasons


def test_active_weight_cut_blocks_explicitly_incompatible_strength_item():
    result = strength._evaluate_strength_late_window(
        {
            "name": "Heavy Trap Bar Cluster",
            "phases": ["TAPER"],
            "movement": "hinge",
            "tags": ["mech_lower_hip_hinge", "mech_cns_high"],
            "equipment": "trap_bar",
            "cut_buckets_allowed": ["none", "low"],
            "impact_cost": "low",
            "eccentric_cost": "high",
            "landing_cost": "none",
            "soreness_risk": "high",
            "cns_load": "high",
        },
        window=D7,
        cut_bucket="high",
    )

    assert result["blocked"] is True
    assert "late_strength_block_cut_bucket_mismatch" in result["block_codes"]
    assert "late_strength_penalty_cut_pressure_high_cost_metadata" in result["reason_codes"]


def test_high_fatigue_athlete_avoids_high_cns_load(monkeypatch):
    exercise_bank = [
        {
            "name": "High CNS Med-Ball Blast",
            "phases": ["SPP"],
            "method": "power",
            "movement": "core",
            "type": "bilateral",
            "tags": ["high_cns", "explosive", "mech_ballistic", "mech_cns_high"],
            "equipment": "bodyweight",
            "cns_load": "high",
            "soreness_risk": "low",
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "none",
        },
        {
            "name": "Low CNS Pallof Hold",
            "phases": ["SPP"],
            "method": "strength",
            "movement": "core",
            "type": "isometric",
            "tags": ["low_cns", "isometric", "anti_rotation", "mech_trunk_stability"],
            "equipment": "bands",
            "cns_load": "low",
            "soreness_risk": "low",
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "none",
        },
    ]
    _patch_minimal_strength_runtime(monkeypatch, exercise_bank, {"high_cns": 10.0, "low_cns": 9.8})

    result = strength.generate_strength_block(flags=_flags(phase="SPP", fatigue="high", days_until_fight=21))

    assert _selected_names(result) == ["Low CNS Pallof Hold"]
    blocked_reasons = result["candidate_reservoir"]["core"][1]["score_evidence"]["reason_codes"]
    assert "strength_penalty_high_fatigue_high_cns_load" in blocked_reasons


def test_explicit_low_impact_metadata_overrides_landing_tag_heuristic():
    result = strength._evaluate_strength_late_window(
        {
            "name": "Low-Amplitude Ankle Pop",
            "phases": ["TAPER"],
            "movement": "core",
            "tags": ["explosive", "mech_landing_impact"],
            "equipment": "bodyweight",
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "low",
            "soreness_risk": "low",
            "cns_load": "low",
            "low_impact": True,
            "low_eccentric": True,
        },
        window=D4_TO_D2,
        cut_bucket="none",
    )

    assert result["blocked"] is False
    assert "late_strength_block_trap_bar_jump" not in result["block_codes"]
    assert "late_strength_boost_low_impact" in result["reason_codes"]


def test_strength_bank_duplicate_names_are_resolved():
    items = json.loads(Path("data/exercise_bank.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for item in items:
        key = item["name"].strip().casefold()
        counts[key] = counts.get(key, 0) + 1

    assert {name: count for name, count in counts.items() if count > 1} == {}
