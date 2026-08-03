from api.services.plan_milestones import record_plan_milestones_after_completed_week
from api.services.week_progress import award_completed_week


def _week(week_id, index, phase, start, end, session_id):
    return {
        "week_id": week_id,
        "week_index": index,
        "phase_label": phase,
        "start_date": start,
        "end_date": end,
        "days": [
            {
                "date": start,
                "day_type": "high",
                "sessions": [{"session_id": session_id}],
            }
        ],
    }


def _plan(plan_type="fight_camp", weeks=None):
    return {
        "id": "plan-1",
        "structured_plan": {
            "plan_metadata": {"plan_type": plan_type},
            "weeks": weeks or [],
        },
    }


def _completion(session_id, training_day, status="done"):
    return {
        "session_id": session_id,
        "training_day": training_day,
        "status": status,
        "updated_at": f"{training_day}T12:00:00+00:00",
    }


class FakeStore:
    def __init__(self):
        self.calls = []
        self.seen = set()
        self.total = 0
        self.completions = []

    def record_plan_milestone(
        self,
        athlete_id,
        *,
        plan_id,
        milestone_type,
        milestone_key,
        phase_label,
        metadata,
    ):
        identity = (athlete_id, plan_id, milestone_type, milestone_key)
        inserted = identity not in self.seen
        self.seen.add(identity)
        action = {
            "phase_completed": "phase_completed",
            "plan_completed": "first_plan_completed",
            "camp_completed": "camp_completed",
        }[milestone_type]
        amount = {
            "phase_completed": 200,
            "plan_completed": 250,
            "camp_completed": 500,
        }[milestone_type]
        previous = self.total
        if inserted:
            self.total += amount
        self.calls.append(
            {
                "athlete_id": athlete_id,
                "plan_id": plan_id,
                "milestone_type": milestone_type,
                "milestone_key": milestone_key,
                "phase_label": phase_label,
                "metadata": metadata,
            }
        )
        return {
            "milestone_inserted": inserted,
            "award_result": {
                "awarded": inserted,
                "previous_total_xp": previous,
                "state": {"total_xp": self.total},
                "award": {"action": action, "amount": amount},
            },
        }

    def list_plan_session_completions(self, athlete_id, plan_id, *, limit=500):
        return list(self.completions)

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        return {
            "awarded": True,
            "previous_total_xp": 0,
            "state": {"total_xp": 100},
        }

    def get_notification_preferences(self, profile_id):
        return {
            "push_enabled": False,
            "progress_milestones": True,
            "quiet_hours_enabled": False,
        }


def test_contiguous_phase_completes_without_finishing_plan(monkeypatch):
    weeks = [
        _week("gpp-1", 1, "GPP", "2026-08-03", "2026-08-09", "g1"),
        _week("gpp-2", 2, "GPP", "2026-08-10", "2026-08-16", "g2"),
        _week("spp-1", 3, "SPP", "2026-08-17", "2026-08-23", "s1"),
    ]
    completions = [
        _completion("g1", "2026-08-03"),
        _completion("g2", "2026-08-10"),
    ]
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan(weeks=weeks),
        completed_week=weeks[1],
        completions=completions,
    )

    assert [call["milestone_type"] for call in store.calls] == ["phase_completed"]
    assert store.calls[0]["milestone_key"] == "phase:GPP:gpp-1:gpp-2"
    assert store.calls[0]["metadata"]["week_ids"] == ["gpp-1", "gpp-2"]


def test_repeated_phase_labels_create_distinct_contiguous_segments(monkeypatch):
    weeks = [
        _week("gpp-1", 1, "GPP", "2026-08-03", "2026-08-09", "g1"),
        _week("spp-1", 2, "SPP", "2026-08-10", "2026-08-16", "s1"),
        _week("gpp-2", 3, "GPP", "2026-08-17", "2026-08-23", "g2"),
    ]
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=_plan(weeks=weeks),
        completed_week=weeks[0],
        completions=[_completion("g1", "2026-08-03")],
    )

    assert store.calls[0]["milestone_key"] == "phase:GPP:gpp-1:gpp-1"


def test_current_phase_can_complete_while_earlier_week_blocks_plan(monkeypatch):
    weeks = [
        _week("gpp-1", 1, "GPP", "2026-08-03", "2026-08-09", "g1"),
        _week("spp-1", 2, "SPP", "2026-08-10", "2026-08-16", "s1"),
    ]
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=_plan(weeks=weeks),
        completed_week=weeks[1],
        completions=[_completion("s1", "2026-08-10")],
    )

    assert [call["milestone_type"] for call in store.calls] == ["phase_completed"]
    assert store.calls[0]["phase_label"] == "SPP"


def test_open_ongoing_plan_never_records_plan_or_camp_completion(monkeypatch):
    weeks = [_week("open-1", 1, "GPP", "2026-08-03", "2026-08-09", "o1")]
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=_plan(plan_type="open_ongoing_system", weeks=weeks),
        completed_week=weeks[0],
        completions=[_completion("o1", "2026-08-03")],
    )

    assert [call["milestone_type"] for call in store.calls] == ["phase_completed"]


def test_full_fight_camp_records_phase_plan_and_camp(monkeypatch):
    weeks = [
        _week("gpp-1", 1, "GPP", "2026-08-03", "2026-08-09", "g1"),
        _week("taper-1", 2, "TAPER", "2026-08-10", "2026-08-16", "t1"),
    ]
    completions = [
        _completion("g1", "2026-08-03"),
        _completion("t1", "2026-08-10", status="modified"),
    ]
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    results = record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan(weeks=weeks),
        completed_week=weeks[1],
        completions=completions,
    )

    assert len(results) == 3
    assert [call["milestone_type"] for call in store.calls] == [
        "phase_completed",
        "plan_completed",
        "camp_completed",
    ]
    assert store.total == 950


def test_repeat_evaluation_does_not_add_more_xp(monkeypatch):
    weeks = [_week("taper-1", 1, "TAPER", "2026-08-03", "2026-08-09", "t1")]
    completions = [_completion("t1", "2026-08-03")]
    store = FakeStore()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    for _ in range(2):
        record_plan_milestones_after_completed_week(
            store,
            athlete_id="athlete-1",
            athlete_timezone="UTC",
            plan=_plan(weeks=weeks),
            completed_week=weeks[0],
            completions=completions,
        )

    assert store.total == 950
    assert len(store.seen) == 3


def test_week_completion_invokes_lifecycle_evaluation(monkeypatch):
    week = _week("gpp-1", 1, "GPP", "2026-08-03", "2026-08-09", "g1")
    plan = _plan(weeks=[week])
    store = FakeStore()
    store.completions = [_completion("g1", "2026-08-03")]
    captured = []
    monkeypatch.setattr(
        "api.services.week_progress.dispatch_progress_award_notification",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.record_plan_milestones_after_completed_week",
        lambda *args, **kwargs: captured.append(kwargs) or [],
    )

    award_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=plan,
        training_day="2026-08-03",
    )

    assert len(captured) == 1
    assert captured[0]["completed_week"]["week_id"] == "gpp-1"
    assert captured[0]["completions"] == store.completions
