from api.services.plan_milestones import (
    reconcile_plan_milestones_after_completed_week,
)
from api.services.week_progress import award_completed_week


def _week(week_id, phase, start, end, session_id):
    return {
        "week_id": week_id,
        "week_index": 1,
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


def _plan(plan_id, *, plan_type="general_performance", week=None):
    return {
        "id": plan_id,
        "structured_plan": {
            "plan_metadata": {"plan_type": plan_type},
            "weeks": [week] if week is not None else [],
        },
    }


def _completion(session_id, training_day):
    return {
        "session_id": session_id,
        "training_day": training_day,
        "status": "done",
        "updated_at": f"{training_day}T12:00:00+00:00",
    }


class RecoveryStore:
    def __init__(self):
        self.total = 0
        self.xp_keys = set()
        self.milestones = {}
        self.checkpoints = {}
        self.completions = []
        self.fail_once_types = set()

    def list_plan_session_completions(self, athlete_id, plan_id, *, limit=500):
        return list(self.completions)

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        amount = {"full_training_week_completed": 100}[action]
        awarded = idempotency_key not in self.xp_keys
        previous = self.total
        if awarded:
            self.xp_keys.add(idempotency_key)
            self.total += amount
        return {
            "awarded": awarded,
            "previous_total_xp": previous,
            "state": {"total_xp": self.total},
            "award": {"action": action, "amount": amount},
        }

    def begin_week_lifecycle_reconciliation(
        self,
        athlete_id,
        *,
        plan_id,
        week_id,
    ):
        key = (athlete_id, plan_id, week_id)
        row = self.checkpoints.get(
            key,
            {
                "athlete_id": athlete_id,
                "plan_id": plan_id,
                "week_id": week_id,
                "status": "pending",
                "attempt_count": 0,
            },
        )
        row = {**row, "attempt_count": row["attempt_count"] + 1}
        self.checkpoints[key] = row
        return dict(row)

    def complete_week_lifecycle_reconciliation(
        self,
        athlete_id,
        *,
        plan_id,
        week_id,
    ):
        key = (athlete_id, plan_id, week_id)
        row = {**self.checkpoints[key], "status": "completed"}
        self.checkpoints[key] = row
        return dict(row)

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
        if milestone_type in self.fail_once_types:
            self.fail_once_types.remove(milestone_type)
            raise RuntimeError(f"{milestone_type} temporarily unavailable")

        identity = (athlete_id, plan_id, milestone_type, milestone_key)
        inserted = identity not in self.milestones
        if inserted:
            self.milestones[identity] = {
                "plan_id": plan_id,
                "milestone_type": milestone_type,
                "milestone_key": milestone_key,
                "phase_label": phase_label,
                "metadata": metadata,
            }

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
        xp_key = {
            "phase_completed": f"phase-completed:{plan_id}:{milestone_key}",
            "plan_completed": f"first-plan-completed:{athlete_id}",
            "camp_completed": f"camp-completed:{plan_id}",
        }[milestone_type]
        award_was_new = xp_key not in self.xp_keys
        previous = self.total
        if award_was_new:
            self.xp_keys.add(xp_key)
            self.total += amount

        return {
            "milestone_inserted": inserted,
            "milestone": dict(self.milestones[identity]),
            "award_result": {
                "awarded": award_was_new,
                "previous_total_xp": previous,
                "state": {"total_xp": self.total},
                "award": {"action": action, "amount": amount},
            },
        }


def _plan_result(results):
    return next(
        result
        for result in results
        if result["milestone"]["milestone_type"] == "plan_completed"
    )


def test_existing_week_xp_repairs_missing_lifecycle_milestones(monkeypatch):
    week = _week(
        "week-1",
        "TAPER",
        "2026-08-03",
        "2026-08-09",
        "session-1",
    )
    plan = _plan("plan-1", plan_type="fight_camp", week=week)
    store = RecoveryStore()
    store.completions = [_completion("session-1", "2026-08-03")]
    store.xp_keys.add("full-week:plan-1:week-1")
    store.total = 100

    monkeypatch.setattr(
        "api.services.week_progress.dispatch_progress_award_notification",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.build_level_up_candidate",
        lambda **kwargs: None,
    )

    result = award_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=plan,
        training_day="2026-08-03",
    )

    assert result["awarded"] is False
    assert {
        identity[2]
        for identity in store.milestones
    } == {"phase_completed", "plan_completed", "camp_completed"}
    assert store.checkpoints[
        ("athlete-1", "plan-1", "week-1")
    ]["status"] == "completed"


def test_first_plan_gets_xp_and_first_plan_notification(monkeypatch):
    week = _week(
        "week-1",
        "GPP",
        "2026-08-03",
        "2026-08-09",
        "session-1",
    )
    plan = _plan("plan-1", week=week)
    store = RecoveryStore()
    captured = []

    monkeypatch.setattr(
        "api.services.plan_milestones.build_level_up_candidate",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda _store, candidate, **kwargs: captured.append(candidate) or 1,
    )

    outcome = reconcile_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=plan,
        completed_week=week,
        completions=[_completion("session-1", "2026-08-03")],
    )

    plan_result = _plan_result(outcome["results"])
    assert outcome["reconciled"] is True
    assert plan_result["milestone_inserted"] is True
    assert plan_result["award_result"]["awarded"] is True
    assert plan_result["award_result"]["award"]["amount"] == 250
    assert captured[-1].title == "First plan complete"
    assert "plan-1" in captured[-1].dedupe_key


def test_second_plan_gets_milestone_and_notification_without_more_first_plan_xp(
    monkeypatch,
):
    first_week = _week(
        "week-1",
        "GPP",
        "2026-08-03",
        "2026-08-09",
        "session-1",
    )
    second_week = _week(
        "week-1",
        "GPP",
        "2026-08-10",
        "2026-08-16",
        "session-2",
    )
    store = RecoveryStore()
    captured = []

    monkeypatch.setattr(
        "api.services.plan_milestones.build_level_up_candidate",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda _store, candidate, **kwargs: captured.append(candidate) or 1,
    )

    reconcile_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan("plan-1", week=first_week),
        completed_week=first_week,
        completions=[_completion("session-1", "2026-08-03")],
    )
    first_total = store.total
    captured.clear()

    outcome = reconcile_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan("plan-2", week=second_week),
        completed_week=second_week,
        completions=[_completion("session-2", "2026-08-10")],
    )

    plan_result = _plan_result(outcome["results"])
    assert plan_result["milestone_inserted"] is True
    assert plan_result["award_result"]["awarded"] is False
    assert store.total == first_total + 200
    assert captured[-1].title == "Plan complete"
    assert "plan-2" in captured[-1].dedupe_key


def test_pending_checkpoint_repairs_only_missing_milestone_on_retry(monkeypatch):
    week = _week(
        "week-1",
        "TAPER",
        "2026-08-03",
        "2026-08-09",
        "session-1",
    )
    plan = _plan("plan-1", plan_type="fight_camp", week=week)
    completion = _completion("session-1", "2026-08-03")
    store = RecoveryStore()
    store.fail_once_types.add("camp_completed")

    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "api.services.plan_milestones.build_level_up_candidate",
        lambda **kwargs: None,
    )

    first = reconcile_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=plan,
        completed_week=week,
        completions=[completion],
    )
    assert first["reconciled"] is False
    assert store.checkpoints[
        ("athlete-1", "plan-1", "week-1")
    ]["status"] == "pending"

    second = reconcile_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=plan,
        completed_week=week,
        completions=[completion],
    )
    assert second["reconciled"] is True
    assert store.checkpoints[
        ("athlete-1", "plan-1", "week-1")
    ]["status"] == "completed"
    assert {
        identity[2]
        for identity in store.milestones
    } == {"phase_completed", "plan_completed", "camp_completed"}
    assert store.total == 950
