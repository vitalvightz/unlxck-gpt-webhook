"""Unit tests for the central active-plan resolver (Block 4 / PR #1800).

Exercises eligibility, explicit-vs-fallback selection, archive handling, and the
new-plan edge cases against the in-memory FakeStore.
"""

from api.active_plan import (
    plan_is_eligible_for_active,
    resolve_active_plan,
    resolve_active_plan_row,
)
from tests.support import FakeStore

ATHLETE = "athlete-1"
PLAN_A = "11111111-1111-1111-1111-111111111111"
PLAN_B = "22222222-2222-2222-2222-222222222222"
PLAN_C = "33333333-3333-3333-3333-333333333333"


def _store() -> FakeStore:
    store = FakeStore()
    store.profiles[ATHLETE] = {"id": ATHLETE, "email": "ari@example.com"}
    return store


def _seed(store: FakeStore, plan_id: str, *, status: str = "ready", created_at: str, athlete_id: str = ATHLETE) -> None:
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": status,
        "plan_name": f"Camp {plan_id[:1]}",
        "created_at": created_at,
    }


def _row(status: str) -> dict:
    return {
        "id": PLAN_A,
        "athlete_id": ATHLETE,
        "status": status,
        "created_at": "2026-06-01T00:00:00+00:00",
    }


class TestEligibility:
    def test_ready_is_eligible(self):
        assert plan_is_eligible_for_active(_row("ready"))

    def test_publishable_with_flags_is_eligible(self):
        assert plan_is_eligible_for_active(_row("publishable_with_flags"))

    def test_non_displayable_statuses_are_not_eligible(self):
        for status in (
            "generated",
            "review_required",  # normalizes to held_for_review without a report
            "held_for_review",
            "triage_blocked",
            "medical_hold",
            "restricted_rehab_only",
            "needs_review",
            "failed",
            "archived",
        ):
            assert not plan_is_eligible_for_active(_row(status)), status

    def test_missing_plan_is_not_eligible(self):
        assert not plan_is_eligible_for_active(None)


class TestResolution:
    def test_no_plans_yields_no_active_plan(self):
        resolution = resolve_active_plan(_store(), ATHLETE)
        assert resolution.plan_row is None
        assert resolution.source is None
        assert resolution.plan_id is None

    def test_single_ready_plan_is_active(self):
        store = _store()
        _seed(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        resolution = resolve_active_plan(store, ATHLETE)
        assert resolution.plan_id == PLAN_A
        assert resolution.source == "auto_selected"

    def test_multiple_ready_plans_pick_latest_deterministically(self):
        store = _store()
        _seed(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        _seed(store, PLAN_B, created_at="2026-06-10T00:00:00+00:00")
        assert resolve_active_plan(store, ATHLETE).plan_id == PLAN_B
        # Stable across repeated reads.
        assert resolve_active_plan(store, ATHLETE).plan_id == PLAN_B

    def test_explicit_active_plan_wins_over_latest(self):
        store = _store()
        _seed(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        _seed(store, PLAN_B, created_at="2026-06-10T00:00:00+00:00")
        store.set_active_plan_id(ATHLETE, PLAN_A)
        resolution = resolve_active_plan(store, ATHLETE)
        assert resolution.plan_id == PLAN_A
        assert resolution.source == "explicit"

    def test_archived_explicit_active_falls_back_to_next_eligible(self):
        store = _store()
        _seed(store, PLAN_A, status="archived", created_at="2026-06-10T00:00:00+00:00")
        _seed(store, PLAN_B, created_at="2026-06-01T00:00:00+00:00")
        store.set_active_plan_id(ATHLETE, PLAN_A)
        resolution = resolve_active_plan(store, ATHLETE)
        # Archived plan is ineligible, so the resolver never returns it as active.
        assert resolution.plan_id == PLAN_B
        assert resolution.source == "auto_selected"

    def test_review_required_explicit_active_is_rejected(self):
        store = _store()
        _seed(store, PLAN_A, status="held_for_review", created_at="2026-06-10T00:00:00+00:00")
        store.set_active_plan_id(ATHLETE, PLAN_A)
        assert resolve_active_plan(store, ATHLETE).plan_row is None

    def test_medical_hold_cannot_be_active(self):
        store = _store()
        _seed(store, PLAN_A, status="medical_hold", created_at="2026-06-10T00:00:00+00:00")
        assert resolve_active_plan_row(store, ATHLETE) is None

    def test_only_eligible_plan_chosen_when_latest_is_ineligible(self):
        store = _store()
        _seed(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")  # ready, older
        _seed(store, PLAN_B, status="review_required", created_at="2026-06-10T00:00:00+00:00")  # newer, ineligible
        assert resolve_active_plan(store, ATHLETE).plan_id == PLAN_A


class TestNewPlanEdgeCases:
    def test_no_active_plan_then_new_ready_plan_becomes_active(self):
        store = _store()
        _seed(store, PLAN_A, created_at="2026-06-05T00:00:00+00:00")
        assert resolve_active_plan(store, ATHLETE).plan_id == PLAN_A

    def test_existing_active_plan_not_replaced_by_new_unrelated_ready_plan(self):
        store = _store()
        _seed(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        store.set_active_plan_id(ATHLETE, PLAN_A)
        # A newer, unrelated ready plan is generated.
        _seed(store, PLAN_B, created_at="2026-06-20T00:00:00+00:00")
        resolution = resolve_active_plan(store, ATHLETE)
        assert resolution.plan_id == PLAN_A, "explicit active plan must not be silently replaced"

    def test_overlapping_dates_do_not_block_selection(self):
        store = _store()
        # Two plans with the same fight date / overlapping camp window.
        store.plans[PLAN_A] = {
            "id": PLAN_A, "athlete_id": ATHLETE, "status": "ready",
            "fight_date": "2026-09-01", "created_at": "2026-06-01T00:00:00+00:00",
        }
        store.plans[PLAN_B] = {
            "id": PLAN_B, "athlete_id": ATHLETE, "status": "ready",
            "fight_date": "2026-09-01", "created_at": "2026-06-10T00:00:00+00:00",
        }
        # Overlap is allowed; resolution still deterministic (latest eligible).
        assert resolve_active_plan(store, ATHLETE).plan_id == PLAN_B
