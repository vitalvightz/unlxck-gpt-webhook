from __future__ import annotations

from copy import deepcopy

from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_role_map import (
    _build_weekly_role_map,
    _enforce_combat_pressure_floor,
)


def _week(phase: str = "GPP", *, must_keep: list[str] | None = None) -> dict:
    protected = ["aerobic"] if must_keep is None else list(must_keep)
    return {
        "week_index": 1,
        "phase": phase,
        "calendar_days": [{"weekday": "monday", "d_day": 35}],
        "hard_sparring_plan": [],
        "effective_hard_sparring_days": [],
        "must_keep": protected,
        "resolved_rule_state": {"must_keep": protected},
    }


def _aerobic_role() -> dict:
    return {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "aerobic_base_day",
        "preferred_pool": "conditioning_slots",
        "preferred_system": "aerobic",
        "governance": {},
        "scheduled_day_hint": "monday",
    }


def _alactic_role() -> dict:
    return {
        "session_index": 2,
        "category": "conditioning",
        "role_key": "alactic_speed_day",
        "preferred_pool": "conditioning_slots",
        "preferred_system": "alactic",
        "governance": {},
        "scheduled_day_hint": "thursday",
    }


def _athlete(**overrides) -> dict:
    athlete = {
        "sport": "boxing",
        "training_days": ["monday", "tuesday", "wednesday", "thursday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
        "fight_date": "2027-07-18",
        "key_goals": [],
        "weaknesses": [],
    }
    athlete.update(overrides)
    return athlete


def _progression() -> dict:
    weeks = []
    for idx in range(6):
        weeks.append(
            {
                "week_index": idx + 1,
                "phase": "GPP",
                "phase_week_index": idx + 1,
                "phase_week_total": 6,
                "span_days": 7,
                "stage_key": "general_capacity",
                "session_counts": {"strength": 0, "conditioning": 1, "recovery": 0},
                "conditioning_sequence": ["aerobic"],
                "must_keep": ["aerobic"],
                "resolved_rule_state": {"must_keep": ["aerobic"]},
            }
        )
    return {"weeks": weeks}


def _sparse_roles(week: dict) -> list[dict]:
    return [
        role
        for role in week.get("session_roles", [])
        if role.get("sparse_combat_week_hard_fallback")
    ]


def test_zero_combat_sessions_repurposes_sole_aerobic_slot_to_hard_gpp() -> None:
    week = _week()
    roles = _enforce_combat_pressure_floor(week, [_aerobic_role()], [], _athlete())
    role = roles[0]
    assert role["preferred_system"] == "glycolytic"
    assert role["role_key"] == "controlled_repeatability_day"
    assert role["mandatory_hard_conditioning_exposure"] is True
    assert role["prescribed_intensity_rpe"] == "8"
    assert role["sparse_combat_week_hard_fallback"] is True
    assert week["combat_pressure_floor"]["source"] == "sparse_week_upgraded_conditioning_slot"


def test_one_light_combat_day_still_gets_hard_sparse_fallback() -> None:
    week = _week("SPP")
    roles = _enforce_combat_pressure_floor(
        week,
        [_aerobic_role()],
        [],
        _athlete(support_work_days=["wednesday"]),
    )
    role = roles[0]
    assert role["preferred_system"] == "glycolytic"
    assert role["role_key"] == "fight_pace_repeatability_day"
    assert role["prescribed_intensity_rpe"] == "8-9"
    assert role["sparse_combat_week_hard_fallback"] is True


def test_two_light_combat_days_do_not_activate_sparse_override() -> None:
    week = _week()
    roles = _enforce_combat_pressure_floor(
        week,
        [deepcopy(_aerobic_role())],
        [],
        _athlete(support_work_days=["tuesday", "thursday"]),
    )
    assert roles[0]["preferred_system"] == "aerobic"
    assert not roles[0].get("sparse_combat_week_hard_fallback")
    assert week["combat_pressure_floor"]["active"] is False


def test_resolved_hard_plan_prevents_sparse_override() -> None:
    week = _week()
    week["hard_sparring_plan"] = [
        {
            "day": "tuesday",
            "status": "convert_to_technical_suggested",
            "effective_load": "technical",
        }
    ]
    roles = _enforce_combat_pressure_floor(
        week,
        [_aerobic_role()],
        [],
        _athlete(hard_sparring_days=["tuesday"]),
    )
    assert roles[0]["preferred_system"] == "aerobic"
    assert not roles[0].get("sparse_combat_week_hard_fallback")


def test_sparse_override_never_breaks_alactic_must_keep() -> None:
    week = _week("SPP", must_keep=["alactic"])
    roles = _enforce_combat_pressure_floor(
        week,
        [_alactic_role()],
        [],
        _athlete(),
    )
    assert roles[0]["preferred_system"] == "alactic"
    assert not roles[0].get("sparse_combat_week_hard_fallback")
    assert week["combat_pressure_floor"]["active"] is False


def test_sparse_override_relaxes_only_aerobic_and_preserves_alactic() -> None:
    week = _week("SPP", must_keep=["aerobic", "alactic"])
    roles = _enforce_combat_pressure_floor(
        week,
        [_aerobic_role(), _alactic_role()],
        [],
        _athlete(),
    )
    assert roles[0]["preferred_system"] == "glycolytic"
    assert roles[0]["sparse_combat_week_hard_fallback"] is True
    assert roles[1]["preferred_system"] == "alactic"
    assert not roles[1].get("sparse_combat_week_hard_fallback")


def test_existing_safety_blockers_still_win_before_sparse_override() -> None:
    week = _week()
    roles = _enforce_combat_pressure_floor(
        week,
        [_aerobic_role()],
        [],
        _athlete(fatigue="high", readiness_flags=["high_fatigue"]),
    )
    assert roles[0]["preferred_system"] == "aerobic"
    assert week["combat_pressure_floor"]["active"] is False
    assert "high_fatigue" in week["combat_pressure_floor"]["reason_codes"]


def test_build_weekly_role_map_zero_combat_keeps_one_app_session_and_makes_it_hard() -> None:
    role_map = _build_weekly_role_map(
        _athlete(),
        _progression(),
        {"key": "general_fight_readiness"},
    )
    week = role_map["weeks"][0]
    sparse = _sparse_roles(week)
    assert len(sparse) == 1
    assert sparse[0]["preferred_system"] == "glycolytic"
    assert sparse[0]["mandatory_hard_conditioning_exposure"] is True
    assert len([role for role in week["session_roles"] if not role.get("coach_owned")]) == 1
    assert week["hard_sparring_plan"] == []


def test_build_weekly_role_map_one_light_day_preserves_coach_lock_and_one_app_session() -> None:
    role_map = _build_weekly_role_map(
        _athlete(support_work_days=["wednesday"]),
        _progression(),
        {"key": "general_fight_readiness"},
    )
    week = role_map["weeks"][0]
    sparse = _sparse_roles(week)
    assert len(sparse) == 1
    assert sparse[0]["preferred_system"] == "glycolytic"
    assert len([role for role in week["session_roles"] if not role.get("coach_owned")]) == 1

    light_roles = [
        role for role in week["session_roles"] if role.get("role_key") == "light_combat_day"
    ]
    assert len(light_roles) == 1
    assert light_roles[0]["coach_owned"] is True
    assert light_roles[0]["declared_day_locked"] is True
    assert light_roles[0]["scheduled_day_hint"] == "wednesday"


def test_finalizer_preserves_and_locks_sparse_hard_dose_via_canonical_compactor() -> None:
    week = _week()
    roles = _enforce_combat_pressure_floor(week, [_aerobic_role()], [], _athlete())
    week["session_roles"] = roles
    week["suppressed_roles"] = []
    week["declared_training_days"] = ["monday", "tuesday", "wednesday", "thursday"]
    weekly_role_map = {"weeks": [week]}
    packet = build_stage2_finalizer_packet(
        stage2_payload={},
        planning_brief={
            "athlete_snapshot": _athlete(),
            "weekly_role_map": weekly_role_map,
        },
    )
    compact_role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]
    assert compact_role["sparse_combat_week_hard_fallback"] is True
    assert compact_role["mandatory_hard_conditioning_exposure"] is True
    assert compact_role["prescribed_intensity_rpe"] == "8"
    assert "hard" in compact_role["prescribed_dose"].lower()
    assert any(
        "MUST remain a hard glycolytic/fight-pace exposure" in rule
        for rule in packet["hard_rules"]
    )