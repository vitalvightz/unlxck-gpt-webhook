import pytest

from api.models import MAX_OPEN_CAMP_WEEKS, AthleteProfileInput, PlanRequest


def _athlete() -> AthleteProfileInput:
    return AthleteProfileInput(
        full_name="Test Athlete",
        technical_style=["boxing"],
        tactical_style=[],
        stance="orthodox",
        professional_status="amateur",
        athlete_timezone="UTC",
    )


def test_to_payload_open_camp_clears_fight_date_field() -> None:
    request = PlanRequest(
        athlete=_athlete(),
        fight_date="2026-12-01",
        no_scheduled_fight=True,
        rounds_format="3 x 3",
        weekly_training_frequency=4,
    )

    payload = request.to_payload()
    fields = payload["data"]["fields"]
    fight_date_field = next(field for field in fields if field["label"] == "When is your next fight?")

    assert fight_date_field["value"] == ""
    assert payload["camp_timeline_type"] == "open_camp"
    assert payload["no_scheduled_fight"] is True


@pytest.mark.parametrize(
    "raw, expected",
    [
        (999, MAX_OPEN_CAMP_WEEKS),
        (MAX_OPEN_CAMP_WEEKS + 1, MAX_OPEN_CAMP_WEEKS),
        (MAX_OPEN_CAMP_WEEKS, MAX_OPEN_CAMP_WEEKS),
        (0, 1),
        (-5, 1),
        ("9999", MAX_OPEN_CAMP_WEEKS),
        (8, 8),
    ],
)
def test_open_camp_weeks_is_clamped(raw: object, expected: int) -> None:
    request = PlanRequest(athlete=_athlete(), open_camp_weeks=raw)
    assert request.open_camp_weeks == expected
