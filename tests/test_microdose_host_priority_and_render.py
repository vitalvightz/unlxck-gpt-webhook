"""Host eligibility and athlete-facing propagation for the weekly microdose.

Two separate concerns:

* Host eligibility - only an existing strength session with composed
  membership can host: the microdose is an already-selected strength-pool
  exercise and only the strength dose resolver can price it. A technical or
  conditioning day (declared light combat included) is never filled with
  strength work by goal preservation.
* Propagation - when Stage 2 fails there is no structured_plan, so the
  deterministic fallback IS the athlete-facing plan. A renderer that reads only
  `selected_exercise_assignments` drops a microdose that lives on the role.
"""

from __future__ import annotations

import pytest

from api.structured_plan_deterministic_fallback import _blocks, _session
from fightcamp.declared_combat_ownership import build_declared_light_combat_role
from fightcamp.goal_preservation import _attach_goal_microdose, _microdose_host_roles


# ---------------------------------------------------------------------------
# Host eligibility
# ---------------------------------------------------------------------------


def _light_combat(day="monday"):
    role = build_declared_light_combat_role(day)
    role["session_index"] = 1
    return role


def _conditioning(day="Tuesday"):
    return {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": day,
        "session_index": 2,
        "selected_exercise_assignments": [
            {"name": "Double-End Bag Circuit", "slot_group": "conditioning_slots"}
        ],
    }


def _strength(day="Wednesday"):
    return {
        "category": "strength",
        "role_key": "primary_strength_day",
        "scheduled_day_hint": day,
        "scheduled_countdown_label": "D-24",
        "session_index": 3,
        "strength_session_index": 1,
        "strength_composition_policy": {"effective_exercise_cap": 3},
        "selected_exercise_assignments": [
            {"slot_id": "spp_a", "name": "DB Bench Press", "slot_group": "strength_slots",
             "source_phase": "SPP", "base_prescription": "3x5 @ RPE 7"}
        ],
    }


def _pool_slot(slot_id, name, quality_class, prescription, tags, session_index):
    return {"slot_id": slot_id, "session_index": session_index, "quality_class": quality_class,
            "selected": {"name": name, "prescription": prescription, "quality_class": quality_class,
                         "tags": tags, "mechanical_risk_tags": []}}


def _week(*roles):
    return {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 26},
            {"weekday": "tuesday", "d_day": 25},
            {"weekday": "wednesday", "d_day": 24},
        ],
        "declared_training_days": ["monday", "tuesday", "wednesday"],
        "session_roles": list(roles),
    }


def _brief(week):
    return {
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": 27,
            "training_frequency": 4,
            "key_goals": ["power"],
            "primary_goal": "power",
            "weak_areas": ["footwork"],
            "primary_weak_area": "footwork",
        },
        "weekly_role_map": {"weeks": [week]},
        "candidate_pools": {"SPP": {"strength_slots": [
            _pool_slot("spp_a", "DB Bench Press", "anchor_loaded", "3x5 @ RPE 7", ["strength"], 1),
            _pool_slot("spp_b", "Med Ball Scoop Toss", "anchor_power", "4x3 @ RPE 7, full rest",
                       ["power", "explosive"], 2),
        ]}},
    }


_POWER = {
    "goal": "power",
    "priority": "primary",
    "state": "build",
    "required_intent": "ballistic_power",
    "evidence": [],
}


def _winner(week):
    brief = _brief(week)
    _attach_goal_microdose(brief, 0, _POWER)
    return next(
        (
            role["role_key"]
            for role in brief["weekly_role_map"]["weeks"][0]["session_roles"]
            if role.get("priority_microdose")
        ),
        None,
    )


def test_the_strength_session_hosts_even_beside_technical_and_conditioning():
    assert _winner(_week(_conditioning(), _light_combat(), _strength())) == "primary_strength_day"


def test_light_combat_and_conditioning_alone_get_no_strength_work():
    """F06: goal preservation no longer hangs an invented touch on a coach-owned
    technical day or a conditioning session."""
    assert _winner(_week(_conditioning(), _light_combat())) is None


def test_the_canonical_light_combat_role_is_not_an_eligible_host():
    hosts = _microdose_host_roles(_week(_conditioning(), _light_combat(), _strength()))
    assert [role["role_key"] for role in hosts] == ["primary_strength_day"]


def test_host_choice_is_independent_of_role_list_order():
    for week in (
        _week(_strength(), _light_combat(), _conditioning()),
        _week(_conditioning(), _light_combat(), _strength()),
    ):
        assert _winner(week) == "primary_strength_day"


# ---------------------------------------------------------------------------
# Propagation into the deterministic fallback
# ---------------------------------------------------------------------------


def _host_with_microdose(**extra):
    role = {
        "category": "technical",
        "role_key": "light_combat_day",
        "session_index": 1,
        "selected_exercise_assignments": [
            {"name": "Technical Rounds", "effective_prescription": "5 x 3 min"}
        ],
        "priority_microdose": {
            "goal": "power",
            "name": "Med-Ball Rotational Throw",
            "prescription": "2 x 3/side @ RPE 7",
            "sets": 2,
            "intents": ["ballistic_power"],
        },
    }
    role.update(extra)
    return role


def test_the_microdose_survives_deterministic_fallback_rendering():
    blocks = _blocks(_host_with_microdose(), 26, "light_combat_day")
    assert "Med-Ball Rotational Throw" in blocks[0]["display_name"]


def test_it_renders_as_subordinate_work_inside_the_host_session():
    session = _session(_host_with_microdose(), 26)
    names = [block["display_name"] for block in session["blocks"]]
    assert len(names) == 2
    assert "Med-Ball Rotational Throw" in names[0]
    assert names[1] == "Technical Rounds"
    assert [block["order_index"] for block in session["blocks"]] == [0, 1]


def test_the_host_session_identity_is_unchanged():
    session = _session(_host_with_microdose(), 26)
    assert session["session_id"].startswith("deterministic-26-light_combat_day")
    assert session["session_type"] == "skill"
    assert session["title"] == "Light technical combat"


def test_no_separate_session_is_created_for_the_microdose():
    """A role with no selected exercise renders no session; a microdose must not
    be the thing that brings one into existence."""
    bare = {
        "category": "technical",
        "role_key": "light_combat_day",
        "priority_microdose": _host_with_microdose()["priority_microdose"],
    }
    assert _session(bare, 26) is None


def test_the_microdose_carries_its_dose_into_the_rendered_block():
    block = _blocks(_host_with_microdose(), 26, "light_combat_day")[0]
    # Movement guidance may precede it (#2894); the dose itself is carried.
    assert block["coaching_cues"][-1] == "2 x 3/side @ RPE 7"


@pytest.mark.parametrize(
    "goal,block_type",
    [
        ("power", "plyometric_power"),
        ("speed", "speed"),
        ("strength", "strength"),
        ("footwork", "skill"),
        ("mobility", "mobility_activation"),
    ],
)
def test_each_goal_renders_with_an_honest_block_type(goal, block_type):
    role = _host_with_microdose()
    role["priority_microdose"] = dict(role["priority_microdose"], goal=goal)
    assert _blocks(role, 26, "light_combat_day")[0]["block_type"] == block_type


def test_a_role_without_a_microdose_renders_exactly_as_before():
    role = _host_with_microdose()
    del role["priority_microdose"]
    blocks = _blocks(role, 26, "light_combat_day")
    assert [block["display_name"] for block in blocks] == ["Technical Rounds"]
    assert blocks[0]["order_index"] == 0


def test_rendering_is_idempotent_across_repeated_builds():
    role = _host_with_microdose()
    first = _blocks(role, 26, "light_combat_day")
    second = _blocks(role, 26, "light_combat_day")
    assert [b["display_name"] for b in first] == [b["display_name"] for b in second]
    assert len(second) == 2


def test_synced_microdose_membership_does_not_create_a_second_fallback_block():
    """Reproduce the real role shape after `_sync_microdose_membership`."""
    role = _host_with_microdose()
    role["selected_exercise_assignments"].append({
        "slot_id": "priority_microdose::power",
        "slot_group": "priority_microdose",
        "name": "Med-Ball Rotational Throw",
        "effective_prescription": "2 x 3/side @ RPE 7",
    })

    blocks = _blocks(role, 26, "light_combat_day")
    assert len(blocks) == 2
    assert sum("Med-Ball Rotational Throw" in block["display_name"] for block in blocks) == 1
