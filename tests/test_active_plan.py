import pytest
from fastapi import HTTPException

from api.services.active_plan import (
    ACTIVE_PLAN_OVERLAP_CONFLICT_CODE,
    ACTIVE_PLAN_OVERLAP_CONFLICT_MESSAGE,
    ACTIVE_PLAN_REPLACE_FAILED_MESSAGE,
    resolve_active_plan,
    set_active_plan,
)
from api.services.today_service import build_today_command_view


class Store:
    def __init__(self, plans, active=None):
        self.plans = plans
        self.active = active
        self.set_to = None
        self.set_calls = []
        self.fail_archive = False

    def list_user_plans(self, athlete_id):
        return [p for p in self.plans if p.get("athlete_id") == athlete_id]

    def get_plan_for_athlete(self, plan_id, athlete_id):
        return next((p for p in self.plans if p.get("id") == plan_id and p.get("athlete_id") == athlete_id), None)

    def get_active_plan_id(self, athlete_id):
        return self.active

    def set_active_plan_id(self, athlete_id, plan_id):
        self.set_calls.append(plan_id)
        self.set_to = plan_id
        self.active = plan_id

    def archive_plan_for_athlete(self, plan_id, athlete_id):
        if self.fail_archive:
            raise HTTPException(status_code=503, detail="archive failed")
        row = self.get_plan_for_athlete(plan_id, athlete_id)
        if row is None:
            raise AssertionError("plan not found")
        row["status"] = "archived"
        return row

    def get_today_checkin(self, athlete_id, plan_id, training_day):
        return None

    def get_session_completion(self, athlete_id, session_id, training_day):
        return None


def plan(id, status="ready", created_at="2026-01-01T00:00:00Z", athlete_id="ath"):
    return {"id": id, "status": status, "created_at": created_at, "athlete_id": athlete_id}


def ranged_plan(
    id,
    *,
    start="2026-06-12",
    end="2026-07-12",
    status="ready",
    created_at="2026-01-01T00:00:00Z",
    athlete_id="ath",
):
    return {
        **plan(id, status=status, created_at=created_at, athlete_id=athlete_id),
        "structured_plan": {
            "weeks": [
                {
                    "start_date": start,
                    "end_date": end,
                    "days": [{"date": start}, {"date": end}],
                }
            ]
        },
    }


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


def test_set_active_blocks_overlapping_current_active_plan_without_choice():
    store = Store(
        [
            ranged_plan("active", start="2026-06-12", end="2026-07-12"),
            ranged_plan("draft", start="2026-06-20", end="2026-07-20"),
        ],
        active="active",
    )

    with pytest.raises(HTTPException) as exc:
        set_active_plan(store, "ath", "draft")

    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "code": ACTIVE_PLAN_OVERLAP_CONFLICT_CODE,
        "message": ACTIVE_PLAN_OVERLAP_CONFLICT_MESSAGE,
    }
    assert store.active == "active"


def test_set_active_allows_non_overlapping_plan():
    store = Store(
        [
            ranged_plan("active", start="2026-06-12", end="2026-07-12"),
            ranged_plan("next", start="2026-07-13", end="2026-08-13"),
        ],
        active="active",
    )

    assert set_active_plan(store, "ath", "next")["id"] == "next"
    assert store.active == "next"


def test_set_active_pause_choice_switches_active_pointer_without_archiving_current_plan():
    current = ranged_plan("active", start="2026-06-12", end="2026-07-12")
    store = Store(
        [
            current,
            ranged_plan("draft", start="2026-06-20", end="2026-07-20"),
        ],
        active="active",
    )

    assert set_active_plan(store, "ath", "draft", overlap_action="pause")["id"] == "draft"
    assert store.active == "draft"
    assert current["status"] == "ready"


def test_set_active_replace_choice_sets_new_active_then_archives_current_plan():
    current = ranged_plan("active", start="2026-06-12", end="2026-07-12")
    store = Store(
        [
            current,
            ranged_plan("draft", start="2026-06-20", end="2026-07-20"),
        ],
        active="active",
    )

    assert set_active_plan(store, "ath", "draft", overlap_action="replace")["id"] == "draft"
    assert store.active == "draft"
    assert store.set_calls == ["draft"]
    assert current["status"] == "archived"


def test_set_active_replace_choice_rolls_back_if_archive_fails():
    current = ranged_plan("active", start="2026-06-12", end="2026-07-12")
    store = Store(
        [
            current,
            ranged_plan("draft", start="2026-06-20", end="2026-07-20"),
        ],
        active="active",
    )
    store.fail_archive = True

    with pytest.raises(HTTPException) as exc:
        set_active_plan(store, "ath", "draft", overlap_action="replace")

    assert exc.value.status_code == 503
    assert exc.value.detail == ACTIVE_PLAN_REPLACE_FAILED_MESSAGE
    assert store.active == "active"
    assert store.set_calls == ["draft", "active"]
    assert current["status"] == "ready"


def test_set_active_rejects_unknown_overlap_action():
    store = Store([ranged_plan("p1")])

    with pytest.raises(HTTPException) as exc:
        set_active_plan(store, "ath", "p1", overlap_action="start_after_current")

    assert exc.value.status_code == 422


def test_set_active_rejects_non_owned_plan():
    with pytest.raises(HTTPException) as exc:
        set_active_plan(Store([plan("p1", athlete_id="other")]), "ath", "p1")
    assert exc.value.status_code == 404


def test_set_active_rejects_archived_plan():
    with pytest.raises(HTTPException) as exc:
        set_active_plan(Store([plan("p1", "archived")]), "ath", "p1")
    assert exc.value.status_code == 409




@pytest.mark.parametrize("status", ["review_required", "medical_hold", "failed"])
def test_set_active_rejects_review_medical_and_failed_plans(status):
    with pytest.raises(HTTPException) as exc:
        set_active_plan(Store([plan("p1", status)]), "ath", "p1")
    assert exc.value.status_code == 409

def test_set_active_accepts_owned_ready_plan():
    store = Store([plan("p1")])
    assert set_active_plan(store, "ath", "p1")["id"] == "p1"
    assert store.set_to == "p1"


def test_set_active_stores_active_plan_id():
    store = Store([plan("p1"), plan("p2")])
    set_active_plan(store, "ath", "p2")
    assert store.active == "p2"


def test_today_command_view_and_active_resolver_use_same_plan():
    store = Store([
        {**plan("old", created_at="2026-01-01"), "plan_name": "Old"},
        {**plan("new", created_at="2026-02-01"), "plan_name": "New"},
    ], active="old")
    resolved = resolve_active_plan(store, "ath")
    today = build_today_command_view(store, athlete_id="ath", athlete_timezone="", now=None)
    assert resolved.plan_id == "old"
    assert today.active_plan.get("id") == "old"
