import pytest

from fightcamp.stage2_payload import _slot_matches_late_fight_role, build_planning_brief
from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_weekly_role_map,
    _countdown_weekday_map,
    _days_out_payload_mode,
    _is_app_owned_visible_role,
    _late_fight_active_role_count,
    _late_fight_allocation_plan,
    _late_fight_permission_policy,
    ensure_declared_coach_combat_spine,
)
_PERFORMANCE_ROLE_KEYS = {
    "neural_plus_strength_day",
    "fight_pace_repeatability_day",
    "aerobic_support_day",
}


def _low_risk_boxer(days_until_fight: int, *, hard_sparring_days=None, **overrides):
    athlete = {
        "sport": "boxing",
        "status": "professional",
        "rounds_format": "3x3",
        "tactical_style": "counter striker",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": list(hard_sparring_days or []),
        "fatigue": "low",
        "fatigue_level": "low",
        "weight_cut_pct": 3.4,
        "weight_cut_risk": True,
        "cut_severity_bucket": "moderate",
        "readiness_flags": [],
        "key_goals": ["power", "conditioning", "coordination"],
        "weaknesses": ["gas_tank"],
        "injuries": [],
        "days_until_fight": days_until_fight,
        "plan_creation_weekday": "monday",
        "weekly_training_frequency": 4,
    }
    athlete.update(overrides)
    return athlete


def _role_keys(plan):
    return {role.get("role_key") for role in plan.get("session_roles", [])}


def _planning_brief_for(athlete):
    phase_briefs = {
        "SPP": {
            "objective": "fight readiness",
            "weeks": 3,
            "days": 22,
            "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
            "emphasize": ["sport speed"],
            "deprioritize": [],
            "risk_flags": [],
            "selection_guardrails": {
                "must_keep_if_present": [],
                "conditioning_drop_order_if_thin": [],
            },
        }
    }
    candidate_pools = {
        "SPP": {
            "strength_slots": [
                {
                    "role": "primary_strength",
                    "anchor_capable": True,
                    "exercise": {"name": "familiar primary pattern"},
                }
            ],
            "conditioning_slots": [
                {"role": "aerobic", "exercise": {"name": "aerobic support"}},
                {"role": "glycolytic", "exercise": {"name": "fight pace"}},
                {"role": "alactic", "exercise": {"name": "alactic speed"}},
            ],
            "rehab_slots": [],
        }
    }
    return build_planning_brief(
        athlete_model=athlete,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )


def test_d22_to_d21_keeps_normal_spp_role_vocabulary_for_low_risk_athlete():
    d22 = _low_risk_boxer(22, hard_sparring_days=[])
    d21 = _low_risk_boxer(21, hard_sparring_days=[])

    assert _days_out_payload_mode(d22["days_until_fight"]) == "camp_payload"
    assert _days_out_payload_mode(d21["days_until_fight"]) == "bridge_compression_payload"

    d22_brief = _planning_brief_for(d22)
    d21_brief = _planning_brief_for(d21)
    d22_roles = {
        role.get("role_key")
        for role in d22_brief["weekly_role_map"]["weeks"][0]["session_roles"]
    }
    d21_roles = {
        role.get("role_key")
        for role in d21_brief["weekly_role_map"]["weeks"][0]["session_roles"]
    }

    assert d22_brief["weekly_role_map"]["model"] == "session_role_overlay.v1"
    assert d21_brief["weekly_role_map"]["model"] == "late_fight_role_overlay.v1"
    assert {"neural_plus_strength_day", "fight_pace_repeatability_day"} <= d22_roles
    assert {"neural_plus_strength_day", "fight_pace_repeatability_day"} <= d21_roles
    assert "fight_week_freshness_day" in d21_roles
    assert "strength_touch_day" not in d21_roles


def test_d21_one_hard_day_keeps_strength_and_routes_aerobic_support_around_collision():
    athlete = _low_risk_boxer(21, hard_sparring_days=["thursday"])
    plan = _late_fight_allocation_plan(21, athlete)
    roles = plan["session_roles"]
    role_keys = _role_keys(plan)

    assert {"neural_plus_strength_day", "aerobic_support_day", "fight_week_freshness_day"} <= role_keys
    assert "fight_pace_repeatability_day" not in role_keys
    assert sum(role.get("role_key") == "hard_sparring_day" for role in roles) == 1
    assert _late_fight_active_role_count(roles) == 3
    assert all(
        str(role.get("scheduled_day_hint") or "").lower() != "thursday"
        for role in roles
        if _is_app_owned_visible_role(role.get("role_key"))
    )


def test_d21_two_hard_days_constrain_placement_without_spending_app_quota():
    athlete = _low_risk_boxer(21, hard_sparring_days=["tuesday", "thursday"])
    plan = _late_fight_allocation_plan(21, athlete)
    roles = plan["session_roles"]
    role_keys = _role_keys(plan)

    assert {"neural_plus_strength_day", "aerobic_support_day", "fight_week_freshness_day"} <= role_keys
    assert sum(role.get("role_key") == "hard_sparring_day" for role in roles) == 2
    assert _late_fight_active_role_count(roles) == 3
    assert plan["role_budget"]["selected_active_roles"] == 3
    assert plan["role_budget"]["coach_owned_roles_count_toward_app_active_budget"] is False
    assert all(
        str(role.get("scheduled_day_hint") or "").lower() not in {"tuesday", "thursday"}
        for role in roles
        if _is_app_owned_visible_role(role.get("role_key"))
    )


def test_d17_declared_hard_day_converts_to_technical_context_without_snc_stack():
    athlete = _low_risk_boxer(17, hard_sparring_days=["thursday"], weight_cut_pct=0.0, weight_cut_risk=False)
    plan = _late_fight_allocation_plan(17, athlete)
    actions = plan["permission_policy"]["declared_hard_day_actions"]

    assert actions == [
        {
            "day": "thursday",
            "outcome": "technical_touch_day",
            "locked": False,
            "downgraded_from_role_key": "hard_sparring_day",
        }
    ]

    sequence = ensure_declared_coach_combat_spine(
        plan["session_roles"],
        athlete,
        _countdown_weekday_map("monday", 17),
    )
    coach_labels = {
        role.get("countdown_label")
        for role in sequence
        if role.get("role_key") == "hard_sparring_day" and role.get("downgraded") is True
    }
    assert coach_labels
    downgraded_coach_roles = [
        role
        for role in sequence
        if role.get("role_key") == "hard_sparring_day" and role.get("downgraded") is True
    ]
    assert all(role.get("coach_owned") is True for role in downgraded_coach_roles)
    assert all(not _is_app_owned_visible_role(role.get("role_key")) for role in downgraded_coach_roles)
    assert _late_fight_active_role_count(sequence) == sum(
        _is_app_owned_visible_role(role.get("role_key")) for role in sequence
    )
    assert not any(
        role.get("countdown_label") in coach_labels
        and role.get("category") in {"strength", "conditioning"}
        and _is_app_owned_visible_role(role.get("role_key"))
        for role in sequence
    )


def test_d21_routine_moderate_cut_does_not_collapse_performance_bridge():
    athlete = _low_risk_boxer(21, hard_sparring_days=[])
    plan = _late_fight_allocation_plan(21, athlete)

    assert plan["permission_policy"]["performance_bridge_active"] is True
    assert {"neural_plus_strength_day", "fight_pace_repeatability_day"} <= _role_keys(plan)


@pytest.mark.parametrize(
    "overrides",
    [
        {"fatigue": "high", "fatigue_level": "high"},
        {"injuries": ["moderate hamstring strain"]},
        {"cut_severity_bucket": "high", "weight_cut_pct": 6.0},
        {"cut_severity_bucket": "high"},
        {"injury_mode": "restricted_rehab_only"},
        {"readiness_flags": ["red_flag_injury"]},
    ],
)
def test_d21_genuine_risk_profiles_keep_conservative_bridge(overrides):
    athlete = _low_risk_boxer(21, **overrides)
    plan = _late_fight_allocation_plan(21, athlete)

    assert plan["permission_policy"]["performance_bridge_active"] is False
    assert _PERFORMANCE_ROLE_KEYS.isdisjoint(_role_keys(plan))
    assert "light_fight_pace_touch_day" not in _role_keys(plan)
    assert "fight_week_freshness_day" in _role_keys(plan)


@pytest.mark.parametrize(
    ("days", "expected_mode", "performance_bridge"),
    [
        (22, "camp_payload", False),
        (21, "bridge_compression_payload", True),
        (20, "bridge_compression_payload", True),
        (18, "bridge_compression_payload", True),
        (17, "bridge_compression_payload", False),
        (14, "bridge_compression_payload", False),
        (13, "pre_fight_compressed_payload", False),
        (8, "pre_fight_compressed_payload", False),
        (7, "late_fight_week_payload", False),
        (3, "late_fight_session_payload", False),
        (1, "pre_fight_day_payload", False),
        (0, "fight_day_protocol_payload", False),
    ],
)
def test_countdown_boundaries_expose_performance_bridge_only_at_d21_to_d18(
    days, expected_mode, performance_bridge
):
    athlete = _low_risk_boxer(days, weight_cut_pct=0.0, weight_cut_risk=False, cut_severity_bucket="none")
    policy = _late_fight_permission_policy(days, athlete)

    assert _days_out_payload_mode(days) == expected_mode
    assert policy["performance_bridge_active"] is performance_bridge

    if days <= 17:
        assert _PERFORMANCE_ROLE_KEYS.isdisjoint(_role_keys(_late_fight_allocation_plan(days, athlete)))


def test_d21_role_map_contains_performance_backbone_before_stage2_rendering():
    athlete = _low_risk_boxer(21, hard_sparring_days=["thursday"])
    role_map = _build_late_fight_weekly_role_map(21, athlete, phase="SPP")
    bridge_week = role_map["weeks"][0]
    bridge_roles = bridge_week["session_roles"]
    role_keys = {role.get("role_key") for role in bridge_roles}

    assert bridge_week["stage_label"] == "Late-SPP Performance Bridge"
    assert {"neural_plus_strength_day", "aerobic_support_day", "fight_week_freshness_day"} <= role_keys
    assert any(role.get("role_key") == "hard_sparring_day" for role in bridge_roles)
    assert not any(
        str(role.get("scheduled_day_hint") or "").lower() == "thursday"
        and role.get("category") in {"strength", "conditioning"}
        and _is_app_owned_visible_role(role.get("role_key"))
        for role in bridge_roles
    )


def test_performance_bridge_roles_bind_to_stage2_candidate_pools():
    strength_slot = {
        "role": "primary_strength",
        "anchor_capable": True,
        "exercise": {"name": "familiar primary pattern"},
    }

    assert _slot_matches_late_fight_role(
        strength_slot,
        "strength_slots",
        {"role_key": "neural_plus_strength_day"},
    )
    assert _slot_matches_late_fight_role(
        {"role": "glycolytic"},
        "conditioning_slots",
        {"role_key": "fight_pace_repeatability_day", "preferred_system": "glycolytic"},
    )
    assert _slot_matches_late_fight_role(
        {"role": "aerobic"},
        "conditioning_slots",
        {"role_key": "aerobic_support_day", "preferred_system": "aerobic"},
    )
