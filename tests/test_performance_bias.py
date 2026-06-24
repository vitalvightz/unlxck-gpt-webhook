"""Tests for the opt-in performance-bias layer.

Two guarantees are proven here:

1. Default behaviour is completely unchanged (the bias is off unless opted in
   *and* the low-risk eligibility gate passes).
2. When active, the bias only preserves one extra low-risk performance exposure
   in the D-21..D-18 bridge window — it never restores hard sparring or hard
   glycolytic work, and never fires for any unsafe profile.
"""

from __future__ import annotations

import pytest

from fightcamp.performance_bias import (
    performance_bias_active,
    performance_bias_eligibility,
    performance_bias_requested,
)
from fightcamp.stage2_payload_late_fight import compute_bridge_rules


def _low_risk_model(**overrides):
    base = {
        "performance_bias": True,
        "fatigue": "low",
        "weight_cut_pct": 3.5,
        "cut_severity_bucket": "moderate",
        "days_until_fight": 21,
        "sport": "boxing",
        "injuries": ["left quad low, stable pain"],
        "injury_mode": "full_plan",
        "readiness_flags": ["injury_management"],
    }
    base.update(overrides)
    return base


class TestOptIn:
    def test_requested_defaults_off(self):
        assert performance_bias_requested({}) is False

    def test_requested_when_flag_set(self):
        assert performance_bias_requested({"performance_bias": True}) is True

    def test_active_requires_opt_in(self):
        model = _low_risk_model(performance_bias=False)
        assert performance_bias_active(model) is False

    def test_active_when_opted_in_and_eligible(self):
        assert performance_bias_active(_low_risk_model()) is True


class TestEligibilityGate:
    def test_low_risk_profile_is_eligible(self):
        eligible, reasons = performance_bias_eligibility(_low_risk_model())
        assert eligible is True
        assert reasons == []

    @pytest.mark.parametrize(
        "overrides,expected_reason",
        [
            ({"fatigue": "high"}, "fatigue_not_low"),
            ({"fatigue": "moderate"}, "fatigue_not_low"),
            ({"cut_severity_bucket": "high"}, "cut_bucket_above_moderate"),
            ({"cut_severity_bucket": "critical"}, "cut_bucket_above_moderate"),
            ({"injury_mode": "medical_hold"}, "injury_mode_restricted"),
            ({"injury_mode": "restricted_rehab_only"}, "injury_mode_restricted"),
            ({"injury_mode": "needs_review"}, "injury_mode_restricted"),
            ({"readiness_flags": ["red_flag_injury"]}, "red_flag_injury"),
            ({"injuries": ["moderate hamstring strain"]}, "injury_severity_moderate_plus"),
            ({"injuries": ["mild quad pain, worsening"]}, "injury_worsening"),
            ({"injuries": ["knee giving way, instability"]}, "injury_instability"),
            ({"injuries": ["shoulder pain, daily symptoms at rest"]}, "injury_daily_symptoms"),
            ({"days_until_fight": 7}, "inside_fight_week"),
            ({"days_until_fight": 3}, "inside_fight_week"),
        ],
    )
    def test_disqualifiers(self, overrides, expected_reason):
        eligible, reasons = performance_bias_eligibility(_low_risk_model(**overrides))
        assert eligible is False
        assert expected_reason in reasons

    def test_no_injury_is_eligible(self):
        model = _low_risk_model(injuries=[], readiness_flags=[])
        eligible, reasons = performance_bias_eligibility(model)
        assert eligible is True
        assert reasons == []


class TestDefaultBridgeBehaviourUnchanged:
    """The bias is a pure no-op unless explicitly passed performance_bias=True."""

    @pytest.mark.parametrize("days", [21, 20, 19, 18, 17, 16, 15, 14])
    def test_default_moderate_cut_boxing_unchanged(self, days):
        result = compute_bridge_rules(
            days_until_fight=days,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
        )
        assert result.get("performance_bias_active") is False
        assert "performance_bias_extra_low_risk_exposure" not in result["reason_codes"]

    def test_default_d20_moderate_cut_keeps_two_active_roles(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
        )
        # Locks the conservative default that the bias opts out of.
        assert result["max_active_roles"] == 2
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0


class TestPerformanceBiasActive:
    def test_d20_moderate_cut_preserves_one_extra_low_risk_exposure(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            performance_bias=True,
        )
        assert result["performance_bias_active"] is True
        assert result["max_active_roles"] == 3
        assert result["max_meaningful_stress_exposures"] == 3
        assert "performance_bias_extra_low_risk_exposure" in result["reason_codes"]
        # Hard sparring + glycolytic stay exactly where safety left them.
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0
        assert result["freshness_mandatory"] is True

    def test_d18_moderate_cut_preserves_one_extra_low_risk_exposure(self):
        result = compute_bridge_rules(
            days_until_fight=18,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            performance_bias=True,
        )
        assert result["performance_bias_active"] is True
        assert result["max_active_roles"] == 3
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0

    def test_clean_athlete_already_at_ceiling_is_noop(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            performance_bias=True,
        )
        # Nothing was throttled, so there is nothing to give back.
        assert result["performance_bias_active"] is False
        assert result["max_active_roles"] == 3
        assert result["glycolytic_touch_max"] == 1


class TestPerformanceBiasNeverOverridesSafety:
    def test_d17_outside_window_is_noop(self):
        result = compute_bridge_rules(
            days_until_fight=17,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            performance_bias=True,
        )
        assert result["performance_bias_active"] is False
        assert result["max_active_roles"] == 2
        assert result["hard_sparring_cap"] == 0

    def test_high_cut_internal_guard_blocks_bias(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="high",
            injury_mode="full_plan",
            performance_bias=True,
        )
        assert result["performance_bias_active"] is False
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0

    def test_high_fatigue_internal_guard_blocks_bias(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="high",
            weight_cut_bucket="low",
            injury_mode="full_plan",
            performance_bias=True,
        )
        assert result["performance_bias_active"] is False
        assert result["max_active_roles"] == 1

    def test_restricted_rehab_internal_guard_blocks_bias(self):
        result = compute_bridge_rules(
            days_until_fight=19,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="low",
            injury_mode="restricted_rehab_only",
            performance_bias=True,
        )
        assert result["performance_bias_active"] is False
        assert result["block_full_plan"] is True
        assert result["max_active_roles"] == 0

    def test_unsafe_weight_internal_guard_blocks_bias(self):
        result = compute_bridge_rules(
            days_until_fight=20,
            sport="boxing",
            fatigue="low",
            weight_cut_bucket="moderate",
            injury_mode="full_plan",
            athlete_pct_above_class=6.0,
            performance_bias=True,
        )
        assert result["performance_bias_active"] is False
        assert result["block_full_plan"] is True
        assert result["hard_sparring_cap"] == 0
