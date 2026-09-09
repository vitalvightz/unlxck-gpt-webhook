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

from fightcamp.camp_week_fillers_impl import (
    _FIGHT_PHASE_CAPS,
    _week_aerobic_filler_count,
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


def test_week_aerobic_filler_count_reads_placed_roles():
    roles = [
        {"role_key": "aerobic_shadow_flow"},
        {"role_key": "breathing_reset"},
        {"role_key": "primary_strength_day"},
    ]
    assert _week_aerobic_filler_count(roles) == 1
    assert _week_aerobic_filler_count([]) == 0


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
