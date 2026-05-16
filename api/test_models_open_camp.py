from api.models import AthleteProfileInput, PlanRequest


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
