from __future__ import annotations

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


def _first_week(role_map):
    return role_map["weeks"][0]


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
    assert week["combat_pressure_floor"]["active"] is True
    assert not any(
        role.get("role_key") == "secondary_strength_day"
        for role in week["session_roles"]
    )
    assert any(
        role.get("role_key") == "primary_strength_day"
        for role in week["session_roles"]
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
