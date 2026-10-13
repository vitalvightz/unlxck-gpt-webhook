"""Fight proximity shapes workload; on its own it never deletes a session.

Proximity is already charged by the phase/taper allocation, the scheduled-day
countdown dose bands (D-17 inward), the late-fight budget (D-13 inward) and
shared calendar legality. The readiness-compression point it used to add for a
fresh, uninjured, non-cutting athlete removed a whole non-spar session on top of
all of those. It now only amplifies a genuine readiness signal.
"""
from __future__ import annotations

import pytest

from fightcamp.stage2_role_map import (
    _build_spar_allocation_reason_codes,
    _compute_readiness_compression,
    _readiness_compression_floor,
)
from fightcamp.stage2_validator import _strength_session_quality_warnings


def _athlete(days, **extra):
    return {"fatigue": "low", "injuries": [], "days_until_fight": days, "weight_cut_risk": False,
            "weight_cut_pct": 0.0, "readiness_flags": [], **extra}


@pytest.mark.parametrize("days", [21, 17, 14, 13, 10, 7, 5, 2, 1, 0])
def test_proximity_alone_removes_no_session(days):
    athlete = _athlete(days)
    assert _compute_readiness_compression(athlete) == 0
    assert _readiness_compression_floor(athlete) == 0
    assert "proximity_to_fight" not in _build_spar_allocation_reason_codes(athlete, 0, False, False)


@pytest.mark.parametrize("days", [17, 10])
def test_proximity_still_amplifies_high_fatigue(days):
    athlete = _athlete(days, fatigue="high")
    assert _compute_readiness_compression(athlete) == 2
    assert "proximity_to_fight" in _build_spar_allocation_reason_codes(athlete, 2, False, False)
    # Outside the proximity window high fatigue keeps its own single point.
    assert _compute_readiness_compression(_athlete(28, fatigue="high")) == 1


def _validator_brief(scheduled):
    pool = {"strength_slots": [
        {"session_index": 1, "selected": {"name": "Trap Bar Deadlift", "anchor_capable": True}},
        {"session_index": 1, "selected": {"name": "Technical Shadowboxing Tempo", "support_only": True}},
    ]}
    return {"candidate_pools": {"TAPER": pool}, "phase_strategy": {"TAPER": {}},
            "late_fight_session_sequence": [
                {"role_key": "fight_week_freshness_day", "scheduled_countdown_label": "D-2",
                 "selected_exercise_assignments": [{"name": name} for name in scheduled]}]}


def test_a_d2_freshness_session_is_not_weak_for_omitting_a_heavy_lift():
    lines = ["D-2 - Technical Shadowboxing Tempo 2 x 6"]
    warnings = _strength_session_quality_warnings(_validator_brief(["Technical Shadowboxing Tempo"]), {}, lines)
    assert not [w for w in warnings if w["code"] in {"weak_anchor_session", "support_takeover_before_anchor"}]


def test_a_scheduled_anchor_missing_from_the_render_is_still_flagged():
    lines = ["D-2 - Technical Shadowboxing Tempo 2 x 6"]
    brief = _validator_brief(["Trap Bar Deadlift", "Technical Shadowboxing Tempo"])
    codes = {w["code"] for w in _strength_session_quality_warnings(brief, {}, lines)}
    assert "weak_anchor_session" in codes


def test_open_membership_plans_keep_the_pool_based_check():
    brief = _validator_brief([])
    del brief["late_fight_session_sequence"]
    codes = {w["code"] for w in _strength_session_quality_warnings(brief, {}, ["Technical Shadowboxing Tempo 2 x 6"])}
    assert "weak_anchor_session" in codes
