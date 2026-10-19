from api.services import tracking_xp
from support import xp_hardening_ready_payload


def reward(action, amount, previous=0):
    return {"awarded": True, "previous_total_xp": previous, "state": {"total_xp": previous+amount},
            "award": {"id": action, "action": action, "amount": amount}}


class Store:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    def validate_xp_abuse_hardening(self):
        return xp_hardening_ready_payload()

    def reconcile_training_engagement_xp(self, athlete_id, *, manual_session_id=None):
        self.calls.append((athlete_id, manual_session_id))
        return self.results

    def reconcile_approved_contribution_xp(self, revision_id):
        self.calls.append(revision_id)
        return {"athlete_id": "creator", "timezone": "Europe/London", "results": self.results}


def test_one_branded_notification_per_save_and_no_repeat_push(monkeypatch):
    captured = []
    monkeypatch.setattr(tracking_xp, "dispatch_push_candidate", lambda store, candidate, **kw: captured.append(candidate))
    results = [reward("manual_training_logged", 25), reward("first_session_logged", 50, 25)]
    store = Store(results)
    assert tracking_xp.reconcile_training_xp(store, "athlete", manual_session_id="session") == results
    assert store.calls == [("athlete", "session")]
    assert len(captured) == 1
    assert captured[0].title == "First session. UNLXCKED."
    assert "+75 XP" in captured[0].body
    assert captured[0].category == "progress_milestones"
    assert captured[0].respect_quiet_hours
    assert captured[0].notification_class == "event"
    assert captured[0].url == "/progress"
    store.results = [{**result, "awarded": False} for result in results]
    tracking_xp.reconcile_training_xp(store, "athlete", manual_session_id="session")
    assert len(captured) == 1


def test_approval_notifies_rpc_resolved_creator_not_moderator(monkeypatch):
    captured = []
    monkeypatch.setattr(tracking_xp, "dispatch_push_candidate", lambda store, candidate, **kw: captured.append(candidate))
    store = Store([reward("exercise_contribution_approved", 100)])
    tracking_xp.reconcile_contribution_xp(store, "revision")
    assert store.calls == ["revision"]
    assert len(captured) == 1
    assert captured[0].profile_id == "creator"
    assert captured[0].timezone_name == "Europe/London"
    assert captured[0].title == "Your contribution is UNLXCKED."
    assert "approved" in captured[0].body and "+100 XP" in captured[0].body


def test_largest_milestone_wins_and_level_up_is_compounded(monkeypatch):
    captured = []
    monkeypatch.setattr(tracking_xp, "dispatch_push_candidate", lambda store, candidate, **kw: captured.append(candidate))
    store = Store([reward("training_days_100", 500, 0), reward("first_exercise_logged", 25, 500)])
    tracking_xp.reconcile_training_xp(store, "athlete")
    assert len(captured) == 1
    assert len(captured[0].merged_intents) == 1
    assert captured[0].source_event_metadata["compound_intents"] == ["xp_level_up", "training_record_milestone"]


def test_xp_failure_does_not_fail_training_and_push_failure_does_not_erase_awards(monkeypatch):
    store = Store([reward("first_session_logged", 50)])
    def fail(*args, **kwargs):
        raise RuntimeError("unavailable")
    monkeypatch.setattr(tracking_xp, "dispatch_push_candidate", fail)
    assert tracking_xp.reconcile_training_xp(store, "athlete") == store.results
    monkeypatch.setattr(store, "reconcile_training_engagement_xp", fail)
    assert tracking_xp.reconcile_training_xp(store, "athlete") == []


def test_failed_hardening_prevents_new_reward_rpcs(monkeypatch):
    store = Store()
    monkeypatch.setattr(store, "validate_xp_abuse_hardening", lambda: {})
    assert tracking_xp.reconcile_training_xp(store, "athlete") == []
    tracking_xp.reconcile_contribution_xp(store, "revision")
    assert store.calls == []


class ReplayStore(Store):
    def __init__(self):
        super().__init__([reward("exercise_contribution_approved", 100)])
        self.pending = {"a": "rev-a", "b": "rev-b"}
        self.failures = {"rev-a"}

    def list_unrewarded_contribution_revisions(self, *, after_id=None, limit=50):
        return [{"exercise_id": key, "revision_id": revision}
                for key, revision in sorted(self.pending.items()) if after_id is None or key > after_id][:limit]

    def reconcile_approved_contribution_xp(self, revision_id):
        self.calls.append(revision_id)
        if revision_id in self.failures:
            raise RuntimeError("temporary XP outage")
        self.pending = {key: value for key, value in self.pending.items() if value != revision_id}
        return {"athlete_id": "creator", "results": self.results}


def test_replay_recovers_missed_approval_and_revisits_failures_without_starving_later_rows(monkeypatch):
    store = ReplayStore()
    notifications = []
    monkeypatch.setattr(tracking_xp, "dispatch_push_candidate", lambda store, candidate, **kw: notifications.append(candidate))
    cursor = tracking_xp.replay_contribution_xp(store)
    assert cursor == "b"
    assert store.calls == ["rev-a", "rev-b"]
    assert store.pending == {"a": "rev-a"}
    assert len(notifications) == 1
    assert tracking_xp.replay_contribution_xp(store, after_id=cursor) is None
    store.failures.clear()
    assert tracking_xp.replay_contribution_xp(store) == "a"
    assert store.pending == {}
    assert len(notifications) == 2
    assert tracking_xp.replay_contribution_xp(store) is None
    assert len(notifications) == 2


def test_replay_keeps_cursor_on_discovery_failure_and_stops_before_next_row(monkeypatch):
    store = ReplayStore()
    assert tracking_xp.replay_contribution_xp(store, after_id="previous", should_stop=lambda: True) == "previous"
    assert store.calls == []
    monkeypatch.setattr(store, "list_unrewarded_contribution_revisions", lambda **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    assert tracking_xp.replay_contribution_xp(store, after_id="previous") == "previous"
    assert store.calls == []
