from __future__ import annotations

from datetime import datetime, timezone

from api.contracts.command_view import CommandView
from api.services.fight_camp_notifications import build_fight_camp_candidates
from api.services.notification_foundation import list_notification_evaluations


class FightDayStore:
    def list_session_completions(self, _profile_id: str, *, limit: int = 60) -> list[dict]:
        return []

    def get_session_completion(self, *_args) -> dict | None:
        return None

    def get_plan(self, _plan_id: str) -> dict | None:
        return None


def _view(*, training_day: str, fight_date: str, session_scope: str = "none") -> CommandView:
    return CommandView.model_validate(
        {
            "active_plan": {"id": "plan-1", "fight_date": fight_date},
            "today": {
                "training_day": training_day,
                "recommendation_state": "not_checked_in",
                "decision_tier": "green",
                "session_scope": session_scope,
                "completion_status": "not_started",
                "next_session": {},
            },
            "open_injuries": [],
        }
    )


def _candidates(at: datetime, *, training_day: str, fight_date: str):
    store = FightDayStore()
    candidates = build_fight_camp_candidates(
        store,
        _view(training_day=training_day, fight_date=fight_date),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=at,
    )
    return store, candidates


def test_fight_day_is_one_source_backed_morning_event() -> None:
    store, candidates = _candidates(
        datetime(2026, 8, 16, 8, 30, tzinfo=timezone.utc),
        training_day="2026-08-16",
        fight_date="2026-08-16",
    )

    fight_day = [candidate for candidate in candidates if candidate.intent == "fight_day"]
    assert len(fight_day) == 1
    candidate = fight_day[0]
    assert candidate.notification_class == "event"
    assert candidate.priority == 28
    assert candidate.dedupe_key == "fight-day:plan-1:2026-08-16"
    assert candidate.title == "IT'S TIME."
    assert candidate.body == "Fight day. Stay sharp, stay calm. Stick to the plan."
    assert candidate.timing_source is None
    assert candidate.timing_confidence is None
    assert candidate.variant_id == "fd-01"
    assert candidate.source_event_metadata["plan_id"] == "plan-1"
    assert candidate.source_event_metadata["fight_date"] == "2026-08-16"
    assert "recovery_checkin" not in {item.intent for item in candidates}

    recovery = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-16",
        intent="recovery_checkin",
    )
    assert recovery[0]["decision"] == "replaced_by_fight_day"


def test_fight_day_replaces_afternoon_recovery_nudge() -> None:
    store, candidates = _candidates(
        datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc),
        training_day="2026-08-16",
        fight_date="2026-08-16",
    )

    intents = {candidate.intent for candidate in candidates}
    assert "fight_day" not in intents
    assert "recovery_nudge" not in intents
    recovery = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-16",
        intent="recovery_nudge",
    )
    assert recovery[0]["decision"] == "replaced_by_fight_day"


def test_fight_day_only_uses_the_morning_window() -> None:
    for hour in (6, 11):
        _store, candidates = _candidates(
            datetime(2026, 8, 16, hour, 0, tzinfo=timezone.utc),
            training_day="2026-08-16",
            fight_date="2026-08-16",
        )
        assert "fight_day" not in {candidate.intent for candidate in candidates}


def test_d1_countdown_remains_separate_from_fight_day() -> None:
    _store, candidates = _candidates(
        datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
        training_day="2026-08-15",
        fight_date="2026-08-16",
    )
    intents = {candidate.intent for candidate in candidates}
    assert "fight_countdown" in intents
    assert "fight_day" not in intents
