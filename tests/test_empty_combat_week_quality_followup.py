from __future__ import annotations

from fightcamp import conditioning
import fightcamp.empty_combat_week_policy as policy
from fightcamp.stage2_role_map import _build_weekly_role_map


LIMITER = {"key": "aerobic_repeatability"}


def _athlete(**overrides):
    data = {
        "sport": "boxing",
        "status": "amateur",
        "record": "0-0",
        "competitive_maturity": "novice_amateur",
        "rounds_format": "3 x 3",
        "days_until_fight": 22,
        "fight_date": "2026-09-28",
        "plan_creation_weekday": "sunday",
        "fatigue": "moderate",
        "cut_severity_bucket": "low",
        "weight_cut_pct": 2.0,
        "weight_cut_risk": False,
        "injury_mode": "full_plan",
        "injuries": [],
        "readiness_flags": ["moderate_fatigue", "reduced_contact_requested"],
        "key_goals": ["conditioning", "speed"],
        "primary_goal": "conditioning",
        "weaknesses": ["gas_tank", "trunk_strength"],
        "training_frequency": 4,
        "training_days": ["Monday", "Friday", "Wednesday", "Sunday", "Thursday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "technical_skill_days": [],
        "tactical_styles": ["distance_striker"],
    }
    data.update(overrides)
    return data


def _progression():
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic", "alactic"],
            },
            {
                "week_index": 2,
                "phase": "SPP",
                "stage_key": "specific_density_to_peak",
                "span_days": 8,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["glycolytic", "alactic", "aerobic"],
            },
            {
                "week_index": 3,
                "phase": "TAPER",
                "stage_key": "fight_week_survival_rhythm",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1},
                "conditioning_sequence": ["alactic", "aerobic", "glycolytic"],
            },
        ]
    }


def test_pressure_slot_can_start_well_before_d21(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: True)
    athlete = _athlete(training_days=["Monday", "Wednesday"])
    week = {
        "phase": "GPP",
        "declared_training_days": ["Monday", "Wednesday"],
        "calendar_days": [
            {"weekday": "monday", "d_day": 35},
            {"weekday": "wednesday", "d_day": 33},
        ],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) == ("monday", 35)
    assert not hasattr(policy, "_MIN_DEVELOPMENT_D_DAY")


def test_canonical_bridge_not_local_cutoff_blocks_d7_inward():
    athlete = _athlete(
        fatigue="low",
        readiness_flags=[],
        training_days=["Monday"],
    )
    week = {
        "phase": "SPP",
        "declared_training_days": ["Monday"],
        "calendar_days": [{"weekday": "monday", "d_day": 7}],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) is None


def test_technical_attendance_is_avoided_as_pressure_day_when_another_day_exists(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: True)
    athlete = _athlete(
        training_days=["Monday", "Wednesday"],
        support_work_days=["Monday"],
        technical_skill_days=["Monday"],
    )
    week = {
        "phase": "GPP",
        "declared_training_days": ["Monday", "Wednesday"],
        "declared_support_work_days": ["Monday"],
        "declared_technical_skill_days": ["Monday"],
        "calendar_days": [
            {"weekday": "monday", "d_day": 35},
            {"weekday": "wednesday", "d_day": 33},
        ],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) == ("wednesday", 33)


def test_body_mass_and_moderate_fatigue_do_not_force_low_impact_modality():
    assert policy._prefer_low_impact_repeatability(_athlete(body_mass_kg=103)) is False
    assert policy._prefer_low_impact_repeatability(
        _athlete(fatigue="moderate", readiness_flags=["moderate_fatigue"])
    ) is False
    assert policy._prefer_low_impact_repeatability(
        _athlete(fatigue="low", readiness_flags=[], body_mass_kg=80)
    ) is False


def test_mechanical_restriction_can_bias_modality_without_downgrading_system():
    assert policy._prefer_low_impact_repeatability(
        _athlete(
            fatigue="low",
            readiness_flags=["joint_load_restriction"],
            body_mass_kg=80,
        )
    ) is True

    role_map = _build_weekly_role_map(
        _athlete(
            fatigue="low",
            readiness_flags=["joint_load_restriction"],
            body_mass_kg=80,
        ),
        _progression(),
        LIMITER,
    )
    week = role_map["weeks"][0]
    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("upgraded_from_hard_stimulus_deficit")
    )

    assert pressure["low_impact_preferred"] is True
    assert "low_impact" in pressure["preferred_tags"]
    assert pressure["preferred_system"] == "glycolytic"
    assert pressure.get("mandatory_hard_conditioning_exposure") is True


def test_exact_profile_keeps_hard_system_without_body_mass_low_impact_bias():
    role_map = _build_weekly_role_map(_athlete(body_mass_kg=103), _progression(), LIMITER)
    week = role_map["weeks"][0]
    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("upgraded_from_hard_stimulus_deficit")
    )

    assert pressure["preferred_system"] == "glycolytic"
    assert pressure["low_impact_preferred"] is False
    assert "low_impact" not in pressure["preferred_tags"]
    assert "distance_striker" in pressure["preferred_tags"]
    assert pressure.get("mandatory_hard_conditioning_exposure") is True


def test_real_conditioning_selector_has_hard_distance_striker_candidate():
    flags = {
        "phase": "SPP",
        "sport": "boxing",
        "style_technical": ["boxing"],
        "style_tactical": ["distance striker"],
        "key_goals": ["conditioning", "speed"],
        "primary_goal": "conditioning",
        "weaknesses": ["gas tank", "trunk strength"],
        "fatigue": "moderate",
        "equipment": ["bodyweight", "partner", "heavy_bag", "assault_bike", "rower"],
        "training_frequency": 4,
        "days_available": 5,
        "days_until_fight": 22,
        "time_to_fight_days": 22,
        "injuries": [],
        "restrictions": [],
        "priority_focus": {
            "primary_goal": "conditioning",
            "primary_weakness": "gas_tank",
            "derived_clarification_tags": ["glycolytic", "work_capacity", "conditioning"],
        },
    }

    result = conditioning.generate_conditioning_block(flags)
    reservoir = result[5]
    diagnostics = reservoir["__style_conditioning__"]
    selected_names = set(diagnostics["final_selected_style_conditioning_names"])
    style_bank = {
        item["name"]: item
        for item in conditioning.get_style_conditioning_bank()
    }
    selected_hard = [
        style_bank[name]
        for name in selected_names
        if name in style_bank
        and str(style_bank[name].get("system") or "").strip().lower() == "glycolytic"
        and float(style_bank[name].get("rpe") or 0) >= 7
        and str(style_bank[name].get("lactate_load") or "").strip().lower() == "high"
    ]

    assert selected_hard, selected_names
    assert any("distance_striker" in item.get("tags", []) for item in selected_hard)
