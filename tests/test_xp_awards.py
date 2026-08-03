from api.services.xp_awards import award_checkin_xp, award_feedback_xp


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


def test_checkin_awards_first_and_daily_xp():
    store = FakeStore()
    results = award_checkin_xp(
        store,
        athlete_id="athlete-1",
        checkin={"id": "checkin-1", "training_day": "2026-08-03"},
    )
    assert len(results) == 2
    assert store.calls == [
        ("athlete-1", "first_checkin_completed", "first-checkin:athlete-1", None),
        ("athlete-1", "readiness_checkin_completed", "checkin:athlete-1:2026-08-03", None),
    ]


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
    assert store.calls == []
