from pathlib import Path

from api.services.plan_milestones import record_plan_milestones_after_completed_week


def _week():
    return {
        "week_id": "week-1",
        "week_index": 1,
        "phase_label": "TAPER",
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


def _completion():
    return {
        "session_id": "session-1",
        "training_day": "2026-08-03",
        "status": "done",
        "updated_at": "2026-08-03T12:00:00+00:00",
    }


class Store:
    def __init__(self):
        self.total = 0
        self.calls = []

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
        amount = {
            "phase_completed": 200,
            "plan_completed": 250,
            "camp_completed": 500,
        }[milestone_type]
        previous = self.total
        self.total += amount
        self.calls.append(milestone_type)
        return {
            "milestone_inserted": True,
            "award_result": {
                "awarded": True,
                "previous_total_xp": previous,
                "state": {"total_xp": self.total},
            },
        }


def _plan(plan_type_marker):
    metadata = {} if plan_type_marker is None else {"plan_type": plan_type_marker}
    return {
        "id": "plan-1",
        "structured_plan": {
            "plan_metadata": metadata,
            "weeks": [_week()],
        },
    }


def test_missing_plan_type_fails_closed_for_plan_and_camp(monkeypatch):
    store = Store()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=_plan(None),
        completed_week=_week(),
        completions=[_completion()],
    )

    assert store.calls == ["phase_completed"]


def test_finite_non_camp_plan_records_phase_and_first_plan_only(monkeypatch):
    store = Store()
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda *args, **kwargs: 0,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        plan=_plan("general_performance"),
        completed_week=_week(),
        completions=[_completion()],
    )

    assert store.calls == ["phase_completed", "plan_completed"]


def test_full_camp_emits_only_highest_final_level_notification(monkeypatch):
    store = Store()
    delivered = []
    monkeypatch.setattr(
        "api.services.plan_milestones.dispatch_push_candidate",
        lambda _store, candidate, **kwargs: delivered.append(candidate) or 1,
    )

    record_plan_milestones_after_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_plan("fight_camp"),
        completed_week=_week(),
        completions=[_completion()],
    )

    assert len(delivered) == 1
    assert delivered[0].title == "Level 3: Amateur"
    assert delivered[0].category == "progress_milestones"


def test_migration_secures_and_atomically_records_milestones():
    sql = Path(
        "supabase/migrations/20260803123000_add_plan_progress_milestones.sql"
    ).read_text(encoding="utf-8")

    assert "alter table public.plan_milestones enable row level security" in sql
    assert "plan_milestones_select_own" in sql
    assert "record_plan_milestone is restricted to the backend service role" in sql
    assert "v_award_result := public.award_athlete_xp" in sql
    assert "when 'phase_completed' then 200" in sql
    assert "when 'camp_completed' then 500" in sql
    assert "first-plan-completed:" in sql
