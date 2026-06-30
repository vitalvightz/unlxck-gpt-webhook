"""Tests for the unified D-21..D-18 low-risk active-role cap.

Background: the bridge baseline allowed 3 active roles, but the flat late-fight
role budget capped D-14..D-21 at 2 app-owned roles — a silent conflict that
shrank plans for clean / mildly-managed athletes. These tests pin the unified
behaviour:

* one source of truth (`_bridge_active_role_cap`) drives the *binding*
  allocation, and `compute_bridge_rules` guidance agrees with it;
* a low-risk athlete (low fatigue, at most mild injury, none/low/moderate cut)
  keeps one extra low-risk active role in D-21..D-18, by default;
* any safety signal (high fatigue, moderate+ injury, aggressive cut, restricted
  injury mode, D-7 or closer) drops back to the conservative 2;
* hard sparring and glycolytic caps are never raised by this rule.
"""

from __future__ import annotations

import pytest

from fightcamp.performance_bias import (
    bridge_low_risk_profile,
    low_risk_profile_blockers,
)
from fightcamp.stage2_payload_late_fight import (
    _bridge_active_role_cap,
    _late_fight_active_role_count,
    _late_fight_allocation_plan,
    compute_bridge_rules,
)


def _low_risk_model(**overrides):
    base = {
        "sport": "boxing",
        "fatigue": "low",
        "weight_cut_pct": 3.5,
        "cut_severity_bucket": "moderate",
        "days_until_fight": 20,
        "injuries": ["left quad low, stable pain"],
        "injury_mode": "full_plan",
        "readiness_flags": ["injury_management"],
    }
    base.update(overrides)
    return base


def _boxer(fatigue, *, cut_pct=0.0, injuries=None, days=20, hard_sparring_days=None):
    return {
        "sport": "boxing",
        "status": "professional",
        "rounds_format": "3x3",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": hard_sparring_days or [],
        "fatigue": fatigue,
        "weight_cut_pct": cut_pct,
        "weight_cut_risk": cut_pct > 0,
        "readiness_flags": [],
        "key_goals": ["power", "strength"],
        "weaknesses": ["gas_tank"],
        "injuries": injuries or [],
        "fight_date": "2026-07-14",
        "days_until_fight": days,
        "plan_creation_weekday": "tuesday",
    }


class TestLowRiskProfileGate:
    def test_low_risk_profile_qualifies(self):
        assert bridge_low_risk_profile(_low_risk_model()) is True
        assert low_risk_profile_blockers(_low_risk_model()) == []

    def test_no_injury_qualifies(self):
        model = _low_risk_model(injuries=[], readiness_flags=[])
        assert bridge_low_risk_profile(model) is True

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
        blockers = low_risk_profile_blockers(_low_risk_model(**overrides))
        assert expected_reason in blockers
        assert bridge_low_risk_profile(_low_risk_model(**overrides)) is False


class TestBindingActiveRoleCap:
    """`_bridge_active_role_cap` is the single source of truth for allocation."""

    @pytest.mark.parametrize("days", [21, 20, 19, 18])
    def test_low_risk_gets_three_in_window(self, days):
        assert _bridge_active_role_cap(days, _low_risk_model(days_until_fight=days)) == 3

    @pytest.mark.parametrize(
        "overrides",
        [
            {"fatigue": "moderate"},
            {"fatigue": "high"},
            {"injuries": ["moderate hamstring strain"]},
            {"cut_severity_bucket": "high"},
        ],
    )
    def test_safety_signal_stays_at_two(self, overrides):
        assert _bridge_active_role_cap(20, _low_risk_model(**overrides)) == 2

    @pytest.mark.parametrize("days", [17, 16, 15, 14])
    def test_d17_to_d14_low_risk_keeps_three_for_conditioning_touch(self, days):
        # The mandatory freshness day counts against the active-role budget, so a
        # flat cap of 2 in D-17..D-14 is fully consumed by the strength touch +
        # freshness day, leaving no room for a real conditioning exposure. A
        # low-risk athlete keeps the extra role here so one alactic conditioning
        # touch fits. Declared hard sparring is no longer required to earn it.
        model = _low_risk_model(days_until_fight=days, hard_sparring_days=[])
        assert _bridge_active_role_cap(days, model) == 3

    @pytest.mark.parametrize("days", [17, 16, 15, 14])
    def test_d17_to_d14_with_declared_sparring_keeps_three(self, days):
        # Hard sparring converts to technical from D-17; the low-risk athlete keeps
        # the extra app role regardless of whether sparring was declared.
        model = _low_risk_model(days_until_fight=days, hard_sparring_days=["monday", "thursday"])
        assert _bridge_active_role_cap(days, model) == 3

    @pytest.mark.parametrize("days", [17, 15, 14])
    def test_d17_to_d14_safety_signal_blocks_reallocation(self, days):
        model = _low_risk_model(
            days_until_fight=days, hard_sparring_days=["monday"], fatigue="moderate"
        )
        assert _bridge_active_role_cap(days, model) == 2

    def test_late_taper_budget_unchanged(self):
        # D-8..D-13 keeps its own (higher) flat budget; the rule only touches 18..21.
        model = _low_risk_model(days_until_fight=12)
        assert _bridge_active_role_cap(12, model) == 4


class TestComputeBridgeRulesGuidanceAgrees:
    def test_moderate_cut_low_fatigue_gets_three(self):
        result = compute_bridge_rules(
            days_until_fight=20, sport="boxing", fatigue="low",
            weight_cut_bucket="moderate", injury_mode="full_plan",
        )
        assert result["max_active_roles"] == 3
        # Safety caps untouched — this is the load-shape lever only.
        assert result["hard_sparring_cap"] == 0
        assert result["glycolytic_touch_max"] == 0
        # Moderate cut still trims one meaningful stress exposure.
        assert result["max_meaningful_stress_exposures"] == 2

    def test_clean_low_fatigue_gets_three(self):
        result = compute_bridge_rules(
            days_until_fight=20, sport="boxing", fatigue="low",
            weight_cut_bucket="low", injury_mode="full_plan",
        )
        assert result["max_active_roles"] == 3

    def test_high_cut_forces_one(self):
        result = compute_bridge_rules(
            days_until_fight=20, sport="boxing", fatigue="low",
            weight_cut_bucket="high", injury_mode="full_plan",
        )
        assert result["max_active_roles"] == 1

    def test_moderate_fatigue_stays_two(self):
        result = compute_bridge_rules(
            days_until_fight=19, sport="mma", fatigue="moderate",
            weight_cut_bucket="low", injury_mode="full_plan",
        )
        assert result["max_active_roles"] == 2

    def test_d17_outside_window_stays_two(self):
        result = compute_bridge_rules(
            days_until_fight=17, sport="boxing", fatigue="low",
            weight_cut_bucket="moderate", injury_mode="full_plan",
        )
        assert result["max_active_roles"] == 2


class TestEndToEndAllocation:
    """The cap reaches the real plan: low-risk athletes get the 3rd session."""

    @pytest.mark.parametrize(
        "athlete,expected",
        [
            (_boxer("low"), 3),
            (_boxer("low", cut_pct=3.5), 3),
            (_boxer("low", cut_pct=3.5, injuries=["left quad low, stable pain"]), 3),
            (_boxer("moderate"), 2),
            (_boxer("low", injuries=["moderate hamstring strain"]), 2),
        ],
    )
    def test_app_owned_active_role_count(self, athlete, expected):
        roles = _late_fight_allocation_plan(20, athlete).get("session_roles", [])
        assert _late_fight_active_role_count(roles) == expected

    @pytest.mark.parametrize("days", [16, 15])
    def test_d17_to_d14_declared_sparring_gets_three_app_sessions(self, days):
        # Once hard sparring converts to technical (D-17 on), the freed slot is
        # reallocated to a 3rd low-risk app session for a low-risk athlete.
        athlete = _boxer("low", days=days, hard_sparring_days=["tuesday", "thursday"])
        roles = _late_fight_allocation_plan(days, athlete).get("session_roles", [])
        assert _late_fight_active_role_count(roles) == 3

    @pytest.mark.parametrize("days", [16, 15])
    def test_d17_to_d14_no_declared_sparring_gets_conditioning_touch(self, days):
        # Low-risk athlete with no declared sparring now gets a third app session
        # in D-17..D-14: one alactic conditioning touch alongside the strength
        # touch and freshness day, without raising any safety cap.
        athlete = _boxer("low", days=days, hard_sparring_days=[])
        roles = _late_fight_allocation_plan(days, athlete).get("session_roles", [])
        assert _late_fight_active_role_count(roles) == 3
        assert any(role.get("role_key") == "alactic_sharpness_day" for role in roles)
