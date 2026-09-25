"""POST /api/today/sparring-log: the post-sparring entry from the round timer."""

from api.routes.today import ROCKED_SAFETY_NOTICE
from api.services.today_service import resolve_training_day
from tests.support import _build_client, withdraw_health_consent

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PLAN_ID = "22222222-2222-2222-2222-222222222222"


def _seed_plan(store, plan_id: str = PLAN_ID, athlete_id: str = "athlete-1") -> None:
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    store.set_active_plan_id(athlete_id, plan_id)


def _body(**overrides) -> dict:
    base = {
        "plan_id": PLAN_ID,
        "source": "contact",
        "planned_intensity": "hard",
        "intensity": "hard",
        "rounds_completed": 5,
        "round_seconds": 180,
        "head_contact": "light",
        "rocked": False,
        "notes": "  Worked the jab to the body.  ",
    }
    return {**base, **overrides}


def _post(client, **overrides):
    return client.post("/api/today/sparring-log", headers=ATHLETE, json=_body(**overrides))


def test_logs_sparring_on_the_server_training_day():
    client, store, _ = _build_client()
    _seed_plan(store)

    resp = _post(client)

    assert resp.status_code == 201
    body = resp.json()
    assert body["review_created"] is False
    assert body["safety_notice"] is None
    log = body["log"]
    assert log["intensity"] == "hard"
    assert log["rounds_completed"] == 5
    assert log["head_contact"] == "light"
    assert log["notes"] == "Worked the jab to the body."
    assert len(store.sparring_logs) == 1
    stored = store.sparring_logs[0]
    assert stored["athlete_id"] == "athlete-1"
    assert stored["plan_id"] == PLAN_ID
    assert stored["training_day"] == resolve_training_day(None)
    assert store.admin_reviews == []


def test_client_cannot_choose_the_training_day():
    client, store, _ = _build_client()
    _seed_plan(store)

    resp = _post(client, training_day="2020-01-01")

    assert resp.status_code == 422
    assert store.sparring_logs == []


def test_rocked_opens_an_admin_review_and_returns_the_safety_notice():
    client, store, _ = _build_client()
    _seed_plan(store)

    resp = _post(client, rocked=True, head_contact="heavy")

    assert resp.status_code == 201
    body = resp.json()
    assert body["review_created"] is True
    assert body["safety_notice"] == ROCKED_SAFETY_NOTICE
    assert len(store.admin_reviews) == 1
    review = store.admin_reviews[0]
    assert review["athlete_id"] == "athlete-1"
    assert review["status"] == "pending"
    assert "rocked or dropped" in review["reason"]
    assert "hard sparring, 5 rounds, heavy head contact" in review["reason"]


def test_each_rocked_report_is_reviewed_even_with_a_pending_review():
    client, store, _ = _build_client()
    _seed_plan(store)

    assert _post(client, rocked=True).status_code == 201
    assert _post(client, rocked=True).status_code == 201

    assert len(store.admin_reviews) == 2


def test_rocked_does_not_change_todays_readiness():
    client, store, _ = _build_client()
    _seed_plan(store)
    before = client.get("/api/today", headers=ATHLETE).json()["today"]["recommendation_state"]

    _post(client, rocked=True)

    after = client.get("/api/today", headers=ATHLETE).json()["today"]["recommendation_state"]
    assert after == before


def test_requires_health_data_consent():
    client, store, _ = _build_client()
    _seed_plan(store)
    withdraw_health_consent(store)

    resp = _post(client, rocked=True)

    assert resp.status_code == 403
    assert store.sparring_logs == []
    assert store.admin_reviews == []


def test_another_athletes_plan_is_not_found():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_plan(store, OTHER_PLAN_ID, athlete_id="someone-else")

    assert _post(client, plan_id=OTHER_PLAN_ID).status_code == 404
    assert _post(client, plan_id="not-a-uuid").status_code == 404
    assert store.sparring_logs == []


def test_plain_round_timer_logs_without_a_plan():
    client, store, _ = _build_client()

    resp = _post(client, plan_id=None, source="free", planned_intensity=None, intensity="light")

    assert resp.status_code == 201
    assert store.sparring_logs[0]["plan_id"] is None
    assert store.sparring_logs[0]["source"] == "free"


def test_rejects_out_of_range_values():
    client, store, _ = _build_client()
    _seed_plan(store)

    assert _post(client, rounds_completed=31).status_code == 422
    assert _post(client, round_seconds=2).status_code == 422
    assert _post(client, intensity="war").status_code == 422
    assert _post(client, head_contact="some").status_code == 422
    assert _post(client, notes="x" * 1001).status_code == 422
    assert store.sparring_logs == []
