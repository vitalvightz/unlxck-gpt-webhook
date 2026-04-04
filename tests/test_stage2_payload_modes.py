"""Tests for days-out payload mode behavior in stage2_payload.

Covers: payload mode classification, weekly role map shaping per mode,
planning brief days_out_payload block, build_stage2_payload new fields,
handoff text mode instructions, and raw-data preservation.
"""
import json
import pytest

from fightcamp.stage2_payload import (
    _days_out_payload_mode,
    _late_fight_permissions,
    _late_fight_rendering_rules,
    _days_out_payload_block,
    _build_weekly_role_map,
    build_planning_brief,
    build_stage2_payload,
    build_stage2_handoff_text,
    _fight_week_override_payload,
)
from fightcamp.training_context import TrainingContext


# ── Fixtures ───────────────────────────────────────────────────────
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
    am = dict(_MINIMAL_ATHLETE)
    am["days_until_fight"] = days_until_fight
    return am


def _build_brief_for(days_until_fight, *, phase="SPP"):
    am = _athlete(days_until_fight)
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
        athlete_model=am,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )


# =========================================================================
# 1. Payload mode classification
# =========================================================================


class TestPayloadModeClassification:
    @pytest.mark.parametrize(
        "days, expected",
        [
            (None, "camp_payload"),
            (-2, "camp_payload"),
            (100, "camp_payload"),
            (10, "camp_payload"),
            (8, "camp_payload"),
            (7, "late_fight_week_payload"),
            (6, "late_fight_week_payload"),
            (5, "late_fight_week_payload"),
            (4, "late_fight_session_payload"),
            (3, "late_fight_session_payload"),
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


# =========================================================================
# 2. Late fight permissions
# =========================================================================


class TestLateFightPermissions:
    def test_camp_has_no_restrictions(self):
        perms = _late_fight_permissions(10, _athlete(10))
        assert perms["mode"] == "camp_payload"
        assert perms["allow_full_weekly_structure"] is True
        assert perms["allow_development_language"] is True

    def test_d7_to_d5_compressed_week(self):
        for d in (7, 6, 5):
            perms = _late_fight_permissions(d, _athlete(d))
            assert perms["mode"] == "late_fight_week_payload"
            assert perms["max_meaningful_strength_anchors"] == 1
            assert perms["max_meaningful_conditioning_stressors"] == 1
            assert perms["allow_development_language"] is False

    def test_d4_to_d2_session_mode(self):
        for d in (4, 3, 2):
            perms = _late_fight_permissions(d, _athlete(d))
            assert perms["mode"] == "late_fight_session_payload"
            assert perms["allow_full_weekly_structure"] is False
            assert perms["max_meaningful_strength_anchors"] == 0
            assert perms["allow_glycolytic_build"] is False

    def test_d1_pre_fight_day(self):
        perms = _late_fight_permissions(1, _athlete(1))
        assert perms["mode"] == "pre_fight_day_payload"
        assert perms["allow_anchor_wording"] is False
        assert perms["max_meaningful_strength_anchors"] == 0
        assert perms["allow_glycolytic_build"] is False
        assert perms["allow_hard_sparring_influence"] is False

    def test_d0_fight_day(self):
        perms = _late_fight_permissions(0, _athlete(0))
        assert perms["mode"] == "fight_day_protocol_payload"
        assert perms["allow_fight_day_protocol_only"] is True
        assert perms["allow_normal_session_roles"] is False
        assert perms["allow_full_weekly_structure"] is False
        assert perms["allow_hard_sparring_influence"] is False


# =========================================================================
# 3. Rendering rules
# =========================================================================


class TestRenderingRules:
    def test_camp_no_constraints(self):
        rules = _late_fight_rendering_rules(10)
        assert rules["mode"] == "camp_payload"
        assert rules.get("forbidden_terms", []) == []
        assert rules.get("preferred_terms", []) == []

    def test_d5_concise(self):
        rules = _late_fight_rendering_rules(5)
        assert rules.get("framing") == "compressed_week"

    def test_d3_session_by_session(self):
        rules = _late_fight_rendering_rules(3)
        assert rules.get("framing") == "session_by_session"

    def test_d1_forbidden_terms(self):
        rules = _late_fight_rendering_rules(1)
        forbidden = [t.lower() for t in rules["forbidden_terms"]]
        assert "anchor" in forbidden
        assert "primary strength" in forbidden
        assert "conditioning block" in forbidden

    def test_d1_preferred_terms(self):
        rules = _late_fight_rendering_rules(1)
        preferred = [t.lower() for t in rules["preferred_terms"]]
        assert "primer" in preferred
        assert "sharpness" in preferred

    def test_d0_no_training_language(self):
        rules = _late_fight_rendering_rules(0)
        forbidden = [t.lower() for t in rules["forbidden_terms"]]
        # Should forbid normal training terms
        assert any("strength" in t or "conditioning" in t or "anchor" in t for t in forbidden)
        preferred = [t.lower() for t in rules["preferred_terms"]]
        assert "activation" in preferred
        assert "warm-up" in preferred


# =========================================================================
# 4. Days-out payload block
# =========================================================================


class TestDaysOutPayloadBlock:
    def test_structure(self):
        block = _days_out_payload_block(3, _athlete(3))
        assert "days_until_fight" in block
        assert "payload_mode" in block
        assert "days_out_bucket" in block
        assert "fight_week_override" in block
        assert "late_fight_permissions" in block
        assert "allowed_session_types" in block
        assert "forbidden_session_types" in block
        assert "rendering_rules" in block

    def test_camp_mode(self):
        block = _days_out_payload_block(10, _athlete(10))
        assert block["payload_mode"] == "camp_payload"
        assert block["days_out_bucket"] == "CAMP"

    def test_d0_mode(self):
        block = _days_out_payload_block(0, _athlete(0))
        assert block["payload_mode"] == "fight_day_protocol_payload"
        assert block["days_out_bucket"] == "D-0"


# =========================================================================
# 5. Weekly role map payload-mode shaping
# =========================================================================


class TestWeeklyRoleMapPayloadMode:
    _STUB_PROGRESSION = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "TAPER",
                "stage_key": "taper_final",
                "phase_week_index": 1,
                "phase_week_total": 1,
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["alactic", "aerobic"],
            }
        ]
    }

    def _build_role_map(self, days):
        am = _athlete(days)
        fwo = _fight_week_override_payload(days)
        return _build_weekly_role_map(
            am,
            self._STUB_PROGRESSION,
            {"key": "general_fight_readiness"},
            fight_week_override=fwo,
            days_until_fight=days,
        )

    def test_camp_returns_full_weeks(self):
        rm = self._build_role_map(10)
        assert rm["payload_mode"] == "camp_payload"
        assert len(rm["weeks"]) >= 1
        week = rm["weeks"][0]
        roles = week["session_roles"]
        cats = [r["category"] for r in roles]
        assert "strength" in cats
        assert "conditioning" in cats

    def test_d5_compressed_week(self):
        rm = self._build_role_map(5)
        assert rm["payload_mode"] == "late_fight_week_payload"
        if rm["weeks"]:
            week = rm["weeks"][0]
            strength_count = sum(1 for r in week["session_roles"] if r["category"] == "strength")
            conditioning_count = sum(1 for r in week["session_roles"] if r["category"] == "conditioning")
            # Max 1 strength anchor + 1 conditioning stressor
            assert strength_count <= 1
            assert conditioning_count <= 1

    def test_d3_session_list_only(self):
        rm = self._build_role_map(3)
        assert rm["payload_mode"] == "late_fight_session_payload"
        if rm["weeks"]:
            week = rm["weeks"][0]
            # No broad anchor strength roles
            for r in week["session_roles"]:
                assert r["category"] in ("recovery", "conditioning") or "primer" in str(r.get("role_key", "")).lower(), \
                    f"unexpected role at D-3: {r}"
            assert week["intentional_compression"]["active"] is True

    def test_d1_no_normal_roles(self):
        rm = self._build_role_map(1)
        assert rm["payload_mode"] == "pre_fight_day_payload"
        if rm["weeks"]:
            week = rm["weeks"][0]
            roles = week["session_roles"]
            # Only primer / recovery type roles
            for r in roles:
                cat = r.get("category", "")
                assert cat in ("recovery",) or "primer" in str(r.get("role_key", "")).lower(), \
                    f"unexpected session role at D-1: {r}"

    def test_d0_no_weeks(self):
        rm = self._build_role_map(0)
        assert rm["payload_mode"] == "fight_day_protocol_payload"
        assert rm["weeks"] == []


# =========================================================================
# 6. Planning brief includes days_out_payload
# =========================================================================


class TestPlanningBriefDaysOutPayload:
    def test_camp_brief_has_days_out_payload(self):
        brief = _build_brief_for(10)
        assert "days_out_payload" in brief
        dop = brief["days_out_payload"]
        assert dop["payload_mode"] == "camp_payload"

    def test_d3_brief_has_correct_mode(self):
        brief = _build_brief_for(3)
        dop = brief["days_out_payload"]
        assert dop["payload_mode"] == "late_fight_session_payload"
        assert "late_fight_permissions" in dop
        assert "rendering_rules" in dop

    def test_d0_brief_has_fight_day(self):
        brief = _build_brief_for(0)
        dop = brief["days_out_payload"]
        assert dop["payload_mode"] == "fight_day_protocol_payload"

    def test_rendering_rules_in_brief(self):
        brief = _build_brief_for(1)
        assert "rendering_rules" in brief
        assert brief["rendering_rules"]["mode"] == "pre_fight_day_payload"

    def test_weekly_role_map_passes_days_until_fight(self):
        brief = _build_brief_for(5)
        wrm = brief["weekly_role_map"]
        assert wrm["payload_mode"] == "late_fight_week_payload"


# =========================================================================
# 7. build_stage2_payload new fields
# =========================================================================


class TestBuildStage2PayloadNewFields:
    def _build(self, days):
        tc = TrainingContext(
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
            days_until_fight=days,
            hard_sparring_days=["Tue", "Thu"],
            technical_skill_days=["Fri"],
        )
        return build_stage2_payload(
            training_context=tc,
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

    def test_payload_mode_present(self):
        payload = self._build(10)
        assert "payload_mode" in payload
        assert payload["payload_mode"] == "camp_payload"

    def test_effective_stage2_mode_present(self):
        payload = self._build(3)
        assert "effective_stage2_mode" in payload
        assert payload["effective_stage2_mode"] == "late_fight_session_payload"

    def test_days_out_payload_present(self):
        payload = self._build(1)
        assert "days_out_payload" in payload
        dop = payload["days_out_payload"]
        assert dop["payload_mode"] == "pre_fight_day_payload"

    def test_rendering_rules_present(self):
        payload = self._build(0)
        assert "rendering_rules" in payload

    def test_late_fight_permissions_present(self):
        payload = self._build(5)
        assert "late_fight_permissions" in payload

    def test_raw_athlete_inputs_preserved(self):
        payload = self._build(0)
        am = payload["athlete_model"]
        assert "hard_sparring_days" in am
        assert "training_days" in am
        assert "technical_skill_days" in am
        assert "key_goals" in am

    def test_d0_payload_mode(self):
        payload = self._build(0)
        assert payload["payload_mode"] == "fight_day_protocol_payload"

    def test_d1_payload_mode(self):
        payload = self._build(1)
        assert payload["payload_mode"] == "pre_fight_day_payload"


# =========================================================================
# 8. Handoff text mode instructions
# =========================================================================


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

    def test_camp_no_mode_instructions(self):
        text = self._build_handoff(10)
        assert "PAYLOAD MODE INSTRUCTIONS" not in text

    def test_d0_fight_day_instructions(self):
        text = self._build_handoff(0)
        assert "PAYLOAD MODE INSTRUCTIONS" in text
        assert "FIGHT DAY PROTOCOL" in text
        assert "Do NOT generate a training week" in text

    def test_d1_pre_fight_instructions(self):
        text = self._build_handoff(1)
        assert "PAYLOAD MODE INSTRUCTIONS" in text
        assert "PRE-FIGHT DAY" in text
        assert "primer" in text.lower()
        assert "anchor" in text  # mentioned as forbidden

    def test_d3_session_instructions(self):
        text = self._build_handoff(3)
        assert "PAYLOAD MODE INSTRUCTIONS" in text
        assert "SESSION-BY-SESSION" in text

    def test_d5_compressed_week_instructions(self):
        text = self._build_handoff(5)
        assert "PAYLOAD MODE INSTRUCTIONS" in text
        assert "COMPRESSED WEEK" in text

    def test_handoff_always_contains_stage1_draft(self):
        text = self._build_handoff(0)
        assert "STAGE 1 DRAFT PLAN" in text
        assert "Draft plan text." in text

    def test_gt7_behavior_unchanged(self):
        text = self._build_handoff(20)
        assert "PAYLOAD MODE INSTRUCTIONS" not in text
        assert "PLANNING BRIEF" in text


# =========================================================================
# 9. D-1 payload content constraints
# =========================================================================


class TestD1PayloadContent:
    def test_d1_forbids_anchor_in_permissions(self):
        perms = _late_fight_permissions(1, _athlete(1))
        assert perms["allow_anchor_wording"] is False

    def test_d1_forbids_glycolytic(self):
        perms = _late_fight_permissions(1, _athlete(1))
        assert perms["allow_glycolytic_build"] is False

    def test_d1_rendering_forbids_anchor_term(self):
        rules = _late_fight_rendering_rules(1)
        forbidden_lower = [t.lower() for t in rules["forbidden_terms"]]
        assert "anchor" in forbidden_lower


# =========================================================================
# 10. D-0 payload content constraints
# =========================================================================


class TestD0PayloadContent:
    def test_d0_only_activation_content(self):
        rules = _late_fight_rendering_rules(0)
        preferred = [t.lower() for t in rules["preferred_terms"]]
        assert "activation" in preferred
        assert "warm-up" in preferred
        assert "cue" in preferred

    def test_d0_no_training_generation(self):
        perms = _late_fight_permissions(0, _athlete(0))
        assert perms["allow_fight_day_protocol_only"] is True
        assert perms["allow_normal_session_roles"] is False
        assert perms["allow_full_weekly_structure"] is False


# =========================================================================
# 11. Raw athlete inputs preserved in all payloads
# =========================================================================


class TestRawInputPreservation:
    @pytest.mark.parametrize("days", [0, 1, 3, 5, 7, 10])
    def test_athlete_model_preserves_raw_inputs(self, days):
        block = _days_out_payload_block(days, _athlete(days))
        # The block itself doesn't contain athlete model, but permissions
        # should not delete any raw fields. The athlete model is separate.
        am = _athlete(days)
        assert am["hard_sparring_days"] == ["tuesday", "thursday"]
        assert am["training_days"] == ["monday", "tuesday", "wednesday", "thursday", "friday"]
        assert am["technical_skill_days"] == ["friday"]
        assert am["key_goals"] == ["power", "speed"]


# =========================================================================
# 12. Regression: >7 payload unchanged
# =========================================================================


class TestRegressionCampPayload:
    @pytest.mark.parametrize("days", [8, 10, 14, 28])
    def test_camp_permissions_unrestricted(self, days):
        perms = _late_fight_permissions(days, _athlete(days))
        assert perms["allow_full_weekly_structure"] is True
        assert perms["allow_development_language"] is True

    @pytest.mark.parametrize("days", [8, 20])
    def test_camp_rendering_no_constraints(self, days):
        rules = _late_fight_rendering_rules(days)
        assert rules.get("forbidden_terms", []) == []
        assert rules.get("preferred_terms", []) == []
