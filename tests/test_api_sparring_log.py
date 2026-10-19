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


def test_rocked_report_is_never_acknowledged_without_a_durable_review():
    """The log and its review are one transaction: if the review insert fails,
    nothing is saved and the athlete is told to retry, never "logged"."""
    client, store, _ = _build_client()
    _seed_plan(store)
    store.fail_sparring_review_insert = True

    resp = _post(client, rocked=True, head_contact="heavy")

    assert resp.status_code == 503
    assert "not saved" in resp.json()["detail"]
    assert store.sparring_logs == []
    assert store.admin_reviews == []

    # A non-rocked entry is unaffected by the review path.
    assert _post(client, rocked=False).status_code == 201
    assert len(store.sparring_logs) == 1


def test_rocked_log_and_review_are_written_together():
    client, store, _ = _build_client()
    _seed_plan(store)

    resp = _post(client, rocked=True)

    assert resp.status_code == 201
    assert resp.json()["review_created"] is True
    assert len(store.sparring_logs) == 1
    assert len(store.admin_reviews) == 1


# -- GET /api/today/sparring-logs: the History tab ----------------------------


def _seed_log(store, day_offset: int, *, athlete_id: str = "athlete-1", **fields) -> None:
    from datetime import date, timedelta

    today = date.fromisoformat(resolve_training_day(None))
    store.sparring_logs.append(
        {
            "id": f"log-{len(store.sparring_logs)}",
            "athlete_id": athlete_id,
            "plan_id": None,
            "session_id": None,
            "training_day": (today - timedelta(days=day_offset)).isoformat(),
            "source": "free",
            "planned_intensity": None,
            "intensity": "light",
            "rounds_completed": 3,
            "round_seconds": 180,
            "head_contact": "none",
            "rocked": False,
            "notes": "",
            "created_at": f"2026-01-01T00:00:{len(store.sparring_logs):02d}+00:00",
            **fields,
        }
    )


def _history(client, **params):
    return client.get("/api/today/sparring-logs", headers=ATHLETE, params=params)


def test_history_is_empty_before_any_sparring():
    client, _, _ = _build_client()

    resp = _history(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["logs"] == []
    assert body["current_training_day"] == resolve_training_day(None)
    assert body["last_7_days"] == {
        "days": 7,
        "sessions": 0,
        "rounds": 0,
        "hard_rounds": 0,
        "hard_days": 0,
        "heavy_head_contact_sessions": 0,
        "rocked_count": 0,
    }
    assert body["last_hard_day"] is None
    assert body["last_rocked_day"] is None


def test_a_logged_entry_shows_up_in_history():
    client, store, _ = _build_client()
    _seed_plan(store)
    _post(client)

    body = _history(client).json()

    assert len(body["logs"]) == 1
    assert body["logs"][0]["notes"] == "Worked the jab to the body."
    assert body["last_7_days"]["hard_rounds"] == 5
    assert body["last_hard_day"] == resolve_training_day(None)


def test_history_is_newest_first_and_only_the_athletes_own():
    client, store, _ = _build_client()
    _seed_log(store, 3, notes="older")
    _seed_log(store, 0, notes="today")
    _seed_log(store, 0, athlete_id="someone-else", notes="not mine")

    logs = _history(client).json()["logs"]

    assert [log["notes"] for log in logs] == ["today", "older"]


def test_windows_count_rounds_hard_days_head_contact_and_rocked():
    client, store, _ = _build_client()
    _seed_log(store, 0, intensity="hard", rounds_completed=4, head_contact="heavy")
    _seed_log(store, 0, intensity="hard", rounds_completed=2)  # same day: one hard day
    _seed_log(store, 6, intensity="hard", rounds_completed=3, rocked=True, head_contact="heavy")
    _seed_log(store, 7, intensity="medium", rounds_completed=5)  # day 8: outside the week
    _seed_log(store, 27, intensity="hard", rounds_completed=6)  # last day of 28
    _seed_log(store, 28, intensity="hard", rounds_completed=9, rocked=True)  # outside both

    body = _history(client).json()

    assert body["last_7_days"] == {
        "days": 7,
        "sessions": 3,
        "rounds": 9,
        "hard_rounds": 9,
        "hard_days": 2,
        "heavy_head_contact_sessions": 2,
        "rocked_count": 1,
    }
    assert body["last_28_days"]["sessions"] == 5
    assert body["last_28_days"]["rounds"] == 20
    assert body["last_28_days"]["hard_days"] == 3
    assert body["last_28_days"]["rocked_count"] == 1


def test_windows_stay_complete_when_the_list_is_paged():
    client, store, _ = _build_client()
    for _ in range(5):
        _seed_log(store, 1, rounds_completed=2)

    body = _history(client, limit=2).json()

    assert len(body["logs"]) == 2
    assert body["last_7_days"]["sessions"] == 5
    assert body["last_7_days"]["rounds"] == 10


def test_last_hard_and_rocked_days_look_past_the_windows():
    from datetime import date, timedelta

    client, store, _ = _build_client()
    _seed_log(store, 90, intensity="hard", rocked=True)
    _seed_log(store, 40, intensity="hard")

    body = _history(client, limit=1).json()

    today = date.fromisoformat(resolve_training_day(None))
    assert body["last_hard_day"] == (today - timedelta(days=40)).isoformat()
    assert body["last_rocked_day"] == (today - timedelta(days=90)).isoformat()


def test_history_rejects_an_out_of_range_limit():
    client, _, _ = _build_client()

    assert _history(client, limit=0).status_code == 422
    assert _history(client, limit=201).status_code == 422


# -- Manual sparring follow-up and retry safety --------------------------------

REQUEST_ID = "33333333-3333-4333-8333-333333333333"


def _manual_session(client, *, activity: str = "sparring", effort: str = "hard", request_id: str | None = None) -> dict:
    from uuid import uuid4

    resp = client.post("/api/training/sessions", headers=ATHLETE, json={
        "activity": activity, "duration_minutes": 45, "effort": effort,
        "client_request_id": request_id or str(uuid4()),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _manual_detail(client, session_id: str, **overrides):
    return _post(client, **{
        "plan_id": None, "source": "free", "planned_intensity": None, "round_seconds": None,
        "external_session_id": session_id, **overrides,
    })


def test_manual_sparring_detail_links_to_the_session_without_a_plan():
    client, store, _ = _build_client()
    session = _manual_session(client)

    resp = _manual_detail(client, session["id"], client_request_id=REQUEST_ID)

    assert resp.status_code == 201, resp.text
    log = resp.json()["log"]
    assert log["external_session_id"] == session["id"]
    assert log["plan_id"] is None
    assert log["training_day"] == session["training_day"]
    # The manual session stays the one training occurrence in history.
    history = client.get("/api/training/history", headers=ATHLETE).json()["sessions"]
    assert [row["id"] for row in history] == [session["id"]]


def test_manual_detail_uses_the_manual_sessions_own_day():
    client, store, _ = _build_client()
    session = _manual_session(client)
    store.external_training_sessions[session["id"]]["training_day"] = "2026-01-02"

    log = _manual_detail(client, session["id"]).json()["log"]

    assert log["training_day"] == "2026-01-02"


def test_manual_detail_requires_an_owned_live_sparring_session():
    client, store, _ = _build_client()
    boxing = _manual_session(client, activity="boxing")
    assert _manual_detail(client, boxing["id"]).status_code == 404
    assert _manual_detail(client, "44444444-4444-4444-8444-444444444444").status_code == 404
    sparring = _manual_session(client)
    store.external_training_sessions[sparring["id"]]["athlete_id"] = "someone-else"
    assert _manual_detail(client, sparring["id"]).status_code == 404
    assert store.sparring_logs == []


def test_manual_detail_rejects_plan_fields():
    client, store, _ = _build_client()
    _seed_plan(store)
    session = _manual_session(client)

    assert _manual_detail(client, session["id"], plan_id=PLAN_ID).status_code == 422
    assert _manual_detail(client, session["id"], source="contact").status_code == 422
    assert _manual_detail(client, session["id"], planned_intensity="hard").status_code == 422
    assert store.sparring_logs == []


def test_a_retried_report_writes_one_log_and_one_review():
    client, store, _ = _build_client()
    _seed_plan(store)

    first = _post(client, rocked=True, client_request_id=REQUEST_ID)
    retry = _post(client, rocked=True, client_request_id=REQUEST_ID)

    assert first.status_code == retry.status_code == 201
    assert retry.json()["log"]["id"] == first.json()["log"]["id"]
    assert retry.json()["review_created"] is True
    assert retry.json()["safety_notice"] == ROCKED_SAFETY_NOTICE
    assert len(store.sparring_logs) == 1
    assert len(store.admin_reviews) == 1


def test_a_later_correction_never_withdraws_a_head_impact_report():
    client, store, _ = _build_client()
    session = _manual_session(client)

    rocked = _manual_detail(client, session["id"], rocked=True, head_contact="heavy", client_request_id=REQUEST_ID,
                            detail_revision=1)
    corrected = _manual_detail(client, session["id"], rocked=False, head_contact="none", detail_revision=2,
                               rounds_completed=2, client_request_id="55555555-5555-4555-8555-555555555555")

    assert rocked.status_code == corrected.status_code == 201
    assert corrected.json()["log"]["id"] == rocked.json()["log"]["id"]
    # Rounds are corrected; recorded head-impact evidence is not lowered.
    assert corrected.json()["log"]["rounds_completed"] == 2
    assert corrected.json()["log"]["detail_revision"] == 2
    assert corrected.json()["log"]["head_contact"] == "heavy"
    assert corrected.json()["log"]["rocked"] is True
    assert corrected.json()["safety_notice"] == ROCKED_SAFETY_NOTICE
    assert len(store.sparring_logs) == 1
    assert len(store.admin_reviews) == 1


def test_separate_manual_sparring_sessions_on_one_day_stay_distinct():
    client, store, _ = _build_client()
    first = _manual_session(client)
    second = _manual_session(client)

    assert _manual_detail(client, first["id"]).status_code == 201
    assert _manual_detail(client, second["id"]).status_code == 201

    assert len(store.sparring_logs) == 2


def test_rocked_report_leads_today_with_a_no_contact_notice():
    client, store, _ = _build_client()
    assert client.get("/api/today", headers=ATHLETE).json()["today"]["primary_safety_notice"] is None
    session = _manual_session(client)

    _manual_detail(client, session["id"], rocked=True)

    notice = client.get("/api/today", headers=ATHLETE).json()["today"]["primary_safety_notice"]
    assert notice["code"] == "head_impact_no_contact"
    assert notice["tone"] == "red"
    assert "No more contact today" in notice["title"]


def test_rocked_report_notice_also_applies_with_a_plan():
    client, store, _ = _build_client()
    _seed_plan(store)

    _post(client, rocked=True)

    notice = client.get("/api/today", headers=ATHLETE).json()["today"]["primary_safety_notice"]
    assert notice["code"] == "head_impact_no_contact"


def test_an_earlier_days_head_impact_does_not_carry_the_same_day_notice():
    client, store, _ = _build_client()
    _seed_log(store, 1, rocked=True)

    assert client.get("/api/today", headers=ATHLETE).json()["today"]["primary_safety_notice"] is None


def test_hard_manual_effort_alone_never_creates_contact_evidence():
    client, store, _ = _build_client()

    _manual_session(client, effort="hard")

    assert store.sparring_logs == []
    assert store.admin_reviews == []
    assert client.get("/api/today", headers=ATHLETE).json()["today"]["primary_safety_notice"] is None


def test_a_delayed_retry_never_overwrites_a_later_correction():
    client, store, _ = _build_client()
    session = _manual_session(client)
    report_a = "66666666-6666-4666-8666-666666666666"
    report_b = "77777777-7777-4777-8777-777777777777"

    _manual_detail(client, session["id"], client_request_id=report_a, detail_revision=1, rounds_completed=3)
    _manual_detail(client, session["id"], client_request_id=report_b, detail_revision=2, rounds_completed=8)
    stale = _manual_detail(client, session["id"], client_request_id=report_a, detail_revision=1, rounds_completed=3)

    assert stale.status_code == 201
    assert stale.json()["log"]["rounds_completed"] == 8
    assert store.sparring_logs[0]["rounds_completed"] == 8
    assert len(store.sparring_logs) == 1


def test_an_older_revision_arriving_late_cannot_overwrite_a_newer_one():
    client, store, _ = _build_client()
    session = _manual_session(client)

    _manual_detail(client, session["id"], detail_revision=2, rounds_completed=8,
                   client_request_id="88888888-8888-4888-8888-888888888888")
    late = _manual_detail(client, session["id"], detail_revision=1, rounds_completed=3,
                          client_request_id="99999999-9999-4999-8999-999999999999")

    assert late.json()["log"]["rounds_completed"] == 8


def test_detail_revision_is_bounded():
    client, store, _ = _build_client()
    session = _manual_session(client)

    assert _manual_detail(client, session["id"], detail_revision=-1).status_code == 422
    assert store.sparring_logs == []


def test_a_later_correction_can_raise_head_contact_and_history_returns_the_revision():
    client, store, _ = _build_client()
    session = _manual_session(client)
    _manual_detail(client, session["id"], head_contact="none", detail_revision=1)
    corrected = _manual_detail(client, session["id"], head_contact="heavy", detail_revision=2)

    assert corrected.json()["log"]["head_contact"] == "heavy"
    logs = client.get("/api/today/sparring-logs", headers=ATHLETE).json()["logs"]
    assert logs[0]["detail_revision"] == 2 and logs[0]["external_session_id"] == session["id"]
