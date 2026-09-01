"""Step 5: optional support fillers gate through the shared calendar legality.

These tests pin the ownership contract Step 5 establishes:

- normal-camp and late-fight fillers ask ``combat_load_policy`` (through the
  canonical ``calendar_context`` adapter) whether a candidate may coexist on a
  day *before* they mutate the calendar;
- the answer is driven by resolved contact (``hard_sparring_plan`` / the
  late-fight sparring resolver), never by raw declared weekday names;
- ALLOW / DEPRIORITIZE / FORBID semantics are preserved (DEPRIORITIZE stays
  legal but loses to a cleaner ALLOW option);
- the final governor still verifies, but no longer has to clean up a collision
  the shared policy could already see at insertion time.
"""

from __future__ import annotations

import datetime as dt

import fightcamp.stage2_payload_late_fight as _late_fight_module
from fightcamp import calendar_context as cc
from fightcamp import calendar_integrity as ci
from fightcamp import combat_load_policy as clp
from fightcamp.calendar_context import (
    CalendarLegalityView,
    resolved_contact_offsets,
    sequence_legality,
)
from fightcamp.calendar_integrity import apply_final_calendar_integrity
from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.camp_week_fillers_impl import _COORDINATION_LEGALITY_ROLE, _coordination_slot
from fightcamp.combat_load_policy import (
    CONTACT_LOAD_CLASSES,
    LoadClass,
    PlacementDirective,
    role_load_profile,
)
from fightcamp.gap_fill_inserts import (
    LOW_COST_AEROBIC_INSERTS,
    LOW_COST_RECOVERY_INSERTS,
    PHYSICAL_INSERTS,
    ZERO_COST_INSERTS,
    _legal_support_keys,
    apply_gap_fill_inserts,
)
from fightcamp.stage2_payload_late_fight import (
    _classify_declared_hard_days_for_late_window,
    _late_fight_permission_policy,
    resolve_late_fight_contacts,
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
def _calendar(day_to_d: dict[str, int]) -> list[dict]:
    return [{"weekday": w, "d_day": d} for w, d in day_to_d.items()]


def _contact(day: str, *, status: str = "hard_as_planned", load: str = "hard") -> dict:
    return {"day": day, "status": status, "effective_load": load}


def _week(
    *,
    start_d: int = 30,
    week_index: int = 1,
    roles: list[dict] | None = None,
    contacts: list[dict] | None = None,
    calendar_days: list[dict] | None = None,
    declared: list[str] | None = None,
    unused: list[dict] | None = None,
    phase: str = "SPP",
) -> dict:
    if calendar_days is None:
        calendar_days = [
            {"weekday": weekday, "d_day": start_d - idx}
            for idx, weekday in enumerate(WEEKDAYS)
        ]
    return {
        "week_index": week_index,
        "phase": phase,
        "calendar_days": calendar_days,
        "declared_training_days": declared or list(WEEKDAYS),
        "session_roles": roles or [],
        "hard_sparring_plan": contacts or [],
        "intentionally_unused_days": unused or [],
        "suppressed_roles": [],
        "session_count_summary": {"reduced_from_planned": False, "reduction_reasons": []},
    }


def _hard_role(day: str) -> dict:
    return {
        "role_key": "hard_sparring_day",
        "category": "sparring",
        "scheduled_day_hint": day,
        "hard_sparring_status": "hard_as_planned",
    }


def _legality(weekly_role_map: dict, week: dict, ordinal: int = 1) -> CalendarLegalityView:
    return cc.weekly_role_map_legality(weekly_role_map, week, ordinal)


def _fillers(week: dict) -> list[dict]:
    return [r for r in week["session_roles"] if isinstance(r, dict) and r.get("camp_week_filler")]


def _directive(view: CalendarLegalityView, role_key: str, offset: int) -> PlacementDirective:
    profile = role_load_profile({"role_key": role_key})
    return view.decision_for_profile(profile, offset).directive


# --------------------------------------------------------------------------- #
# 1. Normal Tactical Watch on an exclusive contact day survives                #
# --------------------------------------------------------------------------- #
def test_normal_tactical_watch_on_exclusive_contact_day_survives():
    week = _week(roles=[_hard_role("Tuesday")], contacts=[_contact("Tuesday")])
    weekly = {"weeks": [week]}
    view = _legality(weekly, week)
    # Tuesday is D-29 in the default calendar.
    assert _directive(view, "tactical_watch", 29) is PlacementDirective.ALLOW
    assert view.role_is_forbidden({"role_key": "tactical_watch"}, 29) is False


# --------------------------------------------------------------------------- #
# 2. Normal physical filler on an exclusive contact day rejected pre-insertion #
# --------------------------------------------------------------------------- #
def test_normal_physical_filler_on_exclusive_contact_day_rejected():
    # Tuesday is a resolved hard contact and the only shared-day candidate; a
    # footwork weakness biases selection toward a physical insert.
    week = _week(
        roles=[_hard_role("Tuesday")],
        contacts=[_contact("Tuesday")],
        calendar_days=_calendar({"tuesday": 29}),
        declared=["Tuesday"],
    )
    weekly = {"weeks": [week]}
    view = _legality(weekly, week)
    for physical in sorted(PHYSICAL_INSERTS):
        assert view.role_is_forbidden({"role_key": physical}, 29) is True

    apply_camp_week_fillers(
        weekly, {"fatigue": "low", "weaknesses": ["footwork"], "hard_sparring_days": ["Tuesday"]}
    )
    tuesday_fillers = [f for f in _fillers(week) if f["scheduled_day_hint"] == "Tuesday"]
    assert all(f["role_key"] not in PHYSICAL_INSERTS for f in tuesday_fillers)


# --------------------------------------------------------------------------- #
# 3. Coordination support on an exclusive contact day rejected                 #
# --------------------------------------------------------------------------- #
def test_coordination_support_on_exclusive_contact_day_rejected():
    week = _week(roles=[_hard_role("Tuesday")], contacts=[_contact("Tuesday")])
    view = _legality({"weeks": [week]}, week)
    # coordination_support is low-load physical -> forbidden on the exclusive day.
    assert view.role_is_forbidden(_COORDINATION_LEGALITY_ROLE, 29) is True


# --------------------------------------------------------------------------- #
# 4. Low-aerobic filler between two effective hard contacts is allowed         #
# --------------------------------------------------------------------------- #
def test_low_aerobic_between_two_hard_contacts_allowed():
    view = sequence_legality([], resolved_contacts=[(20, "hard"), (14, "hard")])
    # D-17 sits between the two scoped hard contacts.
    for aerobic in sorted(LOW_COST_AEROBIC_INSERTS):
        assert _directive(view, aerobic, 17) is PlacementDirective.ALLOW


# --------------------------------------------------------------------------- #
# 5. Low-physical between hard contacts deprioritized and loses to ALLOW       #
# --------------------------------------------------------------------------- #
def test_low_physical_between_hard_contacts_deprioritized_and_loses_to_allow():
    view = sequence_legality([], resolved_contacts=[(20, "hard"), (14, "hard")])
    assert _directive(view, "footwork_walkthrough", 17) is PlacementDirective.DEPRIORITIZE

    # Given both a DEPRIORITIZE low-physical and an ALLOW aerobic option, the
    # filler-layer filter keeps only the ALLOW option.
    legal = _legal_support_keys(view, {"footwork_walkthrough", "aerobic_shadow_flow"}, 17)
    assert legal == {"aerobic_shadow_flow"}

    # When only low-physical options remain, DEPRIORITIZE survives (never FORBID).
    only_physical = _legal_support_keys(view, {"footwork_walkthrough", "movement_quality"}, 17)
    assert only_physical == {"footwork_walkthrough", "movement_quality"}


# --------------------------------------------------------------------------- #
# 6. Cross-week hard-contact adjacency is respected                            #
# --------------------------------------------------------------------------- #
def test_cross_week_hard_contact_adjacency_respected():
    # Week 2 Sunday (D-15) is an effective hard contact; week 3 Monday (D-14) is
    # the immediately adjacent day in the next planner week. The legality view is
    # built from the whole map, so the Monday query still sees the Sunday contact.
    week_two = _week(
        week_index=2,
        contacts=[_contact("Sunday")],
        calendar_days=[{"weekday": "Sunday", "d_day": 15}],
        declared=["Sunday"],
    )
    week_three = _week(
        week_index=3,
        calendar_days=[{"weekday": "Monday", "d_day": 14}],
        declared=["Monday"],
    )
    weekly = {"weeks": [week_two, week_three]}
    view = _legality(weekly, week_three, ordinal=2)

    # A physical low-load filler immediately after hard contact is allowed as
    # low-cost, but a *meaningful* stressor / additional contact is not — the key
    # point is that the adjacency is visible across the week boundary at all.
    contacts = view.contact_offsets()
    assert 15 in contacts
    # Aerobic the day after hard contact -> allowed (post-hard low cost), proving
    # the neighbouring contact is seen rather than ignored.
    decision = view.decision_for_profile(role_load_profile({"role_key": "aerobic_shadow_flow"}), 14)
    assert decision.reason_code == "post_hard_contact_low_cost"


# --------------------------------------------------------------------------- #
# 7. Raw declared hard day resolving to technical/off uses resolved load       #
# --------------------------------------------------------------------------- #
def test_declared_hard_day_resolving_to_technical_uses_resolved_load():
    # Declared hard Tuesday, but the resolver converted it to a technical touch.
    week = _week(
        roles=[_hard_role("Tuesday")],
        contacts=[_contact("Tuesday", status="convert_to_technical_suggested", load="technical")],
    )
    events = cc.build_events({"weeks": [week]})
    tuesday = [e for e in events if e.position == -29]
    assert len(tuesday) == 1
    # Resolved technical, NOT hard: still exclusive on its own day, but it must
    # not radiate the hard-contact adjacency rule.
    assert tuesday[0].profile.load_class is LoadClass.TECHNICAL_CONTACT


def test_declared_hard_day_resolving_to_off_is_not_a_contact():
    week = _week(
        roles=[_hard_role("Tuesday")],
        contacts=[_contact("Tuesday", status="suppressed", load="none")],
    )
    events = cc.build_events({"weeks": [week]})
    # A suppressed declared hard day produces no contact event at all.
    assert [e for e in events if e.position == -29] == []


# --------------------------------------------------------------------------- #
# 8. Suppressed resolved contact creates no hard-contact recovery pressure     #
# --------------------------------------------------------------------------- #
def test_suppressed_resolved_contact_creates_no_recovery_pressure():
    # Tuesday declared hard but resolved to off: the day is now a legal home for
    # a normal filler, so a physical insert may land there.
    week = _week(
        roles=[_hard_role("Tuesday")],
        contacts=[_contact("Tuesday", status="suppressed", load="none")],
        calendar_days=_calendar({"tuesday": 29}),
        declared=["Tuesday"],
    )
    weekly = {"weeks": [week]}
    view = _legality(weekly, week)
    # Nothing forbidden on the suppressed day.
    assert view.role_is_forbidden({"role_key": "footwork_walkthrough"}, 29) is False
    assert view.contact_offsets() == set()

    apply_camp_week_fillers(
        weekly, {"fatigue": "low", "weaknesses": ["footwork"], "hard_sparring_days": ["Tuesday"]}
    )
    fillers = _fillers(week)
    assert any(f["scheduled_day_hint"] == "Tuesday" for f in fillers)


# --------------------------------------------------------------------------- #
# 9. Direct D-13 gap fillers use the same shared load semantics                #
# --------------------------------------------------------------------------- #
def test_direct_d13_gap_fillers_use_shared_load_semantics():
    athlete = {
        "sport": "boxing",
        "status": "professional",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "fatigue": "low",
        "fatigue_level": "low",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "days_until_fight": 13,
        "plan_creation_weekday": "monday",
    }
    sequence = apply_gap_fill_inserts(
        [
            {"role_key": "strength_touch_day", "category": "strength", "scheduled_day_hint": "monday",
             "countdown_offset": 13, "countdown_label": "D-13", "scheduled_countdown_label": "D-13"},
            {"role_key": "fight_week_freshness_day", "category": "recovery", "scheduled_day_hint": "monday",
             "countdown_offset": 4, "countdown_label": "D-4", "scheduled_countdown_label": "D-4"},
        ],
        athlete,
    )
    aerobic = [
        r for r in sequence
        if r.get("category") == "support_insert" and r["role_key"] in LOW_COST_AEROBIC_INSERTS
    ]
    # Aerobic maintenance never lands on a resolved contact weekday.
    for insert in aerobic:
        weekday = str(insert.get("scheduled_day_hint") or insert.get("real_weekday") or "").lower()
        assert weekday not in {"tuesday", "thursday"}


# --------------------------------------------------------------------------- #
# 10. Long-camp finished D-13 tail remains immutable under the governor        #
# --------------------------------------------------------------------------- #
def test_long_camp_finished_d13_tail_remains_immutable():
    # A D-13 tail role placed on a day the policy would otherwise forbid must not
    # be relocated or suppressed: tail ownership is immutable after handoff.
    tail_role = {
        "role_key": "neural_primer_day",
        "category": "strength",
        "scheduled_day_hint": "Tuesday",
        "session_index": 1,
        "stress_class": "meaningful_stress",
        "cost_class": "medium",
        "late_fight_tail_owned": True,
        "countdown_offset": 13,
        "scheduled_countdown_label": "D-13",
    }
    week = _week(
        roles=[tail_role],
        contacts=[_contact("Tuesday")],
        calendar_days=_calendar({"monday": 14, "tuesday": 13}),
        declared=["Monday", "Tuesday"],
    )
    week["late_fight_tail_days"] = [13]
    apply_final_calendar_integrity({"weeks": [week]})
    assert tail_role in week["session_roles"]
    assert "calendar_integrity_relocation" not in tail_role
    assert week["suppressed_roles"] == []


# --------------------------------------------------------------------------- #
# 11. Every currently reachable filler role key classifies                     #
# --------------------------------------------------------------------------- #
def test_all_reachable_filler_role_keys_classify():
    keys = ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS | PHYSICAL_INSERTS | LOW_COST_AEROBIC_INSERTS
    for key in sorted(keys):
        assert role_load_profile({"role_key": key}) is not None, key
    # coordination_support classifies from its canonical fields.
    assert role_load_profile(_COORDINATION_LEGALITY_ROLE) is not None


# --------------------------------------------------------------------------- #
# 12. Extraction preserved the governor's canonical event construction         #
# --------------------------------------------------------------------------- #
def test_adapter_events_match_governor_contact_dedup():
    # A visible hard_sparring_day mirror and the resolved plan entry describe one
    # appointment: the adapter must emit exactly one contact event, not two.
    week = _week(roles=[_hard_role("Tuesday")], contacts=[_contact("Tuesday")])
    events = cc.build_events({"weeks": [week]})
    tuesday = [e for e in events if e.position == -29]
    assert len(tuesday) == 1
    assert tuesday[0].profile.load_class is LoadClass.HARD_CONTACT


# --------------------------------------------------------------------------- #
# 13. A filler inserted upstream is not cleaned up by the final governor       #
# --------------------------------------------------------------------------- #
def test_upstream_filler_not_cleaned_by_final_governor():
    # Tuesday hard contact + one clean free day (Thursday). The upstream filler
    # must land legally and survive the final governor verification untouched.
    week = _week(
        roles=[_hard_role("Tuesday"), {
            "role_key": "primary_strength_day", "category": "strength",
            "scheduled_day_hint": "Monday", "stress_class": "meaningful_stress", "cost_class": "medium",
        }],
        contacts=[_contact("Tuesday")],
        calendar_days=_calendar({"monday": 30, "tuesday": 29, "thursday": 27}),
        declared=["Monday", "Tuesday", "Thursday"],
        unused=[{"day": "Thursday", "role": "off_day"}],
    )
    weekly = {"weeks": [week]}
    apply_camp_week_fillers(weekly, {"fatigue": "low", "hard_sparring_days": ["Tuesday"]})
    fillers_before = [(f["role_key"], f["scheduled_day_hint"]) for f in _fillers(week)]
    assert fillers_before, "expected at least one upstream filler"

    apply_final_calendar_integrity(weekly)

    integrity = weekly["calendar_integrity"]
    assert integrity["unresolved_forbidden"] == 0
    assert integrity["relocated_roles"] == 0
    assert integrity["suppressed_roles"] == 0
    # No upstream filler was relocated or dropped by the governor.
    fillers_after = [(f["role_key"], f["scheduled_day_hint"]) for f in _fillers(week)]
    assert fillers_after == fillers_before
    for f in _fillers(week):
        assert "calendar_integrity_relocation" not in f


# --------------------------------------------------------------------------- #
# 14. Late gap fillers consume canonical resolved contact, not a re-derivation #
# --------------------------------------------------------------------------- #
def _late_athlete(**overrides: object) -> dict:
    athlete = {
        "sport": "boxing",
        "status": "professional",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "fatigue": "low",
        "fatigue_level": "low",
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
    }
    athlete.update(overrides)
    return athlete


def test_late_fight_hard_contact_only_where_canonical_outcome_is_hard():
    # A resolved contact is `hard` ONLY where the canonical late-fight owner
    # (_late_fight_permission_policy, which resolves through sparring_dose_planner)
    # kept that weekday hard AND the occurrence is the hard-allowed one. The filler
    # never decides hard-vs-technical from countdown status alone.
    athlete = _late_athlete()
    policy = _late_fight_permission_policy(21, athlete)
    outcome_by_day = {
        str(a.get("day") or "").strip().lower(): str(a.get("outcome") or "")
        for a in policy["declared_hard_day_actions"]
    }
    occurrences = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday="monday",
        days_until_fight=21,
        declared_weekdays=["tuesday", "thursday"],
    )
    weekday_by_offset = {e["offset"]: str(e["weekday"]).lower() for e in occurrences}
    status_by_offset = {e["offset"]: str(e["status"]) for e in occurrences}

    resolved = resolve_late_fight_contacts(21, athlete)
    assert resolved, "expected declared hard days to resolve to contact occurrences"
    for offset, load in resolved:
        assert load in {"hard", "technical"}
        if load == "hard":
            weekday = weekday_by_offset[offset]
            assert outcome_by_day.get(weekday) == "hard_sparring_day"
            assert status_by_offset[offset] == "hard_allowed"


# --------------------------------------------------------------------------- #
# 15. Coordination prefers an ALLOW day over a DEPRIORITIZE declared support day #
# --------------------------------------------------------------------------- #
def test_coordination_prefers_allow_day_over_deprioritized_support_day():
    strength = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "scheduled_day_hint": "Monday",
        "stress_class": "meaningful_stress",
        "cost_class": "medium",
    }
    week = _week(
        roles=[strength, _hard_role("Tuesday"), _hard_role("Friday")],
        contacts=[_contact("Tuesday"), _contact("Friday")],
        calendar_days=_calendar(
            {"monday": 30, "tuesday": 29, "wednesday": 28, "thursday": 27, "friday": 26}
        ),
        declared=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    )
    week["declared_support_work_days"] = ["Wednesday"]
    weekly = {"weeks": [week]}
    view = _legality(weekly, week)

    # Wednesday (between the two hard contacts) is DEPRIORITIZE; Monday (the day
    # before hard, carrying a strength anchor) is ALLOW.
    assert view.decision_for_role(_COORDINATION_LEGALITY_ROLE, 28).directive is PlacementDirective.DEPRIORITIZE
    assert view.decision_for_role(_COORDINATION_LEGALITY_ROLE, 30).directive is PlacementDirective.ALLOW

    slot = _coordination_slot(
        week, week["session_roles"], {"weaknesses": ["coordination"]}, legality=view
    )
    # The ALLOW day wins despite Wednesday being the declared support day.
    assert slot == ("Monday", 30)


# --------------------------------------------------------------------------- #
# 16. apply_gap_fill_inserts consumes injected resolved contacts (owned upstream)
# --------------------------------------------------------------------------- #
def _ll_session(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength" if role_key == "strength_touch_day" else "recovery",
        "role_key": role_key,
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def test_apply_gap_fill_consumes_injected_resolved_contacts_and_default_matches_owner():
    athlete = _late_athlete(key_goals=["conditioning"], weaknesses=["gas_tank"])
    sessions = [_ll_session(21), _ll_session(6, "fight_week_freshness_day")]

    # Default path: the late-fight owner resolves the contacts.
    default_seq = apply_gap_fill_inserts([dict(s) for s in sessions], athlete)
    # Injected path: caller passes the owner's resolved contacts explicitly.
    owner_contacts = resolve_late_fight_contacts(21, athlete)
    injected_seq = apply_gap_fill_inserts(
        [dict(s) for s in sessions], athlete, resolved_contacts=owner_contacts
    )

    def shape(seq: list[dict]) -> list[tuple]:
        return [(r.get("role_key"), r.get("countdown_offset")) for r in seq]

    def aerobic(seq: list[dict]) -> list[dict]:
        return [
            r for r in seq
            if r.get("category") == "support_insert" and r["role_key"] in LOW_COST_AEROBIC_INSERTS
        ]

    # Consuming the injected owner contacts is identical to the default.
    assert shape(default_seq) == shape(injected_seq)

    # The filler genuinely consumes the injected value, not athlete_model: with
    # no contacts a conditioning athlete keeps an aerobic maintenance slot; with
    # every day injected as hard contact, aerobic is forbidden everywhere.
    none_seq = apply_gap_fill_inserts([dict(s) for s in sessions], athlete, resolved_contacts=[])
    all_hard = [(offset, "hard") for offset in range(1, 22)]
    blocked_seq = apply_gap_fill_inserts([dict(s) for s in sessions], athlete, resolved_contacts=all_hard)
    assert aerobic(none_seq), "conditioning goal keeps an aerobic slot when unconstrained"
    assert not aerobic(blocked_seq), "every-day-hard injection forbids aerobic everywhere"


# --------------------------------------------------------------------------- #
# 17. Resolved contact preserves the full dose vocabulary (not hard/technical)  #
# --------------------------------------------------------------------------- #
def test_reduced_contact_event_preserved_and_off_dropped():
    # The shared adapter must not collapse the resolver's vocabulary: a reduced
    # contact stays REDUCED_CONTACT and a suppressed/off contact makes no event.
    events = cc.sequence_events([], resolved_contacts=[(20, "reduced"), (10, "none")])
    by_pos = {e.position: e.profile.load_class for e in events}
    assert by_pos.get(-20) is LoadClass.REDUCED_CONTACT
    assert -10 not in by_pos


def test_resolve_late_fight_contacts_preserves_reduced_and_suppressed(monkeypatch):
    # Force the dose resolver to a reduced Tuesday and a suppressed Thursday; the
    # owner resolver must surface Tuesday as REDUCED at its hard-allowed occurrence
    # and emit no occurrence at all for the suppressed Thursday. It must not
    # reinterpret "reduced" as "technical" or invent a phantom technical contact
    # for the suppressed day.
    def fake_plan(*, days_until_fight, athlete_model, declared_hard_days=None, **_kw):
        return [
            {"day": "tuesday", "status": "deload_suggested", "effective_load": "reduced"},
            {"day": "thursday", "status": "suppressed", "effective_load": "none"},
        ]

    monkeypatch.setattr(_late_fight_module, "_late_fight_hard_sparring_plan", fake_plan)
    athlete = _late_athlete(hard_sparring_days=["tuesday", "thursday"], days_until_fight=21)

    contacts = dict(resolve_late_fight_contacts(21, athlete))
    # Tuesday hard-allowed occurrence (D-20) keeps the resolved REDUCED class.
    assert contacts.get(20) == "reduced"
    # The D-17 ban caps reduced to technical inside the taper (D-13, D-6), never hard.
    assert contacts.get(13) == "technical"
    assert contacts.get(6) == "technical"
    assert "hard" not in contacts.values()
    # Suppressed Thursday (D-18 / D-11 / D-4) produces no contact occurrence.
    assert not ({18, 11, 4} & set(contacts))


# --------------------------------------------------------------------------- #
# 18. Missing plan_creation_weekday is derived from fight_date, not collapsed   #
# --------------------------------------------------------------------------- #
def test_resolve_late_fight_contacts_derives_creation_weekday_from_fight_date():
    # fight_date known, plan_creation_weekday absent, Tuesday + Friday declared.
    # The resolver must derive the creation weekday from fight_date (via the
    # canonical owner) and place each declared day on its REAL countdown
    # occurrence, not collapse both onto days_until_fight.
    fight = dt.date(2026, 2, 13)  # Friday
    athlete = {
        "sport": "boxing",
        "status": "professional",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "hard_sparring_days": ["tuesday", "friday"],
        "fatigue": "low",
        "fatigue_level": "low",
        "fight_date": fight.isoformat(),
        # plan_creation_weekday intentionally omitted.
    }
    resolved = resolve_late_fight_contacts(13, athlete)
    offsets = {offset for offset, _load in resolved}
    # Real, distinct occurrences — not both collapsed onto D-13 (days_until_fight).
    assert len(offsets) >= 2
    assert 13 not in offsets

    # End-to-end: the gap filler protects those real contact days — no physical or
    # aerobic support insert lands on a genuine coach-owned contact occurrence.
    sessions = [_ll_session(13), _ll_session(2, "fight_week_freshness_day")]
    seq = apply_gap_fill_inserts(
        [dict(s) for s in sessions],
        dict(athlete, key_goals=["conditioning"], weaknesses=["gas_tank"]),
    )
    for role in seq:
        if role.get("category") != "support_insert":
            continue
        if int(role.get("countdown_offset") or 0) in offsets:
            assert role["role_key"] not in PHYSICAL_INSERTS | LOW_COST_AEROBIC_INSERTS


# --------------------------------------------------------------------------- #
# 19. A visible mirror carrying a contact stamp cannot become a 2nd contact     #
# --------------------------------------------------------------------------- #
def _stamped_hard_mirror(day: str) -> dict:
    # A visible hard_sparring_day role that ALSO carries an explicit resolved
    # contact stamp. On its own it classifies to HARD_CONTACT, so the mirror
    # short-circuit in classify_role is what stops it becoming a second contact.
    return {
        "role_key": "hard_sparring_day",
        "category": "sparring",
        "scheduled_day_hint": day,
        "status": "hard_as_planned",
        "effective_load": "hard",
    }


def test_stamped_mirror_role_alone_would_classify_as_contact():
    # Guard: prove the ordering in classify_role is load-bearing. If the stamped
    # mirror did not classify to a contact profile on its own, the regressions
    # below would pass trivially.
    stamped = _stamped_hard_mirror("Tuesday")
    assert role_load_profile(stamped).load_class is LoadClass.HARD_CONTACT
    # The adapter suppresses it: resolved contact is owned only by hard_sparring_plan.
    assert cc.classify_role(stamped) is None


def test_resolved_sparring_plus_stamped_mirror_counts_as_one_contact():
    # One sparring occurrence described twice (resolved plan entry + its visible
    # stamped mirror) must yield exactly ONE contact event, never two.
    week = _week(roles=[_stamped_hard_mirror("Tuesday")], contacts=[_contact("Tuesday")])
    tuesday = [e for e in cc.build_events({"weeks": [week]}) if e.position == -29]
    assert len(tuesday) == 1
    assert tuesday[0].profile.load_class is LoadClass.HARD_CONTACT


def test_stamped_mirror_cannot_resurrect_suppressed_or_omitted_contact():
    # When the resolved plan suppresses (or omits) the day, a visible stamped
    # mirror must NOT resurrect a contact event.
    suppressed = _week(
        roles=[_stamped_hard_mirror("Tuesday")],
        contacts=[_contact("Tuesday", status="suppressed", load="none")],
    )
    omitted = _week(roles=[_stamped_hard_mirror("Tuesday")], contacts=[])
    assert [e for e in cc.build_events({"weeks": [suppressed]}) if e.position == -29] == []
    assert [e for e in cc.build_events({"weeks": [omitted]}) if e.position == -29] == []


# --------------------------------------------------------------------------- #
# 20. Independent genuine contact occurrences still count independently          #
# --------------------------------------------------------------------------- #
def test_independent_contacts_count_independently():
    # Two genuinely distinct resolved occurrences (Tue D-29 + Thu D-27) each own
    # their day; the mirror de-dup must not collapse them into one.
    week = _week(contacts=[_contact("Tuesday"), _contact("Thursday")])
    events = cc.build_events({"weeks": [week]})
    contacts = [e for e in events if e.profile.load_class in CONTACT_LOAD_CLASSES]
    assert sorted(-e.position for e in contacts) == [27, 29]
    view = _legality({"weeks": [week]}, week)
    assert view.contact_offsets() == {27, 29}


# --------------------------------------------------------------------------- #
# 21. Suppressed/inactive resolved contact does not pollute gap-fill contacts    #
# --------------------------------------------------------------------------- #
def test_resolved_contact_offsets_excludes_off_loads():
    # The shared helper the gap-fill consumes drops none/suppressed/off and keeps
    # the real contact vocabulary, so there is one interpretation of "active
    # contact" for both the filler pre-check and the governor.
    offsets = resolved_contact_offsets(
        [(20, "hard"), (14, "none"), (10, "suppressed"), (7, "technical"), (3, "reduced")]
    )
    assert offsets == {20, 7, 3}


def test_gap_fill_suppressed_injected_contact_is_inert_unlike_hard():
    # End-to-end: none/suppressed injected contacts must not pollute contact_offsets.
    # A conditioning athlete keeps an aerobic maintenance slot when the injected
    # contacts are all none/suppressed (identical to no contacts), but loses it
    # when they are hard — proving the OFF loads are dropped, not counted.
    athlete = _late_athlete(key_goals=["conditioning"], weaknesses=["gas_tank"])
    sessions = [_ll_session(21), _ll_session(6, "fight_week_freshness_day")]

    def aerobic(seq: list[dict]) -> list[dict]:
        return [
            r for r in seq
            if r.get("category") == "support_insert" and r["role_key"] in LOW_COST_AEROBIC_INSERTS
        ]

    def shape(seq: list[dict]) -> list[tuple]:
        return [(r.get("role_key"), r.get("countdown_offset")) for r in seq]

    empty = apply_gap_fill_inserts([dict(s) for s in sessions], athlete, resolved_contacts=[])
    all_none = apply_gap_fill_inserts(
        [dict(s) for s in sessions], athlete, resolved_contacts=[(o, "none") for o in range(1, 22)]
    )
    all_suppressed = apply_gap_fill_inserts(
        [dict(s) for s in sessions], athlete, resolved_contacts=[(o, "suppressed") for o in range(1, 22)]
    )
    all_hard = apply_gap_fill_inserts(
        [dict(s) for s in sessions], athlete, resolved_contacts=[(o, "hard") for o in range(1, 22)]
    )

    assert aerobic(empty), "sanity: conditioning goal keeps an aerobic slot when unconstrained"
    # OFF loads are inert: injecting them is identical to injecting nothing.
    assert shape(all_none) == shape(empty)
    assert shape(all_suppressed) == shape(empty)
    # Hard everywhere DOES block aerobic, proving the contrast is real.
    assert not aerobic(all_hard)


# --------------------------------------------------------------------------- #
# 22. Contact-load vocabulary has exactly one authoritative source              #
# --------------------------------------------------------------------------- #
def test_contact_load_vocabulary_single_source_of_truth():
    # combat_load_policy owns the canonical set and exports it publicly.
    assert "CONTACT_LOAD_CLASSES" in clp.__all__
    assert CONTACT_LOAD_CLASSES is clp.CONTACT_LOAD_CLASSES
    # The shared adapter and the final governor consume that one object — not
    # private per-module copies that could silently drift apart.
    assert cc.CONTACT_LOAD_CLASSES is clp.CONTACT_LOAD_CLASSES
    assert ci.CONTACT_LOAD_CLASSES is clp.CONTACT_LOAD_CLASSES
    # No module keeps a shadow definition of the contact-load set.
    assert not hasattr(cc, "_CONTACT_LOADS")
    assert not hasattr(ci, "_CONTACT_LOADS")
