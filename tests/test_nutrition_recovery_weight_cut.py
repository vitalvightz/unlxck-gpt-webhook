from __future__ import annotations

from fightcamp import recovery
from fightcamp.nutrition import _is_high_pressure_weight_cut as nutrition_high_pressure_cut
from fightcamp.nutrition import generate_nutrition_block
from fightcamp.recovery import generate_recovery_block
from fightcamp.weight_cut import compute_weight_cut_pct, parse_weight_value


def test_nutrition_high_pressure_weight_cut_detects_multiple_triggers():
    assert not nutrition_high_pressure_cut({"weight_cut_risk": False, "weight_cut_pct": 7.0})
    assert nutrition_high_pressure_cut({"weight_cut_risk": True, "weight_cut_pct": 5.1})
    assert nutrition_high_pressure_cut(
        {"weight_cut_risk": True, "weight_cut_pct": 2.0, "fatigue": "moderate", "days_until_fight": 40}
    )
    # A low-fatigue, non-aggressive active cut is only high-pressure inside the final
    # two weeks (<=14) — a routine cut at D-21 is not.
    assert not nutrition_high_pressure_cut(
        {"weight_cut_risk": True, "weight_cut_pct": 2.0, "fatigue": "low", "days_until_fight": 21}
    )
    assert not nutrition_high_pressure_cut(
        {"weight_cut_risk": True, "weight_cut_pct": 2.0, "fatigue": "low", "days_until_fight": 15}
    )
    assert nutrition_high_pressure_cut(
        {"weight_cut_risk": True, "weight_cut_pct": 2.0, "fatigue": "low", "days_until_fight": 14}
    )


def test_generate_nutrition_block_includes_phase_fatigue_and_cut_sections():
    block = generate_nutrition_block(
        flags={
            "phase": "SPP",
            "weight": 72,
            "fatigue": "moderate",
            "weight_cut_risk": True,
            "weight_cut_pct": 5.4,
            "days_until_fight": 18,
        }
    )

    assert "Nutrition Module" in block
    assert "**Active Weight-Cut Note:**" in block
    assert "This is a high-pressure cut window" in block
    assert "**SPP Phase Focus:**" in block
    assert "**Moderate Fatigue Adjustments:**" in block
    assert "**Weight Cut Protocol Triggered:**" in block


def test_generate_nutrition_block_handles_taper_high_fatigue_branch():
    block = generate_nutrition_block(
        flags={
            "phase": "TAPER",
            "weight": 66,
            "fatigue": "high",
            "weight_cut_risk": False,
        }
    )

    assert "**Taper Phase Focus:**" in block
    assert "**High Fatigue in Taper:**" in block
    assert "Light electrolyte intake only" in block


def test_fetch_injury_drills_matches_phase_location_and_caps_results(monkeypatch):
    monkeypatch.setattr(recovery, "parse_injury_phrase", lambda desc: ("strain", "shoulder"))
    monkeypatch.setattr(recovery, "normalize_rehab_location", lambda location: {location.lower()})
    monkeypatch.setattr(
        recovery,
        "get_rehab_bank",
        lambda: [
            {
                "phase_progression": "GPP->SPP",
                "location": "shoulder",
                "type": "strain",
                "drills": [
                    {"name": "Band External Rotation", "notes": "2 x 15"},
                    {"name": "Scap Push-Up", "notes": "2 x 10"},
                    {"name": "Should Not Appear", "notes": "3 x 10"},
                ],
            }
        ],
    )

    drills = recovery._fetch_injury_drills(["right shoulder strain"], "SPP")

    assert drills == [
        "Band External Rotation - 2 x 15",
        "Scap Push-Up - 2 x 10",
    ]


def test_generate_recovery_block_layers_age_fatigue_phase_and_cut_guidance():
    block = generate_recovery_block(
        {
            "phase": "TAPER",
            "fatigue": "high",
            "age": 36,
            "weight_cut_risk": True,
            "weight_cut_pct": 6.4,
            "days_until_fight": 5,
        }
    )

    assert "**Age-Specific Adjustments:**" in block
    assert "**Fatigue Red Flags:**" in block
    assert "**Fight Week Protocol (Taper):**" in block
    assert "**Active Weight-Cut Recovery Note:**" in block
    assert "High-pressure cut: protect freshness first" in block
    assert "**Severe Weight Cut Recovery Warning:**" in block


def test_generate_nutrition_block_handles_missing_weight():
    # Quick Build never collects body weight, so the athlete model carries
    # weight=None. Regression: 1.7 * None crashed Stage 1 inside the
    # nutrition module. The block must fall back to the 70 kg default.
    block = generate_nutrition_block(
        flags={
            "phase": "GPP",
            "fatigue": "low",
            "weight": None,
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
        }
    )

    assert "Protein intake: 1.7-2.2 g/kg -> 119.0-154.0 g/day" in block


def test_generate_recovery_block_handles_missing_age():
    # Quick Build never collects age, so the athlete model carries age=None.
    # Regression: int(None) crashed Stage 1 inside the recovery module.
    block = generate_recovery_block(
        {
            "phase": "GPP",
            "fatigue": "low",
            "age": None,
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "days_until_fight": 42,
        }
    )

    assert "**Core Recovery Strategies:**" in block
    assert "**Age-Specific Adjustments:**" not in block


def test_parse_weight_value_returns_zero_for_blank_or_invalid_inputs():
    assert parse_weight_value(None) == 0.0
    assert parse_weight_value("") == 0.0
    assert parse_weight_value("no number here") == 0.0


def test_compute_weight_cut_pct_clamps_negative_and_zero_current_weight():
    assert compute_weight_cut_pct(0, 65) == 0.0
    assert compute_weight_cut_pct("64 kg", "66 kg") == 0.0
    assert compute_weight_cut_pct("70kg", "66kg") == 5.7