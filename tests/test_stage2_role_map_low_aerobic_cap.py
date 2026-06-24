"""Tests for the severity-aware low-aerobic support cap in stage2_role_map.

Cut severity comes from the deterministic source of truth in weight_cut.py
(compute_cut_severity_score / cut_severity_bucket / _resolved_cut_severity_bucket).
The cap is applied inside both _upgrade_recovery_days_to_gas_tank and
_upgrade_unused_days_to_low_load_support and gates how many low-aerobic
support touches the role map can add for a given week.
"""
from fightcamp.stage2_role_map import (
    _count_low_aerobic_support_roles,
    _is_low_aerobic_support_role,
    _low_aerobic_support_cap_for_week,
    _upgrade_recovery_days_to_gas_tank,
    _upgrade_unused_days_to_low_load_support,
)


def _gas_tank_athlete(**overrides):
    base = {
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
    }
    base.update(overrides)
    return base


def _mobility_athlete(**overrides):
    base = {
        "key_goals": ["mobility"],
        "weaknesses": ["mobility"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Cap helper
# ---------------------------------------------------------------------------


def test_cap_none_low_cut_allows_one_low_aerobic_support_touch_in_gpp_and_spp():
    week = {"phase": "GPP", "calendar_days": [{"weekday": "tuesday", "d_day": 36}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="none")
    assert _low_aerobic_support_cap_for_week(week, athlete, []) == 1

    week = {"phase": "SPP", "calendar_days": [{"weekday": "thursday", "d_day": 27}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="low")
    assert _low_aerobic_support_cap_for_week(week, athlete, []) == 1


def test_cap_none_low_cut_caps_taper_at_one():
    week = {"phase": "TAPER", "calendar_days": [{"weekday": "thursday", "d_day": 14}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="low")
    assert _low_aerobic_support_cap_for_week(week, athlete, []) == 1


def test_cap_fight_week_drops_to_zero_when_high_fatigue():
    week = {"phase": "TAPER", "calendar_days": [{"weekday": "wednesday", "d_day": 4}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="low", fatigue="high")
    assert _low_aerobic_support_cap_for_week(week, athlete, []) == 0


def test_cap_fight_week_allows_one_when_fresh():
    week = {"phase": "TAPER", "calendar_days": [{"weekday": "wednesday", "d_day": 4}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="low")
    assert _low_aerobic_support_cap_for_week(week, athlete, []) == 1


def test_cap_moderate_cut_caps_taper_and_fight_week_at_one():
    taper = {"phase": "TAPER", "calendar_days": [{"weekday": "thursday", "d_day": 12}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="moderate")
    assert _low_aerobic_support_cap_for_week(taper, athlete, []) == 1

    fight_week = {"phase": "TAPER", "calendar_days": [{"weekday": "wednesday", "d_day": 4}]}
    assert _low_aerobic_support_cap_for_week(fight_week, athlete, []) == 1


def test_cap_moderate_cut_drops_gpp_to_one_with_high_fatigue_or_three_hard_spar():
    gpp = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 40}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="moderate", fatigue="high")
    assert _low_aerobic_support_cap_for_week(gpp, athlete, []) == 1

    athlete = _gas_tank_athlete(cut_severity_bucket="moderate")
    plan = [
        {"day": "monday", "status": "hard_as_planned"},
        {"day": "wednesday", "status": "hard_as_planned"},
        {"day": "friday", "status": "hard_as_planned"},
    ]
    assert (
        _low_aerobic_support_cap_for_week(gpp, athlete, [], hard_sparring_plan=plan)
        == 1
    )


def test_cap_moderate_cut_stays_one_in_gpp_when_fresh_and_low_hard_spar():
    gpp = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 40}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="moderate")
    plan = [{"day": "tuesday", "status": "hard_as_planned"}]
    assert (
        _low_aerobic_support_cap_for_week(gpp, athlete, [], hard_sparring_plan=plan)
        == 1
    )


def test_cap_high_critical_extreme_cut_caps_gpp_spp_at_one():
    gpp = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 40}]}
    spp = {"phase": "SPP", "calendar_days": [{"weekday": "monday", "d_day": 25}]}
    for bucket in ("high", "critical", "extreme"):
        athlete = _gas_tank_athlete(cut_severity_bucket=bucket)
        assert _low_aerobic_support_cap_for_week(gpp, athlete, []) == 1
        assert _low_aerobic_support_cap_for_week(spp, athlete, []) == 1


def test_cap_high_cut_with_high_fatigue_returns_zero():
    gpp = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 40}]}
    athlete = _gas_tank_athlete(cut_severity_bucket="high", fatigue="high")
    assert _low_aerobic_support_cap_for_week(gpp, athlete, []) == 0


def test_cap_high_cut_with_red_flag_readiness_returns_zero():
    spp = {"phase": "SPP", "calendar_days": [{"weekday": "monday", "d_day": 25}]}
    athlete = _gas_tank_athlete(
        cut_severity_bucket="critical",
        readiness_flags=["red_flag_injury"],
    )
    assert _low_aerobic_support_cap_for_week(spp, athlete, []) == 0


def test_cap_uses_weight_cut_pct_when_explicit_bucket_missing():
    """Falls back through compute_cut_severity_score when bucket is absent."""
    gpp = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 40}]}
    # 8% cut at 40 days out → moderate or low depending on math; not high+
    athlete = _gas_tank_athlete(weight_cut_pct=8.0, days_until_fight=40)
    cap = _low_aerobic_support_cap_for_week(gpp, athlete, [])
    assert 1 <= cap <= 2


# ---------------------------------------------------------------------------
# Counting helper
# ---------------------------------------------------------------------------


def test_counting_helper_includes_known_low_aerobic_keys():
    roles = [
        {"category": "conditioning", "role_key": "recovery_aerobic_gas_tank_day"},
        {"category": "conditioning", "role_key": "converted_low_aerobic_gas_tank_day"},
        {"category": "conditioning", "role_key": "aerobic_support_day"},
        {"category": "conditioning", "role_key": "aerobic_base_day"},
        {"category": "conditioning", "role_key": "aerobic_coordination_day"},
        {"category": "conditioning", "role_key": "aerobic_flush_day"},
    ]
    assert _count_low_aerobic_support_roles(roles) == 6


def test_counting_helper_includes_repeatability_only_when_aerobic():
    aerobic_repeatability = {
        "category": "conditioning",
        "role_key": "repeatability_support_day",
        "preferred_system": "aerobic",
    }
    glycolytic_repeatability = {
        "category": "conditioning",
        "role_key": "repeatability_support_day",
        "preferred_system": "glycolytic",
    }
    assert _is_low_aerobic_support_role(aerobic_repeatability) is True
    assert _is_low_aerobic_support_role(glycolytic_repeatability) is False


def test_counting_helper_excludes_recovery_mobility_breathing_strength_glyco_alactic():
    skipped = [
        {"category": "recovery", "role_key": "recovery_reset_day"},
        {"category": "recovery", "role_key": "tissue_recovery_day"},
        {"category": "strength", "role_key": "primary_strength_day"},
        {"category": "conditioning", "role_key": "alactic_sharpness_day", "preferred_system": "alactic"},
        {"category": "conditioning", "role_key": "fight_pace_repeatability_day", "preferred_system": "glycolytic"},
    ]
    assert _count_low_aerobic_support_roles(skipped) == 0


def test_counting_helper_includes_aerobic_with_recovery_compatible_flag():
    role = {
        "category": "conditioning",
        "role_key": "custom_aerobic_thing",
        "preferred_system": "aerobic",
        "recovery_compatible": True,
    }
    assert _is_low_aerobic_support_role(role) is True


# ---------------------------------------------------------------------------
# Cap applied inside _upgrade_recovery_days_to_gas_tank
# ---------------------------------------------------------------------------


def test_recovery_upgrade_respects_cap_when_aerobic_already_at_cap():
    """High cut → cap is 1. If the week already has a low-aerobic support role,
    the recovery role must NOT be converted."""
    week = {
        "phase": "GPP",
        "calendar_days": [
            {"weekday": "tuesday", "d_day": 36},
            {"weekday": "thursday", "d_day": 34},
        ],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "scheduled_day_hint": "tuesday",
        },
        {
            "session_index": 2,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "thursday",
        },
    ]
    athlete = _gas_tank_athlete(cut_severity_bucket="high")
    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete)
    role_keys = [r["role_key"] for r in upgraded]
    assert "aerobic_support_day" in role_keys
    # Recovery should NOT have been converted since cap (1) is already met.
    assert "recovery_reset_day" in role_keys
    assert "recovery_aerobic_gas_tank_day" not in role_keys


def test_recovery_upgrade_high_fatigue_high_cut_does_not_reopen_volume():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "tuesday", "d_day": 36}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    athlete = _gas_tank_athlete(cut_severity_bucket="critical", fatigue="high")
    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete)
    # Cap is 0 → no conversion happens.
    assert upgraded[0]["role_key"] == "recovery_reset_day"


def test_recovery_upgrade_d_minus_one_guard_still_blocks():
    week = {
        "phase": "TAPER",
        "calendar_days": [{"weekday": "friday", "d_day": 1}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "friday",
        }
    ]
    athlete = _gas_tank_athlete()
    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete)
    assert upgraded[0]["role_key"] == "recovery_reset_day"


# ---------------------------------------------------------------------------
# Cap applied inside _upgrade_unused_days_to_low_load_support
# ---------------------------------------------------------------------------


def test_unused_upgrade_high_cut_caps_gpp_spp_to_one_total():
    week = {
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "thursday", "d_day": 27},
            {"weekday": "saturday", "d_day": 25},
        ],
        "intentionally_unused_days": [
            {"day": "thursday", "role": "off_day"},
            {"day": "saturday", "role": "off_day"},
        ],
    }
    athlete = _gas_tank_athlete(cut_severity_bucket="high")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    converted = [r for r in upgraded if r["role_key"] == "converted_low_aerobic_gas_tank_day"]
    assert len(converted) == 1
    # Skipped day should be annotated and remain unused.
    remaining = week["intentionally_unused_days"]
    assert len(remaining) == 1
    assert remaining[0].get("low_aerobic_cap_skipped") is True
    assert "Low-aerobic support cap reached" in (
        remaining[0].get("low_aerobic_cap_reason") or ""
    )


def test_unused_upgrade_taper_moderate_cut_caps_at_one():
    week = {
        "phase": "TAPER",
        "calendar_days": [
            {"weekday": "tuesday", "d_day": 12},
            {"weekday": "thursday", "d_day": 10},
        ],
        "intentionally_unused_days": [
            {"day": "tuesday", "role": "off_day"},
            {"day": "thursday", "role": "off_day"},
        ],
    }
    athlete = _gas_tank_athlete(cut_severity_bucket="moderate")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    converted = [r for r in upgraded if r["role_key"] == "converted_low_aerobic_gas_tank_day"]
    assert len(converted) == 1


def test_unused_upgrade_high_fatigue_high_cut_blocks_all_conversions():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = _gas_tank_athlete(cut_severity_bucket="extreme", fatigue="high")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert upgraded == []
    assert week["intentionally_unused_days"][0].get("low_aerobic_cap_skipped") is True




def test_unused_upgrade_mobility_high_fatigue_does_not_bypass_zero_cap_safety():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = _mobility_athlete(cut_severity_bucket="extreme", fatigue="high")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert upgraded == []
    assert week["intentionally_unused_days"][0].get("low_aerobic_cap_skipped") is True


def test_unused_upgrade_mobility_safe_state_can_preserve_one_slot():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = _mobility_athlete(cut_severity_bucket="extreme", fatigue="moderate")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert len(upgraded) == 1
    assert upgraded[0]["role_key"] == "converted_mobility_support_day"
    assert week["intentionally_unused_days"] == []


def test_unused_upgrade_rehab_red_flag_does_not_bypass_zero_cap_safety():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = {
        "key_goals": ["rehab"],
        "cut_severity_bucket": "critical",
        "readiness_flags": ["red_flag_injury"],
    }
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert upgraded == []
    assert week["intentionally_unused_days"][0].get("low_aerobic_cap_skipped") is True


def test_unused_upgrade_d_minus_one_still_blocks_after_cap_logic():
    week = {
        "phase": "TAPER",
        "calendar_days": [{"weekday": "friday", "d_day": 1}],
        "intentionally_unused_days": [{"day": "friday", "role": "off_day"}],
    }
    athlete = _gas_tank_athlete()
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert upgraded == []
    # The D-1 guard short-circuits before the cap-skip annotation is added.
    assert week["intentionally_unused_days"][0]["role"] == "off_day"
    assert "low_aerobic_cap_skipped" not in week["intentionally_unused_days"][0]


# ---------------------------------------------------------------------------
# Both upgrade paths share the cap
# ---------------------------------------------------------------------------


def test_both_upgrade_paths_share_the_same_cap():
    """When _upgrade_recovery_days_to_gas_tank fills the cap, the unused-day
    upgrade should not push any further low-aerobic touches."""
    week = {
        "phase": "GPP",
        "calendar_days": [
            {"weekday": "tuesday", "d_day": 36},
            {"weekday": "thursday", "d_day": 34},
        ],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    athlete = _gas_tank_athlete(cut_severity_bucket="high")  # cap = 1

    after_recovery = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete)
    converted_count = sum(
        1 for r in after_recovery if r["role_key"] == "recovery_aerobic_gas_tank_day"
    )
    assert converted_count == 1

    after_unused = _upgrade_unused_days_to_low_load_support(week, after_recovery, athlete)
    new_converted = [
        r
        for r in after_unused
        if r["role_key"] == "converted_low_aerobic_gas_tank_day"
    ]
    # Cap was already met by the recovery upgrade, so no further conversion.
    assert new_converted == []
    remaining = week["intentionally_unused_days"]
    assert len(remaining) == 1
    assert remaining[0].get("low_aerobic_cap_skipped") is True


# ---------------------------------------------------------------------------
# Hard-sparring days remain locked
# ---------------------------------------------------------------------------


def test_hard_sparring_day_is_not_converted_by_recovery_upgrade():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "tuesday", "d_day": 25}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    athlete = _gas_tank_athlete()
    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete)
    assert upgraded[0]["role_key"] == "hard_sparring_day"


def test_hard_sparring_day_blocks_unused_upgrade_on_same_day():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "tuesday", "d_day": 25}],
        "intentionally_unused_days": [{"day": "tuesday", "role": "off_day"}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    athlete = _gas_tank_athlete()
    upgraded = _upgrade_unused_days_to_low_load_support(week, session_roles, athlete)
    role_keys = [r["role_key"] for r in upgraded]
    assert role_keys == ["hard_sparring_day"]
    # Day stays as the existing off_day record (no conversion, no cap-skip).
    assert week["intentionally_unused_days"] == [{"day": "tuesday", "role": "off_day"}]


# ---------------------------------------------------------------------------
# Existing low-load safeguards remain unchanged
# ---------------------------------------------------------------------------


def test_existing_recovery_compatible_metadata_still_applied_on_conversion():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "tuesday", "d_day": 36}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    athlete = _gas_tank_athlete()
    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete)
    assert upgraded[0]["recovery_compatible"] is True
    assert upgraded[0]["allowed_on_recovery_day"] is True
    assert upgraded[0]["gas_tank_recovery_touch"] is True
    assert "glycolytic" in upgraded[0]["blocked_systems"]


def test_unused_upgrade_keeps_low_load_blocked_systems_and_intensities():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 36}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = _gas_tank_athlete()
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert len(upgraded) == 1
    converted = upgraded[0]
    assert "glycolytic" in converted["blocked_systems"]
    assert "high" in converted["blocked_intensities"]
    assert "sprint" in converted["blocked_tags"]
    assert "plyometric" in converted["blocked_tags"]


def test_assign_declared_day_hints_keeps_hard_sparring_day_locked():
    from fightcamp.stage2_role_map import _assign_declared_day_hints

    ordered = [
        {
            "session_index": 1,
            "category": "strength",
            "role_key": "primary_strength_day",
            "scheduled_day_hint": "",
        },
        {
            "session_index": 2,
            "category": "conditioning",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Wednesday",
        },
    ]
    athlete = {
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday"],
        "hard_sparring_days": ["Wednesday"],
    }

    assigned = _assign_declared_day_hints(ordered, athlete, hard_sparring_plan=[{"day": "Wednesday", "status": "hard_as_planned"}])
    hard_role = next(role for role in assigned if role.get("role_key") == "hard_sparring_day")

    assert hard_role.get("scheduled_day_hint") == "Wednesday"


def test_hard_sparring_locked_day_blocks_other_assignments():
    from fightcamp.stage2_role_map import _assign_declared_day_hints

    ordered = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Wednesday",
        },
        {
            "session_index": 2,
            "category": "strength",
            "role_key": "primary_strength_day",
            "scheduled_day_hint": "Wednesday",
        },
    ]
    athlete = {
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday"],
        "hard_sparring_days": ["Wednesday"],
    }

    assigned = _assign_declared_day_hints(
        ordered,
        athlete,
        hard_sparring_plan=[{"day": "Wednesday", "status": "hard_as_planned"}],
    )
    hard_role = next(role for role in assigned if role.get("role_key") == "hard_sparring_day")
    strength_role = next(role for role in assigned if role.get("role_key") == "primary_strength_day")

    assert hard_role.get("scheduled_day_hint") == "Wednesday"
    assert strength_role.get("scheduled_day_hint") != "Wednesday"


# ---------------------------------------------------------------------------
# Mobility / recovery support protection
# ---------------------------------------------------------------------------


def _rehab_athlete(**overrides):
    base = {
        "key_goals": ["rehab"],
        "weaknesses": ["shoulder"],
        "injuries": ["shoulder"],
    }
    base.update(overrides)
    return base


def _recovery_athlete(**overrides):
    base = {
        "key_goals": ["recovery", "fatigue_management"],
        "goals": ["freshness"],
    }
    base.update(overrides)
    return base


def test_converted_mobility_role_carries_protection_flags():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 36}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = _mobility_athlete()
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert len(upgraded) == 1
    role = upgraded[0]
    assert role["role_key"] == "converted_mobility_support_day"
    assert role["counts_toward_conditioning_cap"] is False
    assert role["counts_toward_exercise_cap"] is False
    assert role["counts_toward_strength_cap"] is False
    assert role["is_dedicated_recovery_mobility_day"] is True
    assert role["priority_recovery_touch"] is True
    assert role["support_kind"] == "mobility"


def test_converted_rehab_role_carries_protection_flags():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 36}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], _rehab_athlete())
    assert len(upgraded) == 1
    role = upgraded[0]
    assert role["role_key"] == "converted_rehab_friendly_support_day"
    assert role["counts_toward_conditioning_cap"] is False
    assert role["is_dedicated_recovery_mobility_day"] is True
    assert role["support_kind"] == "rehab_friendly"


def test_converted_recovery_flush_role_carries_protection_flags():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 36}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], _recovery_athlete())
    assert len(upgraded) == 1
    role = upgraded[0]
    assert role["role_key"] == "converted_recovery_flush_day"
    assert role["counts_toward_conditioning_cap"] is False
    assert role["is_dedicated_recovery_mobility_day"] is True
    assert role["support_kind"] == "recovery"


def test_converted_gas_tank_role_still_counts_toward_conditioning_cap():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 36}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], _gas_tank_athlete())
    assert len(upgraded) == 1
    role = upgraded[0]
    assert role["role_key"] == "converted_low_aerobic_gas_tank_day"
    assert role["counts_toward_conditioning_cap"] is True
    assert role["support_kind"] == "gas_tank"
    assert role.get("is_dedicated_recovery_mobility_day") is not True


def test_recovery_day_gas_tank_upgrade_keeps_cap_pressure():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "tuesday", "d_day": 36}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, _gas_tank_athlete())
    assert upgraded[0]["role_key"] == "recovery_aerobic_gas_tank_day"
    assert upgraded[0]["counts_toward_conditioning_cap"] is True
    assert upgraded[0]["support_kind"] == "gas_tank"


def test_mobility_support_does_not_consume_conditioning_cap():
    gas_tank_role = {
        "category": "conditioning",
        "role_key": "recovery_aerobic_gas_tank_day",
        "preferred_system": "aerobic",
        "recovery_compatible": True,
        "gas_tank_recovery_touch": True,
        "counts_toward_conditioning_cap": True,
    }
    mobility_role = {
        "category": "conditioning",
        "role_key": "converted_mobility_support_day",
        "preferred_system": "aerobic",
        "recovery_compatible": True,
        "priority_recovery_touch": True,
        "is_dedicated_recovery_mobility_day": True,
        "counts_toward_conditioning_cap": False,
    }
    # Predicate still recognises both as low-aerobic support semantically.
    assert _is_low_aerobic_support_role(gas_tank_role) is True
    assert _is_low_aerobic_support_role(mobility_role) is True
    # But the cap counter only counts the gas-tank role.
    assert _count_low_aerobic_support_roles([gas_tank_role, mobility_role]) == 1


def test_mobility_support_does_not_block_gas_tank_in_same_week():
    """Mobility support already present must not displace gas-tank cap room."""
    week = {
        "phase": "GPP",
        "calendar_days": [
            {"weekday": "tuesday", "d_day": 36},
            {"weekday": "thursday", "d_day": 34},
        ],
        # The week already has its mobility touch from a previous step.
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    mobility_role = {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "converted_mobility_support_day",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "tuesday",
        "recovery_compatible": True,
        "priority_recovery_touch": True,
        "is_dedicated_recovery_mobility_day": True,
        "counts_toward_conditioning_cap": False,
    }
    # High-cut athlete: gas-tank cap is 1. The mobility role must not eat it.
    athlete = _gas_tank_athlete(cut_severity_bucket="high")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [mobility_role], athlete)
    converted_gas = [
        r for r in upgraded if r["role_key"] == "converted_low_aerobic_gas_tank_day"
    ]
    assert len(converted_gas) == 1


def test_dedicated_mobility_role_priority_rank_above_accessories():
    from fightcamp.stage2_role_map import _non_spar_role_priority_rank

    mobility_role = {
        "category": "conditioning",
        "role_key": "converted_mobility_support_day",
        "preferred_system": "aerobic",
        "is_dedicated_recovery_mobility_day": True,
    }
    accessory_role = {
        "category": "strength",
        "role_key": "secondary_strength_day",
    }
    primary_strength = {
        "category": "strength",
        "role_key": "primary_strength_day",
    }

    # GPP: primary_strength=4, mobility=3, accessory=2 → mobility above accessory, below primary.
    mobility_rank = _non_spar_role_priority_rank(
        mobility_role, "GPP", is_hard_spar_week=True, is_meaningful_cut=False
    )
    accessory_rank = _non_spar_role_priority_rank(
        accessory_role, "GPP", is_hard_spar_week=True, is_meaningful_cut=False
    )
    primary_rank = _non_spar_role_priority_rank(
        primary_strength, "GPP", is_hard_spar_week=True, is_meaningful_cut=False
    )
    assert mobility_rank > accessory_rank
    assert mobility_rank < primary_rank


def test_dedicated_mobility_role_survives_hard_fatigue_compression():
    """Under high-fatigue spar-first compression with one non-spar slot, a dedicated
    mobility role wins the tiebreak against a generic aerobic conditioning role."""
    from fightcamp.stage2_role_map import _apply_high_fatigue_week_compression

    week = {
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 27},
            {"weekday": "wednesday", "d_day": 25},
            {"weekday": "friday", "d_day": 23},
        ],
        "resolved_rule_state": {},
    }
    # Generic aerobic conditioning (no protection flag), appended first.
    generic_aerobic = {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "aerobic_support_day",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "monday",
    }
    # Dedicated mobility support, appended LAST (matches real upgrade ordering).
    mobility = {
        "session_index": 2,
        "category": "conditioning",
        "role_key": "converted_mobility_support_day",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "wednesday",
        "is_dedicated_recovery_mobility_day": True,
        "priority_recovery_touch": True,
        "counts_toward_conditioning_cap": False,
    }
    # Hard sparring fills the Friday slot.
    hard_spar = {
        "session_index": 3,
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "scheduled_day_hint": "friday",
    }
    athlete = {
        "training_days": ["monday", "wednesday", "friday"],
        "hard_sparring_days": ["friday"],
        "training_frequency": 3,
        "fatigue": "high",
    }
    kept, _suppressed = _apply_high_fatigue_week_compression(
        week, [generic_aerobic, mobility, hard_spar], [], athlete,
    )
    kept_keys = {r["role_key"] for r in kept}
    assert "converted_mobility_support_day" in kept_keys
    assert "hard_sparring_day" in kept_keys
    # Only one non-spar slot remained, generic aerobic was dropped first.
    assert "aerobic_support_day" not in kept_keys


def test_mobility_goal_with_hard_sparring_keeps_mobility_role():
    week = {
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 27},
            {"weekday": "wednesday", "d_day": 25},
            {"weekday": "friday", "d_day": 23},
        ],
        "intentionally_unused_days": [{"day": "wednesday", "role": "off_day"}],
    }
    athlete = _mobility_athlete(
        training_days=["monday", "wednesday", "friday"],
        hard_sparring_days=["monday", "friday"],
    )
    plan = [
        {"day": "monday", "status": "hard_as_planned"},
        {"day": "friday", "status": "hard_as_planned"},
    ]
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete, hard_sparring_plan=plan)
    role_keys = [r["role_key"] for r in upgraded]
    assert "converted_mobility_support_day" in role_keys
    mobility_role = next(r for r in upgraded if r["role_key"] == "converted_mobility_support_day")
    assert mobility_role["counts_toward_conditioning_cap"] is False
    assert mobility_role["is_dedicated_recovery_mobility_day"] is True


def test_mobility_red_flag_injury_still_suppresses_mobility_creation():
    """Safety must still win — red-flag injury blocks mobility conversion."""
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete = _mobility_athlete(
        cut_severity_bucket="critical",
        readiness_flags=["red_flag_injury"],
    )
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    assert upgraded == []
    assert week["intentionally_unused_days"][0].get("low_aerobic_cap_skipped") is True


def test_mobility_support_added_when_conditioning_cap_already_full():
    """If a gas-tank role already fills the conditioning cap, a mobility
    support conversion should still be added when the profile justifies it
    and safety gates are clear — the mobility role does not consume the cap."""
    week = {
        "phase": "GPP",
        "calendar_days": [
            {"weekday": "tuesday", "d_day": 36},
            {"weekday": "thursday", "d_day": 34},
        ],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    # Pre-existing gas-tank role that counts toward the conditioning cap.
    gas_tank_role = {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "recovery_aerobic_gas_tank_day",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "tuesday",
        "recovery_compatible": True,
        "gas_tank_recovery_touch": True,
        "counts_toward_conditioning_cap": True,
    }
    # High-cut mobility-profile athlete → cap is 1, already filled by the
    # gas-tank role. Mobility support must still be allowed through.
    athlete = _mobility_athlete(cut_severity_bucket="high")
    upgraded = _upgrade_unused_days_to_low_load_support(
        week, [gas_tank_role], athlete
    )
    role_keys = [r["role_key"] for r in upgraded]
    assert "recovery_aerobic_gas_tank_day" in role_keys
    assert "converted_mobility_support_day" in role_keys
    mobility = next(
        r for r in upgraded if r["role_key"] == "converted_mobility_support_day"
    )
    assert mobility["counts_toward_conditioning_cap"] is False
    assert mobility["is_dedicated_recovery_mobility_day"] is True
    # Not annotated as cap-skipped — the day was converted, not skipped.
    assert week["intentionally_unused_days"] == []


def test_mobility_support_does_not_increment_cap_count_for_later_iterations():
    """Two-day mobility week: both unused days should convert, because mobility
    roles do not consume cap budget. (legacy_phase_ceiling still bounds them at 2.)"""
    week = {
        "phase": "GPP",
        "calendar_days": [
            {"weekday": "tuesday", "d_day": 36},
            {"weekday": "thursday", "d_day": 34},
        ],
        "intentionally_unused_days": [
            {"day": "tuesday", "role": "off_day"},
            {"day": "thursday", "role": "off_day"},
        ],
    }
    # cut_severity_bucket="high" → underlying cap is 1, but mobility bypasses it.
    athlete = _mobility_athlete(cut_severity_bucket="high")
    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete)
    mobility_roles = [
        r for r in upgraded if r["role_key"] == "converted_mobility_support_day"
    ]
    # Both days converted — cap of 1 did not block the second mobility role.
    assert len(mobility_roles) == 2
    assert all(r["counts_toward_conditioning_cap"] is False for r in mobility_roles)
    assert week["intentionally_unused_days"] == []
