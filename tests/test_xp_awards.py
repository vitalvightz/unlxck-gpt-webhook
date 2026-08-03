from api.services.xp_awards import award_checkin_xp, award_feedback_xp


class FakeStore:
    def __init__(self):
        self.calls = []

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        self.calls.append((athlete_id, action, idempotency_key, calendar_date))
        return {"awarded": True, "action": action}


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
    award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={"id": "feedback-1", "comment": "Too hard"},
    )
    assert store.calls[-1][1:] == (
        "feedback_submitted",
        "feedback:feedback-1",
        None,
    )


def test_feedback_with_meaningful_comment_gets_three_total_xp():
    store = FakeStore()
    award_feedback_xp(
        store,
        athlete_id="athlete-1",
        feedback={
            "id": "feedback-2",
            "comment": "The final conditioning block was too hard after sparring.",
        },
    )
    assert store.calls[-1][1:] == (
        "feedback_with_comment",
        "feedback:feedback-2",
        None,
    )


def test_missing_source_ids_do_not_award():
    store = FakeStore()
    assert award_checkin_xp(store, athlete_id="athlete-1", checkin={}) == []
    assert award_feedback_xp(store, athlete_id="athlete-1", feedback={}) is None
    assert store.calls == []
