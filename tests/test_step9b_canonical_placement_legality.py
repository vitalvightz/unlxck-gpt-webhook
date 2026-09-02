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
    # contacts. A low-load movement role is DEPRIORITIZE there
    # (between_hard_contacts_low_load_physical) — legal, not FORBID — so it still
    # places on one of those days rather than being suppressed to dayless.
    plan = [{"day": "Monday", "status": "hard_as_planned"}, {"day": "Friday", "status": "hard_as_planned"}]
    view = cc.normal_week_legality(plan, ["Monday", "Friday"], scope=("normal_week", 1))
    movement = cc.classify_role({"category": "conditioning", "role_key": "movement_quality"})
    assert view.decision_at_position(movement, cc.weekday_position("wednesday")).directive is PlacementDirective.DEPRIORITIZE

    # Mon-Fri only: every non-spar day (Tue/Wed/Thu) is between the two hard days,
    # so the movement role has no ALLOW option — only DEPRIORITIZE ones.
    athlete = {
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "hard_sparring_days": ["Monday", "Friday"],
        "support_work_days": [],
    }
    out = _assign_declared_day_hints(
        [
            {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Monday"},
            {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Friday"},
            {"role_key": "movement_quality", "category": "conditioning"},
        ],
        athlete,
        hard_sparring_plan=plan,
    )
    movement_role = next(r for r in out if r["role_key"] == "movement_quality")
    assert movement_role.get("scheduled_day_hint") in {"Tuesday", "Wednesday", "Thursday"}


def test_normal_forbid_means_unavailable_not_a_forbidden_fallback():
    # Mon & Fri hard, only Mon-Fri training: primary strength has no legal day
    # (Tue/Wed/Thu are between two hard contacts = FORBID for meaningful strength;
    # Mon/Fri are contact days). FORBID must mean *unavailable*: the owner leaves
    # the role dayless (its existing unresolved handling) rather than committing a
    # forbidden day that a later pass could keep — placement never emits an
    # intentionally illegal calendar.
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
    assert not str(primary.get("scheduled_day_hint") or "").strip()


def test_normal_completion_never_refills_a_forbidden_day():
    # The downstream completion helper is part of the placement owner: it must not
    # re-place a dayless role onto a forbidden day. Here every free declared day is
    # FORBID for meaningful strength, so completion leaves it dayless too.
    from fightcamp.normal_calendar_placement import fill_missing_session_days

    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "declared_training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "declared_hard_sparring_days": ["Monday", "Friday"],
                "hard_sparring_plan": [
                    {"day": "Monday", "status": "hard_as_planned"},
                    {"day": "Friday", "status": "hard_as_planned"},
                ],
                "session_roles": [
                    {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Monday"},
                    {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Friday"},
                    {"role_key": "primary_strength_day", "category": "strength"},
                ],
            }
        ]
    }
    fill_missing_session_days(weekly_role_map)
    primary = weekly_role_map["weeks"][0]["session_roles"][2]
    assert not str(primary.get("scheduled_day_hint") or "").strip()


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
def test_late_fight_legality_penalty_is_lexicographic_over_owner_preferences():
    # A meaningful app strength touch immediately after a still-effective hard
    # contact (D-18 hard, touch at D-17) is FORBID; the same touch clear of contact
    # is ALLOW. The legality penalty is lexicographic: FORBID and DEPRIORITIZE tiers
    # each dwarf the largest owner-preference swing the late-fight scorers produce
    # (the single-window -100000 hard-weekday penalty and the composite gap/stage
    # terms), so an owner preference can never flip ALLOW below DEPRIORITIZE or keep
    # a FORBID slot. The compressed D-13-inward window (no effective hard contact)
    # stays a no-op.
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
    _OWNER_PREFERENCE_CEILING = 1_000_000  # far above any single owner-score swing
    assert lf._late_fight_canonical_collision_penalty(allow_case) == 0
    assert lf._late_fight_canonical_collision_penalty(forbid_case) == lf._LATE_FIGHT_FORBID_PENALTY
    # Each tier dominates owner preference, and FORBID dominates DEPRIORITIZE.
    assert lf._LATE_FIGHT_DEPRIORITIZE_PENALTY > _OWNER_PREFERENCE_CEILING
    assert lf._LATE_FIGHT_FORBID_PENALTY > lf._LATE_FIGHT_DEPRIORITIZE_PENALTY * 50


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
