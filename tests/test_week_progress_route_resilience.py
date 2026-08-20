from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"


def test_week_plan_lookup_failure_does_not_break_saved_completion():
    client, store, _ = _build_client()
    store.plans[PLAN_ID] = {
        "id": PLAN_ID,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    # The active-plan pointer is authoritative (see api/services/active_plan.py):
    # seeding plans[...] alone leaves the athlete with no active plan, so the
    # command view degrades to the no-plan shape.
    store.set_active_plan_id("athlete-1", PLAN_ID)

    original_get_plan = store.get_plan_for_athlete
    calls = 0

    def fail_second_plan_lookup(plan_id, athlete_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("week evaluation plan read failed")
        return original_get_plan(plan_id, athlete_id)

    store.get_plan_for_athlete = fail_second_plan_lookup

    response = client.post(
        "/api/today/session-completion",
        headers=ATHLETE,
        json={
            "plan_id": PLAN_ID,
            "session_id": "s1",
            "status": "started",
        },
    )

    assert response.status_code == 201
    assert response.json()["completion_status"] == "started"
    assert calls == 2
    assert len(store.session_completions["athlete-1"]) == 1
