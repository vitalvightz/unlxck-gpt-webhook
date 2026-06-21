"""Tests for recommendation TTL / validity (Block 4 §3)."""

from api.contracts.recommendation import (
    is_recommendation_valid,
    resolve_recommendation_state,
)

TODAY = "2026-06-18"
YESTERDAY = "2026-06-17"


def _rec(training_day, decision="modify", reason="Poor sleep; use the modified option today."):
    return {"training_day": training_day, "decision": decision, "reason": reason}


class TestValidity:
    def test_same_training_day_recommendation_is_valid(self):
        assert is_recommendation_valid(_rec(TODAY), current_training_day=TODAY) is True

    def test_yesterdays_recommendation_is_not_current_after_rollover(self):
        assert is_recommendation_valid(_rec(YESTERDAY), current_training_day=TODAY) is False

    def test_missing_recommendation_is_invalid(self):
        assert is_recommendation_valid(None, current_training_day=TODAY) is False


class TestResolveState:
    def test_valid_recommendation_mirrors_decision_and_reason(self):
        view = resolve_recommendation_state(
            _rec(TODAY, decision="pull_back", reason="Pain is high today; pull back and use recovery work."),
            current_training_day=TODAY,
        )
        assert view.state == "pull_back"
        assert view.reason == "Pain is high today; pull back and use recovery work."
        assert view.is_history is False

    def test_expired_recommendation_returns_not_checked_in_as_history(self):
        view = resolve_recommendation_state(_rec(YESTERDAY), current_training_day=TODAY)
        assert view.state == "not_checked_in"
        # Never surface an expired reason as live readiness...
        assert view.reason is None
        # ...but it may be shown as labelled history.
        assert view.is_history is True
        assert view.history_reason == "Poor sleep; use the modified option today."

    def test_missing_recommendation_returns_not_checked_in(self):
        view = resolve_recommendation_state(None, current_training_day=TODAY)
        assert view.state == "not_checked_in"
        assert view.reason is None
        assert view.is_history is False

    def test_malformed_decision_is_not_treated_as_live(self):
        view = resolve_recommendation_state(
            {"training_day": TODAY, "decision": "garbage"}, current_training_day=TODAY
        )
        assert view.state == "not_checked_in"

    def test_recommendation_state_alias_field_is_read(self):
        view = resolve_recommendation_state(
            {"training_day": TODAY, "recommendation_state": "train_as_planned"},
            current_training_day=TODAY,
        )
        assert view.state == "train_as_planned"
