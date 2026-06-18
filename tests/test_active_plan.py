import pytest
from fastapi import HTTPException

from api.services.active_plan import resolve_active_plan, set_active_plan


class Store:
    def __init__(self, plans, active=None):
        self.plans = plans
        self.active = active
        self.set_to = None

    def list_user_plans(self, athlete_id):
        return [p for p in self.plans if p.get("athlete_id") == athlete_id]

    def get_plan_for_athlete(self, plan_id, athlete_id):
        return next((p for p in self.plans if p.get("id") == plan_id and p.get("athlete_id") == athlete_id), None)

    def get_active_plan_id(self, athlete_id):
        return self.active

    def set_active_plan_id(self, athlete_id, plan_id):
        self.set_to = plan_id
        self.active = plan_id


def plan(id, status="ready", created_at="2026-01-01T00:00:00Z", athlete_id="ath"):
    return {"id": id, "status": status, "created_at": created_at, "athlete_id": athlete_id}


def test_no_plans_no_active_plan():
    assert resolve_active_plan(Store([]), "ath").plan is None


def test_one_ready_plan_is_active():
    assert resolve_active_plan(Store([plan("p1")]), "ath").plan_id == "p1"


def test_multiple_ready_plans_are_deterministic_latest_fallback():
    store = Store([plan("old", created_at="2026-01-01"), plan("new", created_at="2026-02-01")])
    result = resolve_active_plan(store, "ath")
    assert result.plan_id == "new"
    assert result.source == "auto_latest_eligible"


def test_explicit_active_plan_wins_over_newer_unrelated_ready_plan():
    store = Store([plan("old", created_at="2026-01-01"), plan("new", created_at="2026-02-01")], active="old")
    assert resolve_active_plan(store, "ath").plan_id == "old"


def test_archived_explicit_active_plan_is_not_active_and_falls_back():
    store = Store([plan("old", "archived", "2026-02-01"), plan("next", "ready", "2026-01-01")], active="old")
    assert resolve_active_plan(store, "ath").plan_id == "next"


@pytest.mark.parametrize("status", ["review_required", "medical_hold", "generated", "failed", "archived"])
def test_non_displayable_statuses_cannot_be_active(status):
    assert resolve_active_plan(Store([plan("p1", status)]), "ath").plan is None


def test_publishable_with_flags_can_be_active():
    assert resolve_active_plan(Store([plan("p1", "publishable_with_flags")]), "ath").plan_id == "p1"


def test_overlapping_dates_do_not_block_selection():
    store = Store([
        {**plan("p1", created_at="2026-01-01"), "fight_date": "2026-07-01"},
        {**plan("p2", created_at="2026-02-01"), "fight_date": "2026-07-01"},
    ])
    assert resolve_active_plan(store, "ath").plan_id == "p2"


def test_set_active_rejects_non_owned_plan():
    with pytest.raises(HTTPException) as exc:
        set_active_plan(Store([plan("p1", athlete_id="other")]), "ath", "p1")
    assert exc.value.status_code == 404


def test_set_active_rejects_archived_plan():
    with pytest.raises(HTTPException) as exc:
        set_active_plan(Store([plan("p1", "archived")]), "ath", "p1")
    assert exc.value.status_code == 409


def test_set_active_accepts_owned_ready_plan():
    store = Store([plan("p1")])
    assert set_active_plan(store, "ath", "p1")["id"] == "p1"
    assert store.set_to == "p1"
