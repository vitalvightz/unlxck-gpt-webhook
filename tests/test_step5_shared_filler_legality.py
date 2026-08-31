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

from fightcamp import calendar_context as cc
from fightcamp.calendar_context import CalendarLegalityView, sequence_legality
from fightcamp.calendar_integrity import apply_final_calendar_integrity
from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.camp_week_fillers_impl import _COORDINATION_LEGALITY_ROLE
from fightcamp.combat_load_policy import (
    LoadClass,
    PlacementDirective,
    role_load_profile,
)
from fightcamp.gap_fill_inserts import (
    LOW_COST_AEROBIC_INSERTS,
    LOW_COST_RECOVERY_INSERTS,
    PHYSICAL_INSERTS,
    ZERO_COST_INSERTS,
    apply_gap_fill_inserts,
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
    # shared filter keeps only the ALLOW option.
    legal = view.legal_support_keys({"footwork_walkthrough", "aerobic_shadow_flow"}, 17)
    assert legal == {"aerobic_shadow_flow"}

    # When only low-physical options remain, DEPRIORITIZE survives (never FORBID).
    only_physical = view.legal_support_keys({"footwork_walkthrough", "movement_quality"}, 17)
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
