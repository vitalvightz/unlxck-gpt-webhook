"""Focused tests for the late-fight Stage 2 payload split."""

import pytest

from fightcamp.stage2_payload import (
    _build_late_fight_weekly_role_map,
    _days_out_payload_block,
    _days_out_payload_mode,
    _late_fight_permissions,
    _late_fight_rendering_rules,
    build_planning_brief,
    build_stage2_handoff_text,
    build_stage2_payload,
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
    "technical_skill_days": ["friday"],
    "mindset_challenges": "",
    "notes": "",
    "restrictions": [],
    "sport": "boxing",
    "status": "amateur",
    "camp_length_weeks": 6,
    "short_notice": False,
}


def _athlete(days_until_fight):
    athlete = dict(_MINIMAL_ATHLETE)
    athlete["days_until_fight"] = days_until_fight
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
        training_split={},
        key_goals=["power"],
        training_preference="short sessions",
        mental_block=[],
        age=26,
        weight=155.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 0, "SPP": 0, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": days or 7}},
        fight_date="2026-04-10",
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
            (10, "camp_payload"),
            (8, "camp_payload"),
            (7, "late_fight_week_payload"),
            (5, "late_fight_week_payload"),
            (4, "late_fight_session_payload"),
            (2, "late_fight_session_payload"),
            (1, "pre_fight_day_payload"),
            (0, "fight_day_protocol_payload"),
        ],
    )
    def test_mode_mapping(self, days, expected):
        assert _days_out_payload_mode(days) == expected

    def test_string_input_still_works(self):
        assert _days_out_payload_mode("3") == "late_fight_session_payload"
        assert _days_out_payload_mode("0") == "fight_day_protocol_payload"


class TestDaysOutPayloadBlock:
    def test_camp_block_uses_camp_bucket(self):
        block = _days_out_payload_block(10, _athlete(10))
        assert block["payload_mode"] == "camp_payload"
        assert block["payload_variant"] == "normal_stage2_payload"
        assert block["days_out_bucket"] == "CAMP"
        assert block["fight_week_override"] == {"active": False}

    def test_late_fight_block_has_mode_specific_metadata(self):
        block = _days_out_payload_block(3, _athlete(3))
        assert block["payload_mode"] == "late_fight_session_payload"
        assert block["payload_variant"] == "late_fight_stage2_payload"
        assert block["days_out_bucket"] == "D-3"
        assert block["late_fight_window"] == "d4_to_d2"
        assert "rendering_rules" in block
        assert "late_fight_permissions" in block


class TestLateFightPermissionsAndRendering:
    def test_camp_permissions_remain_unrestricted(self):
        permissions = _late_fight_permissions(10, _athlete(10))
        rules = _late_fight_rendering_rules(10)
        assert permissions["allow_full_weekly_structure"] is True
        assert permissions["allow_development_language"] is True
        assert rules == {"mode": "camp_payload", "rules": []}

    def test_d1_forbids_anchor_and_glycolytic_language(self):
        permissions = _late_fight_permissions(1, _athlete(1))
        rules = _late_fight_rendering_rules(1)
        assert permissions["allow_anchor_wording"] is False
        assert permissions["allow_glycolytic_build"] is False
        assert "anchor" in [term.lower() for term in rules["forbidden_terms"]]
        assert "primer" in [term.lower() for term in rules["preferred_terms"]]

    def test_d0_restricts_output_to_protocol_language(self):
        permissions = _late_fight_permissions(0, _athlete(0))
        rules = _late_fight_rendering_rules(0)
        assert permissions["allow_fight_day_protocol_only"] is True
        assert permissions["allow_normal_session_roles"] is False
        assert "activation" in [term.lower() for term in rules["preferred_terms"]]
        assert "warm-up" in [term.lower() for term in rules["preferred_terms"]]


class TestLateFightRoleMap:
    def test_d5_role_map_uses_compressed_overlay(self):
        role_map = _build_late_fight_weekly_role_map(5, _athlete(5))
        assert role_map["model"] == "late_fight_role_overlay.v1"
        assert role_map["payload_mode"] == "late_fight_week_payload"
        assert len(role_map["weeks"]) == 1
        week = role_map["weeks"][0]
        assert week["intentional_compression"]["active"] is True
        assert any(role["role_key"] == "fight_week_freshness_day" for role in week["session_roles"])

    def test_d3_role_map_is_session_list(self):
        role_map = _build_late_fight_weekly_role_map(3, _athlete(3))
        assert role_map["payload_mode"] == "late_fight_session_payload"
        assert role_map["weeks"] == []

    def test_d0_role_map_has_no_weeks(self):
        role_map = _build_late_fight_weekly_role_map(0, _athlete(0))
        assert role_map["payload_mode"] == "fight_day_protocol_payload"
        assert role_map["weeks"] == []


class TestPlanningBriefBranching:
    def test_camp_uses_normal_planning_brief(self):
        brief = _build_brief_for(10)
        assert brief["generator_mode"] == "deterministic_planner_plus_ai_finalizer"
        assert "days_out_payload" not in brief
        assert "payload_variant" not in brief
        assert brief["weekly_role_map"]["model"] == "session_role_overlay.v1"

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

    @pytest.mark.parametrize(
        ("days_until_fight", "expected_window", "expected_training_days", "expected_hard_days"),
        [
            (1, ["Thursday", "Friday"], ["thursday", "friday"], ["thursday"]),
            (3, ["Tuesday", "Wednesday", "Thursday", "Friday"], ["tuesday", "wednesday", "thursday", "friday"], ["tuesday", "thursday"]),
            (6, ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], ["monday", "tuesday", "wednesday", "thursday", "friday"], ["tuesday", "thursday"]),
        ],
    )
    def test_late_fight_brief_trims_to_remaining_window(self, days_until_fight, expected_window, expected_training_days, expected_hard_days):
        brief = _build_brief_for(days_until_fight)
        athlete_snapshot = brief["athlete_snapshot"]
        assert athlete_snapshot["active_window_weekdays"] == expected_window
        assert athlete_snapshot["training_days"] == expected_training_days
        assert athlete_snapshot["hard_sparring_days"] == expected_hard_days
        assert brief["late_fight_plan_spec"]["active_window_weekdays"] == expected_window


class TestStage2PayloadBranching:
    def test_camp_payload_stays_on_normal_stage2_schema(self):
        payload = _build_stage2(10)
        assert payload["generator_mode"] == "restriction_aware_candidate_generator"
        assert "payload_mode" not in payload
        assert "days_out_payload" not in payload

    def test_late_fight_payload_adds_mode_specific_fields(self):
        payload = _build_stage2(5)
        assert payload["generator_mode"] == "restriction_aware_candidate_generator_late_fight"
        assert payload["payload_variant"] == "late_fight_stage2_payload"
        assert payload["payload_mode"] == "late_fight_week_payload"
        assert payload["effective_stage2_mode"] == "late_fight_week_payload"
        assert "late_fight_permissions" in payload
        assert "rendering_rules" in payload

    def test_d3_payload_exposes_flat_session_sequence(self):
        payload = _build_stage2(3)
        assert payload["payload_mode"] == "late_fight_session_payload"
        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [
            "alactic_sharpness_day",
            "fight_week_freshness_day",
        ]

    def test_late_fight_payload_trims_day_lists_to_remaining_window(self):
        payload = _build_stage2(1)
        athlete_model = payload["athlete_model"]
        assert athlete_model["active_window_weekdays"] == ["Thursday", "Friday"]
        assert athlete_model["hard_sparring_days"] == ["Thu"]
        assert athlete_model["training_days"] == ["Thu", "Fri"]
        assert athlete_model["technical_skill_days"] == ["Fri"]
        assert athlete_model["key_goals"] == ["power"]
        assert payload["late_fight_plan_spec"]["active_window_weekdays"] == ["Thursday", "Friday"]

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
        text = self._build_handoff(10)
        assert "PAYLOAD MODE INSTRUCTIONS" not in text
        assert "PLANNING BRIEF" in text

    @pytest.mark.parametrize(
        "days, expected_heading",
        [
            (5, "COMPRESSED WEEK"),
            (3, "SESSION-BY-SESSION"),
            (1, "PRE-FIGHT DAY"),
            (0, "FIGHT DAY PROTOCOL"),
        ],
    )
    def test_late_fight_handoff_includes_mode_instructions(self, days, expected_heading):
        text = self._build_handoff(days)
        assert "PAYLOAD MODE INSTRUCTIONS" in text
        assert expected_heading in text
        assert "STAGE 1 DRAFT PLAN" in text
        assert "Draft plan text." in text

    def test_late_fight_handoff_puts_mode_instructions_before_base_prompt(self):
        text = self._build_handoff(1)
        assert text.index("PAYLOAD MODE INSTRUCTIONS") < text.index("You are Stage 2 (planner/finalizer).")

    def test_d1_handoff_explicitly_limits_output_to_remaining_days(self):
        payload = _build_stage2(1)
        text = build_stage2_handoff_text(stage2_payload=payload, plan_text="Draft plan text.")
        assert "ALLOWED DAYS ONLY: Thursday, Friday." in text
        assert "Do not add earlier weekdays or a Monday-to-Sunday frame." in text

    def test_d3_handoff_explicitly_forbids_week_structure(self):
        text = self._build_handoff(3)
        assert "Do NOT render week headers" in text
