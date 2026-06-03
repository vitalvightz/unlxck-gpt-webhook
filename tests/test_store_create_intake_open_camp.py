from __future__ import annotations

from types import SimpleNamespace

from api.models import AthleteProfileInput, PlanRequest
from api.store import SupabaseAppStore


def _athlete() -> AthleteProfileInput:
    return AthleteProfileInput(
        full_name="Test Athlete",
        technical_style=["boxing"],
        tactical_style=[],
        stance="orthodox",
        professional_status="amateur",
        athlete_timezone="UTC",
    )


def _make_store_capturing_insert(captured: dict) -> SupabaseAppStore:
    store = object.__new__(SupabaseAppStore)

    class _Insert:
        def __init__(self, payload: dict) -> None:
            captured.update(payload)

        def execute(self):
            return SimpleNamespace(data=[{"id": "intake_1", **captured}])

    class _Table:
        def insert(self, payload: dict) -> _Insert:
            return _Insert(payload)

    class _Client:
        def table(self, _name: str) -> _Table:
            return _Table()

    store.client = _Client()
    return store


def test_create_intake_clears_fight_date_for_open_camp() -> None:
    # A client can submit an open camp while still carrying a stale fight date.
    # The persisted intake must not record that date, mirroring the planner
    # payload (which clears it) and the admin update path.
    captured: dict = {}
    store = _make_store_capturing_insert(captured)
    request = PlanRequest(
        athlete=_athlete(),
        fight_date="2026-08-01",
        no_scheduled_fight=True,
        rounds_format="3 x 3",
        weekly_training_frequency=4,
    )

    store.create_intake("00000000-0000-0000-0000-000000000001", request)

    assert captured["fight_date"] is None


def test_create_intake_keeps_fight_date_for_scheduled_fight() -> None:
    captured: dict = {}
    store = _make_store_capturing_insert(captured)
    request = PlanRequest(
        athlete=_athlete(),
        fight_date="2026-08-01",
        no_scheduled_fight=False,
        rounds_format="3 x 3",
        weekly_training_frequency=4,
    )

    store.create_intake("00000000-0000-0000-0000-000000000001", request)

    assert captured["fight_date"] == "2026-08-01"
