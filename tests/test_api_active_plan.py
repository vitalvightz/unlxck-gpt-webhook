"""API tests for the active-plan endpoints (Block 4 / PR #1800).

Covers GET /api/plans/active and POST /api/plans/{plan_id}/active, plus the
guarantee that Overview (/api/today) and the active-plan endpoint agree.
"""

from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
ATHLETE_ID = "athlete-1"
PLAN_A = "11111111-1111-1111-1111-111111111111"
PLAN_B = "22222222-2222-2222-2222-222222222222"
FOREIGN_PLAN = "99999999-9999-9999-9999-999999999999"


def _seed_plan(store, plan_id, *, status="ready", created_at, athlete_id=ATHLETE_ID):
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": status,
        "plan_name": f"Camp {plan_id[:1]}",
        "created_at": created_at,
    }


class TestGetActivePlan:
    def test_no_plans_returns_null_active(self):
        client, _store, _ = _build_client()
        resp = client.get("/api/plans/active", headers=ATHLETE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["active_plan"] is None
        assert body["source"] is None

    def test_latest_eligible_is_auto_selected(self):
        client, store, _ = _build_client()
        _seed_plan(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        _seed_plan(store, PLAN_B, created_at="2026-06-10T00:00:00+00:00")
        body = client.get("/api/plans/active", headers=ATHLETE).json()
        assert body["active_plan"]["plan_id"] == PLAN_B
        assert body["source"] == "auto_selected"


class TestSetActivePlan:
    def test_set_active_accepts_owned_ready_plan(self):
        client, store, _ = _build_client()
        _seed_plan(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        _seed_plan(store, PLAN_B, created_at="2026-06-10T00:00:00+00:00")
        resp = client.post(f"/api/plans/{PLAN_A}/active", headers=ATHLETE)
        assert resp.status_code == 200
        assert resp.json()["active_plan"]["plan_id"] == PLAN_A
        assert resp.json()["source"] == "explicit"
        # Now the explicit choice wins over the newer plan.
        assert client.get("/api/plans/active", headers=ATHLETE).json()["active_plan"]["plan_id"] == PLAN_A

    def test_set_active_rejects_non_owned_plan(self):
        client, store, _ = _build_client()
        _seed_plan(store, FOREIGN_PLAN, created_at="2026-06-01T00:00:00+00:00", athlete_id="someone-else")
        resp = client.post(f"/api/plans/{FOREIGN_PLAN}/active", headers=ATHLETE)
        assert resp.status_code == 404

    def test_set_active_rejects_archived_plan(self):
        client, store, _ = _build_client()
        _seed_plan(store, PLAN_A, status="archived", created_at="2026-06-01T00:00:00+00:00")
        resp = client.post(f"/api/plans/{PLAN_A}/active", headers=ATHLETE)
        assert resp.status_code == 422

    def test_set_active_rejects_review_required_plan(self):
        client, store, _ = _build_client()
        _seed_plan(store, PLAN_A, status="held_for_review", created_at="2026-06-01T00:00:00+00:00")
        resp = client.post(f"/api/plans/{PLAN_A}/active", headers=ATHLETE)
        assert resp.status_code == 422


class TestOverviewTodayAgreement:
    def test_active_endpoint_and_today_use_same_plan(self):
        client, store, _ = _build_client()
        _seed_plan(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        _seed_plan(store, PLAN_B, created_at="2026-06-10T00:00:00+00:00")
        # Pin an explicit (non-latest) active plan.
        client.post(f"/api/plans/{PLAN_A}/active", headers=ATHLETE)
        active = client.get("/api/plans/active", headers=ATHLETE).json()["active_plan"]["plan_id"]
        today_plan = client.get("/api/today", headers=ATHLETE).json()["active_plan"]["id"]
        assert active == today_plan == PLAN_A

    def test_archiving_active_plan_clears_it(self):
        client, store, _ = _build_client()
        _seed_plan(store, PLAN_A, created_at="2026-06-01T00:00:00+00:00")
        _seed_plan(store, PLAN_B, created_at="2026-06-10T00:00:00+00:00")
        client.post(f"/api/plans/{PLAN_A}/active", headers=ATHLETE)
        assert store.get_active_plan_id(ATHLETE_ID) == PLAN_A
        # Archive the active plan -> pointer cleared, fallback to next eligible.
        resp = client.delete(f"/api/plans/{PLAN_A}", headers=ATHLETE)
        assert resp.status_code == 204
        assert store.get_active_plan_id(ATHLETE_ID) is None
        assert client.get("/api/plans/active", headers=ATHLETE).json()["active_plan"]["plan_id"] == PLAN_B
