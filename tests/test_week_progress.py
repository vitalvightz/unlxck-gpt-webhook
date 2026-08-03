from api.services.week_progress import (
    award_completed_week,
    evaluate_week_completion,
    find_week_for_training_day,
    try_award_completed_week_for_completion,
)


def _week():
    return {
        "week_id": "week-1",
        "start_date": "2026-08-03",
        "end_date": "2026-08-09",
        "days": [
            {"date": "2026-08-03", "day_type": "high", "sessions": [{"session_id": "mon-1"}]},
            {"date": "2026-08-05", "day_type": "moderate", "sessions": [{"session_id": "wed-1"}]},
            {"date": "2026-08-07", "day_type": "recovery", "sessions": [{"session_id": "fri-1"}]},
            {"date": "2026-08-08", "day_type": "rest", "sessions": []},
        ],
    }


def _plan():
    return {"id": "plan-1", "structured_plan": {"weeks": [_week()]}}


def _complete_other_sessions():
    return [
        {
            "session_id": "wed-1",
            "status": "modified",
            "updated_at": "2026-08-05T12:00:00+00:00",
        },
        {
            "session_id": "fri-1",
            "status": "done",
            "updated_at": "2026-08-07T12:00:00+00:00",
        },
    ]


def test_find_week_uses_structured_plan_dates():
    assert find_week_for_training_day(_plan(), "2026-08-05")["week_id"] == "week-1"
    assert find_week_for_training_day(_plan(), "2026-08-10") is None


def test_week_complete_when_all_planned_sessions_done_or_modified():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {"session_id": "mon-1", "status": "done"},
            {"session_id": "wed-1", "status": "modified"},
            {"session_id": "fri-1", "status": "done"},
        ],
    )
    assert result["complete"] is True
    assert result["planned"] == 3
    assert result["resolved"] == 3


def test_week_incomplete_when_session_missing():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {"session_id": "mon-1", "status": "done"},
            {"session_id": "wed-1", "status": "modified"},
        ],
    )
    assert result["complete"] is False
    assert result["unresolved_session_ids"] == ["fri-1"]


def test_week_incomplete_when_session_skipped_without_authoritative_stop_evidence():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {"session_id": "mon-1", "status": "done"},
            {"session_id": "wed-1", "status": "skipped"},
            {"session_id": "fri-1", "status": "done"},
        ],
    )
    assert result["complete"] is False
    assert result["skipped_session_ids"] == ["wed-1"]


def test_skipped_followed_by_done_uses_newer_done():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {
                "session_id": "mon-1",
                "status": "skipped",
                "updated_at": "2026-08-03T10:00:00+00:00",
            },
            {
                "session_id": "mon-1",
                "status": "done",
                "updated_at": "2026-08-03T11:00:00+00:00",
            },
            *_complete_other_sessions(),
        ],
    )
    assert result["complete"] is True


def test_done_followed_by_skipped_uses_newer_skipped():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {
                "session_id": "mon-1",
                "status": "done",
                "updated_at": "2026-08-03T10:00:00+00:00",
            },
            {
                "session_id": "mon-1",
                "status": "skipped",
                "updated_at": "2026-08-03T11:00:00+00:00",
            },
            *_complete_other_sessions(),
        ],
    )
    assert result["complete"] is False
    assert result["skipped_session_ids"] == ["mon-1"]


def test_reverse_chronological_rows_do_not_overwrite_newer_status():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {
                "session_id": "mon-1",
                "status": "done",
                "updated_at": "2026-08-03T11:00:00+00:00",
            },
            {
                "session_id": "mon-1",
                "status": "skipped",
                "updated_at": "2026-08-03T10:00:00+00:00",
            },
            *_complete_other_sessions(),
        ],
    )
    assert result["complete"] is True


def test_conflicting_equal_timestamps_are_ambiguous_and_do_not_award():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {
                "session_id": "mon-1",
                "status": "done",
                "updated_at": "2026-08-03T11:00:00+00:00",
            },
            {
                "session_id": "mon-1",
                "status": "skipped",
                "updated_at": "2026-08-03T11:00:00+00:00",
            },
            *_complete_other_sessions(),
        ],
    )
    assert result["complete"] is False
    assert result["ambiguous_session_ids"] == ["mon-1"]
    assert result["unresolved_session_ids"] == ["mon-1"]


def test_conflicting_missing_timestamps_are_ambiguous_and_do_not_award():
    result = evaluate_week_completion(
        week=_week(),
        completions=[
            {"session_id": "mon-1", "status": "done"},
            {"session_id": "mon-1", "status": "skipped"},
            *_complete_other_sessions(),
        ],
    )
    assert result["complete"] is False
    assert result["ambiguous_session_ids"] == ["mon-1"]


class FakeStore:
    def __init__(self):
        self.awards = []
        self.completions = [
            {
                "session_id": "mon-1",
                "training_day": "2026-08-03",
                "status": "done",
                "updated_at": "2026-08-03T12:00:00+00:00",
            },
            {
                "session_id": "wed-1",
                "training_day": "2026-08-05",
                "status": "modified",
                "updated_at": "2026-08-05T12:00:00+00:00",
            },
            {
                "session_id": "fri-1",
                "training_day": "2026-08-07",
                "status": "done",
                "updated_at": "2026-08-07T12:00:00+00:00",
            },
        ]

    def get_plan_for_athlete(self, plan_id, athlete_id):
        return _plan()

    def list_plan_session_completions(self, athlete_id, plan_id, *, limit=500):
        return list(self.completions)

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        self.awards.append((athlete_id, action, idempotency_key, calendar_date))
        return {
            "awarded": True,
            "previous_total_xp": 100,
            "state": {"total_xp": 200},
        }

    def get_notification_preferences(self, profile_id):
        return {
            "push_enabled": False,
            "progress_milestones": True,
            "quiet_hours_enabled": False,
        }


def test_full_week_award_uses_plan_week_and_calendar_scope(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.week_progress.dispatch_progress_award_notification",
        lambda *args, **kwargs: 0,
    )
    result = award_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan(),
        training_day="2026-08-07",
    )
    assert result["awarded"] is True
    assert store.awards == [
        (
            "athlete-1",
            "full_training_week_completed",
            "full-week:plan-1:week-1",
            "2026-08-03",
        )
    ]


def test_full_week_does_not_award_early(monkeypatch):
    store = FakeStore()
    store.completions.pop()
    monkeypatch.setattr(
        "api.services.week_progress.dispatch_progress_award_notification",
        lambda *args, **kwargs: 0,
    )
    assert award_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan(),
        training_day="2026-08-05",
    ) is None
    assert store.awards == []


def test_plan_lookup_failure_is_best_effort():
    class FailingStore:
        def get_plan_for_athlete(self, plan_id, athlete_id):
            raise RuntimeError("database unavailable")

    assert try_award_completed_week_for_completion(
        FailingStore(),
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        completion={
            "plan_id": "plan-1",
            "training_day": "2026-08-07",
        },
    ) is None
