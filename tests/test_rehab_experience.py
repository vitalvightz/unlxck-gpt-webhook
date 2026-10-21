"""Consumer contract: real Today routes, published prescriptions and completion.

Run as a module with an output filename to refresh the synthetic browser fixtures.
No production services, media publication or clinical data writes.
"""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.auth import AuthenticatedUser
from api.services import exercise_media, today_readiness_boundary, today_readiness_boundary_core, today_service
from api.routes import today as today_routes
from fightcamp.exercise_identity import normalize_exercise_key
from tests.support import FakeAuthService, grant_default_compliance
from tests.test_rehab_consumer_journey import Journey, PILOTS

HEADERS = {"Authorization": "Bearer athlete-token"}
CHEST = ("chest_strain", "Chest", "strain", "", "mild")


def consumer(monkeypatch, pilot, **journey_options):
    journey = Journey(monkeypatch, pilot, **journey_options)
    user = AuthenticatedUser(user_id=journey.athlete, email="fixture@example.com", full_name="Test athlete", metadata={})
    journey.store.ensure_profile(user)
    grant_default_compliance(journey.store, journey.athlete)
    journey.store.profiles[journey.athlete]["athlete_timezone"] = "UTC"

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return journey.now if tz else journey.now.replace(tzinfo=None)

    for module in (today_readiness_boundary, today_readiness_boundary_core, today_service, today_routes):
        monkeypatch.setattr(module, "datetime", Clock)
    exercise_media.reset_media_index_cache()
    client = TestClient(create_app(store=journey.store,
        auth_service=FakeAuthService({"athlete-token": user}), enable_in_process_generation=False))
    return journey, client


def view(client):
    response = client.get("/api/today", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def decision(body):
    return body["open_injuries"][0]["rehab_decision"]


def test_chest_restore_has_no_published_load_through_today_api(monkeypatch):
    journey, client = consumer(monkeypatch, CHEST)
    body = view(client)
    current = decision(body)
    assert current["stage"] == "restore"
    assert current["progression"]["next_transition"]["to_stage"] == "load"
    assert current["progression"]["next_transition"]["target_stage_live"] is False
    block = body["live_prescription"]["session"]["blocks"][0]
    assert block["dose"] == {}  # self-paced instructions; no invented numbers
    assert block["instructions"] == current["prescription"]["instructions"]
    assert "own pace" in block["instructions"]
    assert block["drill_snapshot"]["equipment"] == current["prescription"]["drill"]["equipment"]


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_published_load_keeps_exact_prescription_through_today_api(monkeypatch, pilot):
    journey, client = consumer(monkeypatch, pilot)
    body = view(client)
    current = decision(body)
    assert current["stage"] == "load"
    approved = next(p for p in journey.policy.prescriptions if p.stage == "load")
    block = body["live_prescription"]["session"]["blocks"][0]
    assert block["rehab_drill_id"] == approved.drill_id
    assert block["exercise_key"] == normalize_exercise_key(approved.drill_id)
    assert block["dose"] == approved.dose.model_dump(exclude_none=True)
    assert block["instructions"] == approved.instructions
    assert block["stop_rules"] == approved.stop_when
    assert block["mandatory_restrictions"] == approved.mandatory_restrictions
    assert block["resistance"] == approved.resistance
    assert block["range_choice"] == approved.range_choice
    assert block["drill_snapshot"] == current["prescription"]["drill"]


def test_missing_permission_pending_response_and_worsening_remain_engine_holds(monkeypatch):
    journey, client = consumer(monkeypatch, PILOTS[0])
    journey.permission("gentle_recovery")
    current = decision(view(client))
    assert current["stage"] == "restore"
    assert "rehabilitation_loading_not_reported" in current["progression"]["next_transition"]["reason_codes"]
    journey.complete()
    journey.advance()
    journey.permission("loading")
    body = view(client)
    current = decision(body)
    assert current["stage"] == "restore"
    assert "next_day_response_not_yet_known" in current["progression"]["next_transition"]["reason_codes"]
    assert body["delayed_rehab_prompts"]
    journey.report("worse")
    current = decision(view(client))
    assert current["stage"] != "load"
    assert current["loading_hold"]


@pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=AAAAAAAAAAA", "https://youtu.be/AAAAAAAAAAA", "https://youtube.com/shorts/AAAAAAAAAAA", None, "https://example.com/AAAAAAAAAAA"])
def test_exact_demo_metadata_does_not_change_prescription_or_completion(monkeypatch, url):
    journey, client = consumer(monkeypatch, PILOTS[0])
    before = view(client)
    live = before["live_prescription"]
    block = live["session"]["blocks"][0]
    key = block["exercise_key"]
    frozen = deepcopy(live)
    # Same reviewed import parser and serving index used by the media tool.
    video_id = exercise_media.parse_youtube_video_id(url)
    rows = [{"exercise_key": key, "video_id": video_id, "made_for_kids": False, "source": "curated"}]
    monkeypatch.setattr(journey.store, "list_exercise_media", lambda: rows)
    exercise_media.reset_media_index_cache()
    body = view(client)
    assert body["live_prescription"] == frozen
    assert bool(body["exercise_media"]) is bool(video_id)
    if video_id:
        assert body["exercise_media"][f"exercise:{key}"]["video_id"] == video_id
    payload = dict(plan_id=journey.plan, session_id=live["session"]["session_id"],
                   prescription_revision=live["revision"], rehab_tracking="injury_checkin")
    journey.now += timedelta(minutes=1)
    for status in ("started", "done"):
        response = client.post("/api/today/session-completion", headers=HEADERS,
            json={**payload, "status": status, **({"rehab_performance": "done_as_shown"} if status == "done" else {})})
        assert response.status_code == 201, response.text
    assert journey.store.rehab_exposures
    event = next(iter(journey.store.rehab_exposures.values()))["event_json"]
    assert event["drill_id"] == block["rehab_drill_id"]
    assert event["dose_completed"]["completion_state"] == "quantified"
    for field, value in block["dose"].items():
        assert event["dose_completed"][field] == value
    assert event["provenance"]["prescription_revision"] == live["revision"]
    completed = view(client)
    assert decision(completed)["schedule"]["state"] == "already_completed"
    # Completion records the work; it never supplies a favourable injury response.
    assert decision(completed)["stage"] == "restore"
    assert decision(completed)["progression"]["next_transition"]["status"] == "blocked"
    assert event["response"]["during_response"] == "not_reported"


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    fixtures = {}
    for name, pilot in [("chest", CHEST), ("achilles", PILOTS[0])]:
        with pytest.MonkeyPatch.context() as patch:
            journey, client = consumer(patch, pilot)
            fixtures[name] = {"view": view(client), "profile": client.get("/api/me", headers=HEADERS).json()}
    fixtures["pilot_blocks"] = {}
    for pilot in PILOTS[1:]:
        with pytest.MonkeyPatch.context() as patch:
            _, client = consumer(patch, pilot)
            fixtures["pilot_blocks"][pilot[0]] = view(client)["live_prescription"]["session"]["blocks"][0]
    Path(sys.argv[1]).write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")
