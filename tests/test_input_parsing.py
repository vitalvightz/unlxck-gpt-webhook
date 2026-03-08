from fightcamp.input_parsing import PlanInput


def _payload(fields: list[dict]) -> dict:
    return {"data": {"fields": fields}}


def test_training_frequency_fallback():
    data = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Weekly Training Frequency", "value": "abc"},
            {"label": "Training Availability", "value": "Mon, Wed"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.training_frequency == 2
    assert parsed.training_days == ["Mon", "Wed"]


def test_missing_fight_date_sets_na():
    data = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Training Availability", "value": "Mon, Wed, Fri"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.weeks_out == "N/A"
    assert parsed.days_until_fight is None


def test_style_parsing_lowercases():
    data = _payload(
        [
            {"label": "Fighting Style (Technical)", "value": "Boxing, MMA"},
            {"label": "Fighting Style (Tactical)", "value": "Pressure Fighter"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.tech_styles == ["boxing", "mma"]
    assert parsed.tactical_styles == ["pressure fighter"]

def test_past_fight_date_handling_is_explicit():
    data = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "When is your next fight?", "value": "2000-01-01"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.days_until_fight is None
    assert parsed.weeks_out == "N/A"

