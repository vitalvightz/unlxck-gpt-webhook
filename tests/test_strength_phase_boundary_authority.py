"""A calendar week that straddles a phase boundary must not leak GPP-only work.

A weekly container carries the phase its week *starts* in. Stage 1's canonical
allocation is counted back from the fight in days, so a week labelled GPP can
still contain a role whose own D-day belongs to SPP. Strength composition used
to take its candidate pool from the week label, which handed GPP-only exercises
to an SPP day -- exactly what the authority validator flags as
``selected_exercise_phase_ineligible`` (it deliberately recomputes phase from
the D-day so a stale week label cannot hide a bad selection).

Composition now resolves the pool through the same shared resolver.
"""

import pytest

from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import compose_normal_strength_assignments

# TAPER 6 + SPP 14 + GPP 7, counted back from the fight:
#   D-1..D-6 TAPER, D-7..D-20 SPP, D-21+ GPP.
ATHLETE_MODEL = {"phase_weeks": {"days": {"TAPER": 6, "SPP": 14, "GPP": 7}}}

GPP_ONLY = "Single-Leg Romanian Deadlift Hold"
SPP_EXERCISE = "Hang Power Clean"


def _slot(name: str, session_index: int = 1) -> dict:
    return {
        "slot_id": f"slot_{name.lower().replace(' ', '_')}_{session_index}",
        "session_index": session_index,
        "priority": 1,
        "quality_class": "anchor_loaded",
        "anchor_capable": True,
        "selected": {
            "name": name,
            "prescription": "4 x 3 @ RPE 7",
            "quality_class": "anchor_loaded",
            "anchor_capable": True,
        },
    }


def _role(weekday: str, d_day: int) -> dict:
    return {
        "role_key": "primary_strength_day",
        "category": "strength",
        "scheduled_day_hint": weekday,
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_d_day": d_day,
    }


def _compose(week_phase: str, roles: list[dict], pools: dict) -> dict:
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "phase": week_phase,
                "calendar_days": [
                    {"weekday": r["scheduled_day_hint"], "d_day": r["scheduled_d_day"]}
                    for r in roles
                ],
                "session_roles": roles,
            }
        ]
    }
    token = planner_athlete_model_context.set(ATHLETE_MODEL)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=weekly_role_map, candidate_pools=pools
        )
    finally:
        planner_athlete_model_context.reset(token)
    return weekly_role_map


def _names(role: dict) -> list[str]:
    return [a.get("name") for a in (role.get("selected_exercise_assignments") or [])]


# Two strength sessions per week, so a straddling week can hold one role on
# each side of the boundary.
POOLS = {
    "GPP": {"strength_slots": [_slot(GPP_ONLY, 1), _slot(GPP_ONLY, 2)]},
    "SPP": {"strength_slots": [_slot(SPP_EXERCISE, 1), _slot(SPP_EXERCISE, 2)]},
}


def test_week_straddling_a_phase_boundary_doses_each_day_from_its_own_phase():
    gpp_role = _role("monday", 21)   # canonically GPP
    spp_role = _role("tuesday", 20)  # canonically SPP, inside a GPP-labelled week
    _compose("GPP", [gpp_role, spp_role], POOLS)

    assert _names(gpp_role) == [GPP_ONLY]
    assert _names(spp_role) == [SPP_EXERCISE]
    assert GPP_ONLY not in _names(spp_role)


def test_d20_role_records_the_spp_phase_on_its_assignment():
    spp_role = _role("tuesday", 20)
    _compose("GPP", [spp_role], POOLS)
    assignment = spp_role["selected_exercise_assignments"][0]
    assert assignment["source_phase"] == "SPP", assignment


@pytest.mark.parametrize(
    "week_phase, d_day, expected",
    [
        ("GPP", 23, GPP_ONLY),   # wholly inside GPP
        ("SPP", 14, SPP_EXERCISE),  # wholly inside SPP
    ],
)
def test_weeks_wholly_inside_one_phase_are_unchanged(week_phase, d_day, expected):
    role = _role("monday", d_day)
    _compose(week_phase, [role], POOLS)
    assert _names(role) == [expected]


def test_resolved_phase_with_no_pool_fails_closed_instead_of_borrowing():
    """No cross-phase substitution: that is how the bug happened in the first place.

    D-20 resolves to SPP. If no SPP pool exists, falling back to the GPP pool
    would hand this SPP day a GPP-only exercise again, so composition yields no
    candidates instead -- the same contract as ``phase_scoped_candidate_pools``.
    """
    role = _role("tuesday", 20)
    _compose("GPP", [role], {"GPP": {"strength_slots": [_slot(GPP_ONLY, 1)]}})
    assert _names(role) == []
    assert GPP_ONLY not in _names(role)


def test_single_phase_camp_still_composes_normally():
    """A GPP-only camp resolves into GPP, so it never needs the unsafe fallback."""
    gpp_only_model = {"phase_weeks": {"days": {"TAPER": 0, "SPP": 0, "GPP": 25}}}
    role = _role("monday", 20)
    weekly_role_map = {
        "weeks": [{
            "week_index": 1,
            "phase": "GPP",
            "calendar_days": [{"weekday": "monday", "d_day": 20}],
            "session_roles": [role],
        }]
    }
    token = planner_athlete_model_context.set(gpp_only_model)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=weekly_role_map,
            candidate_pools={"GPP": {"strength_slots": [_slot(GPP_ONLY, 1)]}},
        )
    finally:
        planner_athlete_model_context.reset(token)
    assert _names(role) == [GPP_ONLY]


def test_d_day_outside_the_camp_allocation_falls_back_to_the_week_label():
    """An unresolvable phase is the one case where the week label is safe."""
    role = _role("monday", 99)  # beyond the 27-day allocation
    _compose("GPP", [role], POOLS)
    assert _names(role) == [GPP_ONLY]


def test_late_fight_owned_roles_are_still_skipped_entirely():
    role = _role("tuesday", 20)
    role["late_fight_tail_owned"] = True
    _compose("GPP", [role], POOLS)
    assert "selected_exercise_assignments" not in role


def test_undated_role_still_uses_the_week_label():
    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "scheduled_day_hint": "monday",
    }
    weekly_role_map = {
        "weeks": [{"week_index": 1, "phase": "GPP", "calendar_days": [], "session_roles": [role]}]
    }
    token = planner_athlete_model_context.set(ATHLETE_MODEL)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=weekly_role_map, candidate_pools=POOLS
        )
    finally:
        planner_athlete_model_context.reset(token)
    assert _names(role) == [GPP_ONLY]
