"""POST /api/today/exercise-log and GET /api/today/exercise-logs.

An exercise log records what the athlete actually did for one prescribed block
of today's started session, keyed on the block's server-owned ``block_id``. It
never edits the plan.
"""

import copy

import pytest

from api.services.today_service import resolve_training_day
from tests.support import _build_client, withdraw_health_consent

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PLAN_ID = "22222222-2222-2222-2222-222222222222"
SESSION_ID = "s-strength"


@pytest.fixture(autouse=True)
def no_clinical_policies(monkeypatch):
    monkeypatch.setattr("fightcamp.rehab_clinical.load_clinical_policies", lambda: ())
    monkeypatch.setattr("api.services.today_service.load_clinical_policies", lambda: ())


def _squat(**extra) -> dict:
    return {
        "block_type": "strength",
        "display_name": "Trap Bar Deadlift",
        "exercise_key": "trap-bar-deadlift",
        "sets": 4,
        "reps": 8,
        "effort": {"method": "RPE", "value": 7},
        "rest": {"value": 120, "unit": "seconds"},
        "coaching_cues": ["Push the floor away."],
        "purpose": "Posterior chain strength.",
        **extra,
    }


def _plank(**extra) -> dict:
    return {
        "block_type": "accessory",
        "display_name": "Front Plank",
        "duration": {"value": 3, "unit": "minutes"},
        **extra,
    }


def _seed_plan(store, *, blocks: list[dict], plan_id: str = PLAN_ID, athlete_id: str = "athlete-1") -> str:
    training_day = resolve_training_day(None)
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
        "structured_plan": {
            "weeks": [
                {
                    "week_index": 1,
                    "days": [
                        {
                            "date": training_day,
                            "sessions": [
                                {"session_id": SESSION_ID, "session_type": "strength_power", "blocks": blocks}
                            ],
                        }
                    ],
                }
            ]
        },
    }
    if athlete_id == "athlete-1":
        store.set_active_plan_id(athlete_id, plan_id)
    return training_day


def _start(client, *, status: str = "started", plan_id: str = PLAN_ID, **extra):
    resp = client.post(
        "/api/today/session-completion",
        headers=ATHLETE,
        json={"plan_id": plan_id, "session_id": SESSION_ID, "status": status, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp


def _reported(log: dict) -> dict:
    """The actuals the athlete reported: the served model lists every field."""
    return {key: value for key, value in log["actual"].items() if value is not None}


def _log(client, **overrides):
    body = {"plan_id": PLAN_ID, "block_id": f"blk-{resolve_training_day(None)}-trap-bar-deadlift", "status": "as_prescribed"}
    return client.post("/api/today/exercise-log", headers=ATHLETE, json={**body, **overrides})


def test_logs_a_block_done_as_prescribed_against_its_derived_block_id():
    """The stored card carries no block ids at all: the id is the server's."""
    client, store, _ = _build_client()
    training_day = _seed_plan(store, blocks=[_squat(), _plank()])
    _start(client)

    resp = _log(client)

    assert resp.status_code == 201, resp.text
    log = resp.json()["log"]
    assert log["block_id"] == f"blk-{training_day}-trap-bar-deadlift"
    assert log["status"] == "as_prescribed"
    assert log["training_day"] == training_day
    assert log["session_id"] == SESSION_ID
    assert log["exercise_key"] == "trap-bar-deadlift"
    assert _reported(log) == {}
    assert store.exercise_logs[0]["actual"] == {}
    # The prescription is frozen without the coaching copy.
    assert log["prescribed"] == {
        "display_name": "Trap Bar Deadlift",
        "block_type": "strength",
        "sets": 4,
        "reps": 8,
        "effort": {"method": "RPE", "value": 7},
        "rest": {"value": 120, "unit": "seconds"},
    }
    assert len(store.exercise_logs) == 1


def test_a_log_never_changes_the_plan():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    before = copy.deepcopy(store.plans[PLAN_ID])
    _start(client)

    resp = _log(client, status="modified", actual={"sets": 3, "reps": 6, "load": {"value": 80, "unit": "kg"}})

    assert resp.status_code == 201, resp.text
    assert store.plans[PLAN_ID] == before


def test_logs_what_was_actually_done_with_a_reason():
    client, store, _ = _build_client()
    training_day = _seed_plan(store, blocks=[_squat(), _plank()])
    _start(client)

    resp = _log(
        client,
        block_id=f"blk-{training_day}-front-plank",
        status="modified",
        actual={"duration": {"value": 15, "unit": "minutes"}},
        reason="felt_strong",
        notes="  Held it easily.  ",
    )

    assert resp.status_code == 201, resp.text
    log = resp.json()["log"]
    assert _reported(log) == {"duration": {"value": 15.0, "unit": "minutes"}}
    assert log["prescribed"]["duration"] == {"value": 3, "unit": "minutes"}
    assert log["reason"] == "felt_strong"
    assert log["notes"] == "Held it easily."
    # No planner identity on this block: it is still logged, just unkeyed.
    assert log["exercise_key"] is None


def test_work_done_as_prescribed_can_still_carry_the_weight_used():
    """The plan rarely prescribes an absolute load, so the bar weight is new information."""
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client)

    resp = _log(client, actual={"load": {"value": 100, "unit": "kg"}, "effort": {"method": "RPE", "value": 7.5}})

    assert resp.status_code == 201, resp.text
    assert _reported(resp.json()["log"]) == {
        "load": {"value": 100.0, "unit": "kg"},
        "effort": {"method": "RPE", "value": 7.5},
    }
    # Only what was reported is stored.
    assert store.exercise_logs[0]["actual"] == {
        "load": {"value": 100.0, "unit": "kg"},
        "effort": {"method": "RPE", "value": 7.5},
    }


def test_saving_the_same_block_again_corrects_the_log():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client)

    first = _log(client).json()["log"]
    second = _log(client, status="skipped", reason="equipment").json()["log"]

    assert second["id"] == first["id"]
    assert second["status"] == "skipped"
    assert second["reason"] == "equipment"
    assert len(store.exercise_logs) == 1


def test_logging_stays_open_after_the_session_is_completed():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client, status="done", session_rpe=6)

    assert _log(client).status_code == 201


def test_an_exercise_cannot_be_logged_before_the_session_is_started():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])

    resp = _log(client)

    assert resp.status_code == 409
    assert "Start today's session" in resp.json()["detail"]
    assert store.exercise_logs == []


def test_a_skipped_session_does_not_open_logging():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client, status="skipped", modification_reason="Travel day")

    assert _log(client).status_code == 409
    assert store.exercise_logs == []


def test_a_block_that_is_not_in_todays_session_is_rejected():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client)

    resp = _log(client, block_id="blk-1999-01-01-trap-bar-deadlift")

    assert resp.status_code == 404
    assert "not in today's session" in resp.json()["detail"]
    assert store.exercise_logs == []


def test_rehab_blocks_are_not_logged_here():
    client, store, _ = _build_client()
    rehab = {"block_id": "rehab-1", "block_type": "rehab", "display_name": "Ankle balance"}
    _seed_plan(store, blocks=[_squat(), rehab])
    _start(client)

    resp = _log(client, block_id="rehab-1")

    assert resp.status_code == 409
    assert "Rehab" in resp.json()["detail"]
    assert store.exercise_logs == []


def test_another_athletes_plan_is_not_found():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _seed_plan(store, blocks=[_squat()], plan_id=OTHER_PLAN_ID, athlete_id="athlete-2")
    _start(client)

    assert _log(client, plan_id=OTHER_PLAN_ID).status_code == 404
    assert _log(client, plan_id="not-a-uuid").status_code == 422
    assert client.get(f"/api/today/exercise-logs?plan_id={OTHER_PLAN_ID}", headers=ATHLETE).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"status": "modified"},  # says nothing about what was done
        {"status": "skipped", "actual": {"sets": 1}},
        {"status": "as_prescribed", "reason": "fatigue"},
        {"status": "modified", "actual": {"sets": 3}, "reason": "lazy"},
        {"status": "modified", "actual": {"load": {"value": 80, "unit": "stone"}}},
        {"status": "modified", "actual": {"duration": {"value": 15, "unit": "kg"}}},
        {"status": "modified", "actual": {"sets": -1}},
        {"status": "modified", "actual": {"effort": {"method": "RPE", "value": 11}}},
        {"status": "modified", "actual": {"prescribed_sets": 9}},
        {"status": "done"},
        {"status": "as_prescribed", "training_day": "2020-01-01"},
        {"status": "as_prescribed", "prescribed": {"sets": 1}},
    ],
)
def test_invalid_logs_are_rejected(body):
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client)

    assert _log(client, **body).status_code == 422
    assert store.exercise_logs == []


def test_a_pain_reason_is_dropped_without_health_consent_but_the_log_is_kept():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client)
    withdraw_health_consent(store, "athlete-1")

    resp = _log(client, status="modified", actual={"sets": 2}, reason="pain")

    assert resp.status_code == 201, resp.text
    log = resp.json()["log"]
    assert log["reason"] is None
    assert _reported(log) == {"sets": 2}


def test_a_pain_reason_is_kept_with_health_consent():
    client, store, _ = _build_client()
    _seed_plan(store, blocks=[_squat()])
    _start(client)

    resp = _log(client, status="modified", actual={"sets": 2}, reason="pain")

    assert resp.json()["log"]["reason"] == "pain"


def test_lists_todays_logs_for_the_plan():
    client, store, _ = _build_client()
    training_day = _seed_plan(store, blocks=[_squat(), _plank()])
    _start(client)
    _log(client)
    _log(client, block_id=f"blk-{training_day}-front-plank", status="skipped")
    # A log from another day is not today's.
    store.exercise_logs.append(
        {**store.exercise_logs[0], "id": "old", "training_day": "2020-01-01", "block_id": "old-block"}
    )

    resp = client.get(f"/api/today/exercise-logs?plan_id={PLAN_ID}", headers=ATHLETE)

    assert resp.status_code == 200
    body = resp.json()
    assert body["training_day"] == training_day
    assert [(log["block_id"], log["status"]) for log in body["logs"]] == [
        (f"blk-{training_day}-trap-bar-deadlift", "as_prescribed"),
        (f"blk-{training_day}-front-plank", "skipped"),
    ]


def test_the_frozen_session_prescription_is_what_gets_logged():
    """A session started under live injury guidance is frozen on its completion
    row; the log snapshots that copy, not the plan card's original block."""
    client, store, _ = _build_client()
    training_day = _seed_plan(store, blocks=[_squat()])
    _start(client)
    block_id = f"blk-{training_day}-trap-bar-deadlift"
    completion = store.session_completions["athlete-1"][0]
    completion["prescription_snapshot"] = {
        "plan_id": PLAN_ID,
        "training_day": training_day,
        "session": {
            "session_id": SESSION_ID,
            "blocks": [{"block_id": block_id, "block_type": "strength", "display_name": "Goblet Squat", "sets": 2, "reps": 10}],
        },
    }

    resp = _log(client)

    assert resp.status_code == 201, resp.text
    assert resp.json()["log"]["prescribed"] == {
        "display_name": "Goblet Squat",
        "block_type": "strength",
        "sets": 2,
        "reps": 10,
    }
