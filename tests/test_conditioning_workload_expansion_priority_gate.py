"""The developmental workload envelope belongs to gas-tank athletes only.

`_resolve_conditioning_sessions` keeps extra primaries until the shared
`conditioning_phase_workload_envelope` active-work target is met. That target is
a conditioning *development* dose, so it may only be spent for an athlete whose
primary goal or primary weak area is conditioning / gas tank. Every other
athlete keeps the ordinary one-primary maintenance selection, preserving
Power / Speed / Strength capacity.

The gate reuses `_conditioning_priority_is_primary_gas_tank`, i.e. the same
primary/secondary tiering the rest of conditioning scoring already reads.
"""

from types import SimpleNamespace

import pytest

from fightcamp.conditioning import (
    _conditioning_priority_is_primary_gas_tank,
    _resolve_conditioning_sessions,
)
from fightcamp.priority_profile import build_priority_profile
from fightcamp.session_composition import compose_normal_conditioning_assignments


def _profile(*, goals, primary_goal, weaknesses, primary_weak_area):
    return build_priority_profile(
        SimpleNamespace(
            key_goals=goals,
            primary_goal=primary_goal,
            weak_areas=weaknesses,
            primary_weak_area=primary_weak_area,
        )
    )


CONDITIONING_PRIMARY = _profile(
    goals=["Conditioning", "Power"],
    primary_goal="Conditioning",
    weaknesses=["Gas Tank"],
    primary_weak_area="Gas Tank",
)
GAS_TANK_WEAKNESS = _profile(
    goals=["Power"],
    primary_goal="Power",
    weaknesses=["Gas Tank", "Footwork"],
    primary_weak_area="Gas Tank",
)
POWER_FOOTWORK_SPEED = _profile(
    goals=["Power"],
    primary_goal="Power",
    weaknesses=["Footwork", "Speed"],
    primary_weak_area="Footwork",
)
STRENGTH_PRIMARY = _profile(
    goals=["Strength"],
    primary_goal="Strength",
    weaknesses=["Footwork"],
    primary_weak_area="Footwork",
)
SECONDARY_CONDITIONING = _profile(
    goals=["Power", "Conditioning"],
    primary_goal="Power",
    weaknesses=["Footwork", "Gas Tank"],
    primary_weak_area="Footwork",
)


# ---------------------------------------------------------------------------
# Which athletes open the envelope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "profile",
    [CONDITIONING_PRIMARY, GAS_TANK_WEAKNESS],
    ids=["conditioning_primary_goal", "gas_tank_primary_weakness"],
)
def test_primary_conditioning_targets_open_the_envelope(profile):
    assert _conditioning_priority_is_primary_gas_tank(profile) is True


@pytest.mark.parametrize(
    "profile",
    [POWER_FOOTWORK_SPEED, STRENGTH_PRIMARY, SECONDARY_CONDITIONING],
    ids=["power_footwork_speed", "strength_primary", "secondary_conditioning_only"],
)
def test_other_profiles_do_not_open_the_envelope(profile):
    """A merely *secondary* conditioning target keeps its ordinary secondary
    preference — the same doctrine `_conditioning_priority_is_primary_gas_tank`
    already documents — rather than earning developmental volume."""
    assert _conditioning_priority_is_primary_gas_tank(profile) is False


# ---------------------------------------------------------------------------
# What the gate does to session resolution
# ---------------------------------------------------------------------------


def _drill(name, *, work_sec, rounds, rest_sec=60):
    return {"name": name, "work_sec": work_sec, "rounds": rounds, "rest_sec": rest_sec}


def _short_of_target_drills():
    """Two glycolytic drills where the first alone cannot carry the SPP target."""
    return [
        _drill("Sprawl Circuit", work_sec=30, rounds=5),
        _drill("Bag Intervals", work_sec=30, rounds=6),
    ]


def _primary_names(sessions, system="glycolytic"):
    return [
        entry["primary"]["name"]
        for session in sessions
        for entry in session["entries"]
        if entry["primary"]["system"].lower() == system
    ]


def test_expansion_runs_for_a_primary_conditioning_athlete():
    sessions = _resolve_conditioning_sessions(
        {"glycolytic": _short_of_target_drills()},
        phase="SPP",
        num_sessions=1,
        workload_expansion_allowed=True,
    )
    assert _primary_names(sessions) == ["Sprawl Circuit", "Bag Intervals"]


def test_expansion_is_withheld_without_a_primary_conditioning_target():
    """Conditioning still appears — one normal selection — but the athlete's
    Power/Speed/Strength capacity is not spent closing a developmental envelope."""
    sessions = _resolve_conditioning_sessions(
        {"glycolytic": _short_of_target_drills()},
        phase="SPP",
        num_sessions=1,
        workload_expansion_allowed=False,
    )
    assert _primary_names(sessions) == ["Sprawl Circuit"]


def test_expansion_is_withheld_by_default():
    """The unguarded default is maintenance, not development."""
    sessions = _resolve_conditioning_sessions(
        {"glycolytic": _short_of_target_drills()},
        phase="SPP",
        num_sessions=1,
    )
    assert _primary_names(sessions) == ["Sprawl Circuit"]


def test_the_gate_never_touches_the_explicit_speed_alactic_cap():
    """Speed dose governance is its own authority and is unchanged by the gate."""
    sessions = _resolve_conditioning_sessions(
        {"alactic": [_drill("Sprints", work_sec=6, rounds=4), _drill("Bounds", work_sec=6, rounds=4)]},
        phase="SPP",
        num_sessions=1,
        alactic_primary_cap=2,
        workload_expansion_allowed=False,
    )
    assert len(_primary_names(sessions, system="alactic")) == 2


# ---------------------------------------------------------------------------
# The original #2495 bug stays fixed for every goal profile
# ---------------------------------------------------------------------------


def _role_map():
    return {
        "weeks": [
            {
                "phase": "SPP",
                "effective_hard_sparring_days": [],
                "session_roles": [
                    {
                        "category": "conditioning",
                        "role_key": "aerobic_support_day",
                        "preferred_system": "aerobic",
                        "scheduled_day_hint": "wednesday",
                    }
                ],
            }
        ]
    }


def _option(name, duration):
    return {
        "name": name,
        "selection_metadata": {
            "name": name,
            "system": "aerobic",
            "total_minutes": duration,
            "rpe": 5,
            "intensity": "moderate",
        },
    }


@pytest.mark.parametrize(
    "profile",
    [CONDITIONING_PRIMARY, GAS_TANK_WEAKNESS, POWER_FOOTWORK_SPEED, STRENGTH_PRIMARY],
    ids=["conditioning", "gas_tank", "power_footwork_speed", "strength"],
)
def test_alternates_are_never_session_members_for_any_profile(profile):
    """D-18 regression: a slot's substitution reservoir is not a circuit."""
    role_map = _role_map()
    pools = {
        "SPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-aerobic-1",
                    "role": "aerobic",
                    "selected": _option("Selected Flow", 3),
                    "alternates": [_option("Backup One", 3), _option("Backup Two", 3)],
                }
            ]
        }
    }

    compose_normal_conditioning_assignments(
        weekly_role_map=role_map, candidate_pools=pools
    )

    role = role_map["weeks"][0]["session_roles"][0]
    assert [item["name"] for item in role["selected_exercise_assignments"]] == [
        "Selected Flow"
    ]
