"""Tactical Watch is zero-load, and a build week may spend a filler on aerobic work.

Two corrections are covered here:

1. `apply_camp_week_fillers` charged the zero-load Tactical Watch against the
   week's physical filler budget (`_FIGHT_PHASE_CAPS[phase] - 1`), which left
   GPP (cap 1) with no discretionary budget at all. The contract's ownership
   matrix already forbids the watch consuming physical training budget, and the
   legacy non-fight-dated path only ever charged the coordination insert.
2. The filler's conditioning preference was gated on `remaining_need`, which
   reports whether a goal is represented at all. One conditioning day marked
   conditioning satisfied, so a high-priority conditioning athlete could never
   receive a second, low-cost aerobic touch. Frequency is now the caller's
   decision, capped at one aerobic filler per build week.
"""
import pytest

from fightcamp.camp_week_fillers_impl import _FIGHT_PHASE_CAPS
from fightcamp.stage2_role_map import (
    _count_low_aerobic_support_roles,
    _low_aerobic_support_cap_for_week,
)
from fightcamp.gap_fill_inserts import (
    LOW_COST_AEROBIC_INSERTS,
    ZERO_COST_INSERTS,
    _select_role_key,
)


def test_tactical_watch_is_a_zero_cost_insert():
    assert "tactical_watch" in ZERO_COST_INSERTS
    assert "tactical_watch" not in LOW_COST_AEROBIC_INSERTS


def test_gpp_retains_discretionary_filler_budget():
    """GPP's budget of one must survive the Tactical Watch, or nothing can fill."""
    assert _FIGHT_PHASE_CAPS["GPP"] >= 1
    assert _FIGHT_PHASE_CAPS["SPP"] >= 1


def _allocator_aerobic_role():
    return {
        "role_key": "aerobic_base_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
    }


def test_support_count_covers_allocator_roles_and_filler_inserts():
    """One total count, so the filler cannot add on top of a spent allowance."""
    assert _count_low_aerobic_support_roles([_allocator_aerobic_role()]) == 1
    assert _count_low_aerobic_support_roles([{"role_key": "aerobic_shadow_flow"}]) == 1
    assert (
        _count_low_aerobic_support_roles(
            [_allocator_aerobic_role(), {"role_key": "aerobic_shadow_flow"}]
        )
        == 2
    )
    assert _count_low_aerobic_support_roles([{"role_key": "breathing_reset"}]) == 0


@pytest.mark.parametrize(
    "overrides,expected_room",
    [
        ({}, True),                                   # fresh: cap 2, one used
        ({"cut_severity_bucket": "high"}, False),     # cap 1, already spent
        ({"fatigue": "high"}, False),                 # cap 1, already spent
    ],
)
def test_filler_shares_the_allocator_low_aerobic_allowance(overrides, expected_room):
    week = {"phase": "GPP", "calendar_days": [{"weekday": "tuesday", "d_day": 40}]}
    athlete = {"key_goals": ["conditioning"], "weaknesses": ["gas_tank"], **overrides}
    roles = [_allocator_aerobic_role()]

    cap = _low_aerobic_support_cap_for_week(week, athlete, roles)
    assert (_count_low_aerobic_support_roles(roles) < cap) is expected_room


def test_allowance_is_exhausted_once_the_filler_touch_is_placed():
    week = {"phase": "GPP", "calendar_days": [{"weekday": "tuesday", "d_day": 40}]}
    athlete = {"key_goals": ["conditioning"], "weaknesses": ["gas_tank"]}
    roles = [_allocator_aerobic_role(), {"role_key": "aerobic_shadow_flow"}]

    cap = _low_aerobic_support_cap_for_week(week, athlete, roles)
    assert _count_low_aerobic_support_roles(roles) >= cap


def test_forced_conditioning_prefers_an_aerobic_insert_over_recovery_filler():
    allowed = {"breathing_reset", "recovery_reset", "aerobic_shadow_flow"}
    chosen = _select_role_key(
        {}, 20, allowed, usage_ledger=None, force_conditioning=True, coverage_state=[]
    )
    assert chosen == "aerobic_shadow_flow"


def test_forced_conditioning_falls_back_when_no_aerobic_insert_is_legal():
    """A slot with no safe aerobic option still gets its normal filler."""
    allowed = {"breathing_reset", "recovery_reset"}
    chosen = _select_role_key(
        {}, 20, allowed, usage_ledger=None, force_conditioning=True, coverage_state=[]
    )
    assert chosen in allowed


def test_without_forcing_the_selection_is_unchanged():
    allowed = {"breathing_reset", "recovery_reset"}
    chosen = _select_role_key(
        {}, 20, allowed, usage_ledger=None, force_conditioning=False, coverage_state=[]
    )
    assert chosen in allowed


def test_effective_dose_counts_rest_between_rounds_only():
    """Elapsed time follows the prescription's rest convention: no trailing rest."""
    from fightcamp.config import conditioning_effective_dose

    dose = {"work_sec": 300, "rounds": 5, "rest_sec": 30, "round_based": True}
    effective = conditioning_effective_dose(dose, 300.0)
    # 5 x 300s work + 4 x 30s rest = 1620s = 27 min, not 27.5.
    assert effective["total_minutes"] == 27.0

    single = conditioning_effective_dose(
        {"work_sec": 180, "rounds": 1, "rest_sec": 60, "round_based": True}, 180.0
    )
    assert single["total_minutes"] == 3.0


def test_effective_dose_leaves_other_doses_untouched():
    from fightcamp.config import conditioning_effective_dose

    dose = {"work_sec": 480, "rounds": 2, "rest_sec": 180}
    assert conditioning_effective_dose(dose, 120.0) is dose
    assert conditioning_effective_dose(dict(dose, round_based=True), None) == dict(
        dose, round_based=True
    )
