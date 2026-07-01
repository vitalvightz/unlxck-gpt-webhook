"""Tests for the D-14 to D-21 bridge rule set.

Covers the unit-test cases listed in the evidence-based spec plus the
modifier interactions: fatigue / weight-cut / injury / sport / style.
"""

from __future__ import annotations

import pytest

from fightcamp.stage2_payload_late_fight import (
    TIMING_STATE_BRIDGE,
    TIMING_STATE_LATE_TAPER,
    TIMING_STATE_NORMAL,
    _declared_hard_spar_cap,
    _hard_spar_status_for_countdown_offset,
    bridge_sub_band,
    compute_bridge_rules,
    timing_state,
)


class TestTimingStates:
    @pytest.mark.parametrize(
        "days,expected",
        [
            (None, TIMING_STATE_NORMAL),
            (-1, TIMING_STATE_NORMAL),
            (0, TIMING_STATE_LATE_TAPER),
            (7, TIMING_STATE_LATE_TAPER),
            (13, TIMING_STATE_LATE_TAPER),
            (14, TIMING_STATE_BRIDGE),
            (17, TIMING_STATE_BRIDGE),
            (21, TIMING_STATE_BRIDGE),
            (22, TIMING_STATE_NORMAL),
            (45, TIMING_STATE_NORMAL),
        ],
    )
    def test_timing_state(self, days, expected):
        assert timing_state(days) == expected

    @pytest.mark.parametrize(
        "days,expected",
        [
            (14, "d15_to_d14"),
            (15, "d15_to_d14"),
            (16, "d18_to_d16"),
            (18, "d18_to_d16"),
            (19, "d21_to_d19"),
            (21, "d21_to_d19"),
            (13, None),
            (22, None),
        ],
    )
    def test_bridge_sub_band(self, days, expected):
        assert bridge_sub_band(days) == expected


class TestSpecUnitCases:
    """Direct translation of the spec's unit-test table."""

    def test_bridge_clean_boxer(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["timing_state"] == TIMING_STATE_BRIDGE
        assert result["max_active_roles"] == 3
        assert result["max_meaningful_stress_exposures"] == 3
        assert result["hard_sparring_cap"] == 1
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True
        assert result["glycolytic_touch_max"] == 1
        assert result["remaining_hard_spar_slots"] == 1

    def test_bridge_boxer_with_moderate_cut_at_d17(self):
        # D-17 inside the bridge window always zeros hard sparring regardless
        # of other inputs (the D-window rule, not the cut). A moderate cut is
        # note-only: it does NOT trim meaningful stress, so the baseline bridge
        # exposure of 3 is preserved. Low-fatigue + none/low/moderate cut keeps
        # the extra low-risk active role across the whole bridge, so the
        # active-role guidance is 3 while glycolytic / hard-spar stay 0 by the
        # D-window baseline.
        result = compute_bridge_rules(
            days_until_fight=17,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["max_active_roles"] == 3
        assert result["max_meaningful_stress_exposures"] == 3
        assert result["glycolytic_touch_max"] == 0
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True
        assert result["hard_sparring_cap"] == 0
        assert result["block_full_plan"] is False
        assert "weight_cut_moderate_note_only" in result["reason_codes"]
        assert "weight_cut_moderate_trim_stress" not in result["reason_codes"]

    def test_bridge_d20_boxer_with_moderate_cut(self):
        # D-20 is inside the D-21..D-18 sub-slice where the clean default is
        # cap=1 with one optional glycolytic touch. A moderate cut is note-only
        # and must NOT zero hard sparring or glycolytic density — the baseline
        # allowances stand, with only a calm hydration/fuelling note added.
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["hard_sparring_cap"] == 1
        assert result["glycolytic_touch_max"] == 1
        assert result["block_full_plan"] is False
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True
        assert "weight_cut_moderate_note_only" in result["reason_codes"]
        assert (
            "weight_cut_moderate_bridge_contact_sport_zero_hard_spar"
            not in result["reason_codes"]
        )

    def test_bridge_d16_high_cut_forces_one_active_role(self):
        result = compute_bridge_rules(
            days_until_fight=16,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="high",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["max_active_roles"] == 1

    def test_bridge_d20_high_fatigue_forces_one_active_role(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="high",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["max_active_roles"] == 1

    def test_bridge_mma_with_moderate_fatigue(self):
        # Moderate fatigue alone in D-21..D-18 does NOT zero hard sparring —
        # it trims stress exposure and forbids stacked hard days only.
        result = compute_bridge_rules(
            days_until_fight=19,
            sport="mma",
            fatigue="moderate",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["max_active_roles"] == 2
        assert result["max_meaningful_stress_exposures"] == 2
        assert result["hard_sparring_cap"] == 1
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True
        assert result["double_stress_day_allowed"] is False

    def test_bridge_d15_kickboxer_already_used_hard_slot(self):
        result = compute_bridge_rules(
            days_until_fight=15,
            sport="kickboxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=1,
        )
        assert result["remaining_hard_spar_slots"] == 0
        assert result["glycolytic_touch_max"] == 0
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True
        # D-17 onward forbids further hard sparring.
        assert result.get("no_hard_sparring_after_d16") is True

    def test_late_taper_boxer(self):
        result = compute_bridge_rules(
            days_until_fight=12,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["timing_state"] == TIMING_STATE_LATE_TAPER
        assert result["max_active_roles"] == 2
        assert result["max_meaningful_stress_exposures"] == 2
        assert result["hard_sparring_cap"] == 0
        assert result["strength_touch_max"] == 1
        assert result["glycolytic_touch_max"] == 0
        assert result["freshness_mandatory"] is True

    def test_farther_out_but_high_fatigue_downgrades(self):
        result = compute_bridge_rules(
            days_until_fight=24,
            sport="mma",
            fatigue="high",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        # D-24 would normally be normal camp; high fatigue forces a bridge-
        # style downgrade per the spec.
        assert result["timing_state"] == TIMING_STATE_NORMAL
        assert result["max_active_roles"] == 2
        assert result["max_meaningful_stress_exposures"] == 3
        assert result["hard_sparring_cap"] == 0
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True
        assert result["glycolytic_touch_max"] == 0
        assert result["phase_downgraded_by_fatigue"] is True

    def test_restricted_rehab_blocks_full_plan(self):
        result = compute_bridge_rules(
            days_until_fight=19,
            sport="grappler",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="restricted_rehab_only",
            hard_sparring_days_declared=0,
        )
        assert result["plan_mode"] == "restricted_rehab_only"
        assert result["block_full_plan"] is True
        assert result["hard_sparring_cap"] == 0
        assert result["max_active_roles"] == 0

    def test_critical_fatigue_escalates(self):
        result = compute_bridge_rules(
            days_until_fight=18,
            sport="boxing",
            fatigue="critical",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["plan_mode"] == "needs_review"
        assert result["block_full_plan"] is True
        assert result["max_active_roles"] == 0
        assert result["hard_sparring_cap"] == 0

    def test_unsafe_cut_blocks_plan(self):
        result = compute_bridge_rules(
            days_until_fight=14,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="high",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
            athlete_pct_above_class=6.0,
            hours_to_recovery_after_weigh_in=2.0,
        )
        assert result["unsafe_weight_flag"] is True
        assert result["block_full_plan"] is True
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0

    def test_pressure_style_keeps_bridge_cap(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="kickboxing",
            style=["pressure"],
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        assert result["max_meaningful_stress_exposures"] == 3
        assert result["allow_pace_specific_interval_swap"] is True
        assert result["pressure_style_stress_cap_unchanged"] is True


class TestBridgeHelperConsistency:
    def test_declared_hard_spar_cap_bridge_boundaries(self):
        assert _declared_hard_spar_cap(21) == 1
        assert _declared_hard_spar_cap(18) == 1
        assert _declared_hard_spar_cap(17) == 0
        assert _declared_hard_spar_cap(14) == 0

    def test_hard_spar_status_bridge_boundaries(self):
        assert _hard_spar_status_for_countdown_offset(21) == "hard_allowed"
        assert _hard_spar_status_for_countdown_offset(18) == "hard_allowed"
        assert _hard_spar_status_for_countdown_offset(17) != "hard_allowed"
        assert _hard_spar_status_for_countdown_offset(14) != "hard_allowed"


class TestModifierOrdering:
    def test_medical_hold_short_circuits(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="medical_hold",
        )
        assert result["plan_mode"] == "medical_hold"
        assert result["block_full_plan"] is True
        assert result["max_active_roles"] == 0
        assert result["hard_sparring_cap"] == 0
        assert result["freshness_mandatory"] is True

    def test_needs_review_blocks_full_plan(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            injury_mode="needs_review",
        )
        assert result["plan_mode"] == "needs_review"
        assert result["block_full_plan"] is True

    def test_high_fatigue_zeros_hard_spar_even_if_declared(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="high",
            hard_sparring_days_declared=1,
        )
        assert result["hard_sparring_cap"] == 0
        assert result["remaining_hard_spar_slots"] == 0

    def test_moderate_fatigue_does_not_zero_strength(self):
        result = compute_bridge_rules(
            days_until_fight=17,
            sport="boxing",
            fatigue="moderate",
        )
        assert result["strength_touch_max"] == 1
        assert result["freshness_mandatory"] is True

    def test_weight_cut_high_blocks_glycolytic_and_hard_spar(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            weight_cut_bucket="high",
        )
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0
        assert result["strength_touch_max"] == 1

    def test_moderate_cut_and_moderate_fatigue_stack(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="mma",
            fatigue="moderate",
            weight_cut_bucket="moderate",
        )
        # Only moderate fatigue trims one stress exposure (3 -> 2). A moderate
        # cut is note-only and no longer stacks a second reduction.
        assert result["max_meaningful_stress_exposures"] == 2
        assert result["double_stress_day_allowed"] is False

    def test_sport_style_never_raises_caps_beyond_baseline(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            style=["pressure", "counter"],
            fatigue="high",
        )
        # High fatigue drops meaningful stress to 2; style must not raise it.
        assert result["max_meaningful_stress_exposures"] == 2
        assert result["hard_sparring_cap"] == 0

    def test_grappler_style_blocks_striking_hard_contact(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="mma",
            style=["grappler"],
        )
        assert result["grappler_hard_live_shares_spar_slot"] is True
        assert result["striking_hard_contact_blocked_in_bridge"] is True


class TestHardSparringSlotAccounting:
    def test_declared_less_than_cap(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            hard_sparring_days_declared=0,
        )
        assert result["remaining_hard_spar_slots"] == 1

    def test_declared_equal_to_cap(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            hard_sparring_days_declared=1,
        )
        assert result["remaining_hard_spar_slots"] == 0

    def test_declared_greater_than_cap(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            hard_sparring_days_declared=3,
        )
        assert result["remaining_hard_spar_slots"] == 0


class TestPermissiveFallback:
    def test_permissive_gated_off_for_striking_sport(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
            permissive_mode=True,
        )
        assert result["permissive_mode_eligible"] is True
        # Head-impact evidence prevents striking sports from using permissive mode.
        assert "permissive_mode_blocked_for_contact_sport" in result["reason_codes"]
        assert result["strength_touch_max"] == 1

    def test_permissive_opens_extra_strength_touch_for_grappler_in_d21_d19(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="grappler",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
            permissive_mode=True,
        )
        assert result["permissive_mode_eligible"] is True
        assert result["strength_touch_max"] == 2

    def test_permissive_off_when_any_risk_flag_set(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="grappler",
            fatigue="moderate",
            permissive_mode=True,
        )
        assert result["permissive_mode_eligible"] is False
        assert result["strength_touch_max"] == 1


class TestBaselineNormalCamp:
    def test_normal_camp_defaults(self):
        result = compute_bridge_rules(
            days_until_fight=45,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        assert result["timing_state"] == TIMING_STATE_NORMAL
        assert result["max_active_roles"] == 3
        assert result["max_meaningful_stress_exposures"] == 4
        assert result["hard_sparring_cap"] == 2
        assert result["strength_touch_max"] == 2
        assert result["glycolytic_touch_max"] == 2
        assert result["max_consecutive_hard_days"] == 2
        assert result["double_stress_day_allowed"] is True
        assert result["freshness_mandatory"] is False

    def test_bridge_window_metadata_carries_sub_band(self):
        result = compute_bridge_rules(
            days_until_fight=16,
            sport="mma",
        )
        assert result["bridge_sub_band"] == "d18_to_d16"


class TestUnsafeWeightHeuristic:
    def test_over_five_percent_triggers_unsafe(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            athlete_pct_above_class=5.5,
        )
        assert result["unsafe_weight_flag"] is True
        assert result["block_full_plan"] is True

    def test_over_three_percent_with_short_recovery_triggers_unsafe(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            athlete_pct_above_class=3.5,
            hours_to_recovery_after_weigh_in=3.0,
        )
        assert result["unsafe_weight_flag"] is True

    def test_three_percent_with_long_recovery_is_safe(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            athlete_pct_above_class=3.5,
            hours_to_recovery_after_weigh_in=24.0,
            weight_cut_bucket="moderate",
        )
        assert result["unsafe_weight_flag"] is False
        assert result["block_full_plan"] is False


class TestBridgeCapTransitions:
    """D-21..D-18 keeps cap=1 for clean athletes; D-17..D-14 always zero."""

    def test_d20_clean_boxer_keeps_cap_one(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["hard_sparring_cap"] == 1
        assert result["remaining_hard_spar_slots"] == 1
        assert result["max_active_roles"] == 3
        assert result["max_meaningful_stress_exposures"] == 3
        assert result["block_full_plan"] is False

    def test_d18_clean_boxer_keeps_cap_one(self):
        result = compute_bridge_rules(
            days_until_fight=18,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["hard_sparring_cap"] == 1
        assert result["remaining_hard_spar_slots"] == 1

    def test_d17_clean_boxer_zero_hard_spar(self):
        result = compute_bridge_rules(
            days_until_fight=17,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            hard_sparring_days_declared=0,
        )
        assert result["hard_sparring_cap"] == 0
        assert result["remaining_hard_spar_slots"] == 0

    def test_d16_clean_boxer_zero_hard_spar(self):
        result = compute_bridge_rules(
            days_until_fight=16,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        assert result["hard_sparring_cap"] == 0

    def test_d15_and_d14_zero_hard_spar(self):
        for day in (15, 14):
            result = compute_bridge_rules(
                days_until_fight=day,
                sport="boxing",
                fatigue="low",
                weight_cut_bucket="low",
                injury_mode="full_plan",
            )
            assert result["hard_sparring_cap"] == 0
            assert result["glycolytic_touch_max"] == 0
            assert result["freshness_mandatory"] is True
            assert result.get("no_hard_sparring_after_d16") is True


class TestBridgeModerateCutContactSports:
    """A moderate cut is note-only: it must NOT zero hard spar or optional
    density for contact sports. Only high+ cuts restrict hard work."""

    def test_moderate_cut_boxing_keeps_hard_sparring(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            weight_cut_bucket="moderate",
            fatigue="low",
            injury_mode="full_plan",
        )
        assert result["hard_sparring_cap"] == 1
        assert result["glycolytic_touch_max"] == 1
        assert result["block_full_plan"] is False
        assert "weight_cut_moderate_note_only" in result["reason_codes"]
        assert (
            "weight_cut_moderate_bridge_contact_sport_zero_hard_spar"
            not in result["reason_codes"]
        )
        assert "weight_cut_moderate_trim_stress" not in result["reason_codes"]

    def test_moderate_cut_mma_keeps_hard_sparring(self):
        result = compute_bridge_rules(
            days_until_fight=19,
            sport="mma",
            weight_cut_bucket="moderate",
            fatigue="low",
            injury_mode="full_plan",
        )
        assert result["hard_sparring_cap"] == 1
        assert result["glycolytic_touch_max"] == 1
        assert result["block_full_plan"] is False
        assert "weight_cut_moderate_note_only" in result["reason_codes"]

    def test_moderate_cut_grappler_keeps_hard_sparring(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="wrestling",
            weight_cut_bucket="moderate",
            fatigue="low",
            injury_mode="full_plan",
        )
        assert result["hard_sparring_cap"] == 1
        assert result["block_full_plan"] is False
        assert "weight_cut_moderate_note_only" in result["reason_codes"]

    def test_moderate_cut_grappler_style_keeps_hard_sparring(self):
        # Grappler style still reallocates striking hard contact, but the
        # moderate cut itself no longer zeros the hard sparring cap.
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="mma",
            style=["grappler"],
            weight_cut_bucket="moderate",
            fatigue="low",
            injury_mode="full_plan",
        )
        assert result["hard_sparring_cap"] == 1
        assert "weight_cut_moderate_note_only" in result["reason_codes"]


class TestBridgeGlycolyticRules:
    """D-21..D-19 may allow one short glycolytic touch; a moderate cut is
    note-only and keeps it, only high+ cuts suppress it."""

    def test_d20_clean_allows_one_glycolytic_touch(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        assert result["glycolytic_touch_max"] == 1

    def test_d18_suppresses_glycolytic(self):
        result = compute_bridge_rules(
            days_until_fight=18,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        assert result["glycolytic_touch_max"] == 0

    def test_moderate_cut_keeps_glycolytic_in_d21_to_d19(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
        )
        # Note-only moderate cut keeps the baseline glycolytic touch.
        assert result["glycolytic_touch_max"] == 1
        assert "weight_cut_moderate_note_only" in result["reason_codes"]


class TestBridgeStyleCannotRaiseCaps:
    """Sport/style may reallocate emphasis but never raise total caps."""

    def test_pressure_fighter_cannot_raise_stress_cap(self):
        baseline = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        pressure = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            style=["pressure"],
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        # Caps identical — style only reallocates content inside them.
        assert pressure["max_meaningful_stress_exposures"] <= baseline["max_meaningful_stress_exposures"]
        assert pressure["hard_sparring_cap"] <= baseline["hard_sparring_cap"]
        assert pressure["strength_touch_max"] <= baseline["strength_touch_max"]
        assert pressure["max_active_roles"] <= baseline["max_active_roles"]

    def test_counter_style_cannot_raise_caps(self):
        baseline = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        counter = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            style=["counter"],
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
        )
        assert counter["max_meaningful_stress_exposures"] <= baseline["max_meaningful_stress_exposures"]
        assert counter["hard_sparring_cap"] <= baseline["hard_sparring_cap"]


class TestBridgeHighCut:
    def test_high_cut_zeros_density_and_keeps_freshness(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            weight_cut_bucket="high",
            fatigue="low",
            injury_mode="full_plan",
        )
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0
        assert result["freshness_mandatory"] is True
        # High cut does not auto-block the full plan unless unsafe_weight_flag
        # also fires (existing escalation preserved).


class TestDeclaredHardSparCapHelper:
    """Keeps `_declared_hard_spar_cap` in agreement with the main bridge rules."""

    def test_cap_transitions_through_bridge_window(self):
        from fightcamp.stage2_payload_late_fight import _declared_hard_spar_cap

        assert _declared_hard_spar_cap(21) == 1
        assert _declared_hard_spar_cap(18) == 1
        assert _declared_hard_spar_cap(17) == 0
        assert _declared_hard_spar_cap(14) == 0


class TestHardSparStatusForCountdownOffset:
    """D-17 and below must not be described as hard-allowed anywhere."""

    def test_bridge_offset_statuses(self):
        from fightcamp.stage2_payload_late_fight import (
            _hard_spar_status_for_countdown_offset,
        )

        assert _hard_spar_status_for_countdown_offset(21) == "hard_allowed"
        assert _hard_spar_status_for_countdown_offset(18) == "hard_allowed"
        assert _hard_spar_status_for_countdown_offset(17) == "downgrade"
        assert _hard_spar_status_for_countdown_offset(14) == "downgrade"
