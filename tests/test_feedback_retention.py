from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.feedback_retention import cleanup_expired_screenshots, cleanup_profile_screenshots
from tests.support import FakeStore


def _row(profile_id: str, *, expired: bool) -> dict:
    feedback_id = f"feedback-{len(profile_id)}-{expired}"
    path = f"{profile_id}/{feedback_id}.png"
    return {
        "id": feedback_id,
        "submitted_by_profile_id": profile_id,
        "screenshot_path": path,
        "screenshot_mime": "image/png",
        "screenshot_size_bytes": 20,
        "screenshot_width": 2,
        "screenshot_height": 2,
        "screenshot_expires_at": (
            datetime.now(timezone.utc) + (timedelta(days=-1) if expired else timedelta(days=30))
        ).isoformat(),
        "screenshot_deleted_at": None,
    }


def test_retention_deletes_only_expired_objects_then_clears_reference():
    store = FakeStore()
    expired = _row("athlete-1", expired=True)
    retained = _row("athlete-22", expired=False)
    store.beta_feedback.extend([expired, retained])
    store.feedback_screenshots[expired["screenshot_path"]] = (b"png", "image/png")
    store.feedback_screenshots[retained["screenshot_path"]] = (b"png", "image/png")

    result = cleanup_expired_screenshots(store)
    assert result.deleted == 1
    assert result.failed == 0
    assert expired["screenshot_path"] is None
    assert expired["screenshot_deleted_at"] is not None
    assert retained["screenshot_path"] in store.feedback_screenshots


def test_account_cleanup_purges_profile_objects_before_cascade():
    store = FakeStore()
    row = _row("athlete-1", expired=False)
    store.beta_feedback.append(row)
    store.feedback_screenshots[row["screenshot_path"]] = (b"png", "image/png")
    result = cleanup_profile_screenshots(store, "athlete-1")
    assert result == type(result)(deleted=1, failed=0)
    assert not store.feedback_screenshots
    assert row["screenshot_path"] is None


def test_failed_storage_delete_leaves_reference_for_retry():
    class FailingDeleteStore(FakeStore):
        def delete_feedback_screenshots(self, paths: list[str]) -> None:
            raise RuntimeError("storage unavailable")

    store = FailingDeleteStore()
    row = _row("athlete-1", expired=True)
    original_path = row["screenshot_path"]
    store.beta_feedback.append(row)
    result = cleanup_expired_screenshots(store)
    assert result.failed == 1
    assert result.deleted == 0
    assert row["screenshot_path"] == original_path
    assert row["screenshot_deleted_at"] is None
