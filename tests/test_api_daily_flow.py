"""API tests for the live athlete daily flow.

Covers daily check-in creation, session-log creation, dashboard state
retrieval, injury flagging into the admin review queue, review resolution,
and persistence of generated plans into the dashboard.
"""

from tests.support import _build_client, _start_generation


def _checkin_payload(**overrides: object) -> dict:
    base = {
        "readiness": 4,
        "fatigue": 2,
        "soreness": 2,
        "sleep_quality": 4,
        "sleep_hours": 8.0,
    }
    return {**base, **overrides}


ATHLETE = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}


class TestDailyCheckin:
    def test_create_checkin_persists_and_returns_readiness(self):
        client, store, _ = _build_client()
        response = client.post("/api/checkins", headers=ATHLETE, json=_checkin_payload())
        assert response.status_code == 201
        body = response.json()
        assert body["checkin"]["readiness"] == 4
        assert body["readiness"]["state"] == "ready"
        assert [n["decision"] for n in body["adaptation_notes"]] == ["keep_plan"]
        assert store.daily_checkins["athlete-1"], "check-in row must be persisted"

    def test_checkin_same_day_upserts_single_row(self):
        client, store, _ = _build_client()
        first = client.post("/api/checkins", headers=ATHLETE, json=_checkin_payload())
        second = client.post(
            "/api/checkins", headers=ATHLETE, json=_checkin_payload(fatigue=5)
        )
        assert first.status_code == 201 and second.status_code == 201
        assert len(store.daily_checkins["athlete-1"]) == 1
        assert store.daily_checkins["athlete-1"][0]["fatigue"] == 5

    def test_high_fatigue_checkin_records_adaptations(self):
        client, store, _ = _build_client()
        response = client.post(
            "/api/checkins", headers=ATHLETE, json=_checkin_payload(fatigue=5, soreness=4)
        )
        body = response.json()
        assert body["readiness"]["state"] == "high_fatigue"
        decisions = {n["decision"] for n in body["adaptation_notes"]}
        assert decisions == {"reduce_intensity", "add_recovery"}
        assert store.adaptation_notes["athlete-1"]

    def test_injury_note_opens_flag_and_admin_review(self):
        client, store, _ = _build_client()
        response = client.post(
            "/api/checkins",
            headers=ATHLETE,
            json=_checkin_payload(injury_note="sharp pain in right knee"),
        )
        body = response.json()
        assert body["readiness"]["state"] == "injury_flag"
        assert body["injury_flag"]["status"] == "open"
        assert body["admin_review_created"] is True
        assert store.injury_flags["athlete-1"][0]["source"] == "checkin"
        assert store.admin_reviews and store.admin_reviews[0]["status"] == "pending"

    def test_duplicate_injury_note_does_not_duplicate_flag_or_review(self):
        client, store, _ = _build_client()
        for _ in range(2):
            client.post(
                "/api/checkins",
                headers=ATHLETE,
                json=_checkin_payload(injury_note="sharp pain in right knee"),
            )
        assert len(store.injury_flags["athlete-1"]) == 1
        assert len(store.admin_reviews) == 1

    def test_checkin_validation_rejects_out_of_range(self):
        client, _, _ = _build_client()
        response = client.post(
            "/api/checkins", headers=ATHLETE, json=_checkin_payload(fatigue=9)
        )
        assert response.status_code == 422

    def test_checkin_requires_auth(self):
        client, _, _ = _build_client()
        assert client.post("/api/checkins", json=_checkin_payload()).status_code == 401

    def test_list_checkins(self):
        client, _, _ = _build_client()
        client.post(
            "/api/checkins", headers=ATHLETE, json=_checkin_payload(checkin_date="2026-06-10")
        )
        client.post(
            "/api/checkins", headers=ATHLETE, json=_checkin_payload(checkin_date="2026-06-11")
        )
        response = client.get("/api/checkins", headers=ATHLETE)
        assert response.status_code == 200
        dates = [row["checkin_date"] for row in response.json()]
        assert dates == ["2026-06-11", "2026-06-10"]


class TestSessionLog:
    def test_create_session_log_persists(self):
        client, store, _ = _build_client()
        response = client.post(
            "/api/session-logs",
            headers=ATHLETE,
            json={"session_type": "sparring", "rpe": 7, "duration_minutes": 60},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["log"]["session_type"] == "sparring"
        assert body["log"]["rpe"] == 7
        assert [n["decision"] for n in body["adaptation_notes"]] == ["keep_plan"]
        assert store.session_logs["athlete-1"]

    def test_session_log_attaches_latest_plan(self):
        client, store, _ = _build_client()
        _start_generation(client)
        plan_id = next(iter(store.plans))
        response = client.post("/api/session-logs", headers=ATHLETE, json={"rpe": 6})
        assert response.json()["log"]["plan_id"] == plan_id

    def test_session_log_rejects_foreign_plan(self):
        client, store, _ = _build_client()
        _start_generation(client)
        plan_id = next(iter(store.plans))
        store.plans[plan_id]["athlete_id"] = "someone-else"
        response = client.post(
            "/api/session-logs", headers=ATHLETE, json={"plan_id": plan_id, "rpe": 6}
        )
        assert response.status_code == 404

    def test_repeated_high_rpe_triggers_reduce_intensity(self):
        client, _, _ = _build_client()
        for day in ("2026-06-09", "2026-06-10", "2026-06-11"):
            response = client.post(
                "/api/session-logs",
                headers=ATHLETE,
                json={"session_date": day, "rpe": 9},
            )
        body = response.json()
        assert any(
            n["rule_code"] == "repeated_high_rpe" and n["decision"] == "reduce_intensity"
            for n in body["adaptation_notes"]
        )

    def test_repeated_missed_sessions_flag_admin_review(self):
        client, store, _ = _build_client()
        for day in ("2026-06-09", "2026-06-10", "2026-06-11"):
            response = client.post(
                "/api/session-logs",
                headers=ATHLETE,
                json={"session_date": day, "completed": False},
            )
        assert response.json()["admin_review_created"] is True
        assert store.admin_reviews

    def test_list_session_logs(self):
        client, _, _ = _build_client()
        client.post("/api/session-logs", headers=ATHLETE, json={"rpe": 6})
        response = client.get("/api/session-logs", headers=ATHLETE)
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestDashboard:
    def test_dashboard_without_plan_or_checkin(self):
        client, _, _ = _build_client()
        response = client.get("/api/dashboard", headers=ATHLETE)
        assert response.status_code == 200
        body = response.json()
        assert body["plan"] is None
        assert body["checked_in_today"] is False
        # No check-in yet should prompt the athlete rather than claim readiness.
        assert body["readiness"]["state"] == "caution"

    def test_dashboard_shows_persisted_plan_and_checkin(self):
        client, store, _ = _build_client()
        _start_generation(client)
        client.post("/api/checkins", headers=ATHLETE, json=_checkin_payload())
        response = client.get("/api/dashboard", headers=ATHLETE)
        body = response.json()
        assert body["plan"] is not None
        assert body["plan"]["plan_id"] in store.plans
        assert body["checked_in_today"] is True
        assert body["readiness"]["state"] == "ready"
        assert body["latest_checkin"]["readiness"] == 4
        assert body["completion"]["checkins_7d"] == 1

    def test_dashboard_surfaces_injury_state_and_notes(self):
        client, _, _ = _build_client()
        client.post(
            "/api/checkins",
            headers=ATHLETE,
            json=_checkin_payload(injury_note="rolled left ankle"),
        )
        body = client.get("/api/dashboard", headers=ATHLETE).json()
        assert body["readiness"]["state"] == "injury_flag"
        assert len(body["open_injury_flags"]) == 1
        assert body["recent_adaptation_notes"]

    def test_dashboard_completion_counts_missed_sessions(self):
        client, _, _ = _build_client()
        client.post("/api/session-logs", headers=ATHLETE, json={"completed": False})
        client.post("/api/session-logs", headers=ATHLETE, json={"rpe": 5})
        body = client.get("/api/dashboard", headers=ATHLETE).json()
        assert body["completion"]["logged_sessions_7d"] == 2
        assert body["completion"]["completed_sessions_7d"] == 1
        assert body["completion"]["missed_sessions_7d"] == 1

    def test_dashboard_requires_auth(self):
        client, _, _ = _build_client()
        assert client.get("/api/dashboard").status_code == 401


class TestInjuryFlags:
    def test_manual_injury_report_creates_flag_and_review(self):
        client, store, _ = _build_client()
        response = client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"body_area": "shoulder", "description": "pinch on overhead press", "severity": "mild"},
        )
        assert response.status_code == 201
        assert response.json()["source"] == "manual"
        assert store.admin_reviews and store.admin_reviews[0]["status"] == "pending"

    def test_admin_resolves_injury_flag(self):
        client, store, _ = _build_client()
        client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"description": "pinch on overhead press"},
        )
        flag_id = store.injury_flags["athlete-1"][0]["id"]
        response = client.patch(
            f"/api/admin/injury-flags/{flag_id}", headers=ADMIN, json={"status": "resolved"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "resolved"
        assert response.json()["resolved_at"]
        # Resolved flag no longer drives the readiness state.
        client.post("/api/checkins", headers=ATHLETE, json=_checkin_payload())
        body = client.get("/api/dashboard", headers=ATHLETE).json()
        assert body["readiness"]["state"] == "ready"

    def test_athlete_cannot_resolve_flags(self):
        client, store, _ = _build_client()
        client.post(
            "/api/injury-flags", headers=ATHLETE, json={"description": "tweak"}
        )
        flag_id = store.injury_flags["athlete-1"][0]["id"]
        response = client.patch(
            f"/api/admin/injury-flags/{flag_id}", headers=ATHLETE, json={"status": "resolved"}
        )
        assert response.status_code == 403


class TestAdminReviewQueue:
    def test_admin_sees_pending_reviews_with_athlete_context(self):
        client, _, _ = _build_client()
        client.post(
            "/api/checkins",
            headers=ATHLETE,
            json=_checkin_payload(injury_note="sharp pain in right knee"),
        )
        response = client.get("/api/admin/reviews", headers=ADMIN)
        assert response.status_code == 200
        reviews = response.json()
        assert len(reviews) == 1
        assert reviews[0]["status"] == "pending"
        assert reviews[0]["athlete_email"] == "ari@example.com"
        assert "knee" in reviews[0]["reason"] or "review" in reviews[0]["reason"].lower()

    def test_resolve_review_records_admin_and_clears_queue(self):
        client, _, _ = _build_client()
        client.post(
            "/api/checkins",
            headers=ATHLETE,
            json=_checkin_payload(injury_note="sharp pain in right knee"),
        )
        review_id = client.get("/api/admin/reviews", headers=ADMIN).json()[0]["id"]
        response = client.post(
            f"/api/admin/reviews/{review_id}/resolve",
            headers=ADMIN,
            json={"status": "resolved", "resolution_notes": "spoke to athlete, swapped drills"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "resolved"
        assert body["resolved_by"] == "ops@unlxck.test"
        assert client.get("/api/admin/reviews", headers=ADMIN).json() == []

    def test_review_queue_is_admin_only(self):
        client, _, _ = _build_client()
        assert client.get("/api/admin/reviews", headers=ATHLETE).status_code == 403

    def test_admin_athlete_daily_status(self):
        client, _, _ = _build_client()
        client.post(
            "/api/checkins", headers=ATHLETE, json=_checkin_payload(fatigue=5)
        )
        client.post("/api/session-logs", headers=ATHLETE, json={"rpe": 9})
        response = client.get(
            "/api/admin/athletes/athlete-1/daily-status", headers=ADMIN
        )
        assert response.status_code == 200
        body = response.json()
        assert body["readiness"]["state"] == "high_fatigue"
        assert body["latest_checkin"]["fatigue"] == 5
        assert len(body["recent_session_logs"]) == 1
        assert body["recent_adaptation_notes"]

    def test_admin_athlete_daily_status_unknown_athlete(self):
        client, _, _ = _build_client()
        response = client.get(
            "/api/admin/athletes/nobody/daily-status", headers=ADMIN
        )
        assert response.status_code == 404
