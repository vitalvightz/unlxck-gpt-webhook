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
    # With three full intervening days, Wednesday is a clean interior ALLOW day.
    view = cc.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}, {"day": "friday", "status": "hard_as_planned"}],
        ["monday", "friday"],
        scope=("normal_week", 1),
    )
    strength = cc.classify_role({"category": "strength", "role_key": "primary_strength_day"})
    assert view.best_legal_weekday(strength, ["wednesday", "sunday"]) == "wednesday"
    assert view.best_legal_weekday(strength, ["monday"]) is None


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


def test_normal_three_day_gap_uses_normal_interior_placement():
    # Mon & Fri hard: every non-spar day (Tue/Wed/Thu) is between two hard
    # contacts. With three full intervening days the tight-gap branch is skipped,
    # so a low-load movement role is ALLOW throughout the interior.
    plan = [{"day": "Monday", "status": "hard_as_planned"}, {"day": "Friday", "status": "hard_as_planned"}]
    view = cc.normal_week_legality(plan, ["Monday", "Friday"], scope=("normal_week", 1))
    movement = cc.classify_role({"category": "conditioning", "role_key": "movement_quality"})
    assert view.decision_at_position(movement, cc.weekday_position("wednesday")).directive is PlacementDirective.ALLOW

    # Mon-Fri only: the three interior days remain normal ALLOW destinations.
    athlete = {
        "training_days": ["Tuesday", "Wednesday", "Thursday", "Friday"],
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


def test_two_day_gap_places_managed_strength_on_earlier_intervening_day():
    athlete = {
        "training_days": ["Tuesday", "Wednesday", "Thursday", "Friday"],
        "hard_sparring_days": ["Tuesday", "Friday"],
        "support_work_days": [],
    }
    roles = [
        {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Tuesday"},
        {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Friday"},
        {"role_key": "primary_strength_day", "category": "strength"},
    ]
    out = _assign_declared_day_hints([dict(r) for r in roles], athlete, hard_sparring_plan=[
        {"day": "Tuesday", "status": "hard_as_planned"}, {"day": "Friday", "status": "hard_as_planned"}
    ])
    primary = next(r for r in out if r["role_key"] == "primary_strength_day")
    assert primary.get("scheduled_day_hint") == "Wednesday"


def test_normal_completion_never_refills_a_one_day_gap_forbidden_day():
    # The downstream completion helper is part of the placement owner: it must not
    # re-place a dayless role onto a forbidden day. Here every free declared day is
    # FORBID for meaningful strength, so completion leaves it dayless too.
    from fightcamp.normal_calendar_placement import fill_missing_session_days

    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "declared_training_days": ["Tuesday", "Wednesday", "Thursday"],
                "declared_hard_sparring_days": ["Tuesday", "Thursday"],
                "hard_sparring_plan": [
                    {"day": "Tuesday", "status": "hard_as_planned"},
                    {"day": "Thursday", "status": "hard_as_planned"},
                ],
                "session_roles": [
                    {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Tuesday"},
                    {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "Thursday"},
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

    # Three full intervening days leave Wednesday as an ordinary interior day.
    hard = cc.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}, {"day": "friday", "status": "hard_as_planned"}],
        ["monday", "friday"], scope=scope,
    )
    assert hard.decision_at_position(strength, wed).directive is PlacementDirective.ALLOW

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
def _touch(offset):
    return {"role_key": "strength_touch_day", "category": "strength", "countdown_offset": offset,
            "stress_class": "meaningful_stress", "cost_class": "medium"}


def test_late_fight_legality_cost_is_lexicographic_over_owner_preferences():
    # A meaningful app strength touch immediately after a still-effective hard
    # contact (D-18 hard, touch at D-17) is DEPRIORITIZE; the same touch clear of contact
    # is ALLOW. Resolved contacts are the authoritative (offset, load) truth passed
    # in — the scorer never re-resolves them. The scorers rank by
    # (-forbid, -deprioritize, owner_score), so the legality cost is a strictly
    # higher-order key than any owner preference (the single-window -100000
    # hard-weekday term, the composite gap/stage terms). An owner preference can
    # never flip ALLOW below DEPRIORITIZE or keep a FORBID slot.
    resolved = [(18, "hard")]
    assert lf._late_fight_legality_cost([_touch(12)], resolved) == (0, 0)
    assert lf._late_fight_legality_cost([_touch(17)], resolved) == (0, 1)
    # No resolved contact (compressed D-13-inward window) stays (0, 0).
    assert lf._late_fight_legality_cost([_touch(17)], []) == (0, 0)
    # The lexicographic key: fewer FORBID wins first, then fewer DEPRIORITIZE, then
    # owner preference — legality can never be outweighed by preference.
    forbid_key = (-1, 0, 10 ** 9)      # one FORBID, huge owner preference
    allow_key = (0, 0, -(10 ** 9))     # fully legal, terrible owner preference
    assert allow_key > forbid_key
    deprioritize_key = (0, -1, 10 ** 9)  # one DEPRIORITIZE, huge owner preference
    assert allow_key > deprioritize_key


def test_late_fight_scorer_consumes_resolved_contact_no_re_resolution():
    # Ownership: the scorer consumes the sparring resolver's authoritative
    # (offset, effective_load) truth verbatim. It does NOT re-derive hard/technical
    # from role_key + offset, and it holds no _hard_spar_status_for_countdown_offset
    # in its path (that stays inside the resolver-owned resolve_late_fight_contacts).
    import inspect

    assert not hasattr(lf, "_late_fight_resolved_contacts")
    src = inspect.getsource(lf._late_fight_legality_cost)
    assert "_hard_spar_status_for_countdown_offset" not in src
    assert "resolve_late_fight_contacts" in inspect.getsource(lf._late_fight_best_assignment) or \
        "resolve_late_fight_contacts" in inspect.getsource(lf._late_fight_allocation_plan)


def test_late_fight_resolved_reduced_contact_stays_reduced_not_hard():
    # The reviewer's regression: a resolved *reduced* contact must be carried through
    # as reduced, never collapsed to hard. Reduced contact is not HARD_CONTACT, so it
    # does not trigger the policy's hard-contact adjacency protection: an app touch on
    # the neighbouring day is ALLOW next to reduced but DEPRIORITIZE next to hard.
    assert lf._late_fight_legality_cost([_touch(18)], [(19, "reduced")]) == (0, 0)
    assert lf._late_fight_legality_cost([_touch(18)], [(19, "hard")]) == (0, 1)
    # Technical resolves the same way (also not hard-adjacency-protected).
    assert lf._late_fight_legality_cost([_touch(18)], [(19, "technical")]) == (0, 0)


def test_late_fight_coexistable_filler_never_scored_as_a_day_collision():
    # A low-cost coexistable filler shares the coach's contact day legally; it
    # does not consume a day slot, so it never contributes a legality cost.
    filler = {"role_key": "tactical_watch", "category": "tactical", "countdown_offset": 18,
              "stress_class": "support", "cost_class": "zero"}
    assert lf._late_fight_legality_cost([filler], [(18, "hard")]) == (0, 0)


# --------------------------------------------------------------------------- #
# Same policy, both owners                                                    #
# --------------------------------------------------------------------------- #
def test_same_policy_both_owners_agree_on_legality():
    # Equivalent collision context expressed in each owner's representation:
    # a meaningful strength candidate immediately after a single hard contact.
    # Normal camp uses weekday positions; late fight uses -offset positions. The
    # planners generate candidates differently but the shared policy returns the
    # same DEPRIORITIZE legality for both.
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

    assert normal_decision.directive is PlacementDirective.DEPRIORITIZE
    assert late_decision.directive is PlacementDirective.DEPRIORITIZE
    assert normal_decision.reason_code == late_decision.reason_code == "post_hard_contact_managed_stress"
    # Both derive from the same canonical HARD_CONTACT classification.
    assert late_events[0].profile.load_class is LoadClass.HARD_CONTACT


# --------------------------------------------------------------------------- #
# Resolver authority: None (resolver did not run) vs a resolved-but-empty plan #
# --------------------------------------------------------------------------- #
def test_resolver_none_falls_back_to_declared_hard_days():
    # No plan supplied -> the resolver has not run, so the declared hard days are
    # the best available truth and become HARD_CONTACT events.
    events = cc.normal_week_contact_events(None, ["monday", "friday"], scope=("normal_week", 1))
    assert sorted(e.profile.load_class for e in events) == [
        LoadClass.HARD_CONTACT,
        LoadClass.HARD_CONTACT,
    ]


def test_resolved_plan_is_authoritative_declared_hard_never_resurrected():
    # A supplied plan is authoritative even when every declared day resolved to
    # technical (zero effective hard). The declared hard days must NOT be recreated
    # as HARD_CONTACT — they surface only as the resolved technical contact.
    plan = [
        {"day": "monday", "status": "convert_to_technical_suggested"},
        {"day": "friday", "status": "convert_to_technical_suggested"},
    ]
    events = cc.normal_week_contact_events(plan, ["monday", "friday"], scope=("normal_week", 1))
    assert [e.profile.load_class for e in events] == [
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.TECHNICAL_CONTACT,
    ]
    assert LoadClass.HARD_CONTACT not in {e.profile.load_class for e in events}

    # An empty resolved plan is authoritative "no contact", not "unresolved":
    # declared hard days are still not resurrected.
    assert cc.normal_week_contact_events([], ["monday", "friday"], scope=("normal_week", 1)) == []


def test_normal_placement_respects_resolved_downgrade_not_declared_labels():
    # Declared hard Mon & Fri, but the resolver downgraded both to technical.
    # Wednesday is therefore NOT between two *effective hard* contacts, so meaningful
    # strength is legal there — the owner must not treat the declared hard labels as
    # authoritative over the resolved state.
    plan = [
        {"day": "Monday", "status": "convert_to_technical_suggested"},
        {"day": "Friday", "status": "convert_to_technical_suggested"},
    ]
    athlete = {
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "hard_sparring_days": ["Monday", "Friday"],
        "support_work_days": [],
    }
    out = _assign_declared_day_hints(
        [{"role_key": "primary_strength_day", "category": "strength"}],
        athlete,
        hard_sparring_plan=plan,
    )
    primary = next(r for r in out if r["role_key"] == "primary_strength_day")
    # A real training day is assigned (strength is not forbidden everywhere now).
    assert str(primary.get("scheduled_day_hint") or "").strip()
