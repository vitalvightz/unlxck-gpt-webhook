from api.services.week_progress import award_completed_week


class Store:
    def list_plan_session_completions(self, athlete_id, plan_id, *, limit=500):
        return [
            {
                "session_id": "session-1",
                "training_day": "2026-08-03",
                "status": "done",
                "updated_at": "2026-08-03T12:00:00+00:00",
            }
        ]

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        return {
            "awarded": True,
            "previous_total_xp": 0,
            "state": {"total_xp": 100},
        }


def test_week_push_failure_does_not_block_lifecycle_evaluation(monkeypatch):
    week = {
        "week_id": "week-1",
        "week_index": 1,
        "phase_label": "GPP",
        "start_date": "2026-08-03",
        "end_date": "2026-08-09",
        "days": [
            {
                "date": "2026-08-03",
                "day_type": "high",
                "sessions": [{"session_id": "session-1"}],
            }
        ],
    }
    plan = {
        "id": "plan-1",
        "structured_plan": {
            "plan_metadata": {"plan_type": "general_performance"},
            "weeks": [week],
        },
    }
    captured = []

    def fail_push(*args, **kwargs):
        raise RuntimeError("push unavailable")

    monkeypatch.setattr(
        "api.services.week_progress.dispatch_progress_award_notification",
        fail_push,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.record_plan_milestones_after_completed_week",
        lambda *args, **kwargs: captured.append(kwargs) or [],
    )

    result = award_completed_week(
        Store(),
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=plan,
        training_day="2026-08-03",
    )

    assert result["awarded"] is True
    assert len(captured) == 1
    assert captured[0]["completed_week"]["week_id"] == "week-1"
