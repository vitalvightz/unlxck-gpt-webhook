"""Regression tests for fail-safe Today readiness context handling."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api.services import readiness_fail_safe
from api.services.readiness_fail_safe import (
    build_today_command_view,
    submit_today_checkin,
    upsert_session_completion,
)
from tests.support import FakeStore

ATHLETE = "athlete-1"
PLAN = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def _store_with_plan(store_type=FakeStore) -> FakeStore:
    store = store_type()
    store.plans[PLAN] = {
        "id": PLAN,
        "athlete_id": ATHLETE,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    return store


def _checkin_payload(**overrides):
    payload = {
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
    return {**payload, **overrides}


class FailingRecentCheckinsStore(FakeStore):
    def list_today_checkins(self, athlete_id: str, *, limit: int = 14) -> list[dict]:
        raise RuntimeError("check-in history unavailable")


class FailingInjuryFlagsStore(FakeStore):
    def list_injury_flags(
        self,
        athlete_id: str,
        *,
        statuses: tuple = ("open", "monitoring"),
        limit: int = 20,
    ) -> list[dict]:
        raise RuntimeError("injury flags unavailable")


def test_genuine_empty_context_can_still_return_train_as_planned():
    store = _store_with_plan()

    row = submit_today_checkin(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload=_checkin_payload(),
        now=NOW,
    )

    assert row["recommendation_state"] == "train_as_planned"
    assert not any(
        str(trigger).startswith("readiness_context_status:")
        for trigger in row["recommendation_triggers"]
    )


def test_failed_history_read_cannot_return_train_as_planned():
    store = _store_with_plan(FailingRecentCheckinsStore)

    row = submit_today_checkin(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload=_checkin_payload(),
        now=NOW,
    )

    assert row["recommendation_state"] == "modify"
    assert "readiness_context_status:degraded" in row["recommendation_triggers"]
    assert "readiness_context_failure:recent_checkins" in row["recommendation_triggers"]
    assert row["recommendation_reason"].splitlines()[0] == "Readiness check limited."
    assert any(
        warning.startswith("readiness_context_status=degraded")
        for warning in row["warnings"]
    )


def test_context_failure_never_weakens_existing_pull_back():
    store = _store_with_plan(FailingRecentCheckinsStore)

    row = submit_today_checkin(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload=_checkin_payload(pain="high"),
        now=NOW,
    )

    assert row["recommendation_state"] == "pull_back"
    assert "pain is high" in row["recommendation_reason"].lower()
    assert "readiness_context_status:degraded" in row["recommendation_triggers"]
    assert any(
        warning.startswith("readiness_context_status=degraded")
        for warning in row["warnings"]
    )


def test_schedule_resolver_failure_forces_unavailable_modify(monkeypatch):
    store = _store_with_plan()
    store.plans[PLAN]["planning_brief"] = {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "GPP",
                    "calendar_days": [],
                    "hard_sparring_plan": [],
                }
            ]
        }
    }

    def fail_resolve(*args, **kwargs):
        raise RuntimeError("schedule resolver unavailable")

    monkeypatch.setattr(
        readiness_fail_safe._today_service,
        "_plan_schedule_helpers",
        lambda: (
            lambda *args, **kwargs: None,
            lambda value: date.fromisoformat(str(value)),
            fail_resolve,
            fail_resolve,
            lambda *args, **kwargs: None,
        ),
    )

    row = submit_today_checkin(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload=_checkin_payload(),
        now=NOW,
    )

    assert row["recommendation_state"] == "modify"
    assert "readiness_context_status:unavailable" in row["recommendation_triggers"]
    assert "readiness_context_failure:schedule" in row["recommendation_triggers"]


def test_injury_classifier_failure_is_not_treated_as_minor(monkeypatch):
    store = _store_with_plan()
    store.create_injury_flag(
        ATHLETE,
        {
            "body_area": "Head / Neck",
            "description": "neck symptoms",
            "severity": "moderate",
            "status": "open",
        },
    )

    def fail_classification(*args, **kwargs):
        raise RuntimeError("injury classifier unavailable")

    monkeypatch.setattr(
        readiness_fail_safe,
        "injury_consequence_tier",
        fail_classification,
    )

    row = submit_today_checkin(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload=_checkin_payload(),
        now=NOW,
    )

    assert row["recommendation_state"] != "train_as_planned"
    assert "readiness_context_status:unavailable" in row["recommendation_triggers"]
    assert "readiness_context_failure:injury_classification" in row["recommendation_triggers"]


def test_command_view_revokes_stored_green_when_injury_context_fails():
    store = _store_with_plan(FailingInjuryFlagsStore)
    store.upsert_today_checkin(
        ATHLETE,
        {
            **_checkin_payload(),
            "training_day": NOW.date().isoformat(),
            "athlete_timezone": "",
            "recommendation_state": "train_as_planned",
            "recommendation_reason": "Train as planned.",
            "recommendation_triggers": [],
        },
    )

    view = build_today_command_view(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        now=NOW,
    )

    assert view.today.recommendation_state == "modify"
    assert view.today.decision_tier == "modify"
    assert view.today.recommendation_reason.splitlines()[0] == "Readiness check limited."
    assert any(
        warning.startswith("readiness_context_status=unavailable")
        for warning in view.today.warnings
    )
    assert any(
        risk.text == "Safety context is unavailable, so hard training is not cleared."
        for risk in view.risk_watch
    )


def test_current_session_execution_is_blocked_when_injury_state_is_unknown():
    store = _store_with_plan(FailingInjuryFlagsStore)

    with pytest.raises(HTTPException) as exc:
        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={
                "plan_id": PLAN,
                "session_id": "session-1",
                "status": "started",
            },
            now=NOW,
        )

    assert exc.value.status_code == 503
    assert exc.value.headers == {"Retry-After": "30"}
    assert not store.session_completions.get(ATHLETE)


def test_retro_log_does_not_require_current_injury_snapshot():
    store = _store_with_plan(FailingInjuryFlagsStore)
    yesterday = (NOW.date() - timedelta(days=1)).isoformat()

    row = upsert_session_completion(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload={
            "plan_id": PLAN,
            "session_id": "session-1",
            "status": "done",
            "training_day": yesterday,
        },
        now=NOW,
    )

    assert row["status"] == "done"
    assert row["training_day"] == yesterday
