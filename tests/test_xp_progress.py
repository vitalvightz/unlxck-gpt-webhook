from __future__ import annotations

from types import SimpleNamespace

from api.routes import xp as xp_routes
from api.services.xp_progress import (
    _RecordRead,
    _current_week,
    _opportunities,
    _safe_latest_intake,
    _safe_latest_plan,
)
from support import _build_client


ATHLETE = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}


class ProgressStore:
    def __init__(self):
        self.xp_awards: dict[str, list[dict]] = {"athlete-1": []}
        self.completions: list[dict] = []

    def list_plan_session_completions(self, athlete_id, plan_id, *, limit=500):
        assert athlete_id == "athlete-1"
        assert plan_id == "plan-1"
        return list(self.completions)


class FailingActivationStore(ProgressStore):
    def get_latest_intake(self, athlete_id):
        assert athlete_id == "athlete-1"
        raise RuntimeError("intake database unavailable")

    def get_latest_plan(self, athlete_id):
        assert athlete_id == "athlete-1"
        raise RuntimeError("plan database unavailable")


def command(
    *,
    recommendation_state="not_checked_in",
    decision_tier="green",
    session_scope="today",
    completion_status="not_started",
    with_session=True,
    injuries=(),
):
    return SimpleNamespace(
        today=SimpleNamespace(
            training_day="2026-08-03",
            recommendation_state=recommendation_state,
            decision_tier=decision_tier,
            session_scope=session_scope,
            completion_status=completion_status,
            next_session={"session_id": "session-1"} if with_session else {},
        ),
        open_injuries=list(injuries),
    )


def found(record: dict) -> _RecordRead:
    return _RecordRead(status="found", value=record)


def opportunity_codes(store, *, today=None, week=None):
    return _opportunities(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        latest_intake=found({"id": "intake-1"}),
        latest_plan=found({"id": "plan-1", "status": "ready"}),
        command=today or command(),
        current_week=week,
    )


def test_first_checkin_is_35_xp_then_daily_checkin_is_10():
    store = ProgressStore()
    first = opportunity_codes(store)
    assert first[0] == {
        "code": "complete_today_checkin",
        "label": "Complete today's check-in",
        "xp": 35,
        "href": "/today",
        "priority": 10,
    }

    store.xp_awards["athlete-1"].append(
        {
            "action": "first_checkin_completed",
            "idempotency_key": "first-checkin:athlete-1",
        }
    )
    repeated = opportunity_codes(store)
    assert repeated[0]["code"] == "complete_today_checkin"
    assert repeated[0]["xp"] == 10


def test_session_opportunity_uses_combined_75_xp_and_stop_hides_it():
    store = ProgressStore()
    checked_in = command(recommendation_state="train_as_planned")
    available = opportunity_codes(store, today=checked_in)
    assert available[0]["code"] == "complete_today_session"
    assert available[0]["xp"] == 75

    stopped = opportunity_codes(
        store,
        today=command(
            recommendation_state="pull_back",
            decision_tier="stop",
        ),
    )
    assert "complete_today_session" not in {item["code"] for item in stopped}


def test_rest_preview_and_completed_session_do_not_offer_session_xp():
    store = ProgressStore()
    rest = opportunity_codes(
        store,
        today=command(
            recommendation_state="train_as_planned",
            session_scope="none",
            with_session=False,
        ),
    )
    assert "complete_today_session" not in {item["code"] for item in rest}

    done = opportunity_codes(
        store,
        today=command(
            recommendation_state="train_as_planned",
            completion_status="done",
        ),
    )
    assert "complete_today_session" not in {item["code"] for item in done}


def test_only_three_highest_priority_opportunities_are_returned():
    store = ProgressStore()
    result = _opportunities(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "", "technical_style": []},
        latest_intake=_RecordRead(status="not_found"),
        latest_plan=_RecordRead(status="not_found"),
        command=command(
            injuries=[{"id": "injury-1", "status": "open"}],
        ),
        current_week={
            "planned_sessions": 3,
            "complete": False,
            "week_xp_earned": False,
        },
    )
    assert len(result) == 3
    assert [item["code"] for item in result] == [
        "complete_today_checkin",
        "update_active_injury",
        "complete_today_session",
    ]


def test_activation_actions_require_confirmed_absence():
    store = ProgressStore()
    result = _opportunities(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        latest_intake=_RecordRead(status="not_found"),
        latest_plan=_RecordRead(status="not_found"),
        command=command(
            recommendation_state="train_as_planned",
            session_scope="none",
            with_session=False,
        ),
        current_week=None,
    )

    assert {item["code"] for item in result} == {
        "complete_first_intake",
        "build_first_plan",
    }


def test_failed_activation_reads_do_not_create_false_actions():
    store = FailingActivationStore()
    intake_read = _safe_latest_intake(store, "athlete-1")
    plan_read = _safe_latest_plan(store, "athlete-1")

    assert intake_read.status == "unavailable"
    assert plan_read.status == "unavailable"

    result = _opportunities(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        latest_intake=intake_read,
        latest_plan=plan_read,
        command=command(
            recommendation_state="train_as_planned",
            session_scope="none",
            with_session=False,
        ),
        current_week=None,
    )
    codes = {item["code"] for item in result}

    assert "complete_first_intake" not in codes
    assert "build_first_plan" not in codes


def test_week_progress_ignores_rest_days_and_week_action_disappears_after_award():
    store = ProgressStore()
    plan = {
        "id": "plan-1",
        "structured_plan": {
            "weeks": [
                {
                    "week_id": "week-1",
                    "week_index": 0,
                    "phase_label": "GPP",
                    "start_date": "2026-08-03",
                    "end_date": "2026-08-09",
                    "days": [
                        {
                            "date": "2026-08-03",
                            "day_type": "hard",
                            "sessions": [{"session_id": "session-1"}],
                        },
                        {
                            "date": "2026-08-04",
                            "day_type": "rest",
                            "sessions": [{"session_id": "rest-placeholder"}],
                        },
                        {
                            "date": "2026-08-05",
                            "day_type": "technical",
                            "sessions": [{"session_id": "session-2"}],
                        },
                    ],
                }
            ]
        },
    }
    store.completions = [
        {
            "session_id": "session-1",
            "training_day": "2026-08-03",
            "status": "done",
            "updated_at": "2026-08-03T12:00:00Z",
        }
    ]

    week = _current_week(
        store,
        athlete_id="athlete-1",
        plan=plan,
        training_day="2026-08-03",
    )
    assert week is not None
    assert week["planned_sessions"] == 2
    assert week["completed_sessions"] == 1
    assert week["remaining_sessions"] == 1
    assert "complete_training_week" in {
        item["code"]
        for item in opportunity_codes(
            store,
            today=command(recommendation_state="train_as_planned"),
            week=week,
        )
    }

    store.xp_awards["athlete-1"].append(
        {
            "action": "full_training_week_completed",
            "idempotency_key": "full-week:plan-1:week-1",
        }
    )
    repaired_week = _current_week(
        store,
        athlete_id="athlete-1",
        plan=plan,
        training_day="2026-08-03",
    )
    assert repaired_week is not None
    assert repaired_week["week_xp_earned"] is True
    assert "complete_training_week" not in {
        item["code"]
        for item in opportunity_codes(
            store,
            today=command(recommendation_state="train_as_planned"),
            week=repaired_week,
        )
    }


def test_progress_endpoint_is_athlete_only_and_read_only(monkeypatch):
    calls = []

    def fake_progress(store, **kwargs):
        calls.append(kwargs)
        return {
            "state": {
                "total_xp": 0,
                "last_daily_login_date": None,
                "recent_awards": [],
            },
            "opportunities": [],
            "current_week": None,
            "major_milestones": [],
        }

    monkeypatch.setattr(xp_routes, "build_xp_progress", fake_progress)
    client, store, _ = _build_client()
    before = dict(store.xp_accounts)

    response = client.get("/api/xp/progress", headers=ATHLETE)

    assert response.status_code == 200
    assert calls[0]["athlete_id"] == "athlete-1"
    assert store.xp_accounts == before
    assert client.get("/api/xp/progress").status_code in (401, 403)
    assert client.get("/api/xp/progress", headers=ADMIN).status_code == 403
