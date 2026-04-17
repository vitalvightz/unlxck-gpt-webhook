"""Focused tests for the late-fight Stage 2 payload split."""

import pytest

from fightcamp.stage2_payload import (
    _build_late_fight_plan_spec,
    _build_late_fight_weekly_role_map,
    _days_out_payload_block,
    _days_out_payload_mode,
    _late_fight_permissions,
    _late_fight_rendering_rules,
    build_planning_brief,
    build_stage2_handoff_text,
    build_stage2_payload,
)
from fightcamp.stage2_payload_late_fight import _late_fight_stage_label
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
    "technical_skill_days": ["friday"],
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


def _build_brief_for(days_until_fight, *, phase="SPP"):
    athlete_model = _athlete(days_until_fight)
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
        technical_skill_days=["Fri"],
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


class TestPayloadModeClassification:
    @pytest.mark.parametrize(
        "days, expected",
        [
            (None, "camp_payload"),
            (-2, "camp_payload"),
            (14, "camp_payload"),
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


class TestDaysOutPayloadBlock:
    def test_camp_block_uses_camp_bucket(self):
        block = _days_out_payload_block(14, _athlete(14))
        assert block["payload_mode"] == "camp_payload"
        assert block["payload_variant"] == "normal_stage2_payload"
        assert block["days_out_bucket"] == "CAMP"
        assert block["fight_week_override"] == {"active": False}

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
        permissions = _late_fight_permissions(14, _athlete(14))
        rules = _late_fight_rendering_rules(14)
        assert permissions["allow_full_weekly_structure"] is True
        assert permissions["allow_development_language"] is True
        assert rules == {"mode": "camp_payload", "rules": []}

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


class TestLateFightRoleMap:
    def test_d5_role_map_uses_transition_overlay(self):
        role_map = _build_late_fight_weekly_role_map(5, _athlete(5))
        assert role_map["model"] == "late_fight_role_overlay.v1"
        assert role_map["payload_mode"] == "late_fight_transition_payload"
        assert role_map["weeks"] == []

    def test_d3_role_map_is_session_list(self):
        role_map = _build_late_fight_weekly_role_map(3, _athlete(3))
        assert role_map["payload_mode"] == "late_fight_session_payload"
        assert role_map["weeks"] == []

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
        brief = _build_brief_for(14)
        assert brief["generator_mode"] == "deterministic_planner_plus_ai_finalizer"
        assert "days_out_payload" not in brief
        assert "payload_variant" not in brief
        assert brief["weekly_role_map"]["model"] == "session_role_overlay.v1"

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
        assert brief["week_by_week_progression"]["weeks"] == []
        assert brief["weekly_role_map"]["weeks"] == []
        assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == [
            "alactic_sharpness_day",
            "fight_week_freshness_day",
        ]

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
        assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == ["neural_primer_day"]

    def test_d7_planning_brief_uses_sharpness_week_labels(self):
        brief = _build_brief_for(7)

        week = brief["week_by_week_progression"]["weeks"][0]
        assert week["stage_label"] == "Sharpness Week"
        assert "power touch" in week["stage_objective"].lower()
        assert "freshness" in week["stage_objective"].lower()


class TestStage2PayloadBranching:
    def test_camp_payload_stays_on_normal_stage2_schema(self):
        payload = _build_stage2(14)
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

    def test_d3_payload_exposes_flat_session_sequence(self):
        payload = _build_stage2(3)
        assert payload["payload_mode"] == "late_fight_session_payload"
        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [
            "alactic_sharpness_day",
            "fight_week_freshness_day",
        ]

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

        assert spec["allocator"]["legal_countdown_labels"] == ["D-5", "D-4", "D-3", "D-2", "D-1"]
        assert spec["role_budget"]["selected_active_roles"] == len(spec["session_sequence"])
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

    def test_d7_plan_spec_keeps_boxing_roles_out_of_visible_insert_sessions(self):
        spec = _build_late_fight_plan_spec(7, _athlete(7))

        assert "hard_sparring_day" in spec["session_roles"]
        assert "hard_sparring_day" not in spec["visible_session_roles"]
        assert spec["visible_session_cap"] == len(spec["visible_session_sequence"])
        assert [entry["role_key"] for entry in spec["visible_session_sequence"]] == spec["visible_session_roles"]

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
        "days,expected_visible",
        [
            (13, 3),
            (11, 3),
            (9, 3),
            (7, 2),
            (5, 2),
            (3, 2),
            (1, 1),
        ],
    )
    def test_late_fight_visible_session_count_varies_by_countdown_and_context(self, days, expected_visible):
        athlete = _athlete(
            days,
            hard_sparring_days=["thursday"],
            fatigue="moderate",
            fatigue_level="moderate",
            readiness_flags=["injury_management", "weight_cut_active"],
            weekly_training_frequency=5,
            weight_cut_risk=True,
            weight_cut_pct=2.0,
        )
        spec = _build_late_fight_plan_spec(days, athlete)
        assert spec["visible_session_cap"] == expected_visible

    def test_raw_athlete_inputs_are_preserved_in_late_fight_payload(self):
        payload = _build_stage2(1)
        athlete_model = payload["athlete_model"]
        assert athlete_model["hard_sparring_days"] == ["Tue", "Thu"]
        assert athlete_model["training_days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
        assert athlete_model["technical_skill_days"] == ["Fri"]
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

    def test_camp_handoff_has_no_payload_mode_section(self):
        text = self._build_handoff(14)
        assert "PAYLOAD MODE INSTRUCTIONS" not in text
        assert "INJURY CONTEXT" in text
        assert "PLANNING BRIEF" in text

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

        assert "No SPP development framing" in text
        assert "Hard sparring: 2 max" in text

    def test_d3_handoff_explicitly_forbids_week_structure(self):
        text = self._build_handoff(3)
        assert "no week headers" in text or "No week headers" in text
        assert "Session-by-session only" in text

    def test_d7_handoff_uses_sharpness_week_heading_map(self):
        text = self._build_handoff(7)

        assert "SHARPNESS WEEK" in text
        assert "Hard sparring: 1 declared day" in text
        assert "Stress cap" in text

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
