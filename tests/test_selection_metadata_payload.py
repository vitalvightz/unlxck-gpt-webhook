from __future__ import annotations

from fightcamp.conditioning import _build_conditioning_candidate_reservoir
from fightcamp.selection_metadata import normalize_selection_metadata
from fightcamp.stage2_payload import (
    _build_conditioning_slots,
    _build_strength_slots,
    _serialize_strength_option,
)
from fightcamp.strength import _build_strength_candidate_reservoir
from tools.validate_banks import discover_banks


def test_missing_selection_metadata_defaults_are_conservative():
    metadata = normalize_selection_metadata({"name": "Fallback Drill"})

    assert metadata["movement_cost"] == "moderate"
    assert metadata["impact_cost"] == "moderate"
    assert metadata["eccentric_cost"] == "moderate"
    assert metadata["cns_load"] == "moderate"
    assert metadata["soreness_risk"] == "moderate"
    assert metadata["late_windows"] == []


def test_strength_serialization_includes_score_evidence_and_metadata():
    option = _serialize_strength_option(
        {
            "name": "Trap Bar Jump",
            "movement": "hinge",
            "tags": ["power"],
            "cns_load": "low",
            "low_impact": True,
        },
        "matched power goal",
        {
            "score": 8.5,
            "reason_codes": ["goal_match", "late_safe"],
            "penalties": 1,
            "restriction_hits": 0,
            "late_window_adjustment": 2,
        },
    )

    assert option["score"] == 8.5
    assert option["reason_codes"] == ["goal_match", "late_safe"]
    assert option["penalties"] == 1
    assert option["restriction_hits"] == 0
    assert option["late_window_adjustment"] == 2
    assert option["score_evidence"]["score"] == 8.5
    assert option["selection_metadata"]["cns_load"] == "low"
    assert option["selection_metadata"]["low_impact"] is True


def test_candidate_reservoirs_include_evidence_and_metadata():
    strength_reservoir = _build_strength_candidate_reservoir(
        [
            (
                {"name": "Goblet Squat", "movement": "squat", "tags": ["strength"]},
                3.25,
                {"final_score": 3.25, "reason_codes": ["phase_match"], "penalties": 0},
            )
        ]
    )
    conditioning_reservoir = _build_conditioning_candidate_reservoir(
        {"aerobic": [({"name": "Zone 2 Bike", "tags": ["aerobic"], "system": "aerobic"}, 4.0, {"final_score": 4.0})]},
        {},
        {},
        {},
    )

    strength_candidate = strength_reservoir["squat"][0]
    conditioning_candidate = conditioning_reservoir["aerobic"][0]

    assert strength_candidate["score_evidence"]["score"] == 3.25
    assert strength_candidate["score_evidence"]["reason_codes"] == ["phase_match"]
    assert strength_candidate["metadata"]["impact_cost"] == "moderate"
    assert conditioning_candidate["score_evidence"]["score"] == 4.0
    assert conditioning_candidate["metadata"]["movement_cost"] == "moderate"


def test_stage2_slots_include_score_evidence_for_selected_items_and_alternates():
    strength_slots = _build_strength_slots(
        {
            "num_sessions": 1,
            "exercises": [{"name": "Goblet Squat", "movement": "squat", "tags": ["strength"]}],
            "why_log": [
                {
                    "name": "Goblet Squat",
                    "explanation": "phase match",
                    "reasons": {"final_score": 5.0, "reason_codes": ["phase_match"]},
                }
            ],
            "candidate_reservoir": {
                "squat": [
                    {
                        "exercise": {"name": "Box Squat", "movement": "squat", "tags": ["strength"]},
                        "score": 4.5,
                        "reasons": {"final_score": 4.5, "penalties": 1},
                        "explanation": "similar pattern",
                    }
                ]
            },
        },
        "GPP",
    )
    conditioning_slots = _build_conditioning_slots(
        {
            "grouped_drills": {
                "aerobic": [{"name": "Zone 2 Bike", "tags": ["aerobic"], "system": "aerobic"}]
            },
            "why_log": [
                {
                    "name": "Zone 2 Bike",
                    "explanation": "base aerobic",
                    "reasons": {
                        "final_score": 6.0,
                        "reason_codes": ["system_quota"],
                        "late_window_adjustment": -1,
                    },
                }
            ],
            "candidate_reservoir": {
                "aerobic": [
                    {
                        "drill": {"name": "Shadowboxing Tempo", "tags": ["aerobic"], "system": "aerobic"},
                        "score": 5.5,
                        "reasons": {"final_score": 5.5, "restriction_hits": 0},
                        "explanation": "same system",
                    }
                ]
            },
        },
        "GPP",
    )

    strength_selected = strength_slots[0]["selected"]
    strength_alternate = strength_slots[0]["alternates"][0]
    conditioning_selected = conditioning_slots[0]["selected"]
    conditioning_alternate = conditioning_slots[0]["alternates"][0]

    assert strength_selected["score"] == 5.0
    assert strength_selected["reason_codes"] == ["phase_match"]
    assert strength_alternate["score"] == 4.5
    assert strength_alternate["penalties"] == 1
    assert conditioning_selected["score"] == 6.0
    assert conditioning_selected["late_window_adjustment"] == -1
    assert conditioning_alternate["score"] == 5.5
    assert "selection_metadata" in conditioning_alternate


def test_validate_bank_discovery_excludes_parser_config_files():
    discovered_names = {path.name for path in discover_banks()}

    assert "regex_patterns.json" not in discovered_names
