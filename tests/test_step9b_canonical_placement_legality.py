"""Step 9B — the surviving production placement owners consume canonical
combat-load legality.

These are focused integration tests proving the two live placement owners
(normal-camp ``stage2_role_map._assign_declared_day_hints`` and the late-fight
allocator behind ``_build_late_fight_session_sequence``) respond to the shared
``combat_load_policy`` directive semantics — FORBID excluded, ALLOW preferred,
DEPRIORITIZE legal fallback — while keeping their own candidate generation,
anchors, and deterministic tie-breaking. The policy stays the single legality
owner; the planners may differ on candidate order but never on legality.
"""
from __future__ import annotations

from fightcamp import calendar_context as cc
from fightcamp import stage2_payload_late_fight as lf
from fightcamp.combat_load_policy import (
    LoadClass,
    PlacementDirective,
    evaluate_candidate_at_position,
    placement_rank,
)
from fightcamp.stage2_role_map import _assign_declared_day_hints


# --------------------------------------------------------------------------- #
# Shared seam: legality tier + chronology conversion                          #
# --------------------------------------------------------------------------- #
def test_placement_rank_orders_allow_before_deprioritize_before_forbid():
    assert placement_rank(PlacementDirective.ALLOW) == 0
    assert placement_rank(PlacementDirective.DEPRIORITIZE) == 1
    assert placement_rank(PlacementDirective.FORBID) == 2


def test_chronology_adjacent_days_stay_distance_one_after_conversion():
    # Normal camp: adjacent weekdays map to adjacent chronological positions.
    for earlier, later in (("monday", "tuesday"), ("saturday", "sunday")):
        assert cc.weekday_position(later) - cc.weekday_position(earlier) == 1

    # Late fight: adjacent countdown offsets stay distance 1 after the D-day
    # (-offset) conversion, even though raw D-day numbers run in reverse.
    events_prev = cc.sequence_events(
        [{"role_key": "strength_touch_day", "category": "strength", "countdown_offset": 13}],
    )
    events_next = cc.sequence_events(
        [{"role_key": "strength_touch_day", "category": "strength", "countdown_offset": 12}],
    )
    assert abs(events_prev[0].position - events_next[0].position) == 1
    # And the conversion is monotonic: a nearer fight day is a later position.
    assert events_next[0].position > events_prev[0].position


def test_best_legal_weekday_prefers_allow_then_deprioritize_then_none():
    # Hard contacts Monday + Friday: Wed is between (FORBID for meaningful),
    # Tue immediately after Monday hard is DEPRIORITIZE for a neural microdose,
    # and a clean day outside the span is ALLOW.
    view = cc.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}, {"day": "friday", "status": "hard_as_planned"}],
        ["monday", "friday"],
        scope=("normal_week", 1),
    )
    strength = cc.classify_role({"category": "strength", "role_key": "primary_strength_day"})
    # Owner offers Wed (FORBID) first, then Sunday (ALLOW): ALLOW wins despite order.
    assert view.best_legal_weekday(strength, ["wednesday", "sunday"]) == "sunday"
    # Only FORBID candidates -> None (no-legal-candidate signal).
    assert view.best_legal_weekday(strength, ["wednesday", "monday"]) is None


# --------------------------------------------------------------------------- #
# Normal camp owner                                                           #
# --------------------------------------------------------------------------- #
_TRAINING_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _assign(roles, *, hard_days, plan, support=None):
    athlete = {
        "training_days": _TRAINING_WEEK,
        "hard_sparring_days": hard_days,
        "support_work_days": support or [],
    }
    out = _assign_declared_day_hints([dict(r) for r in roles], athlete, hard_sparring_plan=plan)
    return {r["role_key"]: r.get("scheduled_day_hint") for r in out}


def test_normal_forbid_not_selected_even_when_locally_preferred():
    # Aerobic support prefers declared Support Work Days in weekday order; Monday
    # is also the declared hard-contact day, so placing aerobic there is FORBID
    # (same-day contact exclusivity). The owner must skip Monday for the next
    # legal support day (Saturday) rather than honour its local preference.
    plan = [{"day": "Monday", "status": "hard_as_planned"}]
    days = _assign(
        [
            {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Monday"},
            {"role_key": "aerobic_base_day", "category": "conditioning", "preferred_system": "aerobic"},
        ],
        hard_days=["Monday"],
        plan=plan,
        support=["Monday", "Saturday"],
    )
    assert days["aerobic_base_day"] == "Saturday"
    # Sanity: the policy really does FORBID aerobic on the Monday hard day.
    view = cc.normal_week_legality(plan, ["Monday"], scope=("normal_week", 1))
    aerobic = cc.classify_role({"category": "conditioning", "role_key": "aerobic_base_day", "preferred_system": "aerobic"})
    assert view.best_legal_weekday(aerobic, ["monday"]) is None


def test_normal_deprioritize_remains_selectable_when_no_allow_slot_exists():
    # Mon & Fri hard: every non-spar day (Tue/Wed/Thu) is between two hard
    # contacts. Recovery between hard contacts is ALLOW, so a recovery role still
    # places there — a legal fallback, never suppressed to dayless.
    plan = [{"day": "Monday", "status": "hard_as_planned"}, {"day": "Friday", "status": "hard_as_planned"}]
    days = _assign(
        [
            {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Monday"},
            {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Friday"},
            {"role_key": "recovery_reset_day", "category": "recovery"},
        ],
        hard_days=["Monday", "Friday"],
        plan=plan,
    )
    assert days["recovery_reset_day"] in {"Tuesday", "Wednesday", "Thursday"}


def test_normal_no_legal_candidate_keeps_owner_fallback_not_a_new_decision():
    # Mon & Fri hard, only Mon-Fri training: primary strength has no legal day
    # (Tue/Wed/Thu are between two hard contacts = FORBID for meaningful
    # strength; Mon/Fri are contact days). The owner keeps its existing
    # least-bad placement (a real training day) rather than inventing a new
    # suppression/dayless decision during Step 9B.
    athlete = {
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "hard_sparring_days": ["Monday", "Friday"],
        "support_work_days": [],
    }
    roles = [
        {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Monday"},
        {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Friday"},
        {"role_key": "primary_strength_day", "category": "strength"},
    ]
    out = _assign_declared_day_hints([dict(r) for r in roles], athlete, hard_sparring_plan=[
        {"day": "Monday", "status": "hard_as_planned"}, {"day": "Friday", "status": "hard_as_planned"}
    ])
    primary = next(r for r in out if r["role_key"] == "primary_strength_day")
    assert primary.get("scheduled_day_hint") in {"Tuesday", "Wednesday", "Thursday"}


# --------------------------------------------------------------------------- #
# Resolved contact truth (owned by the sparring resolver, consumed by policy) #
# --------------------------------------------------------------------------- #
def test_resolved_contact_status_drives_canonical_collision_not_labels():
    scope = ("normal_week", 1)
    strength = cc.classify_role({"category": "strength", "role_key": "primary_strength_day"})
    wed = cc.weekday_position("wednesday")

    # hard + hard -> Wednesday is between two hard contacts -> FORBID.
    hard = cc.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}, {"day": "friday", "status": "hard_as_planned"}],
        ["monday", "friday"], scope=scope,
    )
    assert hard.decision_at_position(strength, wed).directive is PlacementDirective.FORBID

    # Convert Friday to technical-only: only ONE effective hard contact remains,
    # so Wednesday is no longer between two hard contacts -> ALLOW.
    technical = cc.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}, {"day": "friday", "status": "convert_to_technical_suggested"}],
        ["monday", "friday"], scope=scope,
    )
    assert technical.decision_at_position(strength, wed).directive is PlacementDirective.ALLOW


# --------------------------------------------------------------------------- #
# Late-fight owner                                                            #
# --------------------------------------------------------------------------- #
def test_late_fight_forbid_penalty_dominates_deprioritize_and_allow():
    # A meaningful app strength touch immediately after a still-effective hard
    # contact (D-18 hard, touch at D-17) is FORBID; the same touch clear of
    # contact is ALLOW. The FORBID penalty must dwarf the DEPRIORITIZE nudge.
    forbid_case = [
        {"role_key": "hard_sparring_day", "category": "sparring", "countdown_offset": 18},
        {"role_key": "strength_touch_day", "category": "strength", "countdown_offset": 17,
         "stress_class": "meaningful_stress", "cost_class": "medium"},
    ]
    allow_case = [
        {"role_key": "hard_sparring_day", "category": "sparring", "countdown_offset": 18},
        {"role_key": "strength_touch_day", "category": "strength", "countdown_offset": 12,
         "stress_class": "meaningful_stress", "cost_class": "medium"},
    ]
    assert lf._late_fight_canonical_collision_penalty(forbid_case) >= lf._LATE_FIGHT_FORBID_PENALTY
    assert lf._late_fight_canonical_collision_penalty(allow_case) == 0


def test_late_fight_resolved_contacts_respect_d17_cutoff():
    # Coach-owned hard days above D-17 stay hard context; from D-17 inward they
    # are resolved to technical — read back, never re-decided, by the adapter.
    roles = [
        {"role_key": "hard_sparring_day", "category": "sparring", "countdown_offset": 20},
        {"role_key": "hard_sparring_day", "category": "sparring", "countdown_offset": 10},
    ]
    contacts = dict(lf._late_fight_resolved_contacts(roles))
    assert contacts == {20: "hard", 10: "technical"}


def test_late_fight_coexistable_filler_never_scored_as_a_day_collision():
    # A low-cost coexistable filler shares the coach's contact day legally; it
    # does not consume a day slot, so it never contributes a collision penalty.
    roles = [
        {"role_key": "hard_sparring_day", "category": "sparring", "countdown_offset": 18},
        {"role_key": "tactical_watch", "category": "tactical", "countdown_offset": 18,
         "stress_class": "support", "cost_class": "zero"},
    ]
    assert lf._late_fight_canonical_collision_penalty(roles) == 0


# --------------------------------------------------------------------------- #
# Same policy, both owners                                                    #
# --------------------------------------------------------------------------- #
def test_same_policy_both_owners_agree_on_legality():
    # Equivalent collision context expressed in each owner's representation:
    # a meaningful strength candidate immediately after a single hard contact.
    # Normal camp uses weekday positions; late fight uses -offset positions. The
    # planners generate candidates differently but the shared policy returns the
    # same FORBID legality for both.
    strength = cc.classify_role({"category": "strength", "role_key": "primary_strength_day"})

    normal_view = cc.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}], ["monday"], scope=("normal_week", 1)
    )
    normal_decision = normal_view.decision_at_position(strength, cc.weekday_position("tuesday"))

    late_events = cc.sequence_events(
        [], resolved_contacts=[(18, "hard")]
    )
    late_decision = evaluate_candidate_at_position(
        strength, candidate_position=-17, events=late_events, candidate_scope=cc.LATE_FIGHT_SCOPE
    )

    assert normal_decision.directive is PlacementDirective.FORBID
    assert late_decision.directive is PlacementDirective.FORBID
    assert normal_decision.reason_code == late_decision.reason_code == "post_hard_contact_meaningful_stress"
    # Both derive from the same canonical HARD_CONTACT classification.
    assert late_events[0].profile.load_class is LoadClass.HARD_CONTACT
