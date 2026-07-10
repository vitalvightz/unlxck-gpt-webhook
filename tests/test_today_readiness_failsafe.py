"""Integration coverage: the Today/readiness submit path fails CLOSED.

A failed safety-critical read must never be interpreted as a healthy,
no-history athlete. These drive ``submit_today_checkin`` against a FakeStore
whose individual reads raise, and assert the persisted decision and the typed
signal are conservative — a clean check-in that would normally be
``train_as_planned`` is floored instead.
"""

from __future__ import annotations

from api.services.today_service import submit_today_checkin
from api.services.readiness_failsafe import (
    CHECKINS_UNAVAILABLE,
    COMPLETIONS_UNAVAILABLE,
    CONTEXT_UNAVAILABLE,
    INJURY_CONTEXT_UNAVAILABLE,
    INTAKE_UNAVAILABLE,
)
from tests.support import FakeStore

ATHLETE = "athlete-1"
PLAN = "11111111-1111-1111-1111-111111111111"
INTAKE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _store_with_plan(*, intake_id: str | None = None) -> FakeStore:
    store = FakeStore()
    store.plans[PLAN] = {
        "id": PLAN,
        "athlete_id": ATHLETE,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
        **({"intake_id": intake_id} if intake_id else {}),
    }
    return store


def _healthy_payload(**overrides) -> dict:
    base = {
        "plan_id": PLAN,
        "sleep": "good",
        "body": "normal",
        "pain": "none",
        "phase": "GPP",
        "active_injury": "none",
        "previous_session": "none",
        "sharp_pain": False,
        "instability": False,
        "swelling": False,
        "neurological_symptoms": False,
        "illness_symptoms": False,
        "cannot_warm_into_movement": False,
        "worse_next_day_pain": False,
    }
    return {**base, **overrides}


def _submit(store: FakeStore) -> dict:
    return submit_today_checkin(
        store, athlete_id=ATHLETE, athlete_timezone="", payload=_healthy_payload()
    )


# ---------------------------------------------------------------------------
# Baseline: a clean check-in with all reads succeeding is unchanged.
# ---------------------------------------------------------------------------
def test_normal_successful_path_is_train_as_planned():
    store = _store_with_plan()
    row = _submit(store)
    assert row["recommendation_state"] == "train_as_planned"
    signal = row["readiness_signal"]
    assert signal["decision"] == "train_as_planned"
    assert signal["display_state"] == "ready"
    assert signal["blocks_training"] is False
    # No safety-context failure codes on the happy path.
    for code in (
        CONTEXT_UNAVAILABLE,
        CHECKINS_UNAVAILABLE,
        COMPLETIONS_UNAVAILABLE,
        INTAKE_UNAVAILABLE,
        INJURY_CONTEXT_UNAVAILABLE,
    ):
        assert code not in signal["reason_codes"]


# ---------------------------------------------------------------------------
# Degraded reads: never train_as_planned.
# ---------------------------------------------------------------------------
def test_failed_checkin_retrieval_does_not_train_as_planned():
    class Store(FakeStore):
        def list_today_checkins(self, athlete_id, *, limit=14):
            raise RuntimeError("checkins backend down")

    store = Store()
    store.plans.update(_store_with_plan().plans)
    row = _submit(store)
    assert row["recommendation_state"] != "train_as_planned"
    assert row["recommendation_state"] == "modify"
    signal = row["readiness_signal"]
    assert CHECKINS_UNAVAILABLE in signal["reason_codes"]
    assert signal["display_state"] != "ready"


def test_failed_completion_retrieval_does_not_train_as_planned():
    class Store(FakeStore):
        def list_session_completions(self, athlete_id, *, limit=30):
            raise RuntimeError("completions backend down")

    store = Store()
    store.plans.update(_store_with_plan().plans)
    row = _submit(store)
    assert row["recommendation_state"] != "train_as_planned"
    assert row["recommendation_state"] == "modify"
    assert COMPLETIONS_UNAVAILABLE in row["readiness_signal"]["reason_codes"]


def test_failed_intake_retrieval_does_not_silently_act_healthy():
    class Store(FakeStore):
        def get_intake(self, intake_id):
            raise RuntimeError("intake backend down")

    store = Store()
    store.plans.update(_store_with_plan(intake_id=INTAKE).plans)
    row = _submit(store)
    assert row["recommendation_state"] != "train_as_planned"
    assert INTAKE_UNAVAILABLE in row["readiness_signal"]["reason_codes"]


# ---------------------------------------------------------------------------
# Injury context: the most safety-critical read -> unavailable / conservative.
# ---------------------------------------------------------------------------
def test_failed_injury_flag_read_produces_conservative_hold():
    class Store(FakeStore):
        def list_injury_flags(self, athlete_id, *, statuses=("open", "monitoring"), limit=20):
            raise RuntimeError("injury flags backend down")

    store = Store()
    store.plans.update(_store_with_plan().plans)
    row = _submit(store)
    assert row["recommendation_state"] == "pull_back"
    signal = row["readiness_signal"]
    assert signal["blocks_training"] is True
    assert signal["display_state"] == "unavailable"
    assert INJURY_CONTEXT_UNAVAILABLE in signal["reason_codes"]
    assert CONTEXT_UNAVAILABLE in signal["reason_codes"]


def test_failed_injury_classification_produces_conservative_output(monkeypatch):
    store = _store_with_plan()
    # A present open injury whose consequence tier cannot be classified.
    store.injury_flags[ATHLETE] = [
        {
            "id": "flag-1",
            "athlete_id": ATHLETE,
            "body_area": "knee",
            "description": "left knee",
            "severity": "moderate",
            "status": "open",
            "created_at": "2026-06-10T00:00:00+00:00",
        }
    ]

    def _boom(*args, **kwargs):
        raise RuntimeError("classifier down")

    monkeypatch.setattr("api.services.today_service.injury_consequence_tier", _boom)

    row = _submit(store)
    assert row["recommendation_state"] == "pull_back"
    signal = row["readiness_signal"]
    assert signal["blocks_training"] is True
    assert signal["display_state"] == "unavailable"
    assert INJURY_CONTEXT_UNAVAILABLE in signal["reason_codes"]


def test_failed_session_resolution_does_not_train_as_planned(monkeypatch):
    store = _store_with_plan()

    def _boom(*args, **kwargs):
        raise RuntimeError("schedule resolver down")

    # Force the scheduled-session resolution to raise.
    monkeypatch.setattr(
        "api.services.today_service._resolve_today_session_entry", _boom
    )

    row = _submit(store)
    assert row["recommendation_state"] != "train_as_planned"
    assert row["readiness_signal"]["display_state"] != "ready"


# ---------------------------------------------------------------------------
# Severe injury with COMPLETE context stays a specific hold (not "unavailable"):
# the typed contract distinguishes a known stop from a can't-verify hold.
# ---------------------------------------------------------------------------
def test_severe_injury_with_complete_context_is_specific_hold():
    store = _store_with_plan()
    store.injury_flags[ATHLETE] = [
        {
            "id": "flag-1",
            "athlete_id": ATHLETE,
            "body_area": "knee",
            "description": "left knee",
            "severity": "severe",
            "status": "open",
            "created_at": "2026-06-10T00:00:00+00:00",
        }
    ]
    row = _submit(store)
    assert row["recommendation_state"] == "pull_back"
    signal = row["readiness_signal"]
    assert signal["blocks_training"] is True
    # Context is complete, so this is a hold, not the "unavailable" fallback.
    assert signal["display_state"] == "hold"
    assert CONTEXT_UNAVAILABLE not in signal["reason_codes"]
    assert INJURY_CONTEXT_UNAVAILABLE not in signal["reason_codes"]
