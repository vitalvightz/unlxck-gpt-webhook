"""Step 10 — architecture closure freeze.

The staged planner migration replaced a multi-owner architecture (where
placement, payload post-processing, fillers, the renderer and the finalizer could
each independently answer "may this session exist on this day?") with a single
canonical owner per decision. These tests freeze that result so it cannot
silently drift back.

They are architecture regressions, not training-doctrine tests: they assert
*ownership* and the *canonical legality vocabulary*, and they document current
policy rather than inventing it.
"""
from __future__ import annotations

import importlib

import pytest

from fightcamp import calendar_context as cc
from fightcamp import stage2_payload_late_fight as lf
from fightcamp.calendar_integrity import (
    CalendarIntegrityError,
    apply_final_calendar_integrity,
)
from fightcamp.combat_load_policy import (
    CalendarEvent,
    CalendarLoadProfile,
    DayOccupancy,
    LoadClass,
    PlacementDirective,
    _default_occupancy,
    evaluate_candidate_at_position,
)

SCOPE = ("normal_week", 1)
HARD = CalendarLoadProfile(LoadClass.HARD_CONTACT, DayOccupancy.EXCLUSIVE_PHYSICAL)


def _profile(load_class: LoadClass) -> CalendarLoadProfile:
    return CalendarLoadProfile(load_class, _default_occupancy(load_class))


def _directive(load_class: LoadClass, position: int, events) -> PlacementDirective:
    return evaluate_candidate_at_position(
        _profile(load_class),
        candidate_position=position,
        events=events,
        candidate_scope=SCOPE,
    ).directive


# Geometry: hard contact at 0 and 4 (candidate between at 2); hard at 0
# (candidate immediately after at 1); hard at 5 (candidate immediately before at 4).
_BETWEEN = (2, [CalendarEvent(0, HARD, SCOPE), CalendarEvent(4, HARD, SCOPE)])
_AFTER = (1, [CalendarEvent(0, HARD, SCOPE)])
_BEFORE = (4, [CalendarEvent(5, HARD, SCOPE)])
_CONTEXTS = {"between": _BETWEEN, "after": _AFTER, "before": _BEFORE}

A, DP, F = PlacementDirective.ALLOW, PlacementDirective.DEPRIORITIZE, PlacementDirective.FORBID

# ---------------------------------------------------------------------------
# Part E — canonical legality matrix freeze.
# This documents the policy that exists today. It must never be edited to make a
# planner change pass: a diff here means collision doctrine moved.
# ---------------------------------------------------------------------------
_MATRIX = [
    ("between", LoadClass.OFF, A),
    ("between", LoadClass.ZERO_LOAD, A),
    ("between", LoadClass.RECOVERY_ONLY, A),
    ("between", LoadClass.LOW_LOAD_AEROBIC, A),
    ("between", LoadClass.LOW_LOAD_PHYSICAL, DP),
    ("between", LoadClass.TECHNICAL_CONTACT, DP),
    ("between", LoadClass.REDUCED_CONTACT, DP),
    ("between", LoadClass.MEANINGFUL_STRENGTH, F),
    ("between", LoadClass.MEANINGFUL_CONDITIONING, F),
    ("between", LoadClass.NEURAL_MICRODOSE, F),
    ("after", LoadClass.MEANINGFUL_STRENGTH, F),
    ("after", LoadClass.MEANINGFUL_CONDITIONING, F),
    ("after", LoadClass.NEURAL_MICRODOSE, DP),
    ("after", LoadClass.REDUCED_CONTACT, DP),
    ("after", LoadClass.TECHNICAL_CONTACT, A),
    ("after", LoadClass.RECOVERY_ONLY, A),
    ("after", LoadClass.LOW_LOAD_AEROBIC, A),
    ("after", LoadClass.LOW_LOAD_PHYSICAL, A),
    ("before", LoadClass.MEANINGFUL_STRENGTH, DP),
    ("before", LoadClass.MEANINGFUL_CONDITIONING, DP),
    ("before", LoadClass.NEURAL_MICRODOSE, DP),
    ("before", LoadClass.REDUCED_CONTACT, DP),
    ("before", LoadClass.TECHNICAL_CONTACT, A),
    ("before", LoadClass.RECOVERY_ONLY, A),
    ("before", LoadClass.LOW_LOAD_AEROBIC, A),
    ("before", LoadClass.LOW_LOAD_PHYSICAL, A),
]


@pytest.mark.parametrize("context,load_class,expected", _MATRIX)
def test_canonical_legality_matrix_is_frozen(context, load_class, expected):
    position, events = _CONTEXTS[context]
    assert _directive(load_class, position, events) is expected


def test_consecutive_effective_hard_contact_is_forbidden():
    assert _directive(LoadClass.HARD_CONTACT, 1, [CalendarEvent(0, HARD, SCOPE)]) is F


def test_same_day_exclusive_physical_on_contact_day_is_forbidden():
    # Any physical work stacked onto a day a contact occurrence already owns.
    for load_class in (
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
        LoadClass.LOW_LOAD_AEROBIC,
        LoadClass.RECOVERY_ONLY,
    ):
        assert _directive(load_class, 0, [CalendarEvent(0, HARD, SCOPE)]) is F
    # Zero-load coexistable support may still share the day.
    assert _directive(LoadClass.ZERO_LOAD, 0, [CalendarEvent(0, HARD, SCOPE)]) is A


def test_directive_tier_ordering_is_frozen():
    from fightcamp.combat_load_policy import placement_rank

    assert placement_rank(A) < placement_rank(DP) < placement_rank(F)


# ---------------------------------------------------------------------------
# Part F — cross-owner equivalence: the two planners may order candidates
# differently, but they may never disagree about legality.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "load_class",
    [
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
        LoadClass.NEURAL_MICRODOSE,
        LoadClass.REDUCED_CONTACT,
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.LOW_LOAD_AEROBIC,
        LoadClass.RECOVERY_ONLY,
    ],
)
@pytest.mark.parametrize("geometry", ["after", "before", "between"])
def test_normal_and_late_fight_agree_on_legality(load_class, geometry):
    """Same geometry, two representations, one verdict.

    Normal camp uses weekday indices (monday=0 ... sunday=6). Late fight uses
    ``-countdown_offset``. Both must yield the same directive *and* reason code.
    """
    profile = _profile(load_class)

    if geometry == "after":
        normal_events = [CalendarEvent(0, HARD, SCOPE)]
        normal_pos = 1
        late_events = cc.sequence_events([], resolved_contacts=[(19, "hard")])
        late_pos = -18
    elif geometry == "before":
        normal_events = [CalendarEvent(5, HARD, SCOPE)]
        normal_pos = 4
        late_events = cc.sequence_events([], resolved_contacts=[(18, "hard")])
        late_pos = -19
    else:  # between two hard contacts
        normal_events = [CalendarEvent(0, HARD, SCOPE), CalendarEvent(4, HARD, SCOPE)]
        normal_pos = 2
        late_events = cc.sequence_events([], resolved_contacts=[(21, "hard"), (17, "hard")])
        late_pos = -19

    normal = evaluate_candidate_at_position(
        profile, candidate_position=normal_pos, events=normal_events, candidate_scope=SCOPE
    )
    late = evaluate_candidate_at_position(
        profile,
        candidate_position=late_pos,
        events=late_events,
        candidate_scope=cc.LATE_FIGHT_SCOPE,
    )
    assert normal.directive is late.directive
    assert normal.reason_code == late.reason_code


# ---------------------------------------------------------------------------
# Part G — resolved-state authority. A supplied resolver plan is authoritative
# even when it resolves to zero effective hard contact.
# ---------------------------------------------------------------------------
def test_resolver_none_permits_declared_fallback():
    events = cc.normal_week_contact_events(None, ["monday", "friday"], scope=SCOPE)
    assert [e.profile.load_class for e in events] == [LoadClass.HARD_CONTACT] * 2


@pytest.mark.parametrize(
    "plan",
    [
        [],
        [{"day": "monday", "status": "convert_to_technical_suggested"},
         {"day": "friday", "status": "convert_to_technical_suggested"}],
        [{"day": "monday", "status": "deload_suggested"},
         {"day": "friday", "status": "deload_suggested"}],
        [{"day": "monday", "status": "suppressed"},
         {"day": "friday", "status": "suppressed"}],
    ],
    ids=["empty", "all-technical", "all-reduced", "all-suppressed"],
)
def test_supplied_plan_is_authoritative_declared_hard_never_resurrected(plan):
    events = cc.normal_week_contact_events(plan, ["monday", "friday"], scope=SCOPE)
    assert LoadClass.HARD_CONTACT not in {e.profile.load_class for e in events}


def test_late_fight_scorer_preserves_reduced_and_technical_as_not_hard():
    touch = {
        "role_key": "strength_touch_day", "category": "strength", "countdown_offset": 18,
        "stress_class": "meaningful_stress", "cost_class": "medium",
    }
    assert lf._late_fight_legality_cost([touch], [(19, "hard")]) == (1, 0)
    assert lf._late_fight_legality_cost([touch], [(19, "reduced")]) == (0, 0)
    assert lf._late_fight_legality_cost([touch], [(19, "technical")]) == (0, 0)


# ---------------------------------------------------------------------------
# Part D — boundary sweep.
# ---------------------------------------------------------------------------
def test_d14_is_normal_camp_and_d13_inward_is_late_fight():
    for days in (21, 18, 17, 15, 14):
        assert lf._days_out_payload_mode(days) == "camp_payload", days
    for days in (13, 10, 7, 4, 3):
        assert lf._days_out_payload_mode(days) != "camp_payload", days
        assert lf._is_countdown_continuation_start(days) is True, days
    # The boundary itself: D-14 is normal, D-13 is not.
    assert lf._is_countdown_continuation_start(14) is False
    assert lf._is_countdown_continuation_start(13) is True


def test_d17_hard_contact_cutoff_is_resolver_owned():
    for offset in (21, 20, 19, 18):
        assert lf._hard_spar_status_for_countdown_offset(offset) == "hard_allowed", offset
    for offset in (17, 16, 13, 7, 1, 0):
        assert lf._hard_spar_status_for_countdown_offset(offset) == "downgrade", offset


def test_d0_and_d1_are_terminal_protocol_modes():
    assert lf._days_out_payload_mode(0) == "fight_day_protocol_payload"
    assert lf._days_out_payload_mode(1) == "pre_fight_day_payload"
    # Neither is a countdown-continuation window the allocator may fill freely.
    assert lf._is_countdown_continuation_start(0) is False
    assert lf._is_countdown_continuation_start(1) is False


def test_d18_to_d21_is_the_only_effective_hard_contact_band():
    """Effective hard contact survives only in the bridge band, so canonical
    hard-contact protection applies there and is a no-op inside the taper."""
    hard_allowed = {
        offset for offset in range(0, 22)
        if lf._hard_spar_status_for_countdown_offset(offset) == "hard_allowed"
    }
    assert hard_allowed == {18, 19, 20, 21}


# ---------------------------------------------------------------------------
# Part H — final governor defence in depth. The governor must keep enforcing
# even though upstream placement now consults the same policy.
# ---------------------------------------------------------------------------
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def _week(*, roles, contacts, start_d=24, declared=None):
    return {
        "week_index": 1,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": weekday, "d_day": start_d - idx}
            for idx, weekday in enumerate(WEEKDAYS)
        ],
        "declared_training_days": list(declared or WEEKDAYS),
        "session_roles": roles,
        "hard_sparring_plan": contacts,
        "suppressed_roles": [],
        "session_count_summary": {"reduced_from_planned": False, "reduction_reasons": []},
    }


def _strength(day):
    return {
        "role_key": "primary_strength_day", "category": "strength",
        "scheduled_day_hint": day, "session_index": 1,
        "stress_class": "meaningful_stress", "cost_class": "medium",
    }


def test_governor_still_repairs_a_same_day_contact_collision():
    # Upstream placement would never emit this; the governor must still catch it.
    role_map = {"weeks": [_week(
        roles=[_strength("Monday")],
        contacts=[{"day": "Monday", "status": "hard_as_planned", "effective_load": "hard"}],
    )]}
    apply_final_calendar_integrity(role_map)
    report = role_map["calendar_integrity"]
    assert report["unresolved_forbidden"] == 0
    # It acted: the illegal placement was relocated or suppressed, not accepted.
    assert report["relocated_roles"] + report["suppressed_roles"] >= 1
    assert _strength("Monday") not in role_map["weeks"][0]["session_roles"]


def test_governor_raises_rather_than_shipping_an_unrepairable_calendar():
    # Every declared day is contact, so the forbidden strength role has nowhere
    # legal to go. The governor must refuse rather than silently pass it on.
    contacts = [
        {"day": day, "status": "hard_as_planned", "effective_load": "hard"}
        for day in WEEKDAYS
    ]
    role_map = {"weeks": [_week(roles=[_strength("Monday")], contacts=contacts)]}
    with pytest.raises(CalendarIntegrityError):
        apply_final_calendar_integrity(role_map)


def test_governor_runs_after_dose_morph_as_the_last_mutating_stage():
    """Ownership: the dose morph applies countdown dose and then hands the
    finished calendar to the governor, which is the final deterministic check."""
    import inspect

    from fightcamp.late_camp_role_morph import apply_late_camp_role_morph

    src = inspect.getsource(apply_late_camp_role_morph)
    assert "_apply_late_camp_role_morph_once" in src
    assert "apply_final_calendar_integrity" in src
    # dose first, verification last
    assert src.index("_apply_late_camp_role_morph_once") < src.index("apply_final_calendar_integrity")


# ---------------------------------------------------------------------------
# Part I — renderer is read-only.
# ---------------------------------------------------------------------------
def test_renderer_never_invents_a_weekday_for_a_dayless_role():
    from fightcamp.weekly_plan_render import _resolve_role_weekdays

    resolved = _resolve_role_weekdays([
        {"role_key": "primary_strength_day", "scheduled_day_hint": "Tuesday"},
        {"role_key": "aerobic_base_day", "scheduled_day_hint": ""},
        {"role_key": "recovery_reset_day"},
    ])
    assert resolved[0] == "tuesday"
    # A dayless role stays dayless through render.
    assert resolved[1] == ""
    assert resolved[2] == ""


def test_renderer_does_not_own_placement_completion():
    from fightcamp import weekly_plan_render

    # The renderer must not re-export or hold the placement completion helper.
    assert not hasattr(weekly_plan_render, "fill_missing_session_days")
    assert not hasattr(weekly_plan_render, "_assign_declared_day_hints")


# ---------------------------------------------------------------------------
# Ownership freeze — one canonical owner per decision, no resurrected engines.
# ---------------------------------------------------------------------------
def test_deleted_architecture_stays_deleted():
    for module in (
        "late_fight_placement",
        "stage2_role_map_patch",
        "stage2_role_map_integration",
        "stage2_placement_patch",
        "stage2_placement_integration",
        "combat_policy_bridge",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"fightcamp.{module}")


def test_collision_legality_has_exactly_one_owner():
    """Only combat_load_policy may return a PlacementDirective."""
    from fightcamp import combat_load_policy

    assert hasattr(combat_load_policy, "evaluate_calendar_candidate")
    assert hasattr(combat_load_policy, "evaluate_candidate_at_position")
    # calendar_context is representation-only: it builds events/views and
    # delegates every verdict back to the policy.
    assert not hasattr(cc, "evaluate_calendar_candidate")


def test_placement_owners_are_the_step9a_survivors():
    from fightcamp import normal_calendar_placement, stage2_role_map

    assert hasattr(stage2_role_map, "_assign_declared_day_hints")
    assert hasattr(normal_calendar_placement, "fill_missing_session_days")
    assert hasattr(lf, "_build_late_fight_session_sequence")


def test_late_fight_placement_holds_no_second_sparring_resolver():
    import inspect

    assert not hasattr(lf, "_late_fight_resolved_contacts")
    assert "_hard_spar_status_for_countdown_offset" not in inspect.getsource(
        lf._late_fight_legality_cost
    )


# ---------------------------------------------------------------------------
# Duplicate-engine removal (Step 10). stage2_payload carried stale forks of the
# stage2_role_map role-budget/compression engine that no production entry point
# and no test reached. They are deleted; these guard them from returning.
# ---------------------------------------------------------------------------
_REMOVED_PAYLOAD_DUPLICATES = (
    "_compressed_priority_for_role",
    "_is_final_week_capped_sparring_entry",
    "_join_rule_parts",
    "_lock_declared_hard_sparring_roles",
    "_normalize_text",
    "_phrase_in_text",
    "_primary_limiter_key",
    "_recovery_role_key",
    "_role_anchor",
    "_role_selection_rule",
    "_slugify",
)


@pytest.mark.parametrize("name", _REMOVED_PAYLOAD_DUPLICATES)
def test_dead_stage2_payload_duplicates_stay_deleted(name):
    from fightcamp import stage2_payload

    assert not hasattr(stage2_payload, name), (
        f"{name} was a dead duplicate of the stage2_role_map owner, removed in Step 10. "
        "The live implementation belongs to stage2_role_map."
    )


def test_crowded_week_role_budget_has_one_owner():
    """Crowded-week policy and survival decisions belong only to the role map."""
    from fightcamp import stage2_payload, stage2_role_map

    for name in (
        "_apply_boxing_crowded_week_compression",
        "_boxing_crowded_week_policy_state",
        "_boxing_crowded_week_summary",
        "_select_boxing_crowded_week_non_spar_roles",
    ):
        assert hasattr(stage2_role_map, name)
        assert not hasattr(stage2_payload, name)


def test_payload_crowded_week_post_processing_is_decoration_only():
    from fightcamp import stage2_payload

    week = {
        "intentional_compression": {"policy": "boxing_crowded_week"},
        "session_roles": [{"role_key": "primary_strength_day", "category": "strength"}],
        "suppressed_roles": [{"role_key": "aerobic_support_day"}],
        "intentionally_unused_days": ["Friday"],
    }
    before_roles = list(week["session_roles"])
    before_suppressed = list(week["suppressed_roles"])
    before_unused = list(week["intentionally_unused_days"])

    stage2_payload._apply_boxing_crowded_week_post_processing(
        {"weeks": [week]}, athlete_model={"sport": "boxing", "fatigue": "high"}
    )

    assert week["session_roles"] == before_roles
    assert week["suppressed_roles"] == before_suppressed
    assert week["intentionally_unused_days"] == before_unused
    assert week["session_roles"][0]["governance"]["main_job"] == "anchor"


def test_payload_test_oracles_survived_the_dedupe():
    """Helpers that live tests import from stage2_payload as independent oracles."""
    from fightcamp import stage2_payload

    for name in (
        "_is_meaningful_stressor",                    # tests/test_gap_fill_inserts.py
        "_active_injury_affects_generic_compression", # tests/test_surface_injury_train_through.py
        "_apply_high_fatigue_week_compression",       # tests/test_stage2_planning_brief.py
        "_compute_readiness_compression",             # tests/test_stage2_planning_brief.py
    ):
        assert hasattr(stage2_payload, name), name



def test_generic_and_crowded_week_injury_semantics_remain_distinct():
    from fightcamp import stage2_role_map

    athlete = {
        "sport": "boxing",
        "fatigue": "low",
        "injuries": ["mild shoulder irritation"],
        "readiness_flags": [],
        "days_until_fight": 35,
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": [],
        "weight_cut_pct": 0.0,
    }

    assert stage2_role_map._compute_readiness_compression(athlete) == 1
    policy = stage2_role_map._boxing_crowded_week_policy_state(
        {"declared_hard_sparring_days": []}, athlete
    )
    assert "injury_management" not in policy["risk_signals"]
