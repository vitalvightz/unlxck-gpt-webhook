from api.routes import today as today_routes
from support import _build_client


ATHLETE = {"Authorization": "Bearer athlete-token"}
ACTIVE_PLAN = "11111111-1111-1111-1111-111111111111"
INACTIVE_PLAN = "22222222-2222-2222-2222-222222222222"


def _plan(plan_id: str, *, created_at: str) -> dict:
    return {
        "id": plan_id,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": plan_id,
        "fight_date": None,
        "created_at": created_at,
    }


def _complete(client, plan_id: str, session_id: str):
    return client.post(
        "/api/today/session-completion",
        headers=ATHLETE,
        json={
            "plan_id": plan_id,
            "session_id": session_id,
            "status": "done",
        },
    )


def test_owned_inactive_plan_completion_is_accepted_but_cannot_trigger_xp(monkeypatch):
    client, store, _ = _build_client()
    store.plans[ACTIVE_PLAN] = _plan(ACTIVE_PLAN, created_at="2026-07-01T00:00:00Z")
    store.plans[INACTIVE_PLAN] = _plan(INACTIVE_PLAN, created_at="2026-07-02T00:00:00Z")
    store.set_active_plan_id("athlete-1", ACTIVE_PLAN)

    captured = []

    def fake_completion(_store, *, athlete_id, athlete_timezone, payload):
        captured.append((athlete_id, athlete_timezone, dict(payload)))
        return {
            "id": f"completion-{len(captured)}",
            "athlete_id": athlete_id,
            "plan_id": payload["plan_id"],
            "session_id": payload["session_id"],
            "training_day": "2026-08-03",
            "status": payload["status"],
            "created_at": "2026-08-03T12:00:00Z",
            "updated_at": "2026-08-03T12:00:00Z",
        }

    monkeypatch.setattr(today_routes, "upsert_session_completion", fake_completion)

    inactive = _complete(client, INACTIVE_PLAN, "inactive-session")

    assert inactive.status_code == 201
    assert inactive.json()["completion"]["plan_id"] == INACTIVE_PLAN
    assert inactive.json()["completion"]["status"] == "done"
    assert store.xp_awards.get("athlete-1", []) == []

    active = _complete(client, ACTIVE_PLAN, "active-session")

    assert active.status_code == 201
    assert [award["action"] for award in store.xp_awards["athlete-1"]] == [
        "training_logged",
        "planned_session_completed",
    ]
    assert {
        award["calendar_date"] for award in store.xp_awards["athlete-1"]
    } == {"2026-08-03"}
    assert [call[2]["plan_id"] for call in captured] == [INACTIVE_PLAN, ACTIVE_PLAN]
