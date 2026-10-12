"""A bookkeeping-unused weekday holding light combat never receives a microdose.

Live week 2 marked Saturday in `intentionally_unused_days` while that same
Saturday carried the coach-owned `light_combat_day`. The earlier fix let the
weekly microdose land on that technical day through `combat_load_policy`.

The microdose is now an already-selected strength-pool exercise priced by the
strength dose resolver, so only an existing strength session can host it. A
light-combat day, a conditioning day and a hard-sparring day are never hosts,
whatever the bookkeeping flag says, and a protected weekday stays protected.
"""

from __future__ import annotations

from fightcamp.declared_combat_ownership import build_declared_light_combat_role
from fightcamp.goal_preservation import _attach_goal_microdose, _microdose_host_roles


_POWER_ENTRY = {
    "goal": "power",
    "priority": "primary",
    "state": "build",
    "required_intent": "ballistic_power",
    "evidence": [],
}


def _light_combat():
    role = build_declared_light_combat_role("saturday")
    role["session_index"] = 1
    return role


def _conditioning():
    return {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": "Friday",
        "session_index": 2,
        "selected_exercise_assignments": [
            {"name": "Double-End Bag Circuit", "slot_group": "conditioning_slots"}
        ],
    }


def _hard_spar_on_saturday():
    return {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "preferred_pool": "declared_hard_sparring_days",
        "scheduled_day_hint": "Saturday",
        "session_index": 3,
    }


def _strength_on_saturday():
    return {
        "category": "strength",
        "role_key": "primary_strength_day",
        "scheduled_day_hint": "Saturday",
        "scheduled_countdown_label": "D-26",
        "session_index": 4,
        "strength_session_index": 1,
        "strength_composition_policy": {"effective_exercise_cap": 3},
        "selected_exercise_assignments": [
            {"slot_id": "spp_a", "name": "DB Bench Press", "slot_group": "strength_slots",
             "source_phase": "SPP", "base_prescription": "3x5 @ RPE 7"}
        ],
    }


def _week(*roles, protected=("Saturday",)):
    week = {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "saturday", "d_day": 26},
            {"weekday": "friday", "d_day": 25},
        ],
        "declared_training_days": ["friday", "saturday"],
        "session_roles": list(roles),
    }
    if protected:
        week["intentionally_unused_days"] = [
            {"day": day, "role": "recovery_only_day"} for day in protected
        ]
    return week


def _attach(week):
    brief = {
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": 27,
            "training_frequency": 3,
            "key_goals": ["power"],
            "primary_goal": "power",
        },
        "weekly_role_map": {"weeks": [week]},
        "candidate_pools": {"SPP": {"strength_slots": [
            {"slot_id": "spp_a", "session_index": 1, "quality_class": "anchor_loaded",
             "selected": {"name": "DB Bench Press", "prescription": "3x5 @ RPE 7",
                          "quality_class": "anchor_loaded", "tags": ["strength"]}},
            {"slot_id": "spp_b", "session_index": 2, "quality_class": "anchor_power",
             "selected": {"name": "Med Ball Scoop Toss", "prescription": "4x3 @ RPE 7, full rest",
                          "quality_class": "anchor_power", "tags": ["power", "explosive"]}},
        ]}},
    }
    audit = _attach_goal_microdose(brief, 0, _POWER_ENTRY)
    return audit, brief["weekly_role_map"]["weeks"][0]


def _hosted(week_state):
    return [role["role_key"] for role in week_state["session_roles"] if role.get("priority_microdose")]


def test_light_combat_on_a_protected_weekday_is_not_a_host():
    assert _microdose_host_roles(_week(_conditioning(), _light_combat())) == []


def test_neither_light_combat_nor_conditioning_receives_a_microdose():
    audit, week_state = _attach(_week(_conditioning(), _light_combat()))
    assert audit["result"] == "floor_no_safe_host"
    assert _hosted(week_state) == []


def test_hard_sparring_on_the_protected_weekday_is_still_forbidden():
    audit, week_state = _attach(_week(_conditioning(), _hard_spar_on_saturday()))
    assert audit["result"] == "floor_no_safe_host"
    assert _hosted(week_state) == []


def test_a_strength_session_on_a_protected_weekday_stays_protected():
    audit, week_state = _attach(_week(_strength_on_saturday()))
    assert audit["result"] == "floor_no_safe_host"
    assert _hosted(week_state) == []


def test_the_same_strength_session_hosts_once_the_day_is_not_protected():
    audit, week_state = _attach(_week(_strength_on_saturday(), protected=()))
    assert audit["result"] == "microdose_attached"
    assert _hosted(week_state) == ["primary_strength_day"]


def test_session_count_and_training_days_are_unchanged():
    week = _week(_conditioning(), _light_combat())
    before_sessions = len(week["session_roles"])
    before_days = list(week["declared_training_days"])
    _, week_state = _attach(week)
    assert len(week_state["session_roles"]) == before_sessions
    assert week_state["declared_training_days"] == before_days
