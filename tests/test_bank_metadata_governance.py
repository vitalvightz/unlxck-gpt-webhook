from __future__ import annotations

import pytest

from fightcamp import bank_schema, conditioning_boxing
from fightcamp.bank_metadata_governance import apply_bank_metadata


def _base_conditioning(**overrides):
    item = {
        "name": "Base Aerobic",
        "tags": ["aerobic", "conditioning", "low_impact"],
        "phases": ["GPP"],
        "system": "aerobic",
        "total_minutes": 30,
        "rpe": 5,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
    }
    item.update(overrides)
    return item


def test_traditional_zone2_gets_meaningful_governance_and_early_window():
    item = _base_conditioning(
        name="Nasal Jog",
        total_minutes=40,
        rpe=4,
        tags=["aerobic", "low_impact", "recovery"],
    )

    bank_schema.validate_training_item(
        item,
        source="conditioning_bank.json",
        require_phases=True,
        mode="runtime",
    )

    assert item["stress_class"] == "meaningful_stress"
    assert item["cost_class"] == "medium"
    assert item["support_only"] is False
    assert item["meaningful_stress"] is True
    assert item["late_windows"] == [bank_schema.D21_TO_D14]
    assert not set(item.get("_schema_issues", [])) & {
        "missing_work_sec",
        "missing_rest_sec",
        "missing_rounds",
        "missing_rpe_max",
        "missing_stress_class",
        "missing_cost_class",
        "missing_support_only",
        "missing_meaningful_stress",
    }


def test_short_recovery_ladder_is_support_only():
    item = _base_conditioning(
        name="Agility Ladder (Recovery)",
        tags=["footwork", "recovery", "mech_reactive"],
        total_minutes=10,
        rpe=4,
        late_windows=["d13_to_d8", "d7"],
    )

    bank_schema.validate_training_item(
        item,
        source="conditioning_bank.json",
        require_phases=True,
        mode="runtime",
    )

    assert item["stress_class"] == "support"
    assert item["cost_class"] == "low"
    assert item["support_only"] is True
    assert item["meaningful_stress"] is False


def test_high_intensity_missing_window_stays_fail_closed():
    item = _base_conditioning(
        name="Hard Capacity Intervals",
        tags=["conditioning", "glycolytic", "work_capacity"],
        phases=["SPP"],
        system="glycolytic",
        total_minutes=15,
        rpe=9,
        impact_cost="low",
        movement_cost="high",
        lactate_load="high",
    )

    bank_schema.validate_training_item(
        item,
        source="conditioning_bank.json",
        require_phases=True,
        mode="runtime",
    )

    assert item["support_only"] is False
    assert item["meaningful_stress"] is True
    assert item["cost_class"] == "high"
    assert "late_windows" not in item
    assert "missing_late_windows" in item.get("_schema_issues", [])
    assert item["_schema_safety"]["late_fight_eligible"] is False


def test_rpe_max_alone_satisfies_conditioning_rpe_contract():
    item = {
        "name": "Taper Rhythm Touch",
        "tags": ["cns_freshness", "recovery"],
        "phases": ["TAPER"],
        "system": "aerobic",
        "late_windows": ["d4_to_d2"],
        "rpe_max": 5,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
    }

    bank_schema.validate_training_item(
        item,
        source="style_taper_conditioning.json",
        require_phases=True,
        mode="runtime",
    )

    assert "missing_rpe" not in item.get("_schema_issues", [])
    assert "missing_rpe_max" not in item.get("_schema_issues", [])


def test_technical_footwork_bank_is_always_support_governed():
    item = {
        "name": "Technical Reset",
        "tags": ["footwork", "movement_quality", "boxing"],
        "phases": ["GPP", "SPP"],
        "system": "aerobic",
        "modality": "technical_footwork",
        "sets": 2,
        "reps_per_side": 4,
        "rest_sec": 60,
        "quality_stop_rule": "Stop when stance quality drops.",
        "rpe": 5,
        "impact_cost": "low",
        "movement_cost": "moderate",
        "lactate_load": "low",
        "late_windows": ["d21_to_d14"],
    }

    bank_schema.validate_training_item(
        item,
        source="technical_footwork_bank.json",
        require_phases=True,
        mode="runtime",
    )

    assert item["stress_class"] == "support"
    assert item["cost_class"] == "low"
    assert item["support_only"] is True
    assert item["meaningful_stress"] is False
    assert "missing_technical_footwork_dose" not in item.get("_schema_issues", [])


@pytest.mark.parametrize(
    ("item", "expected_support"),
    [
        (
            {
                "name": "Trap Bar Deadlift",
                "tags": ["strength", "posterior_chain", "hip_dominant"],
                "equipment": ["trap_bar"],
                "movement": "deadlift",
                "cns_load": "high",
            },
            False,
        ),
        (
            {
                "name": "Dead Bug Isometric",
                "tags": ["core", "isometric", "trunk_stability"],
                "equipment": [],
                "movement": "dead bug",
            },
            True,
        ),
    ],
)
def test_exercise_bank_uses_existing_strength_quality_classifier(item, expected_support):
    apply_bank_metadata(item, source="exercise_bank.json")

    assert item["support_only"] is expected_support
    assert item["meaningful_stress"] is (not expected_support)
    assert item["stress_class"] == ("support" if expected_support else "meaningful_stress")
    assert item["cost_class"] == ("low" if expected_support else "high")


def test_boxing_primary_aerobic_rank_keeps_support_behind_meaningful_work():
    common = {
        "injuries": [],
        "weaknesses": [],
        "goals": [],
        "restrictions": [],
        "equipment_access_set": set(),
    }
    meaningful = _base_conditioning(
        name="Nasal Jog",
        modality="run",
        support_only=False,
        meaningful_stress=True,
    )
    support = _base_conditioning(
        name="Agility Ladder (Recovery)",
        total_minutes=10,
        support_only=True,
        meaningful_stress=False,
    )

    meaningful_rank = conditioning_boxing._boxing_aerobic_preference_rank(meaningful, **common)
    support_rank = conditioning_boxing._boxing_aerobic_preference_rank(support, **common)

    assert meaningful_rank < support_rank
