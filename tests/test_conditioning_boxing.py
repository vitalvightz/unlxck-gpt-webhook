"""
Tests for fightcamp/conditioning_boxing.py

Covers every function in the module:
  - _restriction_key_set
  - _conditioning_context_text
  - _sanitize_sport_language
  - _normalize_conditioning_name
  - _is_pool_treading_drill
  - _is_continuous_swim_drill
  - _is_shadowbox_aerobic_drill
  - _is_sled_drag_aerobic_drill
  - _boxing_aerobic_context_flags
  - _boxing_aerobic_priority_adjustment
  - _boxing_aerobic_preference_rank
  - _violates_sport_language_blacklist
  - _alactic_maintenance_fallback
  - _suppress_alactic_maintenance
"""
import pytest

from fightcamp.conditioning_boxing import (
    _restriction_key_set,
    _conditioning_context_text,
    _sanitize_sport_language,
    _normalize_conditioning_name,
    _is_pool_treading_drill,
    _is_continuous_swim_drill,
    _is_shadowbox_aerobic_drill,
    _is_sled_drag_aerobic_drill,
    _boxing_aerobic_context_flags,
    _boxing_aerobic_priority_adjustment,
    _boxing_aerobic_preference_rank,
    _violates_sport_language_blacklist,
    _alactic_maintenance_fallback,
    _suppress_alactic_maintenance,
    SPORT_LANGUAGE_BLACKLIST,
    PLAIN_CONDITIONING_NAME_MAP,
    BOXING_NAME_MAP,
)


# ──────────────────────────────────────────────────────────────────────────────
# _restriction_key_set
# ──────────────────────────────────────────────────────────────────────────────

class TestRestrictionKeySet:
    def test_none_returns_empty(self):
        assert _restriction_key_set(None) == set()

    def test_empty_list_returns_empty(self):
        assert _restriction_key_set([]) == set()

    def test_string_list(self):
        result = _restriction_key_set(["high_impact", "No_Jumping"])
        assert result == {"high_impact", "no_jumping"}

    def test_dict_list_with_key_field(self):
        restrictions = [{"key": "High_Impact"}, {"key": "no_jumping"}]
        result = _restriction_key_set(restrictions)
        assert result == {"high_impact", "no_jumping"}

    def test_dict_with_restriction_key_field(self):
        restrictions = [{"restriction_key": "Max_Velocity"}]
        result = _restriction_key_set(restrictions)
        assert {"max_velocity"} == result

    def test_dict_with_type_field_fallback(self):
        restrictions = [{"type": "High_Impact_Lower"}]
        result = _restriction_key_set(restrictions)
        assert result == {"high_impact_lower"}

    def test_single_string_not_list(self):
        # Non-list input should be wrapped
        result = _restriction_key_set("high_impact")
        assert result == {"high_impact"}

    def test_mixed_dict_and_string(self):
        restrictions = [{"key": "high_impact"}, "no_jumping"]
        result = _restriction_key_set(restrictions)
        assert result == {"high_impact", "no_jumping"}

    def test_dict_missing_all_key_fields(self):
        # Dict with no recognised key field yields nothing
        result = _restriction_key_set([{"unknown_field": "value"}])
        assert result == set()


# ──────────────────────────────────────────────────────────────────────────────
# _conditioning_context_text
# ──────────────────────────────────────────────────────────────────────────────

class TestConditioningContextText:
    def test_empty_returns_empty_string(self):
        assert _conditioning_context_text() == ""

    def test_single_string(self):
        result = _conditioning_context_text("Knee Pain")
        assert "knee pain" in result

    def test_single_list(self):
        result = _conditioning_context_text(["ankle", "knee"])
        assert "ankle" in result
        assert "knee" in result

    def test_mixed_list_and_string(self):
        result = _conditioning_context_text(["ankle"], "strength")
        assert "ankle" in result
        assert "strength" in result

    def test_none_group_skipped(self):
        result = _conditioning_context_text(None, "ankle")
        assert "ankle" in result

    def test_empty_list_group_skipped(self):
        result = _conditioning_context_text([], "ankle")
        assert result.strip() == "ankle"

    def test_all_lowercased(self):
        result = _conditioning_context_text(["ANKLE", "KNEE"])
        assert result == result.lower()


# ──────────────────────────────────────────────────────────────────────────────
# _sanitize_sport_language
# ──────────────────────────────────────────────────────────────────────────────

class TestSanitizeSportLanguage:
    def test_empty_string_passthrough(self):
        assert _sanitize_sport_language("", fight_format="boxing") == ""

    def test_non_boxing_format_unchanged(self):
        text = "double leg takedown drill"
        assert _sanitize_sport_language(text, fight_format="mma") == text

    def test_takedown_replaced(self):
        result = _sanitize_sport_language("Takedown drill", fight_format="boxing")
        assert "takedown" not in result.lower()
        assert "entr" in result.lower()

    def test_double_leg_replaced(self):
        result = _sanitize_sport_language("double-leg entry", fight_format="boxing")
        assert "double" not in result.lower()

    def test_single_leg_replaced(self):
        result = _sanitize_sport_language("single leg drill", fight_format="boxing")
        assert "single leg" not in result.lower()

    def test_sprawl_replaced(self):
        result = _sanitize_sport_language("Sprawl and reset", fight_format="boxing")
        assert "sprawl" not in result.lower()

    def test_elbow_replaced(self):
        result = _sanitize_sport_language("Elbow strike combo", fight_format="boxing")
        assert "elbow" not in result.lower()
        assert "hook" in result.lower()

    def test_cage_replaced(self):
        result = _sanitize_sport_language("Cage pressure drill", fight_format="boxing")
        assert "cage" not in result.lower()
        assert "ring" in result.lower()

    def test_octagon_replaced(self):
        result = _sanitize_sport_language("Octagon movement", fight_format="boxing")
        assert "octagon" not in result.lower()
        assert "ring" in result.lower()

    def test_grappling_replaced(self):
        result = _sanitize_sport_language("Grappling conditioning", fight_format="boxing")
        assert "grappling" not in result.lower()

    def test_ground_and_pound_replaced(self):
        result = _sanitize_sport_language("Ground and pound", fight_format="boxing")
        assert "ground" not in result.lower() or "punch" in result.lower()

    def test_thai_clinch_replaced(self):
        result = _sanitize_sport_language("Thai clinch work", fight_format="boxing")
        assert "thai clinch" not in result.lower()

    def test_case_insensitive(self):
        result = _sanitize_sport_language("TAKEDOWN entry", fight_format="boxing")
        assert "TAKEDOWN" not in result


# ──────────────────────────────────────────────────────────────────────────────
# _normalize_conditioning_name
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizeConditioningName:
    def test_plain_name_map_applied(self):
        for original, expected in PLAIN_CONDITIONING_NAME_MAP.items():
            # Non-boxing: only plain map, no boxing-specific sanitization needed
            result = _normalize_conditioning_name(original, fight_format="mma")
            assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_boxing_name_map_applied_after_plain(self):
        for original, expected in BOXING_NAME_MAP.items():
            result = _normalize_conditioning_name(original, fight_format="boxing")
            # After BOXING_NAME_MAP the result has no sport-language issues
            assert expected in result or result == expected

    def test_unknown_name_passthrough(self):
        result = _normalize_conditioning_name("Unknown Drill XYZ", fight_format="boxing")
        assert result == "Unknown Drill XYZ"

    def test_boxing_sanitization_applied_to_remaining_blacklist(self):
        # Name not in either map but contains blacklisted term
        result = _normalize_conditioning_name("Cage pressure intervals", fight_format="boxing")
        assert "cage" not in result.lower()

    def test_non_boxing_no_sanitization(self):
        result = _normalize_conditioning_name("Cage pressure intervals", fight_format="mma")
        assert "cage" in result.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Drill classification helpers
# ──────────────────────────────────────────────────────────────────────────────

class TestDrillClassification:
    # _is_pool_treading_drill
    def test_pool_treading_by_name(self):
        assert _is_pool_treading_drill({"name": "Pool Treading"})
        assert _is_pool_treading_drill({"name": "treading in pool"})

    def test_pool_treading_false_for_swim(self):
        assert not _is_pool_treading_drill({"name": "Freestyle Swim", "modality": "swim"})

    def test_pool_treading_false_empty(self):
        assert not _is_pool_treading_drill({})

    # _is_continuous_swim_drill
    def test_continuous_swim_by_modality_and_name(self):
        assert _is_continuous_swim_drill({"modality": "swim", "name": "Freestyle Swimming"})

    def test_continuous_swim_excludes_pool_treading(self):
        assert not _is_continuous_swim_drill({"modality": "swim", "name": "Pool Treading"})

    def test_continuous_swim_excludes_pool_running(self):
        assert not _is_continuous_swim_drill({"modality": "swim", "name": "Pool Running"})

    def test_continuous_swim_excludes_pool_walking(self):
        assert not _is_continuous_swim_drill({"modality": "swim", "name": "Pool Walking"})

    def test_continuous_swim_false_non_swim_modality(self):
        assert not _is_continuous_swim_drill({"modality": "bike", "name": "Bike Swim"})

    # _is_shadowbox_aerobic_drill
    def test_shadowbox_by_modality(self):
        assert _is_shadowbox_aerobic_drill({"modality": "shadowbox", "name": "Drill"})

    def test_shadowbox_by_name(self):
        assert _is_shadowbox_aerobic_drill({"name": "Tempo Shadowboxing", "modality": "cardio"})

    def test_shadowbox_false_for_bike(self):
        assert not _is_shadowbox_aerobic_drill({"modality": "bike", "name": "Bike Drill"})

    # _is_sled_drag_aerobic_drill
    def test_sled_by_modality(self):
        assert _is_sled_drag_aerobic_drill({"modality": "sled", "name": "Sled Work"})

    def test_sled_by_name(self):
        assert _is_sled_drag_aerobic_drill({"name": "Sled Drag Intervals", "modality": "cardio"})

    def test_sled_false_for_bike(self):
        assert not _is_sled_drag_aerobic_drill({"modality": "bike", "name": "Bike"})


# ──────────────────────────────────────────────────────────────────────────────
# _boxing_aerobic_context_flags
# ──────────────────────────────────────────────────────────────────────────────

class TestBoxingAerobicContextFlags:
    def _base_kwargs(self, **overrides):
        defaults = dict(
            injuries=[],
            weaknesses=[],
            goals=[],
            restrictions=[],
            equipment_access_set=set(),
        )
        defaults.update(overrides)
        return defaults

    def test_clean_athlete_no_flags(self):
        flags = _boxing_aerobic_context_flags(**self._base_kwargs())
        assert not flags["lower_limb_unload_desirable"]
        assert not flags["impact_tolerance_reduced"]
        assert not flags["upper_body_swim_sensitive"]
        assert not flags["bike_available"]
        assert not flags["sled_available"]
        # No bike, no sled → pool treading justified as fallback
        assert flags["pool_treading_justified"]

    def test_ankle_injury_sets_lower_limb_unload(self):
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(injuries=["ankle sprain"])
        )
        assert flags["lower_limb_unload_desirable"]

    def test_knee_weakness_sets_lower_limb_unload(self):
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(weaknesses=["knee stability"])
        )
        assert flags["lower_limb_unload_desirable"]

    def test_shoulder_injury_sets_upper_body_swim_sensitive(self):
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(injuries=["shoulder impingement"])
        )
        assert flags["upper_body_swim_sensitive"]

    def test_high_impact_restriction_sets_impact_tolerance_reduced(self):
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(
                restrictions=[{"key": "high_impact"}]
            )
        )
        assert flags["impact_tolerance_reduced"]

    def test_bike_available_sets_bike_flag(self):
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(equipment_access_set={"assault_bike"})
        )
        assert flags["bike_available"]

    def test_sled_available_sets_sled_flag(self):
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(equipment_access_set={"sled"})
        )
        assert flags["sled_available"]

    def test_pool_treading_strong_case_requires_all_conditions(self):
        # Strong case: lower limb + impact reduced + upper body sensitive + no bike
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(
                injuries=["ankle sprain", "shoulder soreness"],
                restrictions=[{"key": "high_impact"}],
                equipment_access_set=set(),  # no bike
            )
        )
        assert flags["pool_treading_strong_case"]

    def test_pool_treading_strong_case_false_with_bike(self):
        # Even with all injury conditions, bike available kills strong case
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(
                injuries=["ankle sprain", "shoulder soreness"],
                restrictions=[{"key": "high_impact"}],
                equipment_access_set={"assault_bike"},
            )
        )
        assert not flags["pool_treading_strong_case"]

    def test_pool_treading_justified_with_bike_and_sled_available(self):
        # Bike and sled available, no injuries → not justified
        flags = _boxing_aerobic_context_flags(
            **self._base_kwargs(
                equipment_access_set={"assault_bike", "sled"}
            )
        )
        assert not flags["pool_treading_justified"]


# ──────────────────────────────────────────────────────────────────────────────
# _boxing_aerobic_priority_adjustment
# ──────────────────────────────────────────────────────────────────────────────

class TestBoxingAerobicPriorityAdjustment:
    def _base_kwargs(self, **overrides):
        defaults = dict(
            injuries=[],
            weaknesses=[],
            goals=[],
            restrictions=[],
            equipment_access_set=set(),
        )
        defaults.update(overrides)
        return defaults

    def test_bike_drill_gets_high_bonus(self):
        drill = {"modality": "bike", "name": "Assault Bike"}
        adj = _boxing_aerobic_priority_adjustment(drill, **self._base_kwargs())
        assert adj == 1.5

    def test_pool_treading_strong_case_gets_bonus(self):
        drill = {"name": "Pool Treading", "modality": "swim"}
        adj = _boxing_aerobic_priority_adjustment(
            drill,
            **self._base_kwargs(
                injuries=["ankle sprain", "shoulder soreness"],
                restrictions=[{"key": "high_impact"}],
                equipment_access_set=set(),
            )
        )
        assert adj == 1.15

    def test_pool_treading_unjustified_gets_penalty(self):
        drill = {"name": "Pool Treading", "modality": "swim"}
        # Bike and sled available, no injuries
        adj = _boxing_aerobic_priority_adjustment(
            drill,
            **self._base_kwargs(equipment_access_set={"assault_bike", "sled"})
        )
        assert adj == -2.0

    def test_pool_treading_justified_not_strong_gets_small_penalty(self):
        drill = {"name": "Pool Treading", "modality": "swim"}
        # Only ankle injury, no shoulder, no bike — justified but not strong
        adj = _boxing_aerobic_priority_adjustment(
            drill,
            **self._base_kwargs(
                injuries=["ankle sprain"],
                equipment_access_set={"assault_bike"},  # bike present kills strong case
            )
        )
        assert adj == -0.25

    def test_continuous_swim_baseline(self):
        drill = {"modality": "swim", "name": "Freestyle Swimming"}
        adj = _boxing_aerobic_priority_adjustment(drill, **self._base_kwargs())
        assert adj == pytest.approx(1.1)

    def test_continuous_swim_reduced_for_shoulder_injury(self):
        drill = {"modality": "swim", "name": "Freestyle Swimming"}
        adj = _boxing_aerobic_priority_adjustment(
            drill,
            **self._base_kwargs(injuries=["shoulder impingement"])
        )
        assert adj == pytest.approx(1.1 - 0.6)

    def test_shadowbox_reduced_for_lower_limb_unload(self):
        drill = {"modality": "shadowbox", "name": "Tempo Shadowboxing"}
        adj_clean = _boxing_aerobic_priority_adjustment(drill, **self._base_kwargs())
        adj_ankle = _boxing_aerobic_priority_adjustment(
            drill,
            **self._base_kwargs(injuries=["ankle sprain"])
        )
        assert adj_ankle < adj_clean

    def test_sled_reduced_for_lower_limb_unload(self):
        drill = {"modality": "sled", "name": "Sled Drag Intervals"}
        adj_clean = _boxing_aerobic_priority_adjustment(drill, **self._base_kwargs())
        adj_ankle = _boxing_aerobic_priority_adjustment(
            drill,
            **self._base_kwargs(injuries=["ankle sprain"])
        )
        assert adj_ankle < adj_clean

    def test_unknown_modality_returns_zero(self):
        drill = {"modality": "unknown_modality", "name": "Weird Drill"}
        adj = _boxing_aerobic_priority_adjustment(drill, **self._base_kwargs())
        assert adj == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# _boxing_aerobic_preference_rank
# ──────────────────────────────────────────────────────────────────────────────

class TestBoxingAerobicPreferenceRank:
    def _base_kwargs(self, **overrides):
        defaults = dict(
            injuries=[],
            weaknesses=[],
            goals=[],
            restrictions=[],
            equipment_access_set=set(),
        )
        defaults.update(overrides)
        return defaults

    def test_bike_is_rank_zero(self):
        drill = {"modality": "bike", "name": "Assault Bike"}
        assert _boxing_aerobic_preference_rank(drill, **self._base_kwargs()) == 0

    def test_pool_treading_strong_case_rank_one(self):
        drill = {"name": "Pool Treading", "modality": "swim"}
        rank = _boxing_aerobic_preference_rank(
            drill,
            **self._base_kwargs(
                injuries=["ankle sprain", "shoulder soreness"],
                restrictions=[{"key": "high_impact"}],
                equipment_access_set=set(),
            )
        )
        assert rank == 1

    def test_pool_treading_unjustified_rank_five(self):
        drill = {"name": "Pool Treading", "modality": "swim"}
        rank = _boxing_aerobic_preference_rank(
            drill,
            **self._base_kwargs(equipment_access_set={"assault_bike", "sled"})
        )
        assert rank == 5

    def test_continuous_swim_upper_body_sensitive_rank_three(self):
        drill = {"modality": "swim", "name": "Freestyle Swimming"}
        rank = _boxing_aerobic_preference_rank(
            drill,
            **self._base_kwargs(injuries=["shoulder impingement"])
        )
        assert rank == 3

    def test_continuous_swim_clean_rank_one(self):
        drill = {"modality": "swim", "name": "Freestyle Swimming"}
        rank = _boxing_aerobic_preference_rank(drill, **self._base_kwargs())
        assert rank == 1

    def test_shadowbox_lower_limb_rank_four(self):
        drill = {"modality": "shadowbox", "name": "Tempo Shadowboxing"}
        rank = _boxing_aerobic_preference_rank(
            drill,
            **self._base_kwargs(injuries=["ankle sprain"])
        )
        assert rank == 4

    def test_shadowbox_clean_rank_two(self):
        drill = {"modality": "shadowbox", "name": "Tempo Shadowboxing"}
        rank = _boxing_aerobic_preference_rank(drill, **self._base_kwargs())
        assert rank == 2

    def test_lower_rank_means_higher_preference(self):
        # Bike (0) should be preferred over shadowbox (2) for a clean boxer
        bike = {"modality": "bike", "name": "Assault Bike"}
        shadow = {"modality": "shadowbox", "name": "Tempo Shadowboxing"}
        kwargs = self._base_kwargs()
        assert (
            _boxing_aerobic_preference_rank(bike, **kwargs)
            < _boxing_aerobic_preference_rank(shadow, **kwargs)
        )


# ──────────────────────────────────────────────────────────────────────────────
# _violates_sport_language_blacklist
# ──────────────────────────────────────────────────────────────────────────────

class TestViolatesSportLanguageBlacklist:
    def test_clean_drill_no_violation(self):
        drill = {"name": "Assault Bike Intervals", "modality": "bike"}
        assert not _violates_sport_language_blacklist(drill, fight_format="boxing")

    def test_takedown_in_name_violates_boxing(self):
        drill = {"name": "Takedown Drill", "modality": "cardio"}
        assert _violates_sport_language_blacklist(drill, fight_format="boxing")

    def test_cage_in_name_violates_boxing(self):
        drill = {"name": "Cage Pressure", "modality": "cardio"}
        assert _violates_sport_language_blacklist(drill, fight_format="boxing")

    def test_elbow_in_name_violates_boxing(self):
        drill = {"name": "Elbow Strike Conditioning", "modality": "cardio"}
        assert _violates_sport_language_blacklist(drill, fight_format="boxing")

    def test_grappling_in_purpose_violates_boxing(self):
        drill = {"name": "Conditioning", "purpose": "grappling endurance"}
        assert _violates_sport_language_blacklist(drill, fight_format="boxing")

    def test_mma_format_no_violation(self):
        # MMA has no blacklist — nothing violates
        drill = {"name": "Takedown Drill", "modality": "cardio"}
        assert not _violates_sport_language_blacklist(drill, fight_format="mma")

    def test_empty_drill_no_violation(self):
        assert not _violates_sport_language_blacklist({}, fight_format="boxing")

    def test_blacklist_is_case_insensitive(self):
        drill = {"name": "TAKEDOWN Entry", "modality": "cardio"}
        assert _violates_sport_language_blacklist(drill, fight_format="boxing")


# ──────────────────────────────────────────────────────────────────────────────
# _alactic_maintenance_fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestAlacticMaintenanceFallback:
    def test_returns_dict_with_required_keys(self):
        result = _alactic_maintenance_fallback("SPP")
        for key in ("system", "name", "load", "rest", "timing", "purpose",
                    "red_flags", "equipment", "required_equipment", "generic_fallback"):
            assert key in result, f"Missing key: {key}"

    def test_system_is_alactic(self):
        assert _alactic_maintenance_fallback("SPP")["system"] == "ALACTIC"
        assert _alactic_maintenance_fallback("TAPER")["system"] == "ALACTIC"

    def test_spp_gets_higher_round_count(self):
        spp = _alactic_maintenance_fallback("SPP")
        taper = _alactic_maintenance_fallback("TAPER")
        # SPP: 6–8 rounds, TAPER: 4–6 rounds
        assert "6–8" in spp["timing"]
        assert "4–6" in taper["timing"]

    def test_generic_fallback_flag_true(self):
        assert _alactic_maintenance_fallback("GPP")["generic_fallback"] is True

    def test_equipment_lists_empty(self):
        result = _alactic_maintenance_fallback("SPP")
        assert result["equipment"] == []
        assert result["required_equipment"] == []

    def test_case_insensitive_phase(self):
        # Should normalise lowercase input
        result = _alactic_maintenance_fallback("spp")
        assert "6–8" in result["timing"]


# ──────────────────────────────────────────────────────────────────────────────
# _suppress_alactic_maintenance
# ──────────────────────────────────────────────────────────────────────────────

class TestSuppressAlacticMaintenance:
    def test_high_fatigue_suppresses(self):
        assert _suppress_alactic_maintenance(fatigue="high", injuries=[])

    def test_low_fatigue_does_not_suppress(self):
        assert not _suppress_alactic_maintenance(fatigue="low", injuries=[])

    def test_moderate_fatigue_does_not_suppress(self):
        assert not _suppress_alactic_maintenance(fatigue="moderate", injuries=[])

    def test_concussion_suppresses(self):
        assert _suppress_alactic_maintenance(
            fatigue="low", injuries=["concussion"]
        )

    def test_dizzy_suppresses(self):
        assert _suppress_alactic_maintenance(fatigue="low", injuries=["dizzy spells"])

    def test_achilles_suppresses(self):
        assert _suppress_alactic_maintenance(
            fatigue="low", injuries=["achilles tendinopathy"]
        )

    def test_calf_tear_suppresses(self):
        assert _suppress_alactic_maintenance(
            fatigue="low", injuries=["calf tear"]
        )

    def test_hamstring_tear_suppresses(self):
        assert _suppress_alactic_maintenance(
            fatigue="low", injuries=["hamstring tear"]
        )

    def test_vertigo_suppresses(self):
        assert _suppress_alactic_maintenance(
            fatigue="low", injuries=["vertigo"]
        )

    def test_minor_injury_does_not_suppress(self):
        assert not _suppress_alactic_maintenance(
            fatigue="low", injuries=["shoulder soreness"]
        )

    def test_empty_injuries_low_fatigue_does_not_suppress(self):
        assert not _suppress_alactic_maintenance(fatigue="low", injuries=[])

    def test_fatigue_case_insensitive(self):
        assert _suppress_alactic_maintenance(fatigue="HIGH", injuries=[])

    def test_multiple_injuries_any_triggers(self):
        assert _suppress_alactic_maintenance(
            fatigue="low", injuries=["shoulder soreness", "achilles pain"]
        )
