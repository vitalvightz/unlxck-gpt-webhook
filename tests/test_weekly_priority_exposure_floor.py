"""Weekly priority exposure floor - the microdose tier of goal repair.

`goal_preservation` already owns a weekly floor (`_requirements`: one build
exposure per development week) and a deterministic repair pass
(`_restore_goal_roles`). That pass could only restore a WHOLE role from the
week's `goal_repair_candidates`, so when the session or category cap blocked it
a primary goal went cold for the entire build week.

`_attach_goal_microdose` is the fallback tier. It adds no session, no training
day and no frequency, and it never authors an exercise or a dose: the only
candidates are the phase's Stage 1 strength slots (already injury-, equipment-
and restriction-filtered), the host must be an existing strength session with
composed membership and spare composed capacity, the dose comes from the
canonical prescription resolver, and the host's measured load may not rise.
When nothing qualifies the gap is recorded as ``floor_no_safe_candidate``.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from fightcamp import goal_preservation
from fightcamp.goal_preservation import (
    _MICRODOSE_FORBIDDEN_HOST_CATEGORIES,
    _MICRODOSE_GOAL_INTENTS,
    _microdose_host_roles,
    _microdose_stimuli,
)


def _role(category, role_key="r", **kw):
    role = {"category": category, "role_key": role_key}
    role.update(kw)
    return role


def _week(*roles, phase="GPP"):
    return {"week_index": 1, "phase": phase, "session_roles": list(roles)}


def _member(slot_id="gpp_a", name="DB Bench Press"):
    # The shape session_composition.assignment_from_slot writes for _ANCHOR.
    return {"slot_id": slot_id, "name": name, "slot_group": "strength_slots", "source_phase": "GPP",
            "base_prescription": "3x5 @ RPE 7"}


def _slot(slot_id, name, quality_class, prescription, *, tags=(), mech=(), equipment="", session_index=1):
    return {
        "slot_id": slot_id,
        "session_index": session_index,
        "quality_class": quality_class,
        "selected": {
            "name": name,
            "prescription": prescription,
            "quality_class": quality_class,
            "tags": list(tags),
            "mechanical_risk_tags": list(mech),
            "equipment": equipment,
        },
    }


_ANCHOR = _slot("gpp_a", "DB Bench Press", "anchor_loaded", "3x5 @ RPE 7", tags=["strength"], equipment="dumbbells")
_POWER = _slot("gpp_b", "Med Ball Scoop Toss", "anchor_power", "4x3 @ RPE 7, full rest",
               tags=["power", "explosive"], session_index=2)
_SPEED = _slot("gpp_c", "Sprint Start Drill", "anchor_power", "4x2 @ RPE 7, full rest",
               tags=["power", "speed"], session_index=2)


# ---------------------------------------------------------------------------
# What the tier may claim
# ---------------------------------------------------------------------------


def test_the_tier_authors_no_exercise_of_its_own():
    """F05/F06: every former hard-coded touch is gone from the module."""
    source = inspect.getsource(goal_preservation)
    for invented in (
        "Reactive Start Burst",
        "Loaded Carry Touch",
        "Med-Ball Rotational Throw",
        "Reactive Footwork Walkthrough",
        "Targeted Mobility Touch",
    ):
        assert invented not in source
    assert not hasattr(goal_preservation, "_MICRODOSE_SPECS")
    assert not hasattr(goal_preservation, "_sync_microdose_membership")


def test_only_goals_the_strength_pool_can_evidence_are_floor_goals():
    assert _MICRODOSE_GOAL_INTENTS == {
        "power": "ballistic_power",
        "speed": "speed_quality",
        "strength": "meaningful_strength",
        "trunk_strength": "trunk_training",
    }
    for goal in ("conditioning", "recovery", "weight_cut", "footwork", "mobility"):
        assert goal not in _MICRODOSE_GOAL_INTENTS


def test_floor_intents_match_the_coverage_ledger_vocabulary():
    for goal, intent in _MICRODOSE_GOAL_INTENTS.items():
        assert goal_preservation.INTENTS[goal] == intent


def test_a_legacy_spec_microdose_still_reads_as_evidence():
    """Briefs saved before this change keep their recorded witness."""
    role = _role("strength", priority_microdose={
        "goal": "power", "name": "Legacy Touch", "prescription": "2 x 3/side @ RPE 7",
        "sets": 2, "intents": ["ballistic_power"]})
    stimulus = _microdose_stimuli(role)[0]
    assert stimulus["intents"] == ["ballistic_power"]
    # A spec-authored touch never passed the bank, resolver or load checks
    # (F07): it can keep a goal warm, never certify development.
    assert stimulus["development_capable"] is False


def test_a_single_set_legacy_touch_is_not_development():
    role = _role("strength", priority_microdose={"goal": "power", "sets": 1, "intents": ["ballistic_power"]})
    assert _microdose_stimuli(role)[0]["development_capable"] is False


def test_a_pool_sourced_microdose_is_not_counted_twice():
    """Its evidence comes from the ordinary strength path with the resolver's dose."""
    role = _role("strength", priority_microdose={
        "goal": "power", "sets": 4, "intents": ["ballistic_power"], "source": "phase_pool"})
    assert _microdose_stimuli(role) == []


def test_a_role_without_a_microdose_produces_no_evidence():
    assert _microdose_stimuli(_role("strength")) == []


# ---------------------------------------------------------------------------
# Host selection: where a microdose may and may not attach
# ---------------------------------------------------------------------------


def _strength_host(**kw):
    return _role("strength", "primary_strength_day", selected_exercise_assignments=[_member()], **kw)


def test_hard_sparring_is_never_a_host():
    assert "sparring" in _MICRODOSE_FORBIDDEN_HOST_CATEGORIES
    assert _microdose_host_roles(_week(_role("sparring", "hard_sparring_day"))) == []


def test_recovery_only_day_stays_recovery_only():
    assert _microdose_host_roles(_week(_role("recovery", "recovery_reset_day"))) == []


def test_fight_day_is_never_a_host():
    assert _microdose_host_roles(_week(_role("fight_day", "fight_day_protocol"))) == []


def test_tactical_watch_does_not_create_physical_capacity():
    tactical = _role("technical", "tactical_watch", support_insert_category="tactical")
    assert _microdose_host_roles(_week(tactical)) == []


def test_a_support_insert_is_not_a_session():
    insert = _role("strength", "footwork_walkthrough", support_kind="technical_footwork",
                   selected_exercise_assignments=[_member()])
    assert _microdose_host_roles(_week(insert)) == []


def test_a_hard_suppressed_role_is_not_a_host():
    suppressed = _strength_host(governance={"hard_suppression_reasons": ["high_fatigue"]})
    assert _microdose_host_roles(_week(suppressed)) == []


def test_only_strength_sessions_host_because_only_they_can_be_priced():
    """A strength-slot member on a technical or conditioning session would have
    no dose authority; the resolver prices strength roles only."""
    week = _week(
        _role("conditioning", "aerobic_base_day", selected_exercise_assignments=[_member()]),
        _role("technical", "light_technical_combat_day"),
        _strength_host(),
    )
    assert [r["category"] for r in _microdose_host_roles(week)] == ["strength"]


@pytest.mark.parametrize("assignments", [None, [], [{"name": "Legacy", "slot_group": "priority_microdose"}]])
def test_an_empty_session_is_never_a_host(assignments):
    host = _role("strength", "primary_strength_day")
    if assignments is not None:
        host["selected_exercise_assignments"] = assignments
    assert _microdose_host_roles(_week(host)) == []


def test_a_host_that_already_carries_a_microdose_is_not_reused():
    week = _week(_strength_host(priority_microdose={"goal": "power", "sets": 2, "intents": ["ballistic_power"]}))
    assert _microdose_host_roles(week) == []


def test_a_converted_hard_spar_day_is_never_a_host_even_if_recategorised():
    converted = _role("strength", "hard_sparring_day", preferred_pool="declared_hard_sparring_days",
                      selected_exercise_assignments=[_member()])
    assert _microdose_host_roles(_week(converted)) == []


def test_provenance_is_detected_from_role_key_pool_or_marker():
    from fightcamp.goal_preservation import _carries_hard_sparring_provenance

    assert _carries_hard_sparring_provenance({"role_key": "hard_sparring_day"})
    assert _carries_hard_sparring_provenance({"preferred_pool": "declared_hard_sparring_days"})
    assert _carries_hard_sparring_provenance({"declared_hard_sparring": True})
    assert not _carries_hard_sparring_provenance({"role_key": "light_technical_combat_day"})


# ---------------------------------------------------------------------------
# The attachment itself, end to end through _attach_goal_microdose
# ---------------------------------------------------------------------------


def _pool_host(cap=3, members=None, **kw):
    host = {
        "category": "strength",
        "role_key": "primary_strength_day",
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": "D-26",
        "session_index": 1,
        "strength_session_index": 1,
        "strength_composition_policy": {"effective_exercise_cap": cap},
        "selected_exercise_assignments": list(members if members is not None else [_member()]),
    }
    host.update(kw)
    return host


def _brief(*, phase="GPP", roles=None, days=30, sport="boxing", slots=None, goals=("power",)):
    return {
        "athlete_snapshot": {
            "sport": sport,
            "days_until_fight": days,
            "training_frequency": 4,
            "key_goals": list(goals),
            "primary_goal": goals[0],
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
                    "session_roles": list(roles if roles is not None else [_pool_host()]),
                }
            ]
        },
        "candidate_pools": {phase: {"strength_slots": list(slots if slots is not None else [_ANCHOR, _POWER])}},
    }


_POWER_ENTRY = {
    "goal": "power",
    "priority": "primary",
    "state": "build",
    "required_intent": "ballistic_power",
    "evidence": [],
}
_SPEED_ENTRY = dict(_POWER_ENTRY, goal="speed", required_intent="speed_quality")
_FOOTWORK_ENTRY = {
    "goal": "footwork",
    "priority": "primary_weakness",
    "state": "build",
    "required_intent": "footwork_practice",
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


def _host(brief):
    return brief["weekly_role_map"]["weeks"][0]["session_roles"][0]


def test_the_microdose_is_an_already_selected_pool_exercise():
    brief = _brief()
    audit = _attach(brief)
    assert audit["result"] == "microdose_attached"
    assert audit["exercise"] == "Med Ball Scoop Toss"
    host = _host(brief)
    assert host["priority_microdose"]["name"] == "Med Ball Scoop Toss"
    assert host["priority_microdose"]["slot_id"] == "gpp_b"
    assert host["priority_microdose"]["source"] == "phase_pool"


def test_the_dose_is_the_resolvers_not_the_tiers():
    brief = _brief()
    _attach(brief)
    host = _host(brief)
    priced = next(p for p in host["effective_strength_prescriptions"] if p["name"] == "Med Ball Scoop Toss")
    assert priced["dose_authority"] != "weekly_priority_exposure_floor"
    assert host["priority_microdose"]["prescription"] == priced["effective_prescription"]
    assert host["priority_microdose"]["dose_authority"] == priced["dose_authority"]


def test_the_member_joins_closed_membership_through_the_normal_assignment_shape():
    brief = _brief()
    _attach(brief)
    host = _host(brief)
    member = next(a for a in host["selected_exercise_assignments"] if a["name"] == "Med Ball Scoop Toss")
    assert member["slot_group"] == "strength_slots"
    assert member["source_phase"] == "GPP"
    assert member["priority_microdose_goal"] == "power"
    assert "Med Ball Scoop Toss" in host["effective_strength_envelope"]["allowed_exercise_names"]


def test_the_witness_comes_from_the_ordinary_strength_evidence_path():
    from fightcamp.goal_preservation import collect_goal_evidence

    brief = _brief()
    _attach(brief)
    witness = [e for e in collect_goal_evidence(brief) if "ballistic_power" in e["intents"]]
    assert len(witness) == 1
    assert witness[0]["name"] == "Med Ball Scoop Toss"
    assert witness[0]["quality_class"] == "anchor_power"


def test_the_attachment_creates_no_new_session():
    brief = _brief()
    _attach(brief)
    week = brief["weekly_role_map"]["weeks"][0]
    assert len(week["session_roles"]) == 1
    assert _host(brief)["role_key"] == "primary_strength_day"


def test_running_the_pass_twice_does_not_add_a_second_copy():
    brief = _brief()
    _attach(brief)
    again = _attach(brief)
    assert again["result"] == "floor_already_met"
    names = [a["name"] for a in _host(brief)["selected_exercise_assignments"]]
    assert names.count("Med Ball Scoop Toss") == 1


def test_no_pool_candidate_records_floor_no_safe_candidate():
    """Safety outranks coverage: nothing is manufactured to fill the week."""
    brief = _brief(slots=[_ANCHOR])
    audit = _attach(brief)
    assert audit["result"] == "floor_no_safe_candidate"
    assert audit["reason_codes"] == ["no_eligible_phase_pool_candidate"]
    assert "priority_microdose" not in _host(brief)
    assert [a["name"] for a in _host(brief)["selected_exercise_assignments"]] == ["DB Bench Press"]


def test_a_candidate_blocked_by_a_restriction_is_never_used():
    blocked = _slot("gpp_b", "Med Ball Scoop Toss", "anchor_power", "4x3 @ RPE 7", tags=["power"], session_index=2)
    blocked["selected"]["restriction_hits"] = 1
    brief = _brief(slots=[_ANCHOR, blocked])
    assert _attach(brief)["result"] == "floor_no_safe_candidate"
    assert "priority_microdose" not in _host(brief)


def test_a_full_session_keeps_its_composed_cap():
    brief = _brief(roles=[_pool_host(cap=1)])
    audit = _attach(brief)
    assert audit["result"] == "floor_no_safe_candidate"
    assert audit["reason_codes"] == ["host_at_composed_exercise_cap"]


def test_a_candidate_that_raises_the_hosts_measured_load_is_refused():
    landing = _slot("gpp_b", "Depth Jump", "anchor_power", "4x3 @ RPE 7",
                    tags=["power", "explosive"], mech=["mech_landing_impact", "mech_lower_jump"], session_index=2)
    brief = _brief(slots=[_ANCHOR, landing])
    audit = _attach(brief)
    assert audit["result"] == "floor_no_safe_candidate"
    assert "host_realised_load_would_increase" in audit["reason_codes"]
    assert "priority_microdose" not in _host(brief)


def test_an_empty_strength_session_is_not_filled():
    brief = _brief(roles=[_pool_host(members=[])])
    audit = _attach(brief)
    assert audit["result"] == "floor_no_safe_host"
    assert _host(brief)["selected_exercise_assignments"] == []


def test_a_technical_or_conditioning_day_gets_nothing():
    for role in (_technical_host(), _role("conditioning", "fight_pace_repeatability_day",
                                          scheduled_day_hint="Monday", selected_exercise_assignments=[])):
        brief = _brief(roles=[role])
        assert _attach(brief)["result"] == "floor_no_safe_host"
        assert "priority_microdose" not in _host(brief)


def test_a_week_of_only_hard_sparring_gets_no_forced_exposure():
    brief = _brief(roles=[_sparring_role()])
    audit = _attach(brief)
    assert audit["result"] == "floor_no_safe_host"
    assert audit["reason_codes"] == ["no_compatible_existing_session"]
    assert "priority_microdose" not in _host(brief)


def test_taper_gets_no_developmental_floor():
    brief = _brief(phase="TAPER")
    audit = _attach(brief)
    assert audit["result"] == "floor_not_applied"
    assert audit["reason_codes"] == ["taper_no_developmental_floor"]


def test_fight_week_tail_days_cannot_host_development():
    brief = _brief(roles=[_pool_host(scheduled_countdown_label="D-10")], days=12)
    brief["weekly_role_map"]["weeks"][0]["calendar_days"] = [{"weekday": "monday", "d_day": 10}]
    assert _attach(brief)["result"] == "floor_no_safe_host"


def test_conditioning_is_not_floor_eligible():
    entry = dict(_POWER_ENTRY, goal="conditioning", required_intent="energy_system_training")
    assert _attach(_brief(), entry) is None


def test_a_maintenance_obligation_does_not_claim_a_weekly_floor():
    assert _attach(_brief(), dict(_POWER_ENTRY, state="maintain")) is None


@pytest.mark.parametrize("sport", ["boxing", "mma", "muay_thai", "bjj"])
def test_the_floor_is_not_sport_specific(sport):
    assert _attach(_brief(sport=sport))["result"] == "microdose_attached"


def test_an_intentionally_unused_day_is_never_used_as_a_host():
    brief = _brief()
    brief["weekly_role_map"]["weeks"][0]["intentionally_unused_days"] = [{"day": "monday"}]
    assert _attach(brief)["result"] == "floor_no_safe_host"


# ---------------------------------------------------------------------------
# Interaction with recovered structured-dose recognition
# ---------------------------------------------------------------------------


def _alactic_speed_role(*, structured: bool):
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


def _brief_with_conditioning_pool(role):
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
    brief = _brief_with_conditioning_pool(_alactic_speed_role(structured=True))
    audit = _attach(brief, _SPEED_ENTRY)
    assert audit["result"] == "floor_already_met"
    assert audit["reason_codes"] == ["existing_weekly_exposure"]
    assert "priority_microdose" not in _host(brief)


def test_the_floor_does_not_duplicate_legitimate_existing_speed_work():
    brief = _brief_with_conditioning_pool(_alactic_speed_role(structured=True))
    _attach(brief, _SPEED_ENTRY)
    _attach(brief, _SPEED_ENTRY)
    roles = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    assert len(roles) == 1
    assert all("priority_microdose" not in role for role in roles)


# ---------------------------------------------------------------------------
# The fallback must run whenever the full repair fails - for ANY reason
# ---------------------------------------------------------------------------


def _blocked_week_brief(*, block="authority_preserved", hosts=None):
    """The only repair candidate is blocked; an existing strength session remains."""
    strength_host = _pool_host(role_key="neural_plus_strength_day", session_index=1)
    spar = {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "preferred_pool": "declared_hard_sparring_days",
        "scheduled_day_hint": "Thursday",
        "session_index": 2,
    }
    week = {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 26},
            {"weekday": "thursday", "d_day": 23},
        ],
        "declared_training_days": ["monday", "thursday"],
        "session_roles": list(hosts if hosts is not None else [strength_host, spar]),
        "goal_repair_candidates": [
            {"category": "strength", "role_key": "primary_strength_day", "strength_session_index": 1}
        ],
    }
    if block == "authority_preserved":
        week["suppressed_roles"] = [
            {
                "role_key": "primary_strength_day",
                "governance": {"hard_suppression_reasons": ["two_hard_spar_days"]},
            }
        ]
    elif block == "no_candidates":
        week["goal_repair_candidates"] = []
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
            {**_ANCHOR, "selected": dict(_ANCHOR["selected"])},
            {**_POWER, "selected": dict(_POWER["selected"])},
        ]}},
    }


def _blocked_fixture(**kw):
    brief = _blocked_week_brief(**kw)
    for role in brief["weekly_role_map"]["weeks"][0]["session_roles"]:
        for member in role.get("selected_exercise_assignments") or []:
            member["source_phase"] = "SPP"
    return brief


def _repair(brief):
    from fightcamp.goal_preservation import _restore_goal_roles

    return _restore_goal_roles(brief, _POWER_ENTRY)


def _results(audit):
    return [entry.get("result") for entry in audit]


def test_authority_preserved_still_reaches_the_microdose_fallback():
    brief = _blocked_fixture()
    audit = _repair(brief)
    assert "authority_preserved" in _results(audit)
    assert "microdose_attached" in _results(audit)
    host = brief["weekly_role_map"]["weeks"][0]["session_roles"][0]
    assert host["role_key"] == "neural_plus_strength_day"
    assert host["priority_microdose"]["goal"] == "power"


def test_a_week_with_no_repair_candidates_still_reaches_the_fallback():
    assert "microdose_attached" in _results(_repair(_blocked_fixture(block="no_candidates")))


def test_the_fallback_is_not_special_cased_to_a_reason_code():
    source = inspect.getsource(goal_preservation._restore_goal_roles)
    fallback = source.split("floor_audit = ")[0].rsplit("for candidate", 1)[-1]
    assert "two_hard_spar" not in fallback


def test_the_blocked_week_gains_no_session_and_no_training_day():
    brief = _blocked_fixture()
    before = len(brief["weekly_role_map"]["weeks"][0]["session_roles"])
    _repair(brief)
    week = brief["weekly_role_map"]["weeks"][0]
    assert len(week["session_roles"]) == before
    assert week["declared_training_days"] == ["monday", "thursday"]


def test_hard_sparring_days_are_untouched_by_the_repair():
    brief = _blocked_fixture()
    _repair(brief)
    spar = [r for r in brief["weekly_role_map"]["weeks"][0]["session_roles"] if r["category"] == "sparring"]
    assert spar and all("priority_microdose" not in role for role in spar)


def test_the_blocked_week_repair_is_idempotent():
    brief = _blocked_fixture()
    _repair(brief)
    second = _repair(brief)
    assert second == []  # A satisfied cadence window needs no further trials.
    roles = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    assert sum(1 for role in roles if role.get("priority_microdose")) == 1


def test_a_blocked_week_with_no_compatible_host_records_an_honest_reason():
    only_sparring = [
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "preferred_pool": "declared_hard_sparring_days",
            "scheduled_day_hint": "Thursday",
            "session_index": 1,
        }
    ]
    audit = _repair(_blocked_fixture(hosts=only_sparring))
    assert "floor_no_safe_host" in _results(audit)
    assert "microdose_attached" not in _results(audit)


def test_neural_microdose_already_coexists_with_declared_light_combat():
    """The canonical collision policy is unchanged by this work."""
    from fightcamp.combat_load_policy import _LIGHT_COMBAT_COEXIST_LOADS, LoadClass

    assert LoadClass.NEURAL_MICRODOSE in _LIGHT_COMBAT_COEXIST_LOADS
    assert LoadClass.MEANINGFUL_STRENGTH not in _LIGHT_COMBAT_COEXIST_LOADS
    assert LoadClass.HARD_CONTACT not in _LIGHT_COMBAT_COEXIST_LOADS


# ---------------------------------------------------------------------------
# The primary weakness is the floor's second build obligation
#
# It reuses this same machinery - required_intent, coverage windows, evidence
# recognition, whole-role repair, microdose fallback - rather than a second,
# competing weakness planner.
# ---------------------------------------------------------------------------


def _athlete(**kw):
    athlete = {
        "key_goals": ["power"],
        "primary_goal": "power",
        "weak_areas": ["footwork"],
        "primary_weak_area": "footwork",
    }
    athlete.update(kw)
    return athlete


_FOOTWORK_ENTRY = {
    "goal": "footwork",
    "priority": "primary_weakness",
    "state": "build",
    "required_intent": "footwork_practice",
    "evidence": [],
}


def test_primary_weakness_is_an_obligation_ranked_under_the_primary_goal():
    from fightcamp.goal_preservation import selected_goals

    assert selected_goals(_athlete(key_goals=["power", "speed"])) == [
        ("power", "primary"),
        ("footwork", "primary_weakness"),
        ("speed", "secondary"),
    ]


def test_a_target_selected_as_both_goal_and_weakness_is_one_obligation():
    """The profile already merges such a collision into one canonical priority
    target; one exposure satisfies both, and it must not be demanded twice."""
    from fightcamp.goal_preservation import selected_goals

    assert selected_goals(_athlete(weak_areas=["power"], primary_weak_area="power")) == [
        ("power", "primary")
    ]


def test_a_weakness_also_named_among_the_goals_is_promoted_not_duplicated():
    from fightcamp.goal_preservation import selected_goals

    assert selected_goals(_athlete(key_goals=["power", "footwork"])) == [
        ("power", "primary"),
        ("footwork", "primary_weakness"),
    ]


def test_selection_vocabulary_is_projected_onto_the_adaptation_family():
    from fightcamp.goal_preservation import selected_goals

    assert ("speed", "primary_weakness") in selected_goals(
        _athlete(weak_areas=["reactive"], primary_weak_area="reactive")
    )


def test_an_unrecognised_weak_area_creates_no_obligation():
    """Weak areas are free text at intake. A target with no required intent,
    role match or evidence path could never be discharged, so admitting it
    would be a permanent blocking obligation rather than a floor."""
    from fightcamp.goal_preservation import selected_goals

    assert selected_goals(_athlete(weak_areas=["chin"], primary_weak_area="chin")) == [
        ("power", "primary")
    ]


def test_the_weakness_obligation_is_a_build_obligation():
    from fightcamp.goal_preservation import classify_goal_preservation

    entry = next(e for e in classify_goal_preservation(_athlete()) if e["goal"] == "footwork")
    assert entry["state"] == "build"
    assert entry["required_intent"] == "footwork_practice"
    assert entry["reason_codes"] == ["primary_weakness"]


def test_a_cold_primary_weakness_with_no_pool_family_is_recorded_not_invented():
    """Footwork has no strength-pool candidate; the gap is reported honestly."""
    brief = _brief()
    audit = _attach(brief, _FOOTWORK_ENTRY)
    assert audit["result"] == "floor_no_safe_candidate"
    assert audit["goal"] == "footwork"
    assert audit["reason_codes"] == ["no_phase_pool_candidate_for_goal"]
    assert "priority_microdose" not in _host(brief)


def test_when_two_goals_compete_for_the_only_host_the_first_keeps_it():
    """Not a forced second touch: the later goal records that the week's only
    safe capacity was already spent."""
    brief = _brief(slots=[_ANCHOR, _POWER, _SPEED])
    assert _attach(brief)["result"] == "microdose_attached"
    audit = _attach(brief, _SPEED_ENTRY)
    assert audit["result"] == "floor_no_safe_capacity"
    assert audit["reason_codes"] == ["priority_capacity_spent"]
    assert audit["held_by"] == ["power"]
    assert _host(brief)["priority_microdose"]["goal"] == "power"


# ---------------------------------------------------------------------------
# Every official intake weak area is serviced deliberately
#
# `WEAK_AREA_OPTIONS` in web/lib/intake-options.ts is the source of truth. A
# weak area must either be an obligation this floor carries or a documented
# delegation to a canonical subsystem - never a value that quietly falls off
# the end of a lookup. The options are read from the intake file itself so a
# new choice cannot be added on the web side without failing here.
# ---------------------------------------------------------------------------

_OFFICIAL_WEAK_AREAS = {
    "gas_tank",
    "strength",
    "power",
    "speed",
    "footwork",
    "balance",
    "mobility",
    "coordination",
    "trunk_strength",
}


def _intake_weak_area_options():
    source = (Path(__file__).parents[1] / "web/lib/intake-options.ts").read_text()
    block = re.search(r"WEAK_AREA_OPTIONS[^=]*=\s*\[(.*?)\];", source, re.S)
    assert block, "WEAK_AREA_OPTIONS not found in web/lib/intake-options.ts"
    return re.findall(r'value:\s*"([^"]+)"', block.group(1))


def _disposition(weak_area):
    from fightcamp.goal_preservation import primary_weakness_disposition

    return primary_weakness_disposition(
        _athlete(weak_areas=[weak_area], primary_weak_area=weak_area)
    )


def test_the_official_weak_area_list_has_not_drifted():
    assert set(_intake_weak_area_options()) == _OFFICIAL_WEAK_AREAS


@pytest.mark.parametrize("weak_area", sorted(_OFFICIAL_WEAK_AREAS))
def test_every_official_weak_area_resolves_deliberately(weak_area):
    """Serviced by the weekly floor, or delegated to a named subsystem. Never
    ignored, and never left to an unrecognised-free-text fallback."""
    disposition = _disposition(weak_area)
    assert disposition["resolution"] in {"weekly_floor", "delegated"}, disposition
    if disposition["resolution"] == "weekly_floor":
        from fightcamp.goal_preservation import INTENTS

        assert INTENTS[disposition["target"]] == disposition["required_intent"]
    else:
        assert disposition["subsystem"]


@pytest.mark.parametrize(
    "weak_area,target",
    [
        ("strength", "strength"),
        ("power", "power"),
        ("speed", "speed"),
        ("footwork", "footwork"),
        ("mobility", "mobility"),
        ("gas_tank", "conditioning"),
    ],
)
def test_floor_serviced_weak_areas_become_build_obligations(weak_area, target):
    from fightcamp.goal_preservation import classify_goal_preservation

    entries = classify_goal_preservation(
        _athlete(key_goals=["skill_refinement"], primary_goal="skill_refinement",
                 weak_areas=[weak_area], primary_weak_area=weak_area)
    )
    entry = next(e for e in entries if e["goal"] == target)
    assert (entry["priority"], entry["state"]) == ("primary_weakness", "build")


def test_gas_tank_is_a_conditioning_obligation_the_floor_never_microdoses():
    """The Gas Tank preset pairs a conditioning goal with a gas_tank weakness,
    so gas_tank must enter the obligation set. Expanding it with a generic
    microdose would re-open the conditioning spillover the workload-envelope
    gate closed, so the fallback tier declines it and the conditioning
    architecture keeps sole authority over conditioning volume."""
    assert _disposition("gas_tank")["target"] == "conditioning"
    assert "conditioning" not in _MICRODOSE_GOAL_INTENTS
    entry = {
        "goal": "conditioning",
        "priority": "primary_weakness",
        "state": "build",
        "required_intent": "energy_system_training",
        "evidence": [],
    }
    assert _attach(_brief(roles=[_technical_host()]), entry) is None


@pytest.mark.parametrize("weak_area", ["balance", "coordination"])
def test_balance_and_coordination_really_do_reach_their_subsystem(weak_area):
    """The delegation is only honest if the named subsystem actually triggers
    on this same weak-area selection."""
    from fightcamp.coordination_support_library import has_coordination_target

    assert _disposition(weak_area)["subsystem"] == "coordination_support_library"
    assert has_coordination_target(_athlete(weak_areas=[weak_area], primary_weak_area=weak_area))


def test_trunk_strength_really_does_reach_its_subsystem():
    from fightcamp.session_composition import _trunk_strength_selected

    assert _disposition("trunk_strength")["subsystem"] == "session_composition.trunk_support"
    assert _trunk_strength_selected(
        _athlete(weak_areas=["trunk_strength"], primary_weak_area="trunk_strength")
    )


def test_the_option_label_spelling_resolves_the_same_way():
    """Some surfaces submit the option label rather than its value."""
    assert _disposition("Core / Trunk Strength")["resolution"] == "delegated"


def test_free_text_stays_unrecognised_and_is_reported_as_such():
    disposition = _disposition("chin")
    assert disposition["resolution"] == "unrecognised"
    assert "target" not in disposition and "subsystem" not in disposition


def test_no_selected_weak_area_is_its_own_resolution():
    from fightcamp.goal_preservation import primary_weakness_disposition

    assert primary_weakness_disposition(
        _athlete(weak_areas=[], primary_weak_area="")
    ) == {"weakness": "", "resolution": "none"}


def test_the_disposition_is_recorded_on_the_brief():
    """A delegated weak area must be auditable: without the record, "serviced
    elsewhere" and "silently dropped" look identical from the outside."""
    from fightcamp.goal_preservation import reconcile_goal_preservation

    brief = _brief(roles=[_technical_host()])
    brief["athlete_snapshot"].update(weak_areas=["balance"], primary_weak_area="balance")
    reconcile_goal_preservation(brief)
    assert brief["primary_weakness_disposition"] == {
        "weakness": "balance",
        "selected_label": "balance",
        "resolution": "delegated",
        "subsystem": "coordination_support_library",
    }


def test_the_gas_tank_preset_is_one_obligation_not_two():
    """The UI preset selects a conditioning goal AND a gas_tank weakness. Both
    resolve to the conditioning family, so they merge: one exposure satisfies
    the pair, and the athlete is not billed twice for the same adaptation."""
    from fightcamp.goal_preservation import selected_goals

    assert selected_goals(
        _athlete(key_goals=["conditioning"], primary_goal="conditioning",
                 weak_areas=["gas_tank"], primary_weak_area="gas_tank")
    ) == [("conditioning", "primary")]




# ---------------------------------------------------------------------------
# Render contract for a pool-sourced microdose
# ---------------------------------------------------------------------------

_RENDER = """## D-26 (Monday) - Strength
- DB Bench Press - 3x5 @ RPE 7
- Med Ball Scoop Toss - 4x3 @ RPE 7, full rest
"""


def test_stage2_render_checks_accept_the_rendered_pool_member():
    from fightcamp.goal_preservation import reconcile_goal_preservation
    from fightcamp.stage2_validator import (
        _goal_preservation_render_errors,
        _priority_microdose_render_errors,
    )

    brief = _brief()
    brief["athlete_snapshot"].update(weak_areas=[], primary_weak_area="")
    reconcile_goal_preservation(brief)
    power = next(e for e in brief["goal_preservation"] if e["goal"] == "power")
    assert power["evidence"][0]["name"] == "Med Ball Scoop Toss"

    codes = [e["code"] for e in _goal_preservation_render_errors(brief, _RENDER)]
    codes += [e["code"] for e in _priority_microdose_render_errors(brief, _RENDER)]
    assert codes == []
