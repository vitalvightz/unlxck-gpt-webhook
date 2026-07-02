"""Focused tests for the late-fight Stage 2 payload split."""

import pytest

from fightcamp.stage2_payload import (
    _build_late_fight_plan_spec,
    _build_late_fight_weekly_role_map,
    _days_out_payload_block,
    _days_out_payload_mode,
    _late_fight_permissions,
    _late_fight_rendering_rules,
    _normalized_fatigue_level,
    _is_app_owned_visible_role,
    build_planning_brief,
    build_stage2_handoff_text,
    build_stage2_payload,
)
from fightcamp.stage2_payload_late_fight import (
    CANONICAL_HARD_SPARRING_LABEL,
    CANONICAL_HARD_SPARRING_NOTE,
    _handoff_mode_instructions,
    _late_fight_legal_offsets,
    _late_fight_stage_label,
    _late_fight_taper_micro_support_policy,
    _normalized_fatigue,
)
from fightcamp.training_context import TrainingContext


_MINIMAL_ATHLETE = {
    "full_name": "Test Athlete",
    "age": 26,
    "current_weight": 155,
    "target_weight": 155,
    "stance": "orthodox",
    "technical_style": "boxing",
    "tactical_style": "pressure",
    "professional_status": "amateur",
    "record": "5-0",
    "athlete_timezone": "America/New_York",
    "fight_date": "2026-04-10",
    "rounds_format": "3x3",
    "weekly_training_frequency": 5,
    "fatigue_level": "moderate",
    "key_goals": ["power", "speed"],
    "weak_areas": ["cardio"],
    "training_preference": "short sessions",
    "equipment_access": ["bodyweight", "dumbbells"],
    "injuries": [],
    "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "hard_sparring_days": ["tuesday", "thursday"],
        "support_work_days": ["friday"],
    "mindset_challenges": "",
    "notes": "",
    "restrictions": [],
    "sport": "boxing",
    "status": "amateur",
    "camp_length_weeks": 6,
    "short_notice": False,
}


def _athlete(days_until_fight, **overrides):
    athlete = dict(_MINIMAL_ATHLETE)
    athlete["days_until_fight"] = days_until_fight
    athlete.setdefault("fatigue", "moderate")
    athlete.setdefault("readiness_flags", [])
    athlete.update(overrides)
    return athlete


@pytest.mark.parametrize(
    ("athlete_model", "expected"),
    [
        ({"readiness_flags": ["high_fatigue"]}, "high"),
        ({"readiness_flags": ["moderate_fatigue"]}, "moderate"),
        ({"fatigue_level": "high"}, "high"),
        (
            {"fatigue": "moderate", "fatigue_level": "high", "readiness_flags": ["high_fatigue"]},
            "moderate",
        ),
    ],
)
def test_fatigue_normalization_matches_regular_and_late_fight_paths(athlete_model, expected):
    assert _normalized_fatigue_level(athlete_model) == expected
    assert _normalized_fatigue(athlete_model) == expected


def test_hard_sparring_render_contract_is_canonical_in_late_fight_handoff():
    instructions = _handoff_mode_instructions("bridge_compression_payload")
    assert CANONICAL_HARD_SPARRING_LABEL in instructions
    assert CANONICAL_HARD_SPARRING_NOTE in instructions


def _build_brief_for(days_until_fight, *, phase="SPP", athlete_overrides=None):
    athlete_model = _athlete(days_until_fight, **(athlete_overrides or {}))
    phase_briefs = {
        phase: {
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
    candidate_pools = {
        phase: {
            "strength_slots": [{"role": "primary_strength"}],
            "conditioning_slots": [{"role": "alactic"}, {"role": "glycolytic"}],
            "rehab_slots": [],
        }
    }
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )


def _build_stage2(days):
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=5,
        days_available=5,
        training_days=["Mon", "Tue", "Wed", "Thu", "Fri"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure"],
        weaknesses=["cardio"],
        equipment=["bodyweight", "dumbbells"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["power"],
        training_preference="short sessions",
        mental_block=[],
        age=26,
        weight=155.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 0, "SPP": 0, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": days or 7}},
        days_until_fight=days,
        hard_sparring_days=["Tue", "Thu"],
        support_work_days=["Fri"],
    )
    return build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="5-0",
        rounds_format="3x3",
        camp_len=6,
        short_notice=False,
        restrictions=[],
        phase_weeks={"TAPER": 1, "days": {"TAPER": days or 7}},
        strength_blocks={},
        conditioning_blocks={},
        rehab_blocks={},
    )


def _composite_stage_keys(sequence):
    return [
        entry.get("composite_segment_stage_key")
        for entry in sequence
        if entry.get("composite_segment_stage_key")
    ]


class TestPayloadModeClassification:
    @pytest.mark.parametrize(
        "days, expected",
        [
            (None, "camp_payload"),
            (-2, "camp_payload"),
            (22, "camp_payload"),
            (21, "bridge_compression_payload"),
            (17, "bridge_compression_payload"),
            (14, "bridge_compression_payload"),
            (13, "pre_fight_compressed_payload"),
            (10, "pre_fight_compressed_payload"),
            (8, "pre_fight_compressed_payload"),
            (7, "late_fight_week_payload"),
            (6, "late_fight_transition_payload"),
            (5, "late_fight_transition_payload"),
            (4, "late_fight_session_payload"),
            (2, "late_fight_session_payload"),
            (1, "pre_fight_day_payload"),
            (0, "fight_day_protocol_payload"),
        ],
    )
    def test_mode_mapping(self, days, expected):
        assert _days_out_payload_mode(days) == expected

    def test_string_input_still_works(self):
        assert _days_out_payload_mode("8") == "pre_fight_compressed_payload"
        assert _days_out_payload_mode("3") == "late_fight_session_payload"
        assert _days_out_payload_mode("0") == "fight_day_protocol_payload"

    def test_bridge_legal_offsets_carry_countdown_continuity(self):
        assert _late_fight_legal_offsets(16) == list(range(16, 0, -1))


class TestDaysOutPayloadBlock:
    def test_camp_block_uses_camp_bucket(self):
        block = _days_out_payload_block(28, _athlete(28))
        assert block["payload_mode"] == "camp_payload"
        assert block["payload_variant"] == "normal_stage2_payload"
        assert block["days_out_bucket"] == "CAMP"
        assert block["fight_week_override"] == {"active": False}

    def test_bridge_block_uses_bridge_mode(self):
        block = _days_out_payload_block(20, _athlete(20))
        assert block["payload_mode"] == "bridge_compression_payload"
        assert block["payload_variant"] == "late_fight_stage2_payload"
        assert block["days_out_bucket"] == "D-20"
        assert block["late_fight_window"] == "d21_to_d14"


def test_camp_week_four_session_boxing_keeps_coach_days_and_recovery_flush_visible():
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=4,
        days_available=6,
        training_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["distance striker"],
        weaknesses=["speed"],
        equipment=["bands", "medicine_ball", "kettlebell", "assault_bike"],
        weight_cut_risk=True,
        weight_cut_pct=4.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["speed", "power", "recovery"],
        training_preference="short sessions",
        mental_block=[],
        age=26,
        weight=155.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 2, "days": {"GPP": 14, "SPP": 14, "TAPER": 14}},
        days_until_fight=28,
        hard_sparring_days=["Mon", "Fri"],
        support_work_days=["Tue", "Thu", "Sat"],
    )
    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="5-0",
        rounds_format="3x3",
        camp_len=8,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 2, "days": {"GPP": 14, "SPP": 14, "TAPER": 14}},
        strength_blocks={},
        conditioning_blocks={},
        rehab_blocks={},
    )

    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload.get("restrictions", []),
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )

    week = brief["weekly_role_map"]["weeks"][0]
    session_roles = week["session_roles"]
    hard_days = {
        str(role.get("scheduled_day_hint") or "").lower()
        for role in session_roles
        if role.get("role_key") == "hard_sparring_day"
    }
    assert hard_days == {"mon", "fri"}

    recovery_flush_days = [
        str(role.get("scheduled_day_hint") or "").lower()
        for role in session_roles
        if role.get("role_key") == "converted_recovery_flush_day"
    ]
    assert recovery_flush_days
    assert any(day in {"thu", "sat"} for day in recovery_flush_days)

    def test_pre_fight_compressed_block_has_bridge_window_metadata(self):
        block = _days_out_payload_block(10, _athlete(10))
        assert block["payload_mode"] == "pre_fight_compressed_payload"
        assert block["payload_variant"] == "late_fight_stage2_payload"
        assert block["days_out_bucket"] == "D-10"
        assert block["late_fight_window"] == "d13_to_d8"
        assert "rendering_rules" in block
        assert "late_fight_permissions" in block

    def test_late_fight_block_has_mode_specific_metadata(self):
        block = _days_out_payload_block(3, _athlete(3))
        assert block["payload_mode"] == "late_fight_session_payload"
        assert block["payload_variant"] == "late_fight_stage2_payload"
        assert block["days_out_bucket"] == "D-3"
        assert block["late_fight_window"] == "d4_to_d2"
        assert "rendering_rules" in block
        assert "late_fight_permissions" in block
        assert "permission_policy" in block
        assert "role_budget" in block


class TestLateFightPermissionsAndRendering:
    def test_camp_permissions_remain_unrestricted(self):
        permissions = _late_fight_permissions(28, _athlete(28))
        rules = _late_fight_rendering_rules(28)
        assert permissions["allow_full_weekly_structure"] is True
        assert permissions["allow_development_language"] is True
        assert rules == {"mode": "camp_payload", "rules": []}

    def test_bridge_permissions_apply_evidence_based_caps(self):
        permissions = _late_fight_permissions(20, _athlete(20, fatigue="low"))
        rules = _late_fight_rendering_rules(20)

        assert permissions["mode"] == "bridge_compression_payload"
        assert permissions["allow_full_weekly_structure"] is False
        assert permissions["allow_development_language"] is False
        assert permissions["allow_glycolytic_build"] is False
        assert permissions["max_active_roles"] == 3
        assert permissions["max_meaningful_stress_exposures"] == 3
        # Two declared hard sparring days are coach-owned combat locks, so the
        # surfaced cap floors at the declared count instead of asking the
        # renderer to drop one.
        assert permissions["hard_sparring_cap"] == 2
        assert permissions["freshness_mandatory"] is True
        assert permissions["double_stress_day_allowed"] is False
        assert "bridge week" in [term.lower() for term in rules["preferred_terms"]]

    def test_bridge_permissions_trim_stress_when_fatigued(self):
        permissions = _late_fight_permissions(20, _athlete(20, fatigue="moderate"))
        # Moderate fatigue must reduce the meaningful-stress cap by one.
        assert permissions["max_meaningful_stress_exposures"] == 2
        assert permissions["freshness_mandatory"] is True

    def test_pre_fight_compressed_permissions_cap_bridge_window_stress(self):
        permissions = _late_fight_permissions(10, _athlete(10))
        rules = _late_fight_rendering_rules(10)

        assert permissions["allow_full_weekly_structure"] is False
        assert permissions["allow_compressed_weekly_structure"] is True
        assert permissions["allow_normal_session_roles"] is True
        assert permissions["allow_development_language"] is False
        assert permissions["allow_glycolytic_build"] is False
        assert permissions["max_meaningful_strength_anchors"] == 1
        assert permissions["max_meaningful_conditioning_stressors"] == 1
        assert permissions["max_meaningful_stress_exposures"] == 3
        assert permissions["max_active_roles"] == 4
        assert "compressed week" in [term.lower() for term in rules["preferred_terms"]]
        assert "conditioning build" in [term.lower() for term in rules["forbidden_terms"]]

    def test_d1_forbids_anchor_and_glycolytic_language(self):
        permissions = _late_fight_permissions(1, _athlete(1))
        rules = _late_fight_rendering_rules(1)
        preferred_terms = [term.lower() for term in rules["preferred_terms"]]

        assert permissions["allow_anchor_wording"] is False
        assert permissions["allow_glycolytic_build"] is False
        assert "anchor" in [term.lower() for term in rules["forbidden_terms"]]
        assert "neural primer" in preferred_terms
        assert "primer" not in preferred_terms

    def test_d0_restricts_output_to_protocol_language(self):
        permissions = _late_fight_permissions(0, _athlete(0))
        rules = _late_fight_rendering_rules(0)
        assert permissions["allow_fight_day_protocol_only"] is True
        assert permissions["allow_normal_session_roles"] is False
        assert "activation" in [term.lower() for term in rules["preferred_terms"]]
        assert "warm-up" in [term.lower() for term in rules["preferred_terms"]]
        assert "walk-through" in [term.lower() for term in rules["preferred_terms"]]

    def test_d7_rendering_rules_prefer_sharpness_week_language(self):
        rules = _late_fight_rendering_rules(7)

        assert "sharpness week" in [term.lower() for term in rules["preferred_terms"]]
        assert "power touch" in [term.lower() for term in rules["preferred_terms"]]
        assert "primary strength" in [term.lower() for term in rules["forbidden_terms"]]

    def test_d3_rendering_rules_prefer_low_noise_session_titles(self):
        rules = _late_fight_rendering_rules(3)

        assert "sharpness session" in [term.lower() for term in rules["preferred_terms"]]
        assert "freshness session" in [term.lower() for term in rules["preferred_terms"]]
        assert "strength block" in [term.lower() for term in rules["forbidden_terms"]]

    def test_final_week_rendering_rules_cap_primer_intensity(self):
        d7_rules = _late_fight_rendering_rules(7)
        d6_rules = _late_fight_rendering_rules(6)
        d1_rules = _late_fight_rendering_rules(1)

        assert any("RPE 6-7" in rule and "3-4 x 6 sec" in rule for rule in d7_rules["rules"])
        assert "all-out bursts" in d7_rules["forbidden_terms"]
        assert "RPE 8" in d7_rules["forbidden_terms"]
        assert any("RPE 6-7" in rule and "3-4 x 6 sec" in rule for rule in d6_rules["rules"])
        assert "all-out bursts" in d6_rules["forbidden_terms"]
        assert any("RPE 3-5" in rule for rule in d1_rules["rules"])
        assert "RPE 6-7" in d1_rules["forbidden_terms"]

    def test_d10_taper_micro_support_policy_stays_optional_and_off_the_role_map(self):
        spec = _build_late_fight_plan_spec(10, _athlete(10))
        policy = spec["taper_micro_support_policy"]

        assert policy["tag"] == "taper_micro_support"
        assert policy["optional_add_on_only"] is True
        assert policy["never_primary_anchor"] is True
        assert policy["standalone_session_allowed"] is False
        assert policy["max_items"] == 1
        assert policy["max_total_minutes"] == 6
        assert "taper_micro_support_day" not in spec["session_roles"]
        assert "taper_micro_support_day" not in spec["visible_session_roles"]

    def test_d1_taper_micro_support_policy_blocks_core_neck_heavy_bag_and_grip(self):
        policy = _late_fight_taper_micro_support_policy(1, _athlete(1))

        assert set(policy["suppressed_categories"]) >= {"core", "neck", "heavy_bag", "grip"}
        assert set(policy["d1_blocked_list"]) >= {"core", "neck", "heavy_bag", "grip"}

    def test_boxing_taper_micro_support_policy_blocks_grip_even_when_window_allows_other_add_ons(self):
        policy = _late_fight_taper_micro_support_policy(8, _athlete(8, sport="boxing"))

        assert "grip" in policy["suppressed_categories"]
        assert "boxing_taper_blocks_grip" in policy["suppression_reasons"]

    def test_high_fatigue_taper_micro_support_policy_reduces_to_breathing_and_mobility_only(self):
        policy = _late_fight_taper_micro_support_policy(
            8,
            _athlete(8, fatigue="high", fatigue_level="high"),
        )

        assert policy["allowed_categories"] == ["breathing", "mobility"]
        assert "high_fatigue_breathing_mobility_only" in policy["suppression_reasons"]

    def test_moderate_weight_cut_suppresses_core_neck_heavy_bag_and_grip_micro_support(self):
        policy = _late_fight_taper_micro_support_policy(
            8,
            _athlete(
                8,
                weight_cut_risk=True,
                weight_cut_pct=3.5,
                cut_severity_bucket="moderate",
            ),
        )

        assert set(policy["suppressed_categories"]) >= {"core", "neck", "heavy_bag", "grip"}
        assert "moderate_or_high_weight_cut_blocks_nonessential_micro_support" in policy["suppression_reasons"]

    def test_transition_permissions_strip_week_logic_and_force_caps(self):
        permissions = _late_fight_permissions(5, _athlete(5))

        assert permissions["allow_normal_session_roles"] is False
        assert permissions["allow_anchor_wording"] is False
        assert permissions["allow_weekly_frequency_reasoning"] is False
        assert permissions["allow_hard_sparring_influence"] is False
        assert permissions["max_meaningful_strength_anchors"] == 0
        assert permissions["max_meaningful_conditioning_stressors"] == 0
        assert permissions["max_meaningful_stress_exposures"] == 1
        assert permissions["max_active_roles"] == 2

    def test_d3_alactic_sharpness_is_conditional(self):
        allowed = _late_fight_permissions(3, _athlete(3))
        suppressed = _late_fight_permissions(
            3,
            _athlete(3, fatigue="high", readiness_flags=["recent_hard_spar_collision_spillover"]),
        )

        assert allowed["allow_alactic_sharpness"] is True
        assert suppressed["allow_alactic_sharpness"] is False

    def test_d3_alactic_sharpness_respects_high_fatigue_readiness_flag(self):
        permissions = _late_fight_permissions(
            3,
            _athlete(3, fatigue="", fatigue_level="", readiness_flags=["high_fatigue"]),
        )

        assert permissions["allow_alactic_sharpness"] is False


class TestLateFightRoleMap:
    def test_d5_role_map_uses_transition_overlay(self):
        role_map = _build_late_fight_weekly_role_map(5, _athlete(5))
        assert role_map["model"] == "late_fight_role_overlay.v1"
        assert role_map["payload_mode"] == "late_fight_transition_payload"
        assert [week["stage_key"] for week in role_map["weeks"]] == ["d6_to_d5", "d4_to_d2", "d1", "d0"]

    def test_d3_role_map_is_session_list(self):
        role_map = _build_late_fight_weekly_role_map(3, _athlete(3))
        assert role_map["payload_mode"] == "late_fight_session_payload"
        assert [week["stage_key"] for week in role_map["weeks"]] == ["d4_to_d2", "d1", "d0"]

    def test_d0_role_map_has_no_weeks(self):
        role_map = _build_late_fight_weekly_role_map(0, _athlete(0))
        assert role_map["payload_mode"] == "fight_day_protocol_payload"
        assert role_map["weeks"] == []


class TestPlanningBriefBranching:
    def test_d10_stage_label_returns_compressed_pre_fight_week(self):
        assert _late_fight_stage_label(10) == "Compressed Pre-Fight Week"

    def test_d7_stage_label_returns_sharpness_week(self):
        assert _late_fight_stage_label(7) == "Sharpness Week"

    def test_camp_uses_normal_planning_brief(self):
        brief = _build_brief_for(28)
        assert brief["generator_mode"] == "deterministic_planner_plus_ai_finalizer"
        assert "days_out_payload" not in brief
        assert "payload_variant" not in brief
        assert brief["weekly_role_map"]["model"] == "session_role_overlay.v1"

    def test_bridge_window_uses_late_fight_planning_brief(self):
        brief = _build_brief_for(20)
        assert brief["generator_mode"] == "deterministic_late_fight_planner_plus_ai_finalizer"
        assert brief["payload_variant"] == "late_fight_stage2_payload"
        assert brief["days_out_payload"]["payload_mode"] == "bridge_compression_payload"

    def test_bridge_d16_includes_bridge_and_late_stage_continuation(self):
        brief = _build_brief_for(16)
        weeks = brief["week_by_week_progression"]["weeks"]
        spans = [week.get("countdown_span") for week in weeks]
        modes = [week.get("payload_mode") for week in weeks]

        assert spans[0] == {"start_day": 16, "end_day": 14}
        assert spans[1:] == [
            {"start_day": 13, "end_day": 8},
            {"start_day": 7, "end_day": 7},
            {"start_day": 6, "end_day": 5},
            {"start_day": 4, "end_day": 2},
            {"start_day": 1, "end_day": 1},
            {"start_day": 0, "end_day": 0},
        ]
        assert modes == [
            "bridge_compression_payload",
            "pre_fight_compressed_payload",
            "late_fight_week_payload",
            "late_fight_transition_payload",
            "late_fight_session_payload",
            "pre_fight_day_payload",
            "fight_day_protocol_payload",
        ]

    def test_bridge_d21_includes_bridge_and_late_stage_continuation(self):
        brief = _build_brief_for(21)
        weeks = brief["week_by_week_progression"]["weeks"]
        assert weeks[0]["countdown_span"] == {"start_day": 21, "end_day": 14}
        assert [week["payload_mode"] for week in weeks[1:]] == [
            "pre_fight_compressed_payload",
            "late_fight_week_payload",
            "late_fight_transition_payload",
            "late_fight_session_payload",
            "pre_fight_day_payload",
            "fight_day_protocol_payload",
        ]

    def test_bridge_d14_includes_single_bridge_day_then_late_stage_continuation(self):
        brief = _build_brief_for(14)
        weeks = brief["week_by_week_progression"]["weeks"]
        assert weeks[0]["countdown_span"] == {"start_day": 14, "end_day": 14}
        assert weeks[0]["payload_mode"] == "bridge_compression_payload"
        assert weeks[1]["countdown_span"] == {"start_day": 13, "end_day": 8}
        assert weeks[-1]["countdown_span"] == {"start_day": 0, "end_day": 0}

    def test_pre_fight_window_uses_dedicated_planning_brief(self):
        brief = _build_brief_for(10)

        assert brief["generator_mode"] == "deterministic_late_fight_planner_plus_ai_finalizer"
        assert brief["payload_variant"] == "late_fight_stage2_payload"
        assert brief["days_out_payload"]["payload_mode"] == "pre_fight_compressed_payload"
        assert brief["weekly_role_map"]["payload_mode"] == "pre_fight_compressed_payload"
        assert brief["rendering_rules"]["mode"] == "pre_fight_compressed_payload"
        assert brief["week_by_week_progression"]["weeks"][0]["stage_label"] == "Compressed Pre-Fight Week"

    def test_late_fight_uses_dedicated_planning_brief(self):
        brief = _build_brief_for(3)
        assert brief["generator_mode"] == "deterministic_late_fight_planner_plus_ai_finalizer"
        assert brief["payload_variant"] == "late_fight_stage2_payload"
        assert brief["days_out_payload"]["payload_mode"] == "late_fight_session_payload"
        assert brief["weekly_role_map"]["payload_mode"] == "late_fight_session_payload"
        assert brief["rendering_rules"]["mode"] == "late_fight_session_payload"
        assert [week["stage_key"] for week in brief["week_by_week_progression"]["weeks"]] == [
            "d4_to_d2",
            "d1",
            "d0",
        ]
        assert [week["stage_key"] for week in brief["weekly_role_map"]["weeks"]] == [
            "d4_to_d2",
            "d1",
            "d0",
        ]
        app_sequence = [
            entry
            for entry in brief["late_fight_session_sequence"]
            if _is_app_owned_visible_role(entry.get("role_key"))
        ]
        assert [entry["role_key"] for entry in app_sequence] == [
            "fight_week_freshness_day",
            "tactical_cue_card",
        ]
        assert any(entry["role_key"] == "hard_sparring_day" for entry in brief["late_fight_session_sequence"])

    def test_d0_planning_brief_has_empty_progression(self):
        brief = _build_brief_for(0)
        assert brief["days_out_payload"]["payload_mode"] == "fight_day_protocol_payload"
        assert brief["week_by_week_progression"]["weeks"] == []
        assert brief["weekly_role_map"]["weeks"] == []

    def test_d1_planning_brief_has_no_week_structure(self):
        brief = _build_brief_for(1)
        assert brief["days_out_payload"]["payload_mode"] == "pre_fight_day_payload"
        assert brief["week_by_week_progression"]["weeks"] == []
        assert brief["weekly_role_map"]["weeks"] == []
        app_sequence = [
            entry
            for entry in brief["late_fight_session_sequence"]
            if _is_app_owned_visible_role(entry.get("role_key"))
        ]
        assert [entry["role_key"] for entry in app_sequence] == ["tactical_cue_card"]
        assert any(entry["role_key"] == "hard_sparring_day" for entry in brief["late_fight_session_sequence"])

    def test_d7_planning_brief_uses_sharpness_week_labels(self):
        brief = _build_brief_for(7)

        week = brief["week_by_week_progression"]["weeks"][0]
        assert week["stage_label"] == "Sharpness Week"
        assert "power touch" in week["stage_objective"].lower()
        assert "freshness" in week["stage_objective"].lower()

    def test_d13_planning_brief_continues_through_d0(self):
        brief = _build_brief_for(13)
        assert [week["stage_key"] for week in brief["week_by_week_progression"]["weeks"]] == [
            "d13_to_d8",
            "d7",
            "d6_to_d5",
            "d4_to_d2",
            "d1",
            "d0",
        ]
        assert [week["stage_key"] for week in brief["weekly_role_map"]["weeks"]] == [
            "d13_to_d8",
            "d7",
            "d6_to_d5",
            "d4_to_d2",
            "d1",
            "d0",
        ]

    def test_guardrail_bridge_mode_does_not_suppress_downstream_late_stage_takeover(self):
        brief = _build_brief_for(16)
        stage_keys = [week["stage_key"] for week in brief["week_by_week_progression"]["weeks"]]
        assert stage_keys == [
            "d21_to_d14",
            "d13_to_d8",
            "d7",
            "d6_to_d5",
            "d4_to_d2",
            "d1",
            "d0",
        ]

    def test_bridge_d20_weekly_role_map_phase_matches_progression(self):
        brief = _build_brief_for(20, phase="SPP")

        assert brief["week_by_week_progression"]["weeks"][0]["phase"] == "SPP"
        assert brief["week_by_week_progression"]["weeks"][0]["phase"] == brief["weekly_role_map"]["weeks"][0]["phase"]

    def test_bridge_continuation_keeps_d1_d0_as_day_specific_modes_not_development_weeks(self):
        brief = _build_brief_for(16)
        weeks_by_key = {
            week["stage_key"]: week
            for week in brief["week_by_week_progression"]["weeks"]
        }
        assert weeks_by_key["d1"]["payload_mode"] == "pre_fight_day_payload"
        assert weeks_by_key["d1"]["stage_label"] == "Primer Day"
        assert weeks_by_key["d0"]["payload_mode"] == "fight_day_protocol_payload"
        assert weeks_by_key["d0"]["stage_label"] == "Fight-Day Protocol"

    def test_bridge_d16_practical_spec_does_not_collapse_to_bridge_only(self):
        brief = _build_brief_for(16)
        spec = brief["late_fight_plan_spec"]
        visible_offsets = [
            entry.get("countdown_offset")
            for entry in spec["visible_session_sequence"]
        ]

        assert spec["visible_session_cap"] > 2
        assert spec["max_active_roles"] == spec["visible_session_cap"]
        assert any(offset is not None and offset <= 13 for offset in visible_offsets)
        assert {16, 14}.issubset(set(visible_offsets))

    def test_bridge_d16_session_sequence_includes_downstream_practical_roles(self):
        brief = _build_brief_for(16)
        sequence = brief["late_fight_session_sequence"]
        downstream_roles = [
            entry
            for entry in sequence
            if isinstance(entry.get("countdown_offset"), int)
            and entry["countdown_offset"] <= 13
        ]

        assert downstream_roles
        assert any(entry.get("composite_segment_stage_key") == "d7" for entry in downstream_roles)
        assert any(entry.get("composite_segment_stage_key") == "d1" for entry in downstream_roles)

    def test_bridge_d16_weekly_role_map_uses_practical_continuation_roles(self):
        brief = _build_brief_for(16)
        roles = [
            role
            for week in brief["weekly_role_map"]["weeks"]
            for role in week["session_roles"]
        ]
        offsets = [
            role.get("countdown_offset")
            for role in roles
            if isinstance(role.get("countdown_offset"), int)
        ]

        assert max(offsets) <= 16
        assert min(offsets) == 1
        assert any(offset <= 13 for offset in offsets)
        assert brief["weekly_role_map"]["allocator"]["composite_practical_allocation"] is True

    def test_bridge_d16_practical_spacing_avoids_adjacent_app_owned_sessions(self):
        brief = _build_brief_for(
            16,
            athlete_overrides={
                "plan_creation_weekday": "monday",
                "hard_sparring_days": [],
            },
        )
        visible_offsets = [
            entry["countdown_offset"]
            for entry in brief["late_fight_plan_spec"]["visible_session_sequence"]
            if isinstance(entry.get("countdown_offset"), int)
        ]

        assert all(
            first - second > 1
            for first, second in zip(visible_offsets, visible_offsets[1:])
        )

    def test_bridge_d16_avoids_meaningful_app_owned_work_on_declared_hard_days(self):
        brief = _build_brief_for(
            16,
            athlete_overrides={
                "plan_creation_weekday": "monday",
                "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "hard_sparring_days": ["thursday"],
            },
        )
        visible_sequence = brief["late_fight_plan_spec"]["visible_session_sequence"]
        meaningful_app_roles = [
            entry
            for entry in visible_sequence
            if _is_app_owned_visible_role(entry.get("role_key"))
            and entry.get("stress_class") == "meaningful_stress"
        ]

        assert meaningful_app_roles
        assert all(
            str(entry.get("scheduled_day_hint") or "").lower() != "thursday"
            for entry in meaningful_app_roles
        )

    def test_d13_practical_behaviour_uses_countdown_continuation_until_d1(self):
        spec = _build_late_fight_plan_spec(13, _athlete(13))

        assert spec["payload_mode"] == "pre_fight_compressed_payload"
        assert spec["allocator"].get("composite_practical_allocation") is True
        assert [segment["stage_key"] for segment in spec["countdown_mode_sequence"]] == [
            "d13_to_d8",
            "d7",
            "d6_to_d5",
            "d4_to_d2",
            "d1",
            "d0",
        ]
        app_visible_sequence = [
            entry
            for entry in spec["visible_session_sequence"]
            if _is_app_owned_visible_role(entry.get("role_key"))
        ]
        assert [entry.get("role_key") for entry in app_visible_sequence] == [
            "strength_touch_day",
            "alactic_sharpness_day",
            "fight_week_freshness_day",
        ]
        assert any(entry.get("role_key") == "hard_sparring_day" for entry in spec["visible_session_sequence"])
        # The session_sequence must cover every downstream stage where the
        # athlete actually has activity. Stages without declared spar in the
        # D-13 calendar (here: D-7=friday and D-6/D-5=sat/sun for a tue/thu
        # spar declaration) legitimately stay empty — see the matching
        # ``test_d5_continuation_does_not_invent_filler_for_an_empty_window``
        # contract that explicitly forbids inventing fillers.
        stage_keys = set(_composite_stage_keys(spec["session_sequence"]))
        assert {"d13_to_d8", "d6_to_d5", "d4_to_d2", "d1"}.issubset(stage_keys)
        # Each declared spar weekday must surface as a coach-owned
        # ``hard_sparring_day`` context entry inside session_sequence (the
        # visibility filter keeps it out of visible_session_sequence).
        hard_spar_context = [
            role
            for role in spec["session_sequence"]
            if role.get("role_key") == "hard_sparring_day"
        ]
        assert hard_spar_context
        assert all(role.get("downgraded") is True for role in hard_spar_context)


class TestStage2PayloadBranching:
    def test_camp_payload_stays_on_normal_stage2_schema(self):
        payload = _build_stage2(28)
        assert payload["generator_mode"] == "restriction_aware_candidate_generator"
        assert "payload_mode" not in payload
        assert "days_out_payload" not in payload

    def test_pre_fight_payload_adds_mode_specific_fields(self):
        payload = _build_stage2(10)
        assert payload["generator_mode"] == "restriction_aware_candidate_generator_late_fight"
        assert payload["payload_variant"] == "late_fight_stage2_payload"
        assert payload["payload_mode"] == "pre_fight_compressed_payload"
        assert payload["effective_stage2_mode"] == "pre_fight_compressed_payload"
        assert "late_fight_permissions" in payload
        assert "rendering_rules" in payload

    def test_late_fight_payload_adds_mode_specific_fields(self):
        payload = _build_stage2(5)
        assert payload["generator_mode"] == "restriction_aware_candidate_generator_late_fight"
        assert payload["payload_variant"] == "late_fight_stage2_payload"
        assert payload["payload_mode"] == "late_fight_transition_payload"
        assert payload["effective_stage2_mode"] == "late_fight_transition_payload"
        assert "late_fight_permissions" in payload
        assert "rendering_rules" in payload

    def test_d3_payload_exposes_continued_session_sequence(self):
        payload = _build_stage2(3)
        assert payload["payload_mode"] == "late_fight_session_payload"
        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [
            "fight_week_freshness_day",
            "neural_primer_day",
        ]
        assert _composite_stage_keys(payload["late_fight_session_sequence"]) == ["d4_to_d2", "d1"]

    def test_d2_payload_exposes_primer_only_sequence(self):
        payload = _build_stage2(2)

        assert payload["payload_mode"] == "late_fight_session_payload"
        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [
            "neural_primer_day",
        ]

    def test_d7_plan_spec_exposes_caps_and_forbidden_blocks(self):
        spec = _build_late_fight_plan_spec(7, _athlete(7))

        assert spec["max_blocks_per_session"] == 5
        assert spec["max_meaningful_stress_exposures"] == 2
        assert spec["max_active_roles"] == 3
        assert "standalone_glycolytic" in spec["forbidden_blocks"]
        assert spec["max_support_roles"] == 1
        assert "role_budget" in spec
        assert "allocator" in spec
        assert "permission_policy" in spec

    def test_plan_spec_exposes_allocator_metadata_and_source_of_truth_fields(self):
        spec = _build_late_fight_plan_spec(5, _athlete(5))

        assert spec["allocator"]["legal_countdown_labels"] == ["D-4", "D-3", "D-2", "D-1"]
        # ``selected_active_roles`` tracks allocator-selected app-owned roles
        # and matches ``visible_session_sequence``. Coach-owned hard_sparring
        # context entries land in ``session_sequence`` (for tracking) but are
        # not part of the active allocation budget.
        app_visible_sequence = [
            entry
            for entry in spec["visible_session_sequence"]
            if _is_app_owned_visible_role(entry.get("role_key"))
        ]
        assert spec["role_budget"]["selected_active_roles"] == len(app_visible_sequence)
        assert all("scheduled_countdown_label" in role for role in spec["session_sequence"])
        assert all("placement_source" in role for role in spec["session_sequence"])

    def test_d5_plan_spec_marks_downgraded_declared_hard_day_as_technical_touch(self):
        spec = _build_late_fight_plan_spec(
            5,
            _athlete(5, hard_sparring_days=["thursday"], plan_creation_weekday="monday"),
        )

        assert spec["permission_policy"]["declared_hard_day_actions"] == [
            {
                "day": "thursday",
                "outcome": "technical_touch_day",
                "locked": False,
                "downgraded_from_role_key": "hard_sparring_day",
            }
        ]

    def test_short_notice_window_keeps_allocator_metadata_even_with_fight_week_override(self):
        brief = _build_brief_for(3)

        assert brief["fight_week_override"]["active"] is True
        assert "allocator" in brief["late_fight_plan_spec"]
        assert "role_budget" in brief["late_fight_plan_spec"]

    def test_d7_plan_spec_keeps_downgraded_boxing_context_out_of_visible_app_sequence(self):
        spec = _build_late_fight_plan_spec(7, _athlete(7))

        assert "hard_sparring_day" in spec["session_roles"]
        assert "hard_sparring_day" not in spec["visible_session_roles"]
        app_visible_sequence = [
            entry
            for entry in spec["visible_session_sequence"]
            if _is_app_owned_visible_role(entry.get("role_key"))
        ]
        assert spec["visible_session_cap"] == len(app_visible_sequence)
        assert [entry["role_key"] for entry in app_visible_sequence] == spec["visible_session_roles"]
        assert any(entry["role_key"] == "hard_sparring_day" for entry in spec["visible_session_sequence"])


    def test_late_fight_weekly_role_map_carries_planner_sparring_plan_for_d17_ban(self):
        role_map = _build_late_fight_weekly_role_map(
            13,
            _athlete(13, plan_creation_weekday="monday", hard_sparring_days=["tuesday", "thursday"]),
        )

        first_week = role_map["weeks"][0]
        assert first_week["hard_sparring_plan"]
        assert first_week["effective_hard_sparring_days"] == []
        assert {entry["effective_load"] for entry in first_week["hard_sparring_plan"]} == {"technical"}
        assert all(entry["status"] == "convert_to_technical_suggested" for entry in first_week["hard_sparring_plan"])

    def test_bridge_weekly_role_map_uses_planner_cap_one_for_d21_to_d18(self):
        role_map = _build_late_fight_weekly_role_map(
            20,
            _athlete(20, plan_creation_weekday="monday", hard_sparring_days=["tuesday", "thursday"]),
        )

        bridge_week = role_map["weeks"][0]
        hard_plan = bridge_week["hard_sparring_plan"]
        assert hard_plan
        assert len(bridge_week["effective_hard_sparring_days"]) <= 1
        assert [entry["effective_load"] for entry in hard_plan].count("hard") <= 1

    def test_d5_plan_spec_adds_structured_hard_sparring_context(self):
        spec = _build_late_fight_plan_spec(
            5,
            _athlete(5, plan_creation_weekday="monday", hard_sparring_days=["tuesday", "thursday"]),
        )
        assert "hard_sparring_context_line" in spec
        assert spec["surviving_hard_spar_days"] == []
        assert spec["downgraded_declared_spar_days"] == ["tuesday", "thursday"]
        assert spec["hard_sparring_context_line"] == (
            "Hard sparring this window: none. Tuesday and Thursday are technical rhythm only."
        )

    @pytest.mark.parametrize(
        "days,expected_stages",
        [
            (13, ["d13_to_d8", "d7", "d6_to_d5", "d4_to_d2", "d1", "d0"]),
            (10, ["d13_to_d8", "d7", "d6_to_d5", "d4_to_d2", "d1", "d0"]),
            (7, ["d7", "d6_to_d5", "d4_to_d2", "d1", "d0"]),
            (5, ["d6_to_d5", "d4_to_d2", "d1", "d0"]),
            (3, ["d4_to_d2", "d1", "d0"]),
        ],
    )
    def test_late_fight_continuation_builds_stage_windows_through_d1(self, days, expected_stages):
        brief = _build_brief_for(days)
        assert [week["stage_key"] for week in brief["week_by_week_progression"]["weeks"]] == expected_stages
        assert [week["stage_key"] for week in brief["weekly_role_map"]["weeks"]] == expected_stages
        assert brief["late_fight_plan_spec"]["allocator"]["composite_practical_allocation"] is True
        assert "d1" in _composite_stage_keys(brief["late_fight_session_sequence"])

    def test_d13_downstream_stage_can_continue_with_zero_visible_app_owned_sessions(self):
        brief = _build_brief_for(13)
        weeks_by_key = {week["stage_key"]: week for week in brief["weekly_role_map"]["weeks"]}

        # No declared spar weekday in the default _MINIMAL_ATHLETE
        # (tuesday/thursday) lines up with the d7 segment (single-day window
        # at D-7 = friday for the baseline 2026-04-10 fight date), so the d7
        # week stays empty — matching the
        # ``test_d5_continuation_does_not_invent_filler_for_an_empty_window``
        # contract. The downstream stages that DO see declared spar
        # (d13_to_d8 / d4_to_d2 / d1 for tuesday & thursday) must surface
        # the coach-owned ``hard_sparring_day`` placeholder, and no d7
        # segment role may appear in the visible insert sequence.
        downstream_weeks_with_hard_spar = [
            stage
            for stage in ("d13_to_d8", "d4_to_d2", "d1")
            if any(
                role["role_key"] == "hard_sparring_day"
                for role in weeks_by_key.get(stage, {}).get("session_roles", [])
            )
        ]
        assert downstream_weeks_with_hard_spar
        assert all(
            entry.get("composite_segment_stage_key") != "d7"
            for entry in brief["late_fight_plan_spec"]["visible_session_sequence"]
        )

    def test_d5_continuation_does_not_invent_filler_for_an_empty_window(self):
        brief = _build_brief_for(5)
        weeks_by_key = {week["stage_key"]: week for week in brief["weekly_role_map"]["weeks"]}

        assert weeks_by_key["d6_to_d5"]["session_roles"] == []
        assert all(
            entry.get("composite_segment_stage_key") != "d6_to_d5"
            for entry in brief["late_fight_session_sequence"]
        )

    def test_raw_athlete_inputs_are_preserved_in_late_fight_payload(self):
        payload = _build_stage2(1)
        athlete_model = payload["athlete_model"]
        assert athlete_model["hard_sparring_days"] == ["Tue", "Thu"]
        assert athlete_model["training_days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
        assert athlete_model["support_work_days"] == ["Fri"]
        assert athlete_model["key_goals"] == ["power"]

    def test_d1_payload_still_uses_late_fight_mode_without_week_structure(self):
        brief = _build_brief_for(1)
        payload = _build_stage2(1)
        assert payload["payload_mode"] == "pre_fight_day_payload"
        assert brief["weekly_role_map"]["weeks"] == []
        assert brief["week_by_week_progression"]["weeks"] == []


class TestHandoffText:
    def _build_handoff(self, days):
        payload = {
            "athlete_model": _athlete(days),
            "payload_mode": _days_out_payload_mode(days),
            "effective_stage2_mode": _days_out_payload_mode(days),
            "restrictions": [],
            "phase_briefs": {},
            "candidate_pools": {},
            "omission_ledger": {},
            "rewrite_guidance": {},
        }
        return build_stage2_handoff_text(
            stage2_payload=payload,
            plan_text="Draft plan text.",
            coach_notes="",
        )

    def _build_handoff_with_brief(self, days):
        payload = _build_stage2(days)
        brief = _build_brief_for(days)
        return build_stage2_handoff_text(
            stage2_payload=payload,
            plan_text="Draft plan text.",
            coach_notes="",
            planning_brief=brief,
        )

    def test_camp_handoff_has_no_payload_mode_section(self):
        text = self._build_handoff(28)
        assert "PAYLOAD MODE INSTRUCTIONS" not in text
        assert "INJURY CONTEXT" in text
        # PLANNING BRIEF section was replaced by the consolidated FINALIZER
        # PACKET — see test_stage2_handoff_text which explicitly asserts the
        # old section is gone.
        assert "FINALIZER PACKET" in text

    @pytest.mark.parametrize(
        "days, expected_heading",
        [
            (10, "COMPRESSED PRE-FIGHT WEEK"),
            (7, "SHARPNESS WEEK"),
            (5, "SHARPNESS & FRESHNESS WINDOW"),
            (3, "SHARPNESS-FIRST SESSIONS"),
            (1, "PRIMER DAY"),
            (0, "FIGHT DAY PROTOCOL"),
        ],
    )
    def test_late_fight_handoff_includes_mode_instructions(self, days, expected_heading):
        text = self._build_handoff(days)
        assert "PAYLOAD MODE INSTRUCTIONS" in text
        assert expected_heading in text

    def test_late_fight_handoff_carries_taper_micro_support_rules(self):
        text = self._build_handoff_with_brief(5)
        assert "taper_micro_support" in text
        assert "optional add-on" in text

    def test_late_fight_handoff_carries_final_week_primer_caps(self):
        d7_text = self._build_handoff(7)
        d6_text = self._build_handoff(6)
        d1_text = self._build_handoff(1)

        assert "use selected drill RPE when present" in d7_text
        assert "RPE 6-7, 3-4 x 6 sec" in d7_text
        assert "RPE 6-7, 3-4 x 6 sec" in d6_text
        assert "No all-out language" in d6_text
        assert "RPE 3-5" in d1_text
        assert "no RPE 6-7" in d1_text

    def test_handoff_injury_context_section_is_visible_and_structured(self):
        payload = _build_stage2(14)
        payload["injury_context"] = {
            "raw_injury_text": "sore shoulder after sparring",
            "injuries_flat": ["shoulder pain"],
            "parsed_injuries": [{"original_phrase": "shoulder pain", "severity": "mild"}],
            "guided_injury": {"area": "right shoulder", "severity": "mild"},
            "restrictions": [{"restriction": "avoid heavy overhead pressing"}],
            "triage_summary": {"mode": "full_plan", "should_block_stage2": False},
        }
        brief = build_planning_brief(
            athlete_model=payload["athlete_model"],
            restrictions=payload["restrictions"],
            phase_briefs=payload["phase_briefs"],
            candidate_pools=payload["candidate_pools"],
            omission_ledger=payload["omission_ledger"],
            rewrite_guidance=payload["rewrite_guidance"],
        )
        text = build_stage2_handoff_text(
            stage2_payload=payload,
            plan_text="Week 1 ...",
            planning_brief=brief,
        )
        assert "INJURY CONTEXT" in text
        assert "sore shoulder after sparring" in text
        assert "avoid heavy overhead pressing" in text
        assert "STAGE 1 DRAFT PLAN" in text
        assert "Week 1 ..." in text

    def test_d10_handoff_blocks_normal_spp_rebuild_language(self):
        text = self._build_handoff(10)

        assert "No effective hard sparring" in text
        assert "technical/rhythm only" in text

    def test_d3_handoff_explicitly_forbids_week_structure(self):
        text = self._build_handoff(3)
        assert "no week headers" in text or "No week headers" in text
        assert "Session-by-session only" in text

    def test_d7_handoff_uses_sharpness_week_heading_map(self):
        text = self._build_handoff(7)

        assert "No effective hard sparring" in text
        assert "technical/rhythm only" in text

    def test_d3_handoff_replaces_camp_titles_with_late_fight_titles(self):
        text = self._build_handoff(3)

        assert "sharpness" in text.lower()
        assert "freshness" in text.lower()
        # Strength Block is a forbidden term that belongs in rendering_rules
        assert "no strength" in text.lower() or "No strength" in text

    def test_d1_handoff_forbids_strength_and_block_language(self):
        text = self._build_handoff(1)

        assert "Banned:" in text
        assert "strength" in text
        assert "neural primer" in text

    def test_d0_handoff_uses_fight_day_protocol_terms(self):
        text = self._build_handoff(0)

        assert "walk-through" in text.lower()
        assert "Do not restore suppressed roles" in text

    def test_late_fight_handoff_uses_app_owned_insert_contract(self):
        text = self._build_handoff(10)

        # Placement governs day assignment only — core contract phrase (stable)
        assert "Placement governs day assignment only" in text
        # App vs coach ownership distinction is present
        assert "app-owned" in text.lower() or "gym/coach" in text.lower(), (
            "Handoff should distinguish app-owned vs coach-owned schedule elements"
        )
        # Spar day accounting fields are present in the payload data
        assert "surviving_hard_spar_days" in text or "hard_spar" in text, (
            "Handoff should reference hard spar day accounting"
        )

    def test_d16_handoff_includes_full_bridge_to_d0_mode_continuation(self):
        text = self._build_handoff_with_brief(16)
        for stage_key in ["d21_to_d14", "d13_to_d8", "d7", "d6_to_d5", "d4_to_d2", "d1", "d0"]:
            assert stage_key in text

    def test_d16_handoff_does_not_limit_countdown_to_bridge_only(self):
        text = self._build_handoff_with_brief(16)
        assert "Bridge segment is front-only" in text
        assert "Continue mode takeover from D-13 to D-0" in text

    def test_d14_handoff_includes_bridge_day_plus_downstream_continuation(self):
        text = self._build_handoff_with_brief(14)
        assert "- d21_to_d14: bridge_compression_payload (D-14 to D-14)" in text
        assert "- d13_to_d8: pre_fight_compressed_payload (D-13 to D-8)" in text
        assert "- d0: fight_day_protocol_payload (D-0 to D-0)" in text

    def test_d21_handoff_includes_full_bridge_and_downstream_continuation(self):
        text = self._build_handoff_with_brief(21)
        assert "- d21_to_d14: bridge_compression_payload (D-21 to D-14)" in text
        assert "- d13_to_d8: pre_fight_compressed_payload (D-13 to D-8)" in text
        assert "- d0: fight_day_protocol_payload (D-0 to D-0)" in text

    def test_d13_handoff_includes_countdown_continuation_map(self):
        text = self._build_handoff_with_brief(13)
        assert "COUNTDOWN CONTINUATION MAP" in text
        assert "COMPRESSED PRE-FIGHT WEEK" in text
        assert "- d13_to_d8: pre_fight_compressed_payload (D-13 to D-8)" in text
        assert "- d0: fight_day_protocol_payload (D-0 to D-0)" in text


class TestLateFightCountdownWeekdayLabels:
    def test_d14_d13_countdown_labels_follow_real_calendar_weekdays(self):
        athlete = _athlete(
            14,
            plan_creation_weekday="saturday",
            fight_date="2026-05-09",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        )

        spec = _build_late_fight_plan_spec(14, athlete)
        raw_map = spec["permission_policy"]["raw_countdown_weekday_map"]

        assert raw_map["D-14"] == "saturday"
        assert raw_map["D-13"] == "sunday"
        assert raw_map["D-7"] == "saturday"
        assert raw_map["D-5"] == "monday"
        assert raw_map["D-3"] == "wednesday"
        assert raw_map["D-1"] == "friday"
        assert raw_map["D-0"] == "saturday"

        visible_labels = {
            entry.get("countdown_label"): entry.get("countdown_display_label")
            for entry in spec.get("visible_session_sequence", [])
            if entry.get("countdown_label") and entry.get("countdown_display_label")
        }
        if "D-14" in visible_labels and "D-13" in visible_labels:
            assert not (
                visible_labels["D-14"].endswith("(Saturday)")
                and visible_labels["D-13"].endswith("(Saturday)")
            )
