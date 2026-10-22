"""The check-in's injury and last-session answers come from tracked data.

Today's injuries already carry each injury's latest answer and logged sessions
carry RPE/pain, so the check-in no longer asks either question.
"""
import pytest

from api.services.today_service import (
    derived_active_injury,
    derived_previous_session,
    submit_today_checkin,
)
from tests.support import FakeStore

DAY = "2026-06-19"


def flag(**fields):
    return {"id": "f1", "status": "open", "severity": "moderate", "body_area": "Left ankle",
            "description": "sprain", "surface_class": "non_surface", **fields}


@pytest.mark.parametrize("injuries,expected", [
    ([], "none"),
    ([flag(latest_reported_status="improving")], "stable"),
    ([flag(latest_reported_status="ongoing", status="monitoring")], "stable"),
    ([flag(latest_reported_status="worse")], "worse"),
    ([flag(severity="severe", latest_reported_status="improving")], "worse"),
    ([flag(status="resolved", latest_reported_status="worse")], "none"),
    # Skin routes through the surface evaluator, never this answer.
    ([flag(body_area="Left foot", description="blister", surface_class="surface_no_contact",
           latest_reported_status="worse")], "none"),
])
def test_active_injury_reads_the_tracked_injuries(injuries, expected):
    assert derived_active_injury(injuries) == expected


def session(day, **fields):
    return {"source": "unlxck", "status": "done", "completion_origin": "reported", "training_day": day,
            "session_id": f"s-{day}-{fields.get('session_rpe')}", **fields}


@pytest.mark.parametrize("sessions,expected", [
    ([], "none"),
    ([session("2026-06-18", session_rpe=5)], "normal"),
    ([session("2026-06-18", session_rpe=9)], "very_hard"),
    ([session("2026-06-18", session_rpe=4, pain_after=7)], "very_hard"),
    ([session("2026-06-16", session_rpe=9)], "none"),  # older than the previous day
    ([{"source": "external", "status": "done", "training_day": "2026-06-18", "effort": "hard",
       "duration_minutes": 60, "id": "x"}], "very_hard"),
    ([session("2026-06-18", session_rpe=9), session("2026-06-19", session_rpe=3)], "very_hard"),
])
def test_previous_session_reads_logged_sessions(sessions, expected):
    assert derived_previous_session(sessions, DAY) == expected


def test_submitted_answers_are_derived_and_a_stale_client_can_only_escalate():
    from datetime import datetime, timezone
    store = FakeStore()
    store.create_injury_flag("athlete-1", {"body_area": "Left ankle", "description": "sprain", "severity": "moderate",
                                           "status": "open", "latest_reported_status": "worse"})
    base = {"sleep": "good", "body": "normal", "pain": "none", "sharp_pain": False, "instability": False,
            "swelling": False, "neurological_symptoms": False, "illness_symptoms": False,
            "cannot_warm_into_movement": False, "worse_next_day_pain": False, "phase": None}
    now = datetime(2026, 6, 19, 12, tzinfo=timezone.utc)
    # A stale client saying "none" cannot hide the tracked Worse injury.
    row = submit_today_checkin(store, athlete_id="athlete-1", athlete_timezone="", now=now,
                               payload={**base, "active_injury": "none", "previous_session": "none"})
    assert row["active_injury"] == "worse"
    assert row["recommendation_state"] != "train_as_planned"
    # A stale client saying "very_hard" still escalates the derived "none".
    row = submit_today_checkin(store, athlete_id="athlete-1", athlete_timezone="", now=now,
                               payload={**base, "active_injury": "none", "previous_session": "very_hard"})
    assert row["previous_session"] == "very_hard"
