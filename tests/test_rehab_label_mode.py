"""Tests for resolve_rehab_label_mode — the server-side Rehab/Prehab decision.

The label is driven by the athlete's live injury flags, NOT the intake
"medically cleared" answer. These lock in the two failure modes flagged in
review: a medically-cleared-but-still-injured athlete must stay on "rehab",
and a genuinely-resolved injury (Today "Cleared" → resolved flag) must flip to
"prehab".
"""
from tests.support import FakeStore

from api.plan_mappers import resolve_rehab_label_mode

ATHLETE = "athlete-1"
PLAN = "plan-1"


def _flag(store: FakeStore, *, status: str, plan_id: str | None) -> None:
    store.create_injury_flag(
        ATHLETE,
        {"description": "left achilles", "plan_id": plan_id, "status": status},
    )


def test_no_injury_flags_defaults_to_rehab() -> None:
    store = FakeStore()
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id=PLAN) == "rehab"


def test_open_injury_stays_rehab() -> None:
    store = FakeStore()
    _flag(store, status="open", plan_id=PLAN)
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id=PLAN) == "rehab"


def test_monitoring_injury_stays_rehab() -> None:
    store = FakeStore()
    _flag(store, status="monitoring", plan_id=PLAN)
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id=PLAN) == "rehab"


def test_all_resolved_for_plan_flips_to_prehab() -> None:
    store = FakeStore()
    _flag(store, status="resolved", plan_id=PLAN)
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id=PLAN) == "prehab"


def test_any_active_injury_anywhere_keeps_rehab() -> None:
    # Resolved for this plan, but a second injury is still open (even on another
    # plan). Safety-first: never label active-injury work as prehab.
    store = FakeStore()
    _flag(store, status="resolved", plan_id=PLAN)
    _flag(store, status="open", plan_id="plan-2")
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id=PLAN) == "rehab"


def test_resolved_only_on_other_plan_stays_rehab() -> None:
    # This plan has no tracked injury of its own; a resolved flag on a different
    # plan must not flip this plan to prehab.
    store = FakeStore()
    _flag(store, status="resolved", plan_id="plan-2")
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id=PLAN) == "rehab"


def test_blank_plan_id_defaults_to_rehab() -> None:
    store = FakeStore()
    _flag(store, status="resolved", plan_id=PLAN)
    assert resolve_rehab_label_mode(store, athlete_id=ATHLETE, plan_id="") == "rehab"


def test_store_without_injury_flags_support_defaults_to_rehab() -> None:
    class BareStore:
        pass

    assert (
        resolve_rehab_label_mode(BareStore(), athlete_id=ATHLETE, plan_id=PLAN) == "rehab"
    )
