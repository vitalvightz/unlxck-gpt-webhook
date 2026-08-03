from types import SimpleNamespace

from api.services.xp_awards import (
    award_checkin_xp,
    award_feedback_xp,
    award_injury_update_xp,
    plan_activation_ready,
    plan_completion_xp_eligible,
    profile_activation_complete,
    reconcile_activation_xp,
)


class FakeStore:
    def __init__(self):
        self.calls = []
        self.feedback_awards = {}

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        self.calls.append((athlete_id, action, idempotency_key, calendar_date))
        return {"awarded": True, "action": action}

    def reconcile_feedback_xp(self, athlete_id, *, feedback_id, target_amount):
        previous = self.feedback_awards.get(feedback_id, 0)
        current = max(previous, target_amount)
        delta = current - previous
        self.feedback_awards[feedback_id] = current
        self.calls.append((athlete_id, "feedback", feedback_id, target_amount, delta))
        return {
            "awarded": delta > 0,
            "xp_delta": delta,
            "award": {
                "action": "feedback_with_comment" if current == 3 else "feedback_submitted",
                "amount": current,
            },
        }


class IdempotentActivationStore(FakeStore):
    def __init__(self):
        super().__init__()
        self.seen_keys = set()

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        awarded = idempotency_key not in self.seen_keys
        self.seen_keys.add(idempotency_key)
        self.calls.append((athlete_id, action, idempotency_key, calendar_date, awarded))
        return {"awarded": awarded, "action": action}


def test_profile_activation_requires_name_and_live_combat_sport():
    assert profile_activation_complete(
        {"full_name": "Ari Mensah", "technical_style": ["boxing"]}
    ) is True
    assert profile_activation_complete(
        SimpleNamespace(full_name="Ari Mensah", technical_style=["MMA"])
    ) is True
    assert profile_activation_complete(
        {"full_name": "Ari Mensah", "technical_style": ["running"]}
    ) is False
    assert profile_activation_complete(
        {"full_name": "Ari Mensah", "technical_style": ["unknown", "test"]}
    ) is False
    assert profile_activation_complete(
        {"full_name": "Ari Mensah", "technical_style": ["muay_thai"]}
    ) is False
    assert profile_activation_complete(
        {"full_name": "Ari Mensah", "technical_style": []}
    ) is False
    assert profile_activation_complete(
        {"full_name": "", "technical_style": ["boxing"]}
    ) is False


def test_plan_activation_requires_an_athlete_visible_ready_status():
    assert plan_activation_ready({"plan_id": "plan-1", "status": "ready"}) is True
    assert plan_activation_ready(
        SimpleNamespace(plan_id="plan-2", status="publishable_with_flags")
    ) is True
    assert plan_activation_ready({"plan_id": "plan-3", "status": "held_for_review"}) is False
    assert plan_activation_ready({"plan_id": "", "status": "ready"}) is False


def test_activation_reconciliation_awards_all_persisted_milestones():
    store = FakeStore()
    results = reconcile_activation_xp(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        latest_intake={"athlete": {"full_name": "Ari Mensah"}},
        latest_plan={"plan_id": "plan-1", "status": "ready"},
    )

    assert len(results) == 3
    assert store.calls == [
        ("athlete-1", "profile_completed", "profile-completed:athlete-1", None),
        (
            "athlete-1",
            "first_intake_completed",
            "first-intake-completed:athlete-1",
            None,
        ),
        ("athlete-1", "first_plan_ready", "first-plan-ready:athlete-1", None),
    ]


def test_profile_award_failure_does_not_block_intake_or_plan_reconciliation():
    class ProfileFailureStore(FakeStore):
        def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
            self.calls.append((athlete_id, action, idempotency_key, calendar_date))
            if action == "profile_completed":
                raise RuntimeError("profile XP unavailable")
            return {"awarded": True, "action": action}

    store = ProfileFailureStore()
    results = reconcile_activation_xp(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        latest_intake={"athlete": {"full_name": "Ari Mensah"}},
        latest_plan={"plan_id": "plan-1", "status": "ready"},
    )

    assert [result["action"] for result in results] == [
        "first_intake_completed",
        "first_plan_ready",
    ]
    assert [call[1] for call in store.calls] == [
        "profile_completed",
        "first_intake_completed",
        "first_plan_ready",
    ]


def test_activation_reconciliation_fails_closed_for_incomplete_state():
    store = FakeStore()
    assert reconcile_activation_xp(
        store,
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": []},
        latest_intake=None,
        latest_plan={"plan_id": "plan-1", "status": "held_for_review"},
    ) == []
    assert store.calls == []


def test_repeated_activation_reconciliation_repairs_without_duplicate_awards():
    store = IdempotentActivationStore()
    state = {
        "athlete_id": "athlete-1",
        "profile": {"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        "latest_intake": {"athlete": {"full_name": "Ari Mensah"}},
        "latest_plan": {"plan_id": "plan-1", "status": "publishable_with_flags"},
    }

    first = reconcile_activation_xp(store, **state)
    repeated = reconcile_activation_xp(store, **state)

    assert [result["awarded"] for result in first] == [True, True, True]
    assert [result["awarded"] for result in repeated] == [False, False, False]
    assert store.seen_keys == {
        "profile-completed:athlete-1",
        "first-intake-completed:athlete-1",
        "first-plan-ready:athlete-1",
    }


def test_activation_xp_failures_never_break_state_reconciliation():
    class FailingStore:
        def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
            raise RuntimeError("xp unavailable")

    assert reconcile_activation_xp(
        FailingStore(),
        athlete_id="athlete-1",
        profile={"full_name": "Ari Mensah", "technical_style": ["boxing"]},
        latest_intake={"athlete": {"full_name": "Ari Mensah"}},
        latest_plan={"plan_id": "plan-1", "status": "ready"},
    ) == []


def test_checkin_awards_first_and_daily_xp_with_authoritative_date():
    store = FakeStore()
    results = award_checkin_xp(
        store,
        athlete_id="athlete-1",
        checkin={"id": "checkin-1", "training_day": "2026-08-03"},
    )
    assert len(results) == 2
    assert store.calls == [
        ("athlete-1", "first_checkin_completed", "first-checkin:athlete-1", None),
        (
            "athlete-1",
            "readiness_checkin_completed",
            "checkin:athlete-1:2026-08-03",
            "2026-08-03",
        ),
    ]


def test_injury_update_is_one_reward_per_declaration_batch_and_athlete_day():
    store = FakeStore()
    result = award_injury_update_xp(
        store,
        athlete_id="athlete-1",
        training_day="2026-08-03",
        updated_injuries=[{"id": "injury-1"}, {"id": "injury-2"}],
    )

    assert result is not None
    assert store.calls == [
        (
            "athlete-1",
            "injury_update_completed",
            "injury-update:athlete-1:2026-08-03",
            "2026-08-03",
        )
    ]


def test_empty_injury_declaration_does_not_award():
    store = FakeStore()
    assert award_injury_update_xp(
        store,
        athlete_id="athlete-1",
        training_day="2026-08-03",
        updated_injuries=[],
    ) is None
    assert store.calls == []


def test_plan_completion_xp_requires_the_server_resolved_active_plan():
    class ActivePlanStore:
        def __init__(self, active_plan_id="plan-active"):
            self.active_plan_id = active_plan_id
            self.plans = {
                "plan-active": {
                    "id": "plan-active",
                    "status": "ready",
                    "fight_date": "2026-09-01",
                    "created_at": "2026-07-01T00:00:00Z",
                },
                "plan-inactive": {
                    "id": "plan-inactive",
                    "status": "ready",
                    "fight_date": "2026-10-01",
                    "created_at": "2026-07-02T00:00:00Z",
                },
            }

        def get_active_plan_id(self, athlete_id):
            return self.active_plan_id

        def get_plan_for_athlete(self, plan_id, athlete_id):
            return self.plans.get(plan_id)

        def list_user_plans(self, athlete_id):
            return list(self.plans.values())

    store = ActivePlanStore()
    assert plan_completion_xp_eligible(
        store,
        athlete_id="athlete-1",
        completion={"plan_id": "plan-active", "training_day": "2026-08-03"},
    ) is True
    assert plan_completion_xp_eligible(
        store,
        athlete_id="athlete-1",
        completion={"plan_id": "plan-inactive", "training_day": "2026-08-03"},
    ) is False


def test_plan_completion_xp_fails_closed_when_active_plan_resolution_breaks():
    class BrokenStore:
        def get_active_plan_id(self, athlete_id):
            raise RuntimeError("database unavailable")

    assert plan_completion_xp_eligible(
        BrokenStore(),
        athlete_id="athlete-1",
        completion={"plan_id": "plan-1", "training_day": "2026-08-03"},
    ) is False


def test_feedback_without_meaningful_comment_gets_one_xp():
    store = FakeStore()
    result = award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={"id": "feedback-1", "comment": "Too hard"},
    )
    assert result["xp_delta"] == 1
    assert result["award"]["amount"] == 1


def test_feedback_edit_with_meaningful_comment_adds_only_two_xp():
    store = FakeStore()
    first = award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={"id": "feedback-1", "comment": "Too hard"},
    )
    upgraded = award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={
            "id": "feedback-1",
            "comment": "The final conditioning block was too hard after sparring.",
        },
    )
    assert first["xp_delta"] == 1
    assert upgraded["xp_delta"] == 2
    assert upgraded["award"]["amount"] == 3
    assert store.feedback_awards["feedback-1"] == 3


def test_repeated_meaningful_feedback_edit_adds_no_xp():
    store = FakeStore()
    feedback = {
        "id": "feedback-2",
        "comment": "The final conditioning block was too hard after sparring.",
    }
    first = award_feedback_xp(store, athlete_id="athlete-1", feedback=feedback)
    repeated = award_feedback_xp(store, athlete_id="athlete-1", feedback=feedback)
    assert first["xp_delta"] == 3
    assert repeated["xp_delta"] == 0
    assert store.feedback_awards["feedback-2"] == 3


def test_shortening_meaningful_comment_does_not_remove_xp():
    store = FakeStore()
    meaningful = award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={
            "id": "feedback-3",
            "comment": "The final conditioning block was too hard after sparring.",
        },
    )
    shortened = award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={"id": "feedback-3", "comment": "Too hard"},
    )
    assert meaningful["xp_delta"] == 3
    assert shortened["xp_delta"] == 0
    assert store.feedback_awards["feedback-3"] == 3


def test_missing_source_ids_do_not_award():
    store = FakeStore()
    assert award_checkin_xp(store, athlete_id="athlete-1", checkin={}) == []
    assert award_feedback_xp(store, athlete_id="athlete-1", feedback={}) is None
    assert award_injury_update_xp(
        store,
        athlete_id="athlete-1",
        training_day="",
        updated_injuries=[{"id": "injury-1"}],
    ) is None
    assert store.calls == []
