from types import SimpleNamespace

from api.services.progress_notifications import award_session_progress
from api.services.xp_awards import award_checkin_xp, award_feedback_xp


class RpcBuilder:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def execute(self):
        self.client.calls.append(self.name)
        if self.client.error:
            raise RuntimeError("missing hardening migration")
        return SimpleNamespace(data={"ok": True, "version": "20260803181000"})


class Client:
    def __init__(self, *, error=False):
        self.error = error
        self.calls = []

    def rpc(self, name, payload=None):
        assert payload is None
        return RpcBuilder(self, name)


class Store:
    def __init__(self, *, hardening_error=False):
        self.client = Client(error=hardening_error)
        self.awards = []
        self.feedback_calls = []

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        self.awards.append((athlete_id, action, idempotency_key, calendar_date))
        return {"awarded": True, "action": action}

    def reconcile_feedback_xp(self, athlete_id, *, feedback_id, target_amount):
        self.feedback_calls.append((athlete_id, feedback_id, target_amount))
        return {"awarded": True, "xp_delta": target_amount}


def test_activation_and_daily_awards_fail_closed_when_migration_is_missing():
    store = Store(hardening_error=True)

    assert award_checkin_xp(
        store,
        athlete_id="athlete-1",
        checkin={"id": "checkin-1", "training_day": "2026-08-03"},
    ) == []
    assert store.awards == []
    assert store.client.calls == [
        "validate_xp_abuse_hardening",
        "validate_xp_abuse_hardening",
    ]


def test_session_awards_fail_closed_without_breaking_completion_flow():
    store = Store(hardening_error=True)

    assert award_session_progress(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        completion={
            "id": "completion-1",
            "training_day": "2026-08-03",
            "status": "done",
        },
    ) == []
    assert store.awards == []


def test_feedback_xp_fails_closed_when_migration_is_missing():
    store = Store(hardening_error=True)

    assert award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={"id": "feedback-1", "comment": "Useful detailed feedback here"},
    ) is None
    assert store.feedback_calls == []


def test_successful_hardening_validation_is_cached_per_live_client():
    store = Store()

    results = award_checkin_xp(
        store,
        athlete_id="athlete-1",
        checkin={"id": "checkin-1", "training_day": "2026-08-03"},
    )

    assert len(results) == 2
    assert store.client.calls == ["validate_xp_abuse_hardening"]
    assert [award[1] for award in store.awards] == [
        "first_checkin_completed",
        "readiness_checkin_completed",
    ]
