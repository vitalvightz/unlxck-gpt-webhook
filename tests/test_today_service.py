"""Contract-to-storage integration tests for the Today/Overview service.

These exercise api/services/today_service.py against the in-memory FakeStore with
an injected ``now``, so training-day boundaries and recommendation validity are
deterministic without a live clock or database.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from api.contracts.completion import completion_landing_state, completion_status_of
from api.services.today_service import (
    build_today_command_view,
    submit_today_checkin,
    upsert_session_completion,
)
from tests.support import FakeStore

NY = "America/New_York"
ATHLETE = "athlete-1"
PLAN = "plan-1"


def _store_with_plan(plan_id: str = PLAN, athlete_id: str = ATHLETE) -> FakeStore:
    store = FakeStore()
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    return store


def _checkin_payload(**overrides) -> dict:
    base = {
        "plan_id": PLAN,
        "sleep": "good",
        "body": "normal",
        "pain": "none",
        "phase": "GPP",
        "active_injury": "none",
        "previous_session": "none",
        "sharp_pain": False,
        "instability": False,
        "swelling": False,
        "neurological_symptoms": False,
        "illness_symptoms": False,
        "cannot_warm_into_movement": False,
        "worse_next_day_pain": False,
    }
    return {**base, **overrides}


class TestTrainingDayPersistence:
    def test_0359_local_stores_previous_training_day(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 3, 59, tzinfo=ZoneInfo(NY))
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone=NY, payload=_checkin_payload(), now=now
        )
        assert row["training_day"] == "2026-06-17"

    def test_0400_local_stores_current_training_day(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 4, 0, tzinfo=ZoneInfo(NY))
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone=NY, payload=_checkin_payload(), now=now
        )
        assert row["training_day"] == "2026-06-18"

    def test_missing_timezone_fallback_does_not_crash(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone=None, payload=_checkin_payload(), now=now
        )
        assert row["training_day"] == "2026-06-18"


class TestCheckinSubmit:
    def test_checkin_and_recommendation_persist(self):
        store = _store_with_plan()
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(sleep="poor")
        )
        assert store.today_checkins[ATHLETE], "check-in row must persist"
        assert row["recommendation_state"] == "modify"
        assert row["recommendation_reason"] == "Poor sleep; use the modified option today."
        assert "poor_sleep" in row["recommendation_triggers"]

    def test_same_day_duplicate_upserts_single_row(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(), now=now)
        second = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(sleep="poor"), now=now
        )
        assert len(store.today_checkins[ATHLETE]) == 1
        assert second["recommendation_state"] == "modify"

    def test_client_supplied_recommendation_is_ignored(self):
        store = _store_with_plan()
        # Client tries to force train_as_planned, but pain=high is a hard override.
        payload = _checkin_payload(pain="high", recommendation_state="train_as_planned")
        row = submit_today_checkin(store, athlete_id=ATHLETE, athlete_timezone="", payload=payload)
        assert row["recommendation_state"] == "pull_back"


class TestRecommendationValidity:
    def test_same_training_day_recommendation_is_live(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(sleep="poor"), now=now
        )
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)
        assert view.today.recommendation_state == "modify"
        assert view.today.recommendation_reason

    def test_previous_training_day_returns_not_checked_in(self):
        store = _store_with_plan()
        submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(sleep="poor"),
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        # Next day: the prior recommendation has expired.
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_reason is None


class TestCommandView:
    def test_no_active_plan_returns_intake_cta(self):
        store = FakeStore()  # no plan seeded
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.active_plan == {}
        assert [a.id for a in view.quick_actions] == ["complete_intake"]

    def test_active_plan_without_checkin_is_not_checked_in(self):
        store = _store_with_plan()
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.active_plan.get("id") == PLAN
        assert view.today.recommendation_state == "not_checked_in"

    def test_missing_structured_plan_does_not_crash(self):
        # Minimal plan row (no planning_brief) must degrade, not raise.
        store = _store_with_plan()
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.today.next_session == {}
        assert view.today.completion_status == "not_started"


class TestSessionCompletion:
    def _payload(self, **overrides) -> dict:
        base = {"plan_id": PLAN, "session_id": "sess-1", "status": "started"}
        return {**base, **overrides}

    def test_start_sets_started_at(self):
        store = _store_with_plan()
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="started")
        )
        assert row["status"] == "started"
        assert row["started_at"]
        assert completion_landing_state(completion_status_of(row)) == "resume"

    def test_done_sets_completed_at(self):
        store = _store_with_plan()
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done")
        )
        assert row["status"] == "done"
        assert row["completed_at"]
        assert completion_landing_state(completion_status_of(row)) == "completed"

    def test_modified_requires_modification_reason(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(
                store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="modified")
            )
        assert exc.value.status_code == 422
        row = upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="modified", modification_reason="swapped to recovery"),
        )
        assert row["status"] == "modified"
        assert row["completed_at"]

    def test_skipped_is_allowed(self):
        store = _store_with_plan()
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="skipped")
        )
        assert row["status"] == "skipped"
        assert completion_landing_state(completion_status_of(row)) == "completed"

    def test_duplicate_completion_upserts_single_row(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="started"), now=now
        )
        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="done"),
            now=now,
        )
        assert len(store.session_completions[ATHLETE]) == 1
        assert store.session_completions[ATHLETE][0]["status"] == "done"
