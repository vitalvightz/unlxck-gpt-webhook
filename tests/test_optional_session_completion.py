"""An optional session is offered, never owed (PR #2763 review blocker).

A training day is one unit: one log is written to every session the card
schedules. The optional camp Fight Visualisation must sit outside that unit, or
logging the day's strength would also record a visualisation the athlete never
opened, and skipping it would read as missed training.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.optional_sessions import is_optional_session
from api.services.streaks import _scheduled_days, _training_schedule
from api.services.today_service import build_today_command_view, submit_today_checkin, upsert_session_completion
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
    # Logging today's session needs today's check-in (session_hold).
    submit_today_checkin(store, athlete_id=ATHLETE, athlete_timezone="", now=datetime.fromisoformat(f"{DAY}T12:00:00+00:00"),
                         payload={"plan_id": PLAN, "sleep": "good", "body": "normal", "pain": "none", "phase": "GPP",
                                  "active_injury": "none", "previous_session": "none", "sharp_pain": False,
                                  "instability": False, "swelling": False, "neurological_symptoms": False,
                                  "illness_symptoms": False, "cannot_warm_into_movement": False,
                                  "worse_next_day_pain": False})
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


@pytest.mark.parametrize(("title", "key", "session_type"), [
    ("Self-Review Cues", "self_review", "skill"),
    ("Breathing Reset", "breathing_reset", "recovery"),
    ("Tactical Watch", "tactical_watch", "skill"),
])
def test_trusted_support_fillers_are_optional_for_logging_and_adherence(title, key, session_type):
    store = _store()
    plan = store.plans[PLAN]["structured_plan"]
    support = plan["weeks"][0]["days"][0]["sessions"][0]
    support.update(title=title, session_type=session_type)
    role = {"role_key": key, "category": "support_insert", "countdown_label": "D-24",
            "governance": {"authority": "gap_fill_support_insert"}}
    merged = merge_locked_structured_content(plan, {"weeks": [{"session_roles": [role]}]}).plan
    store.plans[PLAN]["structured_plan"] = merged
    support = merged["weeks"][0]["days"][0]["sessions"][0]
    assert is_optional_session(support)
    assert _view(store).today.next_session["session_id"] == STRENGTH
    _log(store, STRENGTH, "done")
    assert store.get_session_completion(ATHLETE, VISUALISATION, DAY) is None
    assert _view(store).today.completion_status == "done"
    assert all(VISUALISATION not in ids for ids in _training_schedule(store.plans[PLAN], DAY).values())
    week = merged["weeks"][0]
    result = evaluate_week_completion(week=week, completions=[
        {"session_id": STRENGTH, "status": "done", "training_day": DAY},
        {"session_id": "2026-06-24-sparring", "status": "done", "training_day": "2026-06-24"}])
    assert result["complete"] is True
    assert result["planned"] == 2


@pytest.mark.parametrize("override", [
    {"governance": {"authority": "model"}},
])
def test_untrusted_support_cannot_become_optional(override):
    from api.optional_sessions import mark_optional_support_inserts
    plan = {"weeks": [{"days": [{"countdown_label": "D-24", "sessions": [
        {"title": "Tactical Watch", "session_type": "skill", "blocks": []}]}]}]}
    role = {"role_key": "tactical_watch", "category": "support_insert", "countdown_label": "D-24",
            "governance": {"authority": "gap_fill_support_insert"}, **override}
    mark_optional_support_inserts(plan, {"weeks": [{"session_roles": [role]}]})
    assert not is_optional_session(plan["weeks"][0]["days"][0]["sessions"][0])


def test_support_role_cannot_make_mixed_physical_work_optional():
    from api.optional_sessions import mark_optional_support_inserts
    session = {"title": "Breathing Reset", "session_type": "recovery", "blocks": [
        {"block_type": "preparation", "display_name": "Hip CARs"}]}
    plan = {"weeks": [{"days": [{"countdown_label": "D-24", "sessions": [session]}]}]}
    role = {"role_key": "breathing_reset", "category": "support_insert", "countdown_label": "D-24",
            "governance": {"authority": "gap_fill_support_insert"}}
    mark_optional_support_inserts(plan, {"weeks": [{"session_roles": [role]}]})
    assert not is_optional_session(session)


@pytest.mark.parametrize("override", [
    {"mandatory_tactical_watch": True},
    {"governance": {"authority": "gap_fill_support_insert", "mandatory": True}},
])
def test_mandatory_tactical_placement_is_optional_for_the_athlete(override):
    from api.optional_sessions import mark_optional_support_inserts
    session = {"title": "Tactical Watch", "session_type": "skill", "blocks": []}
    plan = {"weeks": [{"days": [{"countdown_label": "D-24", "sessions": [session]}]}]}
    role = {"role_key": "tactical_watch", "category": "support_insert", "countdown_label": "D-24",
            "governance": {"authority": "gap_fill_support_insert"}, **override}
    mark_optional_support_inserts(plan, {"weekly_role_map": {"weeks": [{"session_roles": [role]}]}})
    assert is_optional_session(session)


def test_saved_camp_self_review_receives_optional_status_on_read_without_mutating_storage():
    from copy import deepcopy
    from api.services.effective_structured_plan import resolve_effective_structured_plan
    store = _store()
    row = store.plans[PLAN]
    support = row["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]
    support.update(title="Self-Review Cues", session_type="skill")
    support.pop("optional")
    support["blocks"] = [{"block_type": "skill", "display_name": "Self-Review Cues"}]
    row["planning_brief"] = {"weekly_role_map": {"weeks": [{"session_roles": [{
        "role_key": "self_review", "category": "support_insert", "countdown_label": "D-24",
        "governance": {"authority": "gap_fill_support_insert"}}]}]}}
    before = deepcopy(row)
    resolved = resolve_effective_structured_plan(row)
    assert resolved is not None
    support = next(s for s in resolved["weeks"][0]["days"][0]["sessions"] if s["title"] == "Self-Review Cues")
    assert is_optional_session(support)
    assert row == before
    assert _view(store).today.next_session["session_id"] == STRENGTH
    _log(store, STRENGTH, "done")
    assert store.get_session_completion(ATHLETE, VISUALISATION, DAY) is None
