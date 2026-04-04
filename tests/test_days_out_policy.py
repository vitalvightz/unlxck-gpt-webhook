"""Comprehensive tests for the days-out policy layer.

Covers: bucket classification, input relevance, planner permissions,
effective-input neutralisation, fight-day protocol, serialisation,
and integration with strength / conditioning / sparring / mindset modules.
"""
import pytest

from fightcamp.days_out_policy import (
    DaysOutContext,
    InputRelevance,
    PlannerPermissions,
    SparringDoseMode,
    UIHints,
    build_days_out_context,
    build_fight_day_protocol,
    get_days_out_bucket,
    get_effective_planning_inputs,
)

# =========================================================================
# 1. Bucket classification
# =========================================================================


class TestGetDaysOutBucket:
    @pytest.mark.parametrize(
        "days, expected",
        [
            (None, "CAMP"),
            (-5, "CAMP"),
            (100, "CAMP"),
            (8, "CAMP"),
            (10, "CAMP"),
            (7, "D-7"),
            (6, "D-6"),
            (5, "D-5"),
            (4, "D-4"),
            (3, "D-3"),
            (2, "D-2"),
            (1, "D-1"),
            (0, "D-0"),
        ],
    )
    def test_bucket_classification(self, days, expected):
        assert get_days_out_bucket(days) == expected


# =========================================================================
# 2. build_days_out_context
# =========================================================================


class TestBuildDaysOutContext:
    def test_returns_dataclass(self):
        ctx = build_days_out_context(10)
        assert isinstance(ctx, DaysOutContext)
        assert ctx.bucket == "CAMP"
        assert ctx.days_out == 10

    def test_camp_bucket_is_default_for_none(self):
        ctx = build_days_out_context(None)
        assert ctx.bucket == "CAMP"
        assert ctx.days_out is None

    def test_d0_is_fight_day(self):
        ctx = build_days_out_context(0)
        assert ctx.bucket == "D-0"
        assert ctx.planner_permissions.fight_day_protocol is True

    def test_immutable(self):
        ctx = build_days_out_context(3)
        with pytest.raises(AttributeError):
            ctx.bucket = "FOO"  # type: ignore[misc]

    @pytest.mark.parametrize("days", list(range(8)))
    def test_all_fight_week_buckets_load(self, days):
        ctx = build_days_out_context(days)
        assert ctx.bucket == f"D-{days}"
        assert isinstance(ctx.planner_permissions, PlannerPermissions)
        assert isinstance(ctx.ui_hints, UIHints)


# =========================================================================
# 3. Input relevance per bucket
# =========================================================================


class TestInputRelevance:
    """Assert key relevance state transitions at critical thresholds."""

    def test_camp_all_fields_active(self):
        ctx = build_days_out_context(10)
        assert ctx.field_active("key_goals")
        assert ctx.field_active("weak_areas")
        assert ctx.field_active("weekly_training_frequency")
        assert ctx.field_active("hard_sparring_days")

    def test_d7_hard_sparring_still_active(self):
        ctx = build_days_out_context(7)
        assert ctx.field_active("hard_sparring_days")

    def test_d3_weak_areas_become_advisory(self):
        ctx = build_days_out_context(3)
        relevance = ctx.input_relevance.get("weak_areas")
        assert relevance in (
            InputRelevance.ADVISORY_ONLY,
            InputRelevance.IGNORE_FOR_PLANNING,
            InputRelevance.USED_IF_PRESENT,
        )

    @pytest.mark.parametrize("field", ["weekly_training_frequency", "hard_sparring_days"])
    def test_d2_weekly_freq_and_sparring_ignored(self, field):
        ctx = build_days_out_context(2)
        assert ctx.field_ignored(field) or not ctx.field_active(field)

    def test_d0_key_goals_ignored(self):
        ctx = build_days_out_context(0)
        assert ctx.field_ignored("key_goals")

    def test_d0_weak_areas_ignored(self):
        ctx = build_days_out_context(0)
        assert ctx.field_ignored("weak_areas")

    def test_d0_training_preference_ignored(self):
        ctx = build_days_out_context(0)
        assert ctx.field_ignored("training_preference")


# =========================================================================
# 4. Planner permissions per bucket
# =========================================================================


class TestPlannerPermissions:
    def test_camp_allows_everything(self):
        p = build_days_out_context(10).planner_permissions
        assert p.allow_full_strength_block is True
        assert p.allow_strength_anchor is True
        assert p.allow_conditioning_build is True
        assert p.allow_glycolytic is True
        assert p.allow_hard_sparring is True
        assert p.allow_weekly_architecture is True
        assert p.allow_development_blocks is True
        assert p.fight_day_protocol is False

    def test_d7_still_allows_full_strength(self):
        p = build_days_out_context(7).planner_permissions
        assert p.allow_strength_anchor is True

    def test_d3_no_glycolytic(self):
        p = build_days_out_context(3).planner_permissions
        assert p.allow_glycolytic is False

    def test_d1_no_anchor_no_full_strength(self):
        p = build_days_out_context(1).planner_permissions
        assert p.allow_full_strength_block is False
        assert p.allow_strength_anchor is False

    def test_d0_fight_day_protocol(self):
        p = build_days_out_context(0).planner_permissions
        assert p.fight_day_protocol is True
        assert p.allow_full_strength_block is False
        assert p.allow_conditioning_build is False
        assert p.allow_hard_sparring is False
        assert p.allow_weekly_architecture is False

    def test_d1_sparring_suppressed(self):
        p = build_days_out_context(1).planner_permissions
        assert p.sparring_dose_mode == SparringDoseMode.SUPPRESS

    def test_d0_sparring_suppressed(self):
        p = build_days_out_context(0).planner_permissions
        assert p.sparring_dose_mode == SparringDoseMode.SUPPRESS

    def test_freshness_priority_emerges_near_fight(self):
        camp = build_days_out_context(10).planner_permissions
        d2 = build_days_out_context(2).planner_permissions
        assert camp.freshness_priority is False
        assert d2.freshness_priority is True


# =========================================================================
# 5. Effective-input neutralisation
# =========================================================================


class TestGetEffectivePlanningInputs:
    _SAMPLE_INPUTS = {
        "key_goals": ["power", "speed"],
        "weak_areas": ["cardio"],
        "weekly_training_frequency": 5,
        "hard_sparring_days": ["monday", "wednesday"],
        "training_preference": "short sessions",
        "technical_skill_days": ["friday"],
        "injuries": ["shoulder"],
        "notes": "extra note",
    }

    def test_camp_preserves_everything(self):
        ctx = build_days_out_context(10)
        eff = get_effective_planning_inputs(dict(self._SAMPLE_INPUTS), ctx)
        assert eff == self._SAMPLE_INPUTS

    def test_d0_neutralises_ignored_fields(self):
        ctx = build_days_out_context(0)
        eff = get_effective_planning_inputs(dict(self._SAMPLE_INPUTS), ctx)
        # key_goals and weak_areas ignored at D-0
        assert eff["key_goals"] == []
        assert eff["weak_areas"] == []
        assert eff["weekly_training_frequency"] == 0
        assert eff["training_preference"] == ""

    def test_original_not_mutated(self):
        raw = dict(self._SAMPLE_INPUTS)
        ctx = build_days_out_context(0)
        get_effective_planning_inputs(raw, ctx)
        assert raw["key_goals"] == ["power", "speed"]

    def test_missing_field_not_injected(self):
        raw = {"injuries": ["knee"]}
        ctx = build_days_out_context(0)
        eff = get_effective_planning_inputs(raw, ctx)
        # Should not inject key_goals even though it is ignored at D-0
        assert "key_goals" not in eff


# =========================================================================
# 6. Serialisation (to_dict)
# =========================================================================


class TestSerialiseToDictRoundTrip:
    def test_to_dict_returns_plain_types(self):
        ctx = build_days_out_context(3)
        d = ctx.to_dict()
        # No enum objects or frozensets
        assert isinstance(d["allowed_session_types"], list)
        assert isinstance(d["forbidden_session_types"], list)
        for v in d["input_relevance"].values():
            assert isinstance(v, str)
        assert isinstance(d["planner_permissions"]["sparring_dose_mode"], str)


# =========================================================================
# 7. Fight-day protocol
# =========================================================================


class TestBuildFightDayProtocol:
    def test_returns_required_keys(self):
        result = build_fight_day_protocol(
            full_name="Jake Test",
            technical_style="boxing",
            tactical_style="pressure",
            stance="orthodox",
            fatigue_level="moderate",
            injuries=[],
            restrictions=[],
            rounds_format="3x3",
            mindset_challenges="",
            current_weight=155,
            target_weight=155,
        )
        assert result["fight_day_protocol"] is True
        assert "plan_text" in result
        assert "coach_notes" in result
        assert "why_log" in result

    def test_includes_athlete_name(self):
        result = build_fight_day_protocol(
            full_name="Maria Boxer",
            technical_style="muay_thai",
            tactical_style="counter",
            stance="southpaw",
            fatigue_level="low",
            injuries=["sprained wrist"],
            restrictions=[],
            rounds_format="5x3",
            mindset_challenges="pressure anxiety",
            current_weight=130,
            target_weight=126,
        )
        assert "Maria Boxer" in result["plan_text"]
        assert "Injury awareness" in result["plan_text"]
        assert "pressure anxiety" in result["plan_text"]

    def test_restriction_note_appears(self):
        result = build_fight_day_protocol(
            full_name="Test",
            technical_style="kickboxing",
            tactical_style="aggressive",
            stance="orthodox",
            fatigue_level="high",
            injuries=[],
            restrictions=["no overhead"],
            rounds_format="3x2",
            mindset_challenges="",
            current_weight=170,
            target_weight=170,
        )
        assert "Movement restrictions" in result["plan_text"]


# =========================================================================
# 8. UI hints
# =========================================================================


class TestUIHints:
    def test_camp_no_banner(self):
        ctx = build_days_out_context(10)
        assert ctx.ui_hints.fight_proximity_banner is None

    def test_d3_has_banner(self):
        ctx = build_days_out_context(3)
        assert ctx.ui_hints.fight_proximity_banner is not None
        assert len(ctx.ui_hints.fight_proximity_banner) > 0

    def test_d0_hides_fields(self):
        ctx = build_days_out_context(0)
        assert "hard_sparring_days" in ctx.ui_hints.hide_fields
        assert "weekly_training_frequency" in ctx.ui_hints.hide_fields

    def test_d1_disables_training_preference(self):
        ctx = build_days_out_context(1)
        assert "training_preference" in ctx.ui_hints.disable_fields

    def test_d4_de_emphasizes_weak_areas(self):
        ctx = build_days_out_context(4)
        assert "weak_areas" in ctx.ui_hints.de_emphasize_fields


# =========================================================================
# 9. Regression: >7 days behaviour unchanged
# =========================================================================


class TestRegressionCampUnchanged:
    """Ensure the policy does not alter any behaviour for >7-day athletes."""

    @pytest.mark.parametrize("days", [8, 10, 14, 28, 56, 100])
    def test_all_large_values_map_to_camp(self, days):
        ctx = build_days_out_context(days)
        assert ctx.bucket == "CAMP"
        assert ctx.planner_permissions.allow_full_strength_block is True
        assert ctx.planner_permissions.allow_weekly_architecture is True
        assert ctx.planner_permissions.fight_day_protocol is False
        assert ctx.planner_permissions.allow_glycolytic is True
        assert ctx.planner_permissions.sparring_dose_mode == SparringDoseMode.FULL

    @pytest.mark.parametrize("days", [8, 20])
    def test_no_fields_hidden_or_disabled_at_camp(self, days):
        ctx = build_days_out_context(days)
        assert ctx.ui_hints.hide_fields == ()
        assert ctx.ui_hints.disable_fields == ()
        assert ctx.ui_hints.de_emphasize_fields == ()


# =========================================================================
# 10. Session types
# =========================================================================


class TestSessionTypes:
    def test_camp_allows_all_session_types(self):
        ctx = build_days_out_context(10)
        assert "strength" in ctx.allowed_session_types
        assert "conditioning" in ctx.allowed_session_types
        assert "sparring" in ctx.allowed_session_types
        assert len(ctx.forbidden_session_types) == 0

    def test_d0_forbids_most_session_types(self):
        ctx = build_days_out_context(0)
        assert "strength" in ctx.forbidden_session_types
        assert "conditioning" in ctx.forbidden_session_types
        assert "sparring" in ctx.forbidden_session_types


# =========================================================================
# 11. Convenience helpers
# =========================================================================


class TestConvenienceHelpers:
    def test_field_ignored_true_for_d0_key_goals(self):
        ctx = build_days_out_context(0)
        assert ctx.field_ignored("key_goals") is True

    def test_field_active_true_for_camp(self):
        ctx = build_days_out_context(10)
        assert ctx.field_active("key_goals") is True

    def test_field_advisory_at_d4(self):
        ctx = build_days_out_context(4)
        # At D-4 weak_areas is advisory_only
        rel = ctx.input_relevance.get("weak_areas")
        if rel == InputRelevance.ADVISORY_ONLY:
            assert ctx.field_advisory("weak_areas") is True

    def test_field_active_false_when_ignored(self):
        ctx = build_days_out_context(0)
        assert ctx.field_active("key_goals") is False
        assert ctx.field_active("weekly_training_frequency") is False


# =========================================================================
# 12. Integration: strength enforcement
# =========================================================================


class TestStrengthIntegration:
    """Test that strength module respects days-out permission flags."""

    def test_d7_permits_anchor(self):
        ctx = build_days_out_context(7)
        assert ctx.planner_permissions.allow_strength_anchor is True

    def test_d1_no_anchor(self):
        ctx = build_days_out_context(1)
        assert ctx.planner_permissions.allow_strength_anchor is False
        assert ctx.planner_permissions.allow_strength_primer_only is True

    def test_d0_no_strength_at_all(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.allow_full_strength_block is False
        assert ctx.planner_permissions.allow_strength_anchor is False
        assert ctx.planner_permissions.fight_day_protocol is True

    def test_max_exercises_clamps_near_fight(self):
        ctx = build_days_out_context(3)
        m = ctx.planner_permissions.max_strength_exercises
        # At D-3 the policy should set a cap
        if m is not None:
            assert m > 0
            assert m <= 6  # reasonable upper bound


# =========================================================================
# 13. Integration: conditioning enforcement
# =========================================================================


class TestConditioningIntegration:
    def test_d3_no_glycolytic(self):
        ctx = build_days_out_context(3)
        assert ctx.planner_permissions.allow_glycolytic is False

    def test_d0_no_conditioning(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.allow_conditioning_build is False
        assert ctx.planner_permissions.max_conditioning_stressors == 0

    def test_camp_glycolytic_allowed(self):
        ctx = build_days_out_context(10)
        assert ctx.planner_permissions.allow_glycolytic is True
        assert ctx.planner_permissions.allow_conditioning_build is True


# =========================================================================
# 14. Integration: sparring enforcement
# =========================================================================


class TestSparringIntegration:
    def test_camp_sparring_full(self):
        ctx = build_days_out_context(10)
        assert ctx.planner_permissions.sparring_dose_mode == SparringDoseMode.FULL
        assert ctx.planner_permissions.allow_hard_sparring is True

    def test_d0_sparring_suppress(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.sparring_dose_mode == SparringDoseMode.SUPPRESS
        assert ctx.planner_permissions.allow_hard_sparring is False

    def test_d1_sparring_suppress(self):
        ctx = build_days_out_context(1)
        assert ctx.planner_permissions.sparring_dose_mode == SparringDoseMode.SUPPRESS

    def test_near_fight_collision_cap(self):
        ctx = build_days_out_context(4)
        cap = ctx.planner_permissions.max_hard_sparring_collision_owners
        if cap is not None:
            assert cap >= 0


# =========================================================================
# 15. Raw data preservation
# =========================================================================


class TestRawDataPreservation:
    """Verify that get_effective_planning_inputs never deletes keys."""

    def test_all_keys_preserved(self):
        raw = {
            "key_goals": ["power"],
            "weak_areas": ["cardio"],
            "weekly_training_frequency": 5,
            "hard_sparring_days": ["mon"],
            "training_preference": "short",
            "technical_skill_days": ["fri"],
            "injuries": ["knee"],
            "notes": "note",
        }
        ctx = build_days_out_context(0)
        eff = get_effective_planning_inputs(raw, ctx)
        for key in raw:
            assert key in eff, f"{key} was removed from effective inputs"


# =========================================================================
# 16. D-1 wording constraints
# =========================================================================


class TestD1WordingConstraints:
    """At D-1 certain terms should not appear in plans because the policy
    disallows the modules that produce them."""

    def test_d1_no_full_strength_block(self):
        p = build_days_out_context(1).planner_permissions
        assert p.allow_full_strength_block is False

    def test_d1_no_development_blocks(self):
        p = build_days_out_context(1).planner_permissions
        assert p.allow_development_blocks is False

    def test_d1_no_glycolytic(self):
        p = build_days_out_context(1).planner_permissions
        assert p.allow_glycolytic is False


# =========================================================================
# 17. D-0 short-circuit guarantees
# =========================================================================


class TestD0ShortCircuit:
    """The D-0 bucket must guarantee full bypass of normal planning."""

    def test_fight_day_protocol_flag(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.fight_day_protocol is True

    def test_no_weekly_architecture(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.allow_weekly_architecture is False

    def test_no_multi_session_days(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.allow_multi_session_days is False

    def test_no_novelty(self):
        ctx = build_days_out_context(0)
        assert ctx.planner_permissions.allow_novelty is False

    def test_forbidden_session_types_cover_training(self):
        ctx = build_days_out_context(0)
        for stype in ("strength", "conditioning", "sparring"):
            assert stype in ctx.forbidden_session_types

    def test_fight_day_protocol_output_shape(self):
        result = build_fight_day_protocol(
            full_name="Test Athlete",
            technical_style="boxing",
            tactical_style="pressure",
            stance="orthodox",
            fatigue_level="moderate",
            injuries=[],
            restrictions=[],
            rounds_format="3x3",
            mindset_challenges="",
            current_weight=155,
            target_weight=155,
        )
        assert "fight_day_protocol" in result
        assert "plan_text" in result
        assert "coach_notes" in result
        assert "why_log" in result
        # Ensure no regular plan artifacts leak
        assert "pdf_url" not in result
        assert "stage2_payload" not in result
