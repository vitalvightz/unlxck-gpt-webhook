"""History paging by whole training days, and manual-session takeaways."""
from datetime import date, timedelta
from uuid import uuid4

import pytest

from api.services.training_history import training_history_page
from tests.support import _build_client
from tests.test_external_training import AUTH, body, log

ATHLETE = "athlete-1"


@pytest.fixture
def api():
    client, store, _ = _build_client()
    return client, store


def _manual(store, day: str, activity: str = "boxing") -> None:
    store.create_external_training_session(ATHLETE, {
        "client_request_id": str(uuid4()), "request_fingerprint": "a" * 64, "training_day": day,
        "activity": activity, "duration_minutes": 60, "effort": "hard"})


def _days(start: str, count: int) -> list[str]:
    first = date.fromisoformat(start)
    return [(first - timedelta(days=offset)).isoformat() for offset in range(count)]


def test_pages_hold_whole_days_and_reach_every_session(api):
    _, store = api
    days = _days("2026-10-10", 7)
    for day in days:
        _manual(store, day)
        _manual(store, day, "roadwork")

    seen, before, pages = [], None, 0
    while True:
        rows, before = training_history_page(store, ATHLETE, limit=5, before_day=before)
        pages += 1
        # No day is split across pages.
        assert not {row["training_day"] for row in rows} & {row["training_day"] for row in seen}
        seen += rows
        if before is None:
            break
        assert pages < 20
    assert len(seen) == 14
    assert [row["training_day"] for row in seen] == sorted((row["training_day"] for row in seen), reverse=True)


def test_last_page_has_no_cursor(api):
    _, store = api
    _manual(store, "2026-10-10")
    rows, before = training_history_page(store, ATHLETE, limit=5)
    assert len(rows) == 1 and before is None


def test_one_day_filling_a_read_still_advances(api):
    _, store = api
    for _ in range(4):
        _manual(store, "2026-10-10")
    _manual(store, "2026-10-09")
    rows, before = training_history_page(store, ATHLETE, limit=3)
    assert {row["training_day"] for row in rows} == {"2026-10-10"} and before == "2026-10-10"
    rows, before = training_history_page(store, ATHLETE, limit=3, before_day=before)
    assert [row["training_day"] for row in rows] == ["2026-10-09"] and before is None


def test_history_endpoint_returns_the_cursor(api):
    client, store = api
    for day in _days("2026-10-10", 4):
        _manual(store, day)
    days, url = [], "/api/training/history?include_skipped=true&limit=2"
    for _ in range(6):
        page = client.get(url, headers=AUTH).json()
        days += [row["training_day"] for row in page["sessions"]]
        if not page["next_before_day"]:
            break
        url = f"/api/training/history?include_skipped=true&limit=2&before_day={page['next_before_day']}"
    assert days == _days("2026-10-10", 4)
    assert client.get("/api/training/history?before_day=10-10-2026", headers=AUTH).status_code == 422


def test_takeaway_is_saved_cleaned_and_survives_edits_and_retries(api):
    client, _ = api
    payload = body(activity="boxing")
    row = client.post("/api/training/sessions", headers=AUTH, json=payload).json()
    assert row["takeaway"] == ""
    saved = client.put(f"/api/training/sessions/{row['id']}/takeaway", headers=AUTH,
                       json={"takeaway": "  Right hand up after the jab  "})
    assert saved.status_code == 200 and saved.json()["takeaway"] == "Right hand up after the jab"
    client.patch(f"/api/training/sessions/{row['id']}", headers=AUTH,
                 json={"activity": "boxing", "duration_minutes": 45, "effort": "moderate"})
    assert client.post("/api/training/sessions", headers=AUTH, json=payload).json()["takeaway"] == \
        "Right hand up after the jab"
    listed = client.get("/api/training/history", headers=AUTH).json()["sessions"]
    assert listed[0]["takeaway"] == "Right hand up after the jab"


def test_takeaway_limits_and_ownership(api):
    client, _ = api
    row = log(api, activity="boxing")
    url = f"/api/training/sessions/{row['id']}/takeaway"
    assert client.put(url, headers=AUTH, json={"takeaway": "x" * 281}).status_code == 422
    assert client.put(url, headers=AUTH, json={"takeaway": "ok", "rpe": 9}).status_code == 422
    assert client.put(url, json={"takeaway": "ok"}).status_code in {401, 403}
    assert client.put(f"/api/training/sessions/{uuid4()}/takeaway", headers=AUTH,
                      json={"takeaway": "ok"}).status_code == 404
    assert client.delete(f"/api/training/sessions/{row['id']}", headers=AUTH).status_code == 204
    assert client.put(url, headers=AUTH, json={"takeaway": "ok"}).status_code == 404
