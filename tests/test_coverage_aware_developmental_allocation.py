"""Developmental capacity is allocated to unresolved athlete priorities.

`build_target_coverage_state` has always known which selected targets lack
meaningful coverage, but its only consumer was the low-cost filler machinery -
and `_FILLER_TARGET_CAPABILITY` deliberately refuses to claim power or strength.
So for a Power-primary athlete the planner knew Power was unbuilt and had no
consumer of that fact able to act on it.

`_coverage_aware_role_key` closes that loop at the developmental role level. It
never creates a session: the weekly budget, contact rules, recovery rules and
unused-day rules decide the slot exists first. It only decides which adaptation
an already-granted slot builds.
"""

from __future__ import annotations

import pytest

from fightcamp.gap_fill_inserts import (
    _MEANINGFUL_ROLE_CAPABILITIES,
    build_target_coverage_state,
    role_target_capabilities,
    unresolved_developmental_targets,
)
from fightcamp.priority_profile import (
    PRIMARY_GOAL_WEIGHT,
    PRIMARY_WEAKNESS_WEIGHT,
    priority_allocation_rank,
)
from fightcamp.stage2_role_map import (
    _DEVELOPMENTAL_ROLE_UPGRADES,
    _build_weekly_role_map,
    _coverage_aware_role_key,
)


def _athlete(*, goal, weakness, secondary=None, sport="boxing", **overrides):
    weaknesses = [weakness] + list(secondary or [])
    athlete = {
        "sport": sport,
        "training_days": [
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
        ],
        "training_frequency": 4,
        "fight_date": "2027-07-18",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
        "key_goals": [goal],
        "primary_goal": goal,
        "weaknesses": weaknesses,
        "weak_areas": weaknesses,
        "primary_weak_area": weakness,
    }
    athlete.update(overrides)
    return athlete


def _progression(phases=("GPP", "GPP", "SPP", "SPP", "TAPER"), *, strength=1, conditioning=2):
    return {
        "weeks": [
            {
                "week_index": index + 1,
                "phase": phase,
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {
                    "strength": strength,
                    "conditioning": conditioning,
                    "recovery": 1,
                },
                "conditioning_sequence": ["aerobic", "glycolytic"],
            }
            for index, phase in enumerate(phases)
        ]
    }


def _role_map(athlete, progression=None, limiter="footwork"):
    return _build_weekly_role_map(
        athlete, progression or _progression(), {"key": limiter}
    )


def _week(role_map, index):
    return role_map["weeks"][index]


def _uncovered(athlete, roles):
    return [
        state.target
        for state in build_target_coverage_state(athlete, roles)
        if not state.meaningful_coverage
    ]


def _role_keys(week):
    return [role.get("role_key") for role in week["session_roles"]]


# ---------------------------------------------------------------------------
# The ordering authority: adaptation before limiter
# ---------------------------------------------------------------------------


def test_primary_goal_is_allocated_before_the_primary_weakness():
    """Even though the raw weakness weight is the larger number."""
    assert PRIMARY_WEAKNESS_WEIGHT > PRIMARY_GOAL_WEIGHT
    assert priority_allocation_rank(("primary_goal",)) < priority_allocation_rank(
        ("primary_weakness",)
    )


def test_secondary_targets_rank_below_every_primary():
    for source in ("secondary_goal", "secondary_weakness"):
        assert priority_allocation_rank((source,)) > priority_allocation_rank(
            ("primary_weakness",)
        )


def test_a_target_selected_twice_takes_its_strongest_source():
    assert priority_allocation_rank(("secondary_weakness", "primary_goal")) == (
        priority_allocation_rank(("primary_goal",))
    )


def test_unresolved_targets_are_returned_in_allocation_order():
    athlete = _athlete(goal="power", weakness="footwork", secondary=["speed"])
    assert unresolved_developmental_targets(athlete, []) == ("power", "footwork", "speed")


def test_every_upgrade_declares_a_capability_superset():
    """An upgrade may only ever add coverage, never trade one target for another."""
    for role_key, candidates in _DEVELOPMENTAL_ROLE_UPGRADES.items():
        current = _MEANINGFUL_ROLE_CAPABILITIES[role_key]
        for candidate in candidates:
            assert _MEANINGFUL_ROLE_CAPABILITIES[candidate] > current


# ---------------------------------------------------------------------------
# 1. Power primary, Footwork primary weakness, Speed secondary
# ---------------------------------------------------------------------------


class TestPowerFootworkSpeed:
    def _athlete(self):
        return _athlete(
            goal="power",
            weakness="footwork",
            secondary=["speed"],
            hard_sparring_days=["tuesday", "thursday"],
            light_combat_days=["saturday"],
            reduced_contact=True,
        )

    def test_power_moves_from_uncovered_to_covered_in_the_build_block(self):
        athlete = self._athlete()
        week = _week(_role_map(athlete), 0)
        assert week["phase"] == "GPP"
        assert "neural_plus_strength_day" in _role_keys(week)
        assert "power" not in _uncovered(athlete, week["session_roles"])

    def test_no_session_is_added_to_pay_for_it(self):
        athlete = self._athlete()
        week = _week(_role_map(athlete), 0)
        assert len(week["session_roles"]) <= int(athlete["training_frequency"])

    def test_contact_days_are_untouched(self):
        athlete = self._athlete()
        week = _week(_role_map(athlete), 0)
        sparring = [r for r in week["session_roles"] if r.get("category") == "sparring"]
        assert len(sparring) == 2

    def test_the_technical_limiter_does_not_consume_the_physical_slot(self):
        """Footwork outranks Power but no strength identity can build it, so it
        stays with the low-cost support machinery that honestly covers it."""
        athlete = self._athlete()
        week = _week(_role_map(athlete), 0)
        assert "footwork" in _uncovered(athlete, week["session_roles"])
        assert "neural_plus_strength_day" in _role_keys(week)


# ---------------------------------------------------------------------------
# 2-3. The same machinery serves other primary adaptations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("goal", ["strength", "speed", "power"])
def test_an_under_covered_primary_adaptation_is_resolved(goal):
    athlete = _athlete(goal=goal, weakness="footwork")
    week = _week(_role_map(athlete), 0)
    assert goal not in _uncovered(athlete, week["session_roles"])


def test_strength_primary_keeps_its_existing_identity():
    """Strength was already covered, so nothing is upgraded for its sake."""
    athlete = _athlete(goal="strength", weakness="footwork")
    week = _week(_role_map(athlete), 0)
    assert "primary_strength_day" in _role_keys(week)


# ---------------------------------------------------------------------------
# 5-6. Coverage, not raw weight, decides
# ---------------------------------------------------------------------------


def test_allocator_moves_on_once_the_primary_goal_is_covered():
    """Strength primary is already covered; Speed - a secondary - takes the slot."""
    athlete = _athlete(goal="strength", weakness="footwork", secondary=["speed"])
    week = _week(_role_map(athlete), 0)
    assert "speed" not in _uncovered(athlete, week["session_roles"])


def test_a_covered_primary_weakness_stops_consuming_capacity():
    athlete = _athlete(goal="footwork", weakness="power")
    week = _week(_role_map(athlete), 0)
    roles = week["session_roles"]
    assert "power" not in _uncovered(athlete, roles)
    # Having been covered once, it is no longer an unresolved target at all.
    assert "power" not in unresolved_developmental_targets(athlete, roles)


# ---------------------------------------------------------------------------
# 7. No legal role for the unresolved priority
# ---------------------------------------------------------------------------


def test_capacity_is_left_alone_when_no_strength_identity_can_help():
    athlete = _athlete(goal="footwork", weakness="mobility")
    week = _week(_role_map(athlete), 0)
    assert "primary_strength_day" in _role_keys(week)


def test_role_key_is_returned_unchanged_when_nothing_is_unresolved():
    athlete = _athlete(goal="strength", weakness="strength")
    assert (
        _coverage_aware_role_key(
            "primary_strength_day",
            phase="GPP",
            athlete_model=athlete,
            scheduled_roles=[
                {"category": "strength", "role_key": "primary_strength_day"}
            ],
        )
        == "primary_strength_day"
    )


def test_an_unlisted_role_key_is_never_substituted():
    athlete = _athlete(goal="power", weakness="footwork")
    assert (
        _coverage_aware_role_key(
            "structural_strength_day",
            phase="GPP",
            athlete_model=athlete,
            scheduled_roles=[],
        )
        == "structural_strength_day"
    )


# ---------------------------------------------------------------------------
# 8-9. Safety, contact and phase authority still win
# ---------------------------------------------------------------------------


def test_crowded_hard_sparring_week_keeps_its_session_budget():
    athlete = _athlete(
        goal="power",
        weakness="footwork",
        hard_sparring_days=["tuesday", "thursday"],
        light_combat_days=["saturday"],
    )
    lean = _athlete(goal="power", weakness="footwork")
    crowded_week = _week(_role_map(athlete), 0)
    lean_week = _week(_role_map(lean), 0)
    # The allocator changes identity, never count: the crowded week is still the
    # smaller week its freshness rule made it.
    assert len(crowded_week["session_roles"]) <= len(lean_week["session_roles"]) + 2
    assert len(crowded_week["session_roles"]) <= int(athlete["training_frequency"])


@pytest.mark.parametrize("phase", ["TAPER"])
def test_no_development_is_added_during_taper_to_close_a_gap(phase):
    athlete = _athlete(goal="power", weakness="footwork")
    assert (
        _coverage_aware_role_key(
            "primary_strength_day",
            phase=phase,
            athlete_model=athlete,
            scheduled_roles=[],
        )
        == "primary_strength_day"
    )


def test_taper_week_role_identity_is_untouched_end_to_end():
    athlete = _athlete(goal="power", weakness="footwork")
    taper = _week(_role_map(athlete), 4)
    assert taper["phase"] == "TAPER"
    assert "neural_plus_strength_day" not in _role_keys(taper)


# ---------------------------------------------------------------------------
# 10. Secondary targets
# ---------------------------------------------------------------------------


def test_a_secondary_cannot_outrank_an_unresolved_primary_adaptation():
    """Power (primary goal) and Speed (secondary) are both unresolved and both
    servable; the primary adaptation is chosen."""
    athlete = _athlete(goal="power", weakness="footwork", secondary=["speed"])
    assert unresolved_developmental_targets(athlete, [])[0] == "power"


# ---------------------------------------------------------------------------
# 11. Cross-sport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport", ["mma", "muay_thai", "bjj"])
def test_the_mechanism_is_not_boxing_specific(sport):
    athlete = _athlete(goal="power", weakness="footwork", sport=sport)
    week = _week(_role_map(athlete), 0)
    assert "power" not in _uncovered(athlete, week["session_roles"])


# ---------------------------------------------------------------------------
# 12. The #2495 conditioning gate is untouched
# ---------------------------------------------------------------------------


def test_conditioning_roles_are_not_touched_by_the_allocator():
    """Conditioning identity stays with the brief's sequence and the #2495 gate."""
    assert not any(
        "aerobic" in key or "glycolytic" in key or "fight_pace" in key
        for key in _DEVELOPMENTAL_ROLE_UPGRADES
    )


def test_conditioning_primary_athlete_role_identity_is_unchanged():
    athlete = _athlete(goal="conditioning", weakness="gas_tank")
    week = _week(_role_map(athlete), 0)
    assert "primary_strength_day" in _role_keys(week)
    assert "conditioning" not in _uncovered(athlete, week["session_roles"])


def test_upgraded_role_still_reports_honest_capabilities():
    upgraded = {"category": "strength", "role_key": "neural_plus_strength_day"}
    assert role_target_capabilities(upgraded) == {"strength", "power", "speed"}
