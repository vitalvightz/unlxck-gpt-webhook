"""Post-session review feedback: the prompt shown after a completed session."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from api.models import SESSION_FEEDBACK_SESSION_ID_MAX_CHARS
from api.services.today_service import resolve_training_day
from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PLAN_ID = "22222222-2222-2222-2222-222222222222"
SESSION_ID = "week-1-day-2-session-1"


def _seed_plan(store, *, plan_id: str = PLAN_ID, athlete_id: str = "athlete-1") -> None:
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "intake_id": None,
        "status": "ready",
        "plan_text": "Released plan",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _seed_completion(
    store,
    *,
    athlete_id: str = "athlete-1",
    plan_id: str = PLAN_ID,
    session_id: str = SESSION_ID,
    status: str = "done",
    training_day: str | None = None,
) -> str:
    day = training_day or resolve_training_day("")
    store.upsert_session_completion(
        athlete_id,
        {
            "plan_id": plan_id,
            "session_id": session_id,
            "training_day": day,
            "status": status,
            "session_rpe": 7,
            "pain_after": 1,
            "modification_reason": "",
            "notes": "",
            "started_at": None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return day


def _png_bytes() -> bytes:
    raw = io.BytesIO()
    Image.new("RGB", (24, 16), "red").save(raw, format="PNG")
    return raw.getvalue()


def test_structured_answers_are_saved_against_the_completed_session():
    client, store, _ = _build_client()
    _seed_plan(store)
    training_day = _seed_completion(store)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={
            "plan_id": PLAN_ID,
            "session_id": SESSION_ID,
            "difficulty": "too_hard",
            "instructions": "clear",
            "plan_accuracy": "something_wrong",
            "comment": "Round count felt off",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["surface"] == "session"
    assert body["category"] == "session_review"
    assert body["response"] is None
    assert body["structured_response"] == {
        "difficulty": "too_hard",
        "instructions": "clear",
        "plan_accuracy": "something_wrong",
    }

    saved = store.beta_feedback[0]
    assert saved["submitted_by_profile_id"] == "athlete-1"
    assert saved["context_key"] == f"session:{PLAN_ID}:{SESSION_ID}:{training_day}"
    assert saved["session_id"] == SESSION_ID
    assert saved["plan_id"] == PLAN_ID
    assert saved["priority"] == "normal"
    assert saved["reason"] is None
    # The logged completion travels with the review so an operator can read the
    # answers against what the athlete actually recorded.
    assert saved["readiness_snapshot"]["session_rpe"] == 7
    assert saved["readiness_snapshot"]["status"] == "done"


def test_unanswered_questions_are_omitted_rather_than_defaulted():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={
            "plan_id": PLAN_ID,
            "session_id": SESSION_ID,
            "difficulty": "appropriate",
            "instructions": "",
            "plan_accuracy": "",
        },
    )

    assert response.status_code == 201
    assert store.beta_feedback[0]["structured_response"] == {"difficulty": "appropriate"}


def test_re_answering_corrects_the_same_row_instead_of_stacking_duplicates():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)

    first = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "too_easy"},
    )
    second = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "too_hard"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert len(store.beta_feedback) == 1
    assert store.beta_feedback[0]["structured_response"] == {"difficulty": "too_hard"}


def test_empty_submission_is_rejected():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "comment": "   "},
    )

    assert response.status_code == 422
    assert not store.beta_feedback


def test_invalid_answer_values_are_rejected():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "brutal"},
    )

    assert response.status_code == 422
    assert not store.beta_feedback


@pytest.mark.parametrize("status", ["not_started", "started", "skipped"])
def test_only_a_trained_session_can_be_reviewed(status: str):
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store, status=status)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "appropriate"},
    )

    assert response.status_code == 409
    assert not store.beta_feedback


def test_a_session_with_no_completion_cannot_be_reviewed():
    client, store, _ = _build_client()
    _seed_plan(store)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "appropriate"},
    )

    assert response.status_code == 404
    assert not store.beta_feedback


def test_another_athletes_plan_cannot_be_reviewed():
    client, store, _ = _build_client()
    _seed_plan(store, plan_id=OTHER_PLAN_ID, athlete_id="other-athlete")
    _seed_completion(store, athlete_id="other-athlete", plan_id=OTHER_PLAN_ID)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": OTHER_PLAN_ID, "session_id": SESSION_ID, "difficulty": "appropriate"},
    )

    assert response.status_code == 404
    assert not store.beta_feedback


def test_a_completion_logged_against_another_plan_is_not_reviewable_under_this_one():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_plan(store, plan_id=OTHER_PLAN_ID)
    _seed_completion(store, plan_id=OTHER_PLAN_ID)

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "appropriate"},
    )

    assert response.status_code == 404
    assert not store.beta_feedback


@pytest.mark.parametrize("role", ["coach", "gym_owner"])
def test_non_training_roles_cannot_review_sessions(role: str):
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)
    store.profiles["athlete-1"]["role"] = role

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "appropriate"},
    )

    assert response.status_code == 403


def test_the_derived_context_key_stays_inside_its_database_ceiling():
    """A long session id must not silently overflow context_key's 180-char check."""

    client, store, _ = _build_client()
    _seed_plan(store)
    longest = "s" * SESSION_FEEDBACK_SESSION_ID_MAX_CHARS
    _seed_completion(store, session_id=longest)

    accepted = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": longest, "difficulty": "appropriate"},
    )

    assert accepted.status_code == 201
    assert len(store.beta_feedback[0]["context_key"]) <= 180

    # One character further is refused up front rather than as a database error.
    over_limit = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": f"{longest}s", "difficulty": "appropriate"},
    )
    assert over_limit.status_code == 422


def test_a_retro_logged_session_is_reviewed_against_the_day_it_was_logged():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store, training_day="2026-01-04")

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={
            "plan_id": PLAN_ID,
            "session_id": SESSION_ID,
            "training_day": "2026-01-04",
            "difficulty": "appropriate",
        },
    )

    assert response.status_code == 201
    assert store.beta_feedback[0]["context_key"].endswith(":2026-01-04")


def test_screenshot_is_sanitised_and_a_replacement_purges_the_superseded_image(monkeypatch):
    monkeypatch.setenv("FEEDBACK_SCREENSHOT_LIMIT_PER_HOUR", "5")
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)

    first = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "too_hard"},
        files={"screenshot": ("shot.png", _png_bytes(), "image/png")},
    )
    assert first.status_code == 201
    original_path = store.beta_feedback[0]["screenshot_path"]
    assert original_path.startswith("athlete-1/session-")
    assert original_path in store.feedback_screenshots

    second = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "too_hard"},
        files={"screenshot": ("shot2.png", _png_bytes(), "image/png")},
    )
    assert second.status_code == 201
    replacement_path = store.beta_feedback[0]["screenshot_path"]
    assert replacement_path != original_path
    assert replacement_path in store.feedback_screenshots
    # Exactly one image is referenced, so the old one must not linger in storage.
    assert original_path not in store.feedback_screenshots


def test_answering_again_without_a_screenshot_keeps_the_attached_one(monkeypatch):
    monkeypatch.setenv("FEEDBACK_SCREENSHOT_LIMIT_PER_HOUR", "5")
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)

    client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "too_hard"},
        files={"screenshot": ("shot.png", _png_bytes(), "image/png")},
    )
    original_path = store.beta_feedback[0]["screenshot_path"]

    response = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": SESSION_ID, "difficulty": "appropriate"},
    )

    assert response.status_code == 201
    assert store.beta_feedback[0]["screenshot_path"] == original_path
    assert original_path in store.feedback_screenshots


def test_screenshot_uploads_are_rate_limited_but_plain_answers_are_not(monkeypatch):
    monkeypatch.setenv("FEEDBACK_SCREENSHOT_LIMIT_PER_HOUR", "1")
    client, store, _ = _build_client()
    _seed_plan(store)
    for index in range(4):
        _seed_completion(store, session_id=f"session-{index}")

    with_image = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": "session-0", "difficulty": "too_hard"},
        files={"screenshot": ("shot.png", _png_bytes(), "image/png")},
    )
    assert with_image.status_code == 201

    blocked = client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={"plan_id": PLAN_ID, "session_id": "session-1", "difficulty": "too_hard"},
        files={"screenshot": ("shot.png", _png_bytes(), "image/png")},
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "screenshot_rate_limited"

    # Answering the quick questions never consumes the screenshot allowance, so
    # a tester who logs several sessions a day is never blocked from reviewing.
    for session_id in ("session-2", "session-3"):
        plain = client.post(
            "/api/feedback/session",
            headers=ATHLETE,
            data={"plan_id": PLAN_ID, "session_id": session_id, "difficulty": "appropriate"},
        )
        assert plain.status_code == 201


def test_session_review_reaches_the_admin_queue_with_its_answers():
    client, store, _ = _build_client()
    _seed_plan(store)
    _seed_completion(store)
    client.post(
        "/api/feedback/session",
        headers=ATHLETE,
        data={
            "plan_id": PLAN_ID,
            "session_id": SESSION_ID,
            "difficulty": "too_hard",
            "plan_accuracy": "something_wrong",
        },
    )

    response = client.get("/api/admin/feedback", headers=ADMIN)

    assert response.status_code == 200
    record = next(item for item in response.json() if item["surface"] == "session")
    assert record["category"] == "session_review"
    assert record["session_id"] == SESSION_ID
    assert record["structured_response"] == {
        "difficulty": "too_hard",
        "plan_accuracy": "something_wrong",
    }
