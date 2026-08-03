from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import api.services.week_progress as week_progress


ROOT = Path(__file__).resolve().parents[1]
ROLLOUT_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803183000_stage_xp_hardening_rollout.sql"
)


class _Store:
    def __init__(self, completions: list[dict[str, Any]]) -> None:
        self.completions = completions
        self.award_calls: list[dict[str, Any]] = []

    def list_plan_session_completions(
        self,
        athlete_id: str,
        plan_id: str,
        *,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return list(self.completions)

    def award_xp(
        self,
        athlete_id: str,
        *,
        action: str,
        idempotency_key: str,
        calendar_date: str | None = None,
    ) -> dict[str, Any]:
        self.award_calls.append(
            {
                "athlete_id": athlete_id,
                "action": action,
                "idempotency_key": idempotency_key,
                "calendar_date": calendar_date,
            }
        )
        return {
            "awarded": True,
            "previous_total_xp": 0,
            "state": {"total_xp": 100},
        }


def _open_plan() -> dict[str, Any]:
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "fight_date": None,
        "created_at": "2026-08-03T10:00:00+00:00",
        "planning_brief": json.dumps(
            {
                "open_plan_spec": {
                    "plan_type": "open_ongoing_system",
                    "weekly_template": {
                        "training_days": ["Mon", "Wed"],
                        "hard_sparring_days": [],
                        "coach_owned_days": {
                            "technical_skill_days": [],
                            "hard_sparring_days": [],
                        },
                    },
                    "development_block": {
                        "week_1": "Stabilise",
                        "week_2": "Build",
                        "week_3": "Peak",
                        "week_4": "Deload",
                    },
                }
            }
        ),
        "structured_plan": {
            "plan_metadata": {"plan_type": "open_ongoing_system"},
            "weeks": [
                {
                    "week_id": "wk-1",
                    "week_index": 1,
                    "phase_label": "GPP",
                    "days": [
                        {
                            "weekday": "Mon",
                            "day_type": "training",
                            "sessions": [
                                {
                                    "session_id": "ses-mon-1",
                                    "title": "Strength",
                                    "blocks": [{"title": "Main"}],
                                }
                            ],
                        },
                        {
                            "weekday": "Wed",
                            "day_type": "training",
                            "sessions": [
                                {
                                    "session_id": "ses-wed-1",
                                    "title": "Conditioning",
                                    "blocks": [{"title": "Main"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        },
    }


def _completion(session_id: str, training_day: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "training_day": training_day,
        "status": "done",
        "updated_at": f"{training_day}T20:00:00+00:00",
    }


def test_open_plan_week_is_projected_to_concrete_dates() -> None:
    week = week_progress.find_week_for_training_day(_open_plan(), "2026-08-05")

    assert week is not None
    assert week["week_id"] == "wk-1-w1"
    assert week["start_date"] == "2026-08-03"
    assert week["end_date"] == "2026-08-09"
    assert [day["date"] for day in week["days"]] == [
        "2026-08-03",
        "2026-08-05",
    ]


def test_open_plan_full_week_uses_projected_week_scope(monkeypatch) -> None:
    store = _Store(
        [
            _completion("ses-mon-1", "2026-08-03"),
            _completion("ses-wed-1", "2026-08-05"),
        ]
    )
    monkeypatch.setattr(
        week_progress,
        "dispatch_progress_award_notification",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        week_progress,
        "_reconcile_completed_week_lifecycle",
        lambda *args, **kwargs: None,
    )

    result = week_progress.award_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_open_plan(),
        training_day="2026-08-05",
    )

    assert result is not None
    assert store.award_calls == [
        {
            "athlete_id": "athlete-1",
            "action": "full_training_week_completed",
            "idempotency_key": (
                "full-week:11111111-1111-4111-8111-111111111111:wk-1-w1"
            ),
            "calendar_date": "2026-08-03",
        }
    ]


def test_open_plan_week_does_not_award_until_every_session_is_complete(monkeypatch) -> None:
    store = _Store([_completion("ses-mon-1", "2026-08-03")])
    monkeypatch.setattr(
        week_progress,
        "_reconcile_completed_week_lifecycle",
        lambda *args, **kwargs: None,
    )

    result = week_progress.award_completed_week(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        plan=_open_plan(),
        training_day="2026-08-05",
    )

    assert result is None
    assert store.award_calls == []


def test_final_migration_is_legacy_compatible_and_rollout_gated() -> None:
    sql = " ".join(ROLLOUT_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "xp_legacy_calendar_date" in sql
    assert "v_calendar_date := public.xp_legacy_calendar_date" in sql
    assert "v_action <> 'daily_login'" in sql
    assert "xp_open_plan_anchor_date" in sql
    assert "xp_open_plan_week_item" in sql
    assert "xp_full_week_planned_sessions" in sql
    assert "from public.xp_full_week_planned_sessions" in sql
    assert "'rollout_ready', true" in sql
    assert "'version', '20260803182000'" in sql
