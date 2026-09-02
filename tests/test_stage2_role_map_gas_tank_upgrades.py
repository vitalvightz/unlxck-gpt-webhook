from fightcamp.stage2_role_map import (
    _assign_declared_day_hints,
    _build_weekly_role_map,
    _upgrade_recovery_days_to_gas_tank,
    _upgrade_unused_days_to_low_load_support,
)
from fightcamp import stage2_payload
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet


def test_recovery_upgrade_adds_gas_tank_preferences_and_label():
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
    athlete_model = {
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
    }

    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete_model)
    assert upgraded[0]["category"] == "conditioning"
    assert upgraded[0]["role_key"] == "recovery_aerobic_gas_tank_day"
    assert upgraded[0]["athlete_facing_label"] == "Low aerobic gas-tank flush"
    assert upgraded[0]["preferred_exercise_names"] == [
        "Assault Bike Easy Gas Tank Ride",
        "Rower Nasal Aerobic Base",
        "Nasal Shadowboxing Flow (Gas Tank)",
        "Nasal Walk with Boxing Posture",
    ]


def test_recovery_upgrade_does_not_default_on_without_explicit_signal():
    week = {"phase": "SPP", "calendar_days": [{"weekday": "thursday", "d_day": 27}]}
    session_roles = [
        {"session_index": 1, "category": "recovery", "role_key": "recovery_reset_day", "scheduled_day_hint": "thursday"}
    ]
    athlete_model = {"fatigue": "moderate", "cut_severity_bucket": "moderate"}

    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete_model)
    assert upgraded[0]["role_key"] == "recovery_reset_day"


def test_recovery_upgrade_stays_recovery_on_high_cut_plus_high_fatigue_without_explicit_signal():
    week = {"phase": "SPP", "calendar_days": [{"weekday": "thursday", "d_day": 27}]}
    session_roles = [
        {"session_index": 1, "category": "recovery", "role_key": "recovery_reset_day", "scheduled_day_hint": "thursday"}
    ]
    athlete_model = {
        "fatigue": "high",
        "cut_severity_bucket": "high",
        "readiness_flags": ["high_fatigue", "active_weight_cut"],
    }

    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete_model)
    assert upgraded[0]["role_key"] == "recovery_reset_day"


def test_unused_day_gas_tank_conversion_removes_day_from_intentionally_unused():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}, {"weekday": "saturday", "d_day": 25}],
        "intentionally_unused_days": [
            {"day": "thursday", "role": "off_day"},
            {"day": "saturday", "role": "off_day"},
        ],
    }
    athlete_model = {"key_goals": ["conditioning"]}

    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete_model)
    assert len(upgraded) == 1
    assert all(role["role_key"] == "converted_low_aerobic_gas_tank_day" for role in upgraded)
    assert week["intentionally_unused_days"] == [
        {
            "day": "saturday",
            "role": "off_day",
            "low_aerobic_cap_skipped": True,
            "low_aerobic_cap_reason": "Low-aerobic support cap reached (1); cut severity, phase, fatigue, or readiness blocked the upgrade for saturday.",
        }
    ]


def test_unused_day_upgrade_protects_d_minus_1_and_d_minus_0():
    week = {"phase": "SPP", "calendar_days": [{"weekday": "thursday", "d_day": 1}], "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}]}
    athlete_model = {
        "weaknesses": ["conditioning"],
    }

    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete_model)
    assert upgraded == []
    assert week["intentionally_unused_days"][0]["role"] == "off_day"




def test_unused_day_upgrade_does_not_trigger_from_non_gas_goal_signal():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete_model = {"key_goals": ["power"]}

    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete_model)
    assert upgraded == []
    assert week["intentionally_unused_days"][0]["role"] == "off_day"



def test_unused_day_upgrade_allows_gas_tank_goal_signal():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete_model = {"key_goals": ["conditioning"]}

    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete_model)
    assert len(upgraded) == 1
    assert upgraded[0]["role_key"] == "converted_low_aerobic_gas_tank_day"
    assert week["intentionally_unused_days"] == []


def test_unused_day_upgrade_does_not_convert_coordination_only_signal():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete_model = {"key_goals": ["coordination"]}

    upgraded = _upgrade_unused_days_to_low_load_support(week, [], athlete_model)
    assert upgraded == []
    assert week["intentionally_unused_days"][0]["role"] == "off_day"

def test_unused_day_upgrade_skips_days_with_existing_session_role():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    session_roles = [{"session_index": 1, "category": "sparring", "role_key": "hard_sparring_day", "scheduled_day_hint": "thursday"}]
    athlete_model = {"weaknesses": ["conditioning"]}

    upgraded = _upgrade_unused_days_to_low_load_support(week, session_roles, athlete_model)
    assert len(upgraded) == 1
    assert upgraded[0]["role_key"] == "hard_sparring_day"
    assert week["intentionally_unused_days"][0]["role"] == "off_day"


def test_weekly_role_map_roles_carry_countdown_labels_for_renderers():
    athlete_model = {
        "sport_style": "boxing",
        "training_days": ["monday", "wednesday", "friday"],
        "fight_date": "2027-07-18",
    }
    week_by_week_progression = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1},
                "conditioning_sequence": ["aerobic"],
            }
        ]
    }
    limiter_profile = {"key": "conditioning_endurance"}

    role_map = _build_weekly_role_map(athlete_model, week_by_week_progression, limiter_profile)
    roles = role_map["weeks"][0]["session_roles"]
    assert any(str(role.get("scheduled_countdown_label") or "").startswith("D-") for role in roles)


def test_finalizer_packet_keeps_converted_support_session_and_no_unused_placeholder():
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "session_roles": [
                    {
                        "session_index": 1,
                        "category": "conditioning",
                        "role_key": "converted_low_aerobic_gas_tank_day",
                        "scheduled_day_hint": "tuesday",
                        "athlete_facing_label": "Low aerobic gas-tank support",
                        "allowed_on_recovery_day": True,
                        "recovery_compatible": True,
                    }
                ],
                "intentionally_unused_days": [],
            }
        ]
    }
    packet = build_stage2_finalizer_packet(stage2_payload={"weekly_role_map": weekly_role_map, "athlete_model": {}}, planning_brief={})
    weeks = packet["selected_plan"]["weekly_role_map"]["weeks"]
    assert weeks[0]["session_roles"][0]["role_key"] == "converted_low_aerobic_gas_tank_day"
    assert "intentionally_unused_days" not in weeks[0] or weeks[0]["intentionally_unused_days"] == []


def test_build_planning_brief_uses_stage2_role_map_builder(monkeypatch):
    called = {"builder": False}

    def _mark_builder(athlete_model, week_by_week_progression, limiter_profile, fight_week_override=None):
        called["builder"] = True
        return {"model": "session_role_overlay.v1", "weeks": [], "fight_week_override": {"active": False}}

    monkeypatch.setattr(stage2_payload.stage2_role_map_module, "_build_weekly_role_map", _mark_builder)

    athlete_model = {
        "full_name": "Test Athlete",
        "age": 27,
        "current_weight": 72,
        "target_weight": 72,
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "camp_length_weeks": 6,
        "days_until_fight": 28,
        "fight_date": "2027-07-18",
        "short_notice": False,
        "fatigue": "high",
        "fatigue_level": "high",
        "readiness_flags": ["high_fatigue"],
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "support_work_days": ["friday"],
        "key_goals": ["gas tank"],
        "weak_areas": ["conditioning"],
        "injuries": [],
    }
    phase_briefs = {
        "SPP": {
            "objective": "fight readiness",
            "emphasize": ["sport speed"],
            "deprioritize": [],
            "risk_flags": [],
            "selection_guardrails": {
                "must_keep_if_present": [],
                "conditioning_drop_order_if_thin": [],
            },
        }
    }
    _ = stage2_payload.build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools={"SPP": {"strength_slots": [], "conditioning_slots": [], "rehab_slots": []}},
        omission_ledger={},
        rewrite_guidance={},
    )
    assert called["builder"] is True

def test_sandwiched_days_prefer_low_load_support_and_primary_strength_stays_off_collision_days():
    # Alternating spar/S&C week: sparring Mon/Wed/Fri, S&C on the off days
    # Tue/Thu/Sat. Low-load aerobic/recovery support belongs on the between-hard
    # days (ALLOW). Primary strength does NOT: Tue and Thu are between two hard
    # contacts (between_hard_contacts_meaningful_or_neural_stress -> FORBID) and
    # Sat is immediately after Friday's hard contact
    # (post_hard_contact_meaningful_stress -> FORBID). Step 9B change: the old
    # local rule treated Sat as "clean" and placed meaningful strength there; the
    # canonical combat_load_policy forbids every training day for it, so the owner
    # leaves it dayless (unavailable) rather than committing a forbidden slot.
    athlete_model = {
        "training_days": ["tuesday", "thursday", "saturday"],
        "support_work_days": ["tuesday", "thursday", "saturday"],
        "hard_sparring_days": ["monday", "wednesday", "friday"],
    }
    roles = _assign_declared_day_hints(
        [
            {"session_index": 1, "category": "strength", "role_key": "primary_strength_day"},
            {"session_index": 2, "category": "conditioning", "role_key": "aerobic_support_day", "preferred_system": "aerobic", "allowed_on_recovery_day": True},
            {"session_index": 3, "category": "recovery", "role_key": "recovery_reset_day"},
        ],
        athlete_model,
        hard_sparring_plan=[
            {"day": "monday", "status": "hard_as_planned"},
            {"day": "wednesday", "status": "hard_as_planned"},
            {"day": "friday", "status": "hard_as_planned"},
        ],
    )

    primary = next(role for role in roles if role.get("category") == "strength")
    aerobic = next(role for role in roles if role.get("category") == "conditioning" and role.get("preferred_system") == "aerobic")

    # Low-load support still lands on the between-hard (ALLOW) days...
    assert aerobic.get("scheduled_day_hint") in {"tuesday", "thursday"}
    # ...but meaningful strength has no legal day, so it is not force-placed on a
    # forbidden one (FORBID means unavailable, not merely dispreferred).
    assert not str(primary.get("scheduled_day_hint") or "").strip()
