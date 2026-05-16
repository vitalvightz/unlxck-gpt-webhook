from api.models import AthleteProfile, PlanRequest


def _athlete() -> AthleteProfile:
    return AthleteProfile(
        full_name="Test",
        sex=None,
        age=None,
        weight_kg=None,
        target_weight_kg=None,
        height_cm=None,
        technical_style=["boxer"],
        tactical_style=[],
        stance="orthodox",
        professional_status="amateur",
        record="",
        athlete_timezone="UTC",
        athlete_locale="",
    )


def test_open_camp_payload_does_not_leak_stale_fight_date() -> None:
    request = PlanRequest(
        athlete=_athlete(),
        fight_date="2030-01-01",
        no_scheduled_fight=True,
    )

    payload = request.to_payload()

    assert payload["camp_timeline_type"] == "open_camp"
    fight_date_field = next(field for field in payload["data"]["fields"] if field["label"] == "When is your next fight?")
    assert fight_date_field["value"] == ""
