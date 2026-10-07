"""An optional session is offered, never owed (PR #2763 review blocker).

A training day is one unit: one log is written to every session the card
schedules. The optional camp Fight Visualisation must sit outside that unit, or
logging the day's strength would also record a visualisation the athlete never
opened, and skipping it would read as missed training.
"""
from __future__ import annotations

from datetime import datetime, timezone

from api.optional_sessions import is_optional_session
from api.services.streaks import _scheduled_days, _training_schedule
from api.services.today_service import build_today_command_view, upsert_session_completion
from api.services.week_progress import evaluate_week_completion
from api.structured_plan_locked_merge import merge_locked_structured_content
from fightcamp.fight_visualization_library import camp_visualization_role
from tests.support import FakeStore

ATHLETE = "athlete-1"
PLAN = "11111111-1111-1111-1111-111111111111"
DAY = "2026-06-23"
STRENGTH = f"{DAY}-strength"
VISUALISATION = "locked-d-24-fight-visualization"


def _week() -> dict:
    return {
        "phase_label": "GPP",
        "days": [
            {
                "date": DAY,
                "countdown_label": "D-24",
                "day_type": "high",
                "today_card": {"headline": "Strength"},
                # Execution order puts the visualisation (prime) first.
                "sessions": [
                    {
                        "session_id": VISUALISATION,
                        "session_type": "skill",
                        "title": "Fight Visualisation",
                        "objective": "Optional. Rehearse the picture.",
                        "optional": True,
                        "blocks": [{"block_type": "mindset", "display_name": "Tactical Picture"}],
                    },
                    {
                        "session_id": STRENGTH,
                        "session_type": "strength",
                        "title": "Posterior chain strength",
                        "blocks": [{"block_id": "hinge", "display_name": "Trap bar deadlift"}],
                    },
                ],
            },
            {
                "date": "2026-06-24",
                "countdown_label": "D-23",
                "day_type": "high",
                "today_card": {"headline": "Hard sparring"},
                "sessions": [
                    {
                        "session_id": "2026-06-24-sparring",
                        "session_type": "sparring",
                        "title": "Hard sparring",
                        "blocks": [{"block_id": "rounds", "display_name": "Sparring rounds"}],
                    }
                ],
            },
        ],
    }


def _store() -> FakeStore:
    store = FakeStore()
    store.plans[PLAN] = {
        "id": PLAN,
        "athlete_id": ATHLETE,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
        "structured_plan": {"weeks": [_week()]},
    }
    store.set_active_plan_id(ATHLETE, PLAN)
    return store


def _log(store: FakeStore, session_id: str, status: str = "done") -> dict:
    return upsert_session_completion(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        payload={"plan_id": PLAN, "session_id": session_id, "status": status},
        now=datetime.fromisoformat(f"{DAY}T12:00:00+00:00"),
    )


def _view(store: FakeStore):
    return build_today_command_view(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        now=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
    )


def test_today_headlines_the_real_session_not_the_optional_one():
    view = _view(_store())
    assert view.today.next_session["session_id"] == STRENGTH


def test_logging_the_day_never_writes_the_optional_session():
    store = _store()
    _log(store, STRENGTH, "started")
    assert store.get_session_completion(ATHLETE, VISUALISATION, DAY) is None
    _log(store, STRENGTH, "done")
    assert store.get_session_completion(ATHLETE, VISUALISATION, DAY) is None
    # The day still reads as done without it.
    view = _view(store)
    assert view.today.completion_status == "done"
    assert view.today.next_session["session_id"] == "2026-06-24-sparring"


def test_logging_the_optional_session_touches_only_itself():
    store = _store()
    _log(store, VISUALISATION, "done")
    assert store.get_session_completion(ATHLETE, VISUALISATION, DAY)["status"] == "done"
    assert store.get_session_completion(ATHLETE, STRENGTH, DAY) is None
    # Doing only the optional work does not finish the day.
    assert _view(store).today.next_session["session_id"] == STRENGTH


def test_streaks_and_week_progress_do_not_owe_optional_work():
    plan = {"structured_plan": {"weeks": [_week()]}}
    scheduled = dict(_scheduled_days(plan, DAY))
    assert VISUALISATION not in next(iter(scheduled.values()))
    assert all(VISUALISATION not in ids for ids in _training_schedule(plan, DAY).values())

    done = [
        {"session_id": STRENGTH, "status": "done", "training_day": DAY},
        {"session_id": "2026-06-24-sparring", "status": "done", "training_day": "2026-06-24"},
    ]
    result = evaluate_week_completion(week=_week(), completions=done)
    assert result["complete"] is True
    assert result["planned"] == 2


def test_only_the_server_can_mark_a_session_optional():
    role = camp_visualization_role(
        {"sport": "boxing", "style_tactical": ["pressure_fighter"]},
        d_day=24,
        weekday="tuesday",
        ordinal=0,
    )
    assert role is not None
    plan = {
        "weeks": [
            {
                "days": [
                    {
                        "countdown_label": "D-24",
                        "sessions": [
                            # A model-supplied flag on real training is discarded.
                            {"title": "Posterior chain strength", "optional": True, "blocks": []},
                        ],
                    }
                ]
            }
        ]
    }
    merged = merge_locked_structured_content(plan, {"weeks": [{"session_roles": [role]}]}).plan
    sessions = merged["weeks"][0]["days"][0]["sessions"]
    by_title = {session["title"]: session for session in sessions}
    assert not is_optional_session(by_title["Posterior chain strength"])
    assert is_optional_session(by_title["Fight Visualisation"])

    # And without a planning brief the model's flag is still cleared.
    bare = merge_locked_structured_content(plan, None).plan
    assert not is_optional_session(bare["weeks"][0]["days"][0]["sessions"][0])
