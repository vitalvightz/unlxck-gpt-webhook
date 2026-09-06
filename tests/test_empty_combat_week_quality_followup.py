from __future__ import annotations

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


def test_pressure_slot_is_not_hard_coded_to_d21_d18(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: True)
    athlete = _athlete(training_days=["Monday", "Wednesday"])
    week = {
        "phase": "GPP",
        "declared_training_days": ["Monday", "Wednesday"],
        "calendar_days": [
            {"weekday": "monday", "d_day": 26},
            {"weekday": "wednesday", "d_day": 24},
        ],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) == ("monday", 26)


def test_pressure_slot_never_turns_d7_inward_into_development_work(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: True)
    athlete = _athlete(training_days=["Monday"])
    week = {
        "phase": "SPP",
        "declared_training_days": ["Monday"],
        "calendar_days": [{"weekday": "monday", "d_day": 7}],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) is None


def test_moderate_fatigue_or_large_body_mass_biases_low_impact_repeatability():
    assert policy._prefer_low_impact_repeatability(_athlete(fatigue="moderate")) is True
    assert policy._prefer_low_impact_repeatability(
        _athlete(fatigue="low", readiness_flags=[], body_mass_kg=103)
    ) is True
    assert policy._prefer_low_impact_repeatability(
        _athlete(fatigue="low", readiness_flags=[], body_mass_kg=80)
    ) is False


def test_upgraded_empty_week_pressure_role_carries_low_impact_selection_bias():
    role_map = _build_weekly_role_map(_athlete(body_mass_kg=103), _progression(), LIMITER)
    week = role_map["weeks"][0]
    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("upgraded_from_empty_combat_week")
    )

    assert pressure["low_impact_preferred"] is True
    assert "low_impact" in pressure["preferred_tags"]
    assert pressure["preferred_system"] == "glycolytic"
