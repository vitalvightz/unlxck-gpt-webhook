"""A planner week is a calendar container; a training phase is not.

Live plan regression: the first weekly container was labelled GPP and spanned
D-26 -> D-20, but the canonical Stage 1 allocation (7 GPP / 14 SPP / 6 TAPER)
puts D-20 in SPP. `compose_normal_strength_assignments` read
`week["phase"]` once per week and handed every role inside that container the
GPP strength pool, so GPP-only exercises (Single-Leg Romanian Deadlift Hold,
Chop Holds (Anti-Rotation)) landed on an SPP day. The authority validator
deliberately recomputes phase from the D-day rather than trusting the week
label, and correctly raised `selected_exercise_phase_ineligible`.

Exercise authority must follow the role's own D-day.
"""

from __future__ import annotations

from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.session_composition import compose_normal_strength_assignments

GPP_ONLY = "Single-Leg Romanian Deadlift Hold"
SPP_ONLY = "Rotational Med-Ball Throw"

# The canonical allocation from the live plan: counting back from the fight,
# D-1..D-6 TAPER, D-7..D-20 SPP, D-21 onward GPP.
_ATHLETE = {
    "fatigue": "low",
    "cut_severity_bucket": "none",
    "phase_weeks": {"days": {"GPP": 7, "SPP": 14, "TAPER": 6}},
}


def _slot(name: str) -> dict:
    return {
        "slot_id": f"slot-{name}",
        "session_index": 1,
        "priority": 1,
        "selected": {
            "name": name,
            "movement": "hinge",
            "tags": ["compound"],
            "movement_patterns": ["hinge"],
            "equipment": ["dumbbell"],
            "prescription": "3 x 5 @ RPE 7",
        },
    }


_POOLS = {
    "GPP": {"strength_slots": [_slot(GPP_ONLY)]},
    "SPP": {"strength_slots": [_slot(SPP_ONLY)]},
}


def _role(day: str) -> dict:
    return {
        "role_key": "primary_strength_day",
        "category": "strength",
        "strength_session_index": 1,
        "scheduled_day_hint": day,
    }


def _boundary_week() -> dict:
    """One GPP-labelled container that crosses into SPP at D-20."""
    return {
        "weeks": [
            {
                # Stale container label: the week STARTS in GPP.
                "phase": "GPP",
                "calendar_days": [
                    {"weekday": "monday", "d_day": 21},
                    {"weekday": "thursday", "d_day": 20},
                ],
                "session_roles": [_role("monday"), _role("thursday")],
            }
        ]
    }


def _compose(role_map: dict, *, athlete: dict | None = None, pools=None) -> dict:
    token = planner_athlete_model_context.set(athlete if athlete is not None else _ATHLETE)
    try:
        compose_normal_strength_assignments(
            weekly_role_map=role_map, candidate_pools=pools or _POOLS,
        )
    finally:
        planner_athlete_model_context.reset(token)
    return role_map


def _names(role: dict) -> list[str]:
    return [item["name"] for item in role.get("selected_exercise_assignments") or []]


def test_the_gpp_day_inside_the_boundary_week_still_uses_the_gpp_pool():
    week = _compose(_boundary_week())["weeks"][0]
    d21 = week["session_roles"][0]
    assert _names(d21) == [GPP_ONLY]
    assert {a["source_phase"] for a in d21["selected_exercise_assignments"]} == {"GPP"}


def test_the_spp_day_inside_the_gpp_labelled_week_cannot_take_a_gpp_only_exercise():
    week = _compose(_boundary_week())["weeks"][0]
    d20 = week["session_roles"][1]
    assert GPP_ONLY not in _names(d20)
    assert _names(d20) == [SPP_ONLY]
    assert {a["source_phase"] for a in d20["selected_exercise_assignments"]} == {"SPP"}


def test_a_week_wholly_inside_one_phase_is_unchanged():
    role_map = {
        "weeks": [
            {
                "phase": "GPP",
                "calendar_days": [
                    {"weekday": "monday", "d_day": 26},
                    {"weekday": "thursday", "d_day": 24},
                ],
                "session_roles": [_role("monday"), _role("thursday")],
            }
        ]
    }
    week = _compose(role_map)["weeks"][0]
    for role in week["session_roles"]:
        assert _names(role) == [GPP_ONLY]


def test_an_undated_role_still_falls_back_to_the_week_label():
    """No D-day to resolve: the container label remains the only authority."""
    role_map = {
        "weeks": [
            {"phase": "GPP", "session_roles": [
                {"role_key": "primary_strength_day", "category": "strength",
                 "strength_session_index": 1},
            ]},
        ]
    }
    role = _compose(role_map)["weeks"][0]["session_roles"][0]
    assert _names(role) == [GPP_ONLY]


def test_a_camp_without_stage1_phase_days_keeps_the_week_label():
    """Nothing to resolve against must never empty a session."""
    role = _compose(_boundary_week(), athlete={"fatigue": "low"})["weeks"][0]["session_roles"][1]
    assert _names(role) == [GPP_ONLY]


def test_late_fight_tail_roles_are_still_skipped_by_normal_composition():
    role_map = _boundary_week()
    for role in role_map["weeks"][0]["session_roles"]:
        role["late_fight_tail_owned"] = True
    week = _compose(role_map)["weeks"][0]
    assert all("selected_exercise_assignments" not in r for r in week["session_roles"])
