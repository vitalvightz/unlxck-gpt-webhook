"""Weekly priority exposure floor - the microdose tier of goal repair.

`goal_preservation` already owns a weekly floor (`_requirements`: one build
exposure per development week) and a deterministic repair pass
(`_restore_goal_roles`). That pass could only restore a WHOLE role from the
week's `goal_repair_candidates`, so when the session or category cap blocked it
a primary goal went cold for the entire build week.

`_attach_goal_microdose` is the fallback tier: the smallest exposure that still
produces honest development evidence, hung off a session the athlete is already
doing. It adds no session, no training day and no frequency.
"""

from __future__ import annotations

import pytest

from fightcamp.goal_preservation import (
    _MICRODOSE_FORBIDDEN_HOST_CATEGORIES,
    _MICRODOSE_SPECS,
    _microdose_host_roles,
    _microdose_stimuli,
)


def _role(category, role_key="r", **kw):
    role = {"category": category, "role_key": role_key}
    role.update(kw)
    return role


def _week(*roles, phase="GPP"):
    return {"week_index": 1, "phase": phase, "session_roles": list(roles)}


# ---------------------------------------------------------------------------
# Exposure quality: what a microdose is allowed to claim
# ---------------------------------------------------------------------------


def test_conditioning_has_no_microdose_spec():
    """Conditioning owns its own workload architecture; this tier must not be a
    back door for conditioning volume on a Power/Speed/Strength athlete."""
    assert "conditioning" not in _MICRODOSE_SPECS


def test_support_serviced_goals_have_no_microdose_spec():
    for goal in ("recovery", "weight_cut"):
        assert goal not in _MICRODOSE_SPECS


def test_every_spec_declares_a_development_capable_dose():
    """Below two quality sets it is maintenance, not development."""
    for goal, spec in _MICRODOSE_SPECS.items():
        assert spec["sets"] >= 2, goal
        assert spec["intents"], goal


@pytest.mark.parametrize(
    "goal,intent",
    [
        ("power", "ballistic_power"),
        ("speed", "speed_quality"),
        ("strength", "meaningful_strength"),
        ("footwork", "footwork_practice"),
        ("mobility", "mobility_dose"),
    ],
)
def test_each_spec_emits_the_canonical_intent_for_its_goal(goal, intent):
    """The spec must speak the same intent vocabulary the coverage ledger reads,
    so a microdose is recognised rather than silently ignored."""
    from fightcamp.goal_preservation import INTENTS

    assert INTENTS[goal] == intent
    assert intent in _MICRODOSE_SPECS[goal]["intents"]


def test_microdose_evidence_is_development_capable():
    role = _role("strength", priority_microdose=dict(_MICRODOSE_SPECS["power"], goal="power"))
    stimulus = _microdose_stimuli(role)[0]
    assert stimulus["intents"] == ["ballistic_power"]
    assert stimulus["development_capable"] is True
    assert stimulus["dose_authority"] == "weekly_priority_exposure_floor"


def test_a_single_set_touch_is_not_development():
    role = _role("strength", priority_microdose={"goal": "power", "sets": 1, "intents": ["ballistic_power"]})
    assert _microdose_stimuli(role)[0]["development_capable"] is False


def test_a_role_without_a_microdose_produces_no_evidence():
    assert _microdose_stimuli(_role("strength")) == []


# ---------------------------------------------------------------------------
# Host selection: where a microdose may and may not attach
# ---------------------------------------------------------------------------


def test_hard_sparring_is_never_a_host():
    assert "sparring" in _MICRODOSE_FORBIDDEN_HOST_CATEGORIES
    assert _microdose_host_roles(_week(_role("sparring", "hard_sparring_day"))) == []


def test_recovery_only_day_stays_recovery_only():
    assert _microdose_host_roles(_week(_role("recovery", "recovery_reset_day"))) == []


def test_fight_day_is_never_a_host():
    assert _microdose_host_roles(_week(_role("fight_day", "fight_day_protocol"))) == []


def test_tactical_watch_does_not_create_physical_capacity():
    """A zero-cost tactical insert is not a session to hang development on."""
    tactical = _role("technical", "tactical_watch", support_insert_category="tactical")
    assert _microdose_host_roles(_week(tactical)) == []


def test_a_support_insert_is_not_a_session():
    insert = _role("technical", "footwork_walkthrough", support_kind="technical_footwork")
    assert _microdose_host_roles(_week(insert)) == []


def test_a_hard_suppressed_role_is_not_a_host():
    suppressed = _role("strength", governance={"hard_suppression_reasons": ["high_fatigue"]})
    assert _microdose_host_roles(_week(suppressed)) == []


def test_strength_session_is_preferred_over_technical_and_conditioning():
    week = _week(
        _role("conditioning", "aerobic_base_day"),
        _role("technical", "technical_day"),
        _role("strength", "primary_strength_day"),
    )
    assert [r["category"] for r in _microdose_host_roles(week)] == [
        "strength",
        "technical",
        "conditioning",
    ]


def test_light_combat_technical_day_can_host():
    week = _week(_role("technical", "light_technical_combat_day"))
    assert [r["role_key"] for r in _microdose_host_roles(week)] == [
        "light_technical_combat_day"
    ]


def test_a_host_that_already_carries_a_microdose_is_not_reused():
    """Idempotence: a second pass cannot stack a second copy on the same host."""
    week = _week(_role("strength", priority_microdose={"goal": "power", "sets": 2, "intents": ["ballistic_power"]}))
    assert _microdose_host_roles(week) == []


def test_hosts_are_filtered_not_invented():
    """The floor never creates a session; with no legal host it yields nothing."""
    week = _week(
        _role("sparring", "hard_sparring_day"),
        _role("recovery", "recovery_reset_day"),
    )
    assert _microdose_host_roles(week) == []


# ---------------------------------------------------------------------------
# The attachment itself, end to end through _attach_goal_microdose
# ---------------------------------------------------------------------------


def _brief(*, phase="GPP", roles=None, days=30, sport="boxing"):
    return {
        "athlete_snapshot": {
            "sport": sport,
            "days_until_fight": days,
            "training_frequency": 4,
            "key_goals": ["power"],
            "primary_goal": "power",
            "weak_areas": ["footwork"],
            "primary_weak_area": "footwork",
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": phase,
                    "calendar_days": [
                        {"weekday": "monday", "d_day": 26},
                        {"weekday": "wednesday", "d_day": 24},
                    ],
                    "session_roles": list(roles or []),
                }
            ]
        },
        "candidate_pools": {},
    }


_POWER_ENTRY = {
    "goal": "power",
    "priority": "primary",
    "state": "build",
    "required_intent": "ballistic_power",
    "evidence": [],
}


def _technical_host():
    return {
        "category": "technical",
        "role_key": "light_technical_combat_day",
        "scheduled_day_hint": "Monday",
        "session_index": 1,
    }


def _sparring_role():
    return {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "scheduled_day_hint": "Monday",
        "session_index": 1,
    }


def _attach(brief, entry=None):
    from fightcamp.goal_preservation import _attach_goal_microdose

    return _attach_goal_microdose(brief, 0, entry or _POWER_ENTRY)


def test_zero_power_week_with_a_compatible_technical_day_gets_one_exposure():
    brief = _brief(roles=[_technical_host()])
    audit = _attach(brief)
    assert audit["result"] == "microdose_attached"
    assert audit["goal"] == "power"
    assert audit["role_key"] == "light_technical_combat_day"


def test_the_attachment_creates_no_new_session():
    brief = _brief(roles=[_technical_host()])
    _attach(brief)
    week = brief["weekly_role_map"]["weeks"][0]
    assert len(week["session_roles"]) == 1
    host = week["session_roles"][0]
    # The host keeps its declared identity; the microdose is subordinate to it.
    assert host["role_key"] == "light_technical_combat_day"
    assert host["category"] == "technical"
    assert host["priority_microdose"]["name"] == "Med-Ball Rotational Throw"


def test_running_the_pass_twice_does_not_add_a_second_copy():
    brief = _brief(roles=[_technical_host()])
    _attach(brief)
    again = _attach(brief)
    assert again["result"] == "floor_already_met"
    host = brief["weekly_role_map"]["weeks"][0]["session_roles"][0]
    assert isinstance(host["priority_microdose"], dict)


def test_a_week_of_only_hard_sparring_gets_no_forced_exposure():
    brief = _brief(roles=[_sparring_role()])
    audit = _attach(brief)
    assert audit["result"] == "floor_no_safe_host"
    assert audit["reason_codes"] == ["no_compatible_existing_session"]
    assert "priority_microdose" not in brief["weekly_role_map"]["weeks"][0]["session_roles"][0]


def test_taper_gets_no_developmental_floor():
    brief = _brief(phase="TAPER", roles=[_technical_host()])
    audit = _attach(brief)
    assert audit["result"] == "floor_not_applied"
    assert audit["reason_codes"] == ["taper_no_developmental_floor"]
    assert "priority_microdose" not in brief["weekly_role_map"]["weeks"][0]["session_roles"][0]


def test_fight_week_tail_days_cannot_host_development():
    """Hosts inside the D-13 tail are skipped by the established cutoff."""
    brief = _brief(roles=[_technical_host()], days=12)
    week = brief["weekly_role_map"]["weeks"][0]
    week["calendar_days"] = [{"weekday": "monday", "d_day": 10}]
    assert _attach(brief)["result"] == "floor_no_safe_host"


def test_conditioning_is_not_floor_eligible():
    """The conditioning workload-envelope gate stays the only conditioning
    authority; this tier must never add conditioning volume."""
    entry = {
        "goal": "conditioning",
        "priority": "primary",
        "state": "build",
        "required_intent": "energy_system_training",
        "evidence": [],
    }
    assert _attach(_brief(roles=[_technical_host()]), entry) is None


def test_a_maintenance_obligation_does_not_claim_a_weekly_floor():
    """Secondary/limited goals keep their 14-day window rather than a hard
    weekly floor."""
    assert _attach(_brief(roles=[_technical_host()]), dict(_POWER_ENTRY, state="maintain")) is None


@pytest.mark.parametrize("sport", ["boxing", "mma", "muay_thai", "bjj"])
def test_the_floor_is_not_sport_specific(sport):
    brief = _brief(roles=[_technical_host()], sport=sport)
    assert _attach(brief)["result"] == "microdose_attached"


def test_an_intentionally_unused_day_is_never_used_as_a_host():
    brief = _brief(roles=[_technical_host()])
    brief["weekly_role_map"]["weeks"][0]["intentionally_unused_days"] = [{"day": "monday"}]
    assert _attach(brief)["result"] == "floor_no_safe_host"


# ---------------------------------------------------------------------------
# Interaction with recovered structured-dose recognition
# ---------------------------------------------------------------------------


def _speed_entry():
    return {
        "goal": "speed",
        "priority": "primary",
        "state": "build",
        "required_intent": "speed_quality",
        "evidence": [],
    }


def _alactic_speed_role(*, structured: bool):
    """Repro B's role: legitimate 8 x 5 sec / 60 sec alactic speed work."""
    assignment = {
        "slot_id": "spp-alactic-1",
        "name": "Backstep Counter Reset",
        "effective_prescription": "8 x 5 sec / 60 sec rest",
        "effective_rounds": 8,
    }
    if structured:
        assignment.update({"work_sec": 5.0, "rest_sec": 60.0, "rounds": 8.0})
    return {
        "category": "conditioning",
        "role_key": "alactic_speed_day",
        "preferred_system": "alactic",
        "scheduled_day_hint": "Monday",
        "session_index": 1,
        "selected_exercise_assignments": [assignment],
    }


def _brief_with_pool(role):
    brief = _brief(roles=[role])
    brief["candidate_pools"] = {
        "GPP": {
            "conditioning_slots": [
                {
                    "slot_id": "spp-alactic-1",
                    "session_index": 1,
                    "selected": {
                        "name": "Backstep Counter Reset",
                        "system": "ATP-PCr",
                        "prescription": "8 x 5 sec / 60 sec rest",
                        "selection_metadata": {},
                    },
                }
            ]
        }
    }
    return brief


def test_recognised_speed_work_makes_the_floor_a_no_op():
    """Repro B's whole point: once the structured dose survives, the existing
    alactic speed day satisfies the weekly floor and nothing is added."""
    brief = _brief_with_pool(_alactic_speed_role(structured=True))
    audit = _attach(brief, _speed_entry())
    assert audit["result"] == "floor_already_met"
    assert audit["reason_codes"] == ["existing_weekly_exposure"]
    assert "priority_microdose" not in brief["weekly_role_map"]["weeks"][0]["session_roles"][0]


def test_the_floor_does_not_duplicate_legitimate_existing_speed_work():
    brief = _brief_with_pool(_alactic_speed_role(structured=True))
    _attach(brief, _speed_entry())
    _attach(brief, _speed_entry())
    roles = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    assert len(roles) == 1
    assert all("priority_microdose" not in role for role in roles)
