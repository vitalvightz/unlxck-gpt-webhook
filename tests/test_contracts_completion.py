"""Tests for the thin session-completion contract (Block 4 §5)."""

import pytest
from pydantic import ValidationError

from api.contracts.completion import (
    COMPLETION_STATUSES,
    SessionCompletionRecord,
    completion_key,
    completion_landing_state,
    completion_status_of,
    find_completion,
)


def _record(**overrides):
    base = {
        "user_id": "u1",
        "plan_id": "p1",
        "session_id": "s1",
        "training_day": "2026-06-18",
        "status": "not_started",
    }
    return SessionCompletionRecord(**{**base, **overrides})


class TestStatusValues:
    def test_status_set_matches_contract(self):
        assert COMPLETION_STATUSES == {
            "not_started",
            "started",
            "done",
            "modified",
            "skipped",
        }


class TestRequiredFields:
    def test_started_requires_started_at(self):
        with pytest.raises(ValidationError):
            _record(status="started")
        # valid when started_at is present
        rec = _record(status="started", started_at="2026-06-18T10:00:00Z")
        assert rec.status == "started"

    def test_done_requires_completed_at(self):
        with pytest.raises(ValidationError):
            _record(status="done")
        rec = _record(status="done", completed_at="2026-06-18T11:00:00Z")
        assert rec.status == "done"

    def test_modified_requires_completed_at_and_reason(self):
        with pytest.raises(ValidationError):
            _record(status="modified", completed_at="2026-06-18T11:00:00Z")
        with pytest.raises(ValidationError):
            _record(status="modified", modification_reason="swapped to recovery")
        rec = _record(
            status="modified",
            completed_at="2026-06-18T11:00:00Z",
            modification_reason="swapped to recovery",
        )
        assert rec.modification_reason == "swapped to recovery"

    def test_skipped_record_is_allowed_without_timestamps(self):
        rec = _record(status="skipped", modification_reason="travel day")
        assert rec.status == "skipped"
        assert rec.started_at is None and rec.completed_at is None

    def test_skipped_requires_a_reason(self):
        with pytest.raises(ValidationError):
            _record(status="skipped")
        with pytest.raises(ValidationError):
            _record(status="skipped", modification_reason="   ")


class TestLandingState:
    def test_started_drives_resume(self):
        assert completion_landing_state("started") == "resume"

    def test_terminal_states_drive_completed(self):
        for status in ("done", "modified", "skipped"):
            assert completion_landing_state(status) == "completed"

    def test_not_started_drives_none(self):
        assert completion_landing_state("not_started") == "none"
        assert completion_landing_state(None) == "none"


class TestHelpers:
    def test_completion_status_of_degrades_gracefully(self):
        assert completion_status_of(None) == "not_started"
        assert completion_status_of({}) == "not_started"
        assert completion_status_of({"status": "bogus"}) == "not_started"
        assert completion_status_of({"status": "started"}) == "started"

    def test_key_property_and_helper_agree(self):
        rec = _record()
        assert rec.key == ("u1", "s1", "2026-06-18")
        assert completion_key(rec.model_dump()) == ("u1", "s1", "2026-06-18")

    def test_find_completion_matches_uniqueness_key(self):
        records = [
            _record(session_id="s1").model_dump(),
            _record(session_id="s2", status="started", started_at="2026-06-18T10:00:00Z").model_dump(),
        ]
        found = find_completion(records, user_id="u1", session_id="s2", training_day="2026-06-18")
        assert found is not None and found["status"] == "started"
        missing = find_completion(records, user_id="u1", session_id="s9", training_day="2026-06-18")
        assert missing is None

    def test_find_completion_accepts_model_instances(self):
        records = [
            _record(session_id="s1"),
            _record(session_id="s2", status="started", started_at="2026-06-18T10:00:00Z"),
        ]
        found = find_completion(
            records,
            user_id="u1",
            session_id="s2",
            training_day="2026-06-18",
        )
        assert found is not None
        assert found.status == "started"

    def test_completion_key_accepts_model_instances(self):
        assert completion_key(_record(session_id="s2")) == ("u1", "s2", "2026-06-18")
