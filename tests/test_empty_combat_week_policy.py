from __future__ import annotations

from fightcamp.goal_preservation import reconcile_goal_preservation, validate_goal_preservation
from fightcamp.stage2_role_map import _build_weekly_role_map
from fightcamp.stage2_validator import validate_stage2_output


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


def _first_week(role_map):
    return role_map["weeks"][0]


def _glycolytic_slot(phase: str) -> dict:
    return {
        "role": "glycolytic",
        "purpose": "fight-pace repeatability",
        "slot_id": f"{phase.lower()}_glycolytic_regression",
        "priority": "critical",
        "selected": {
            "name": "Assault Bike Repeated Hard Efforts",
            "system": "GLYCOLYTIC",
            "prescription": "6 x 30s hard / 90s easy",
            "restriction_hits": 0,
            "selection_metadata": {
                "system": "GLYCOLYTIC",
                "work_sec": 30,
                "rest_sec": 90,
                "rounds": 6,
                "total_minutes": 3,
                "rpe": 8,
                "phases": [phase],
                "late_windows": [],
            },
        },
        "alternates": [],
        "replace_with_same_role": True,
    }


def test_empty_boxing_week_gives_primary_conditioning_the_early_pressure_slot():
    role_map = _build_weekly_role_map(_athlete(), _progression(), LIMITER)
    week = _first_week(role_map)

    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("category") == "conditioning"
        and role.get("preferred_system") == "glycolytic"
        and role.get("combat_pressure_floor")
    )

    assert pressure.get("upgraded_from_empty_combat_week") is True
    assert pressure["scheduled_countdown_label"] == "D-21"
    assert pressure["anchor"] == "highest_glycolytic_day"
    assert pressure["governance"]["authority"] == "execution_layer_only"
    assert pressure["governance"]["execution_only"] is True
    assert "strength" not in pressure["selection_rule"].lower()
    assert pressure["placement_rule"] == week["highest_glycolytic_day"]
    assert week["combat_pressure_floor"]["active"] is True
    assert not any(
        role.get("role_key") == "secondary_strength_day"
        for role in week["session_roles"]
    )
    assert any(
        role.get("role_key") == "primary_strength_day"
        for role in week["session_roles"]
    )


def test_empty_boxing_week_pressure_survives_goal_preservation_and_render_validation():
    athlete = _athlete(key_goals=["conditioning"], primary_goal="conditioning")
    role_map = _build_weekly_role_map(athlete, _progression(), LIMITER)
    brief = {
        "athlete_snapshot": athlete,
        "priority_focus": {"primary_goal": "conditioning", "secondary_goals": []},
        "weekly_role_map": role_map,
        "candidate_pools": {
            "GPP": {"conditioning_slots": [_glycolytic_slot("GPP")]},
            "SPP": {"conditioning_slots": [_glycolytic_slot("SPP")]},
            "TAPER": {"conditioning_slots": []},
        },
        "restrictions": [],
    }

    reconcile_goal_preservation(brief)
    conditioning = next(
        entry for entry in brief["goal_preservation"] if entry["goal"] == "conditioning"
    )

    assert conditioning["satisfied"] is True
    assert any(
        evidence.get("name") == "Assault Bike Repeated Hard Efforts"
        and "energy_system_training" in evidence.get("intents", [])
        for evidence in conditioning["evidence"]
    )
    assert not any(
        error.get("goal") == "conditioning"
        for error in validate_goal_preservation(brief)
    )

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text=(
            "D-21 Monday\n"
            "- Assault Bike Repeated Hard Efforts: 6 x 30s hard / 90s easy\n"
            "D-0 Monday\n"
            "Fight day protocol."
        ),
    )
    assert not any(
        error.get("goal") == "conditioning"
        and error.get("code") in {
            "goal_preservation_failed",
            "goal_preservation_render_mismatch",
        }
        for error in report["errors"]
    )


def test_empty_boxing_week_never_reports_spar_first_cap():
    role_map = _build_weekly_role_map(_athlete(), _progression(), LIMITER)
    week = _first_week(role_map)

    assert "spar_first_cap" not in (week.get("intentional_compression") or {}).get("reason_codes", [])
    assert all(
        "spar_first_cap" not in (row.get("compression_reason_codes") or [])
        for row in week.get("suppressed_roles") or []
    )


def test_real_declared_combat_load_disables_empty_week_substitution():
    role_map = _build_weekly_role_map(
        _athlete(hard_sparring_days=["Friday"]),
        _progression(),
        LIMITER,
    )
    week = _first_week(role_map)

    assert not any(
        role.get("upgraded_from_empty_combat_week")
        for role in week["session_roles"]
    )


def test_declared_light_combat_also_disables_empty_week_substitution():
    role_map = _build_weekly_role_map(
        _athlete(support_work_days=["Wednesday"], technical_skill_days=["Wednesday"]),
        _progression(),
        LIMITER,
    )
    week = _first_week(role_map)

    assert not any(
        role.get("upgraded_from_empty_combat_week")
        for role in week["session_roles"]
    )
