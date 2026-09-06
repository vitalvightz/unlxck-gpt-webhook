from __future__ import annotations

from copy import deepcopy

from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_role_map import _enforce_combat_pressure_floor


def _week(phase: str = "GPP") -> dict:
    return {
        "week_index": 1,
        "phase": phase,
        "calendar_days": [{"weekday": "monday", "d_day": 35}],
        "must_keep": ["aerobic"],
        "resolved_rule_state": {"must_keep": ["aerobic"]},
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


def _athlete(**overrides) -> dict:
    athlete = {
        "sport": "boxing",
        "training_days": ["monday", "tuesday", "wednesday", "thursday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
    }
    athlete.update(overrides)
    return athlete


def test_zero_combat_sessions_repuposes_sole_aerobic_slot_to_hard_gpp() -> None:
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
    original = _aerobic_role()
    roles = _enforce_combat_pressure_floor(
        week,
        [deepcopy(original)],
        [],
        _athlete(support_work_days=["tuesday", "thursday"]),
    )
    assert roles[0]["preferred_system"] == "aerobic"
    assert not roles[0].get("sparse_combat_week_hard_fallback")
    assert week["combat_pressure_floor"]["active"] is False


def test_any_declared_hard_spar_keeps_existing_path_untouched() -> None:
    week = _week()
    roles = _enforce_combat_pressure_floor(
        week,
        [_aerobic_role()],
        [],
        _athlete(hard_sparring_days=["tuesday"]),
    )
    assert roles[0]["preferred_system"] == "aerobic"
    assert not roles[0].get("sparse_combat_week_hard_fallback")


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


def test_finalizer_preserves_and_locks_sparse_hard_dose() -> None:
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
