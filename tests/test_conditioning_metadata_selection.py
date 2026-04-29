from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.late_selector_windows import D4_TO_D2
from fightcamp.stage2_payload import build_stage2_payload
from fightcamp.training_context import TrainingContext


def test_late_taper_blocks_dense_glycolytic_from_structured_metadata():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Neutral Tempo Blend",
            "system": "glycolytic",
            "tags": ["conditioning"],
            "work_sec": 75,
            "rest_sec": 45,
            "rounds": 5,
            "rpe": 8,
            "lactate_load": "high",
            "impact_cost": "low",
            "movement_cost": "high",
        },
        system="glycolytic",
        window=D4_TO_D2,
        bridge_rules={"glycolytic_touch_max": 1},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_structured_glycolytic_density" in result["block_codes"]
    assert "late_conditioning_penalty_high_lactate_metadata" in result["reason_codes"]


def test_athlete_facing_label_uses_structured_dose_before_text_parsing():
    label = conditioning.athlete_facing_system_label(
        {
            "name": "Plain Tempo Blend",
            "system": "glycolytic",
            "tags": [],
            "work_sec": 60,
            "rest_sec": 45,
            "rounds": 4,
            "lactate_load": "high",
        },
        late_window=None,
    )
    late_label = conditioning.athlete_facing_system_label(
        {
            "name": "Plain Tempo Blend",
            "system": "glycolytic",
            "tags": [],
            "work_sec": 60,
            "rest_sec": 45,
            "rounds": 4,
            "lactate_load": "high",
        },
        late_window=D4_TO_D2,
    )

    assert label == "glycolytic"
    assert late_label == "coordination conditioning"


def test_injury_restriction_filter_still_removes_unsafe_conditioning_option(monkeypatch):
    unsafe = {
        "name": "Jump Shuttle",
        "phases": ["SPP"],
        "system": "alactic",
        "tags": ["explosive", "high_impact", "mech_landing_impact"],
        "equipment": [],
        "work_sec": 8,
        "rest_sec": 90,
        "rounds": 4,
        "impact_cost": "high",
        "lactate_load": "low",
        "movement_cost": "moderate",
    }
    safe = {
        "name": "Bike Sprint",
        "phases": ["SPP"],
        "system": "alactic",
        "tags": ["explosive", "low_impact"],
        "equipment": ["assault_bike"],
        "work_sec": 8,
        "rest_sec": 90,
        "rounds": 4,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
    }
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [unsafe, safe])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: {"boxing": {"SPP": {"alactic": 1.0}}})
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 1})

    _text, names, _why, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        {
            "phase": "SPP",
            "fatigue": "low",
            "sport": "boxing",
            "fight_format": "boxing",
            "style_tactical": [],
            "style_technical": ["boxing"],
            "equipment": ["assault_bike"],
            "training_days": ["Mon"],
            "training_frequency": 1,
            "days_available": 1,
            "key_goals": ["conditioning"],
            "weaknesses": [],
            "injuries": [],
            "restrictions": [{"restriction": "high_impact", "strength": "avoid"}],
            "days_until_fight": 28,
        }
    )

    assert "Jump Shuttle" not in names
    assert all(
        drill.get("name") != "Jump Shuttle"
        for drills in grouped.values()
        for drill in drills
    )


def test_stage1_to_stage2_payload_carries_conditioning_metadata_scores_and_omissions():
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=3,
        days_available=3,
        training_days=["Mon", "Wed", "Fri"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure"],
        weaknesses=["cardio"],
        equipment=["bodyweight"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["conditioning"],
        training_preference="short sessions",
        mental_block=[],
        age=26,
        weight=155.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 1, "SPP": 0, "TAPER": 0, "days": {"GPP": 7}},
        days_until_fight=35,
    )
    selected = {
        "name": "Tempo Shadowboxing",
        "system": "aerobic",
        "tags": ["aerobic", "low_impact"],
        "work_sec": 120,
        "rest_sec": 60,
        "rounds": 3,
        "total_minutes": 8,
        "rpe": 5,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
    }
    alternate = {
        "name": "Bike Flush",
        "system": "aerobic",
        "tags": ["aerobic", "low_impact"],
        "total_minutes": 12,
        "rpe": 4,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
    }
    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="5-0",
        rounds_format="3x3",
        camp_len=6,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 1, "days": {"GPP": 7}},
        strength_blocks={"GPP": None},
        conditioning_blocks={
            "GPP": {
                "grouped_drills": {"aerobic": [selected]},
                "why_log": [
                    {
                        "name": "Tempo Shadowboxing",
                        "system": "aerobic",
                        "explanation": "base aerobic rhythm",
                        "reasons": {"final_score": 4.2, "reason_codes": ["system_quota"]},
                    }
                ],
                "candidate_reservoir": {
                    "aerobic": [
                        {
                            "drill": alternate,
                            "score": 3.8,
                            "reasons": {"final_score": 3.8, "reason_codes": ["alternate"]},
                            "explanation": "same system alternate",
                        }
                    ]
                },
                "missing_systems": ["glycolytic"],
            }
        },
        rehab_blocks={},
    )

    slot = payload["candidate_pools"]["GPP"]["conditioning_slots"][0]

    assert slot["selected"]["score"] == 4.2
    assert slot["selected"]["selection_metadata"]["lactate_load"] == "low"
    assert slot["selected"]["selection_metadata"]["work_sec"] == 120
    assert slot["selected"]["prescribed_dose"]["status"] != "blocked"
    assert slot["selected"]["prescribed_dose"]["display"]
    assert slot["alternates"][0]["score"] == 3.8
    assert slot["alternates"][0]["selection_metadata"]["total_minutes"] == 12
    assert slot["alternates"][0]["prescribed_dose"]["status"] != "blocked"
    assert payload["omission_ledger"]["GPP"]["conditioning"][0]["reason"] == "missing_system"


def test_coordination_bank_duplicate_names_are_resolved():
    data = json.loads(Path("data/coordination_bank.json").read_text(encoding="utf-8"))
    items = [item for values in data.values() if isinstance(values, list) for item in values]
    counts: dict[str, int] = {}
    for item in items:
        key = item["name"].strip().casefold()
        counts[key] = counts.get(key, 0) + 1

    assert {name: count for name, count in counts.items() if count > 1} == {}
