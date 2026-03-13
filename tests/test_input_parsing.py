import re
from datetime import datetime

import pytest

from fightcamp import input_parsing
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


def test_same_day_fight_date_remains_fight_week_active():
    today = datetime.now().strftime("%Y-%m-%d")
    data = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "When is your next fight?", "value": today},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.days_until_fight == 0
    assert parsed.weeks_out == 1


def test_field_alias_matching_for_key_inputs():
    data = _payload(
        [
            {"label": "Fight date", "value": "2099-01-20"},
            {"label": "Technical style", "value": "Boxing"},
            {"label": "Tactical style", "value": "Pressure Fighter"},
            {"label": "Training frequency", "value": "4"},
            {"label": "Available training days", "value": "Mon, Wed, Fri"},
            {"label": "Current injuries", "value": "wrist soreness"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.next_fight_date == "2099-01-20"
    assert parsed.tech_styles == ["boxing"]
    assert parsed.tactical_styles == ["pressure fighter"]
    assert parsed.training_frequency == 4
    assert parsed.training_days == ["Mon", "Wed", "Fri"]
    assert parsed.injuries == "wrist soreness"


def test_whitespace_case_insensitive_label_matching():
    data = _payload(
        [
            {"label": "  weekly training frequency  ", "value": "3"},
            {"label": "  training availability  ", "value": "Tue, Thu"},
            {"label": "  when IS your NEXT fight?  ", "value": "2099-02-01"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.training_frequency == 3
    assert parsed.training_days == ["Tue", "Thu"]
    assert parsed.next_fight_date == "2099-02-01"


def test_exact_match_still_preferred_over_alias():
    data = _payload(
        [
            {"label": "Fight date", "value": "2099-02-01"},
            {"label": "When is your next fight?", "value": "2099-03-01"},
            {"label": "Training frequency", "value": "2"},
            {"label": "Weekly Training Frequency", "value": "5"},
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.next_fight_date == "2099-03-01"
    assert parsed.training_frequency == 5


def test_payload_requires_fields_list():
    with pytest.raises(ValueError, match=re.escape("payload missing required data.fields list")):
        PlanInput.from_payload({"data": {}})


def test_multiselect_value_maps_when_option_ids_are_strings():
    data = _payload(
        [
            {
                "label": "Training Availability",
                "value": [1, 3],
                "options": [
                    {"id": "1", "text": "Mon"},
                    {"id": "2", "text": "Tue"},
                    {"id": "3", "text": "Fri"},
                ],
            }
        ]
    )
    parsed = PlanInput.from_payload(data)
    assert parsed.available_days == "Mon, Fri"
    assert parsed.training_days == ["Mon", "Fri"]


def test_compute_days_until_fight_uses_patchable_calendar_reference_for_date_only_values(monkeypatch):
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: datetime(2026, 3, 13, 23, 30))

    fight_date = input_parsing.parse_fight_date("2026-03-14")

    assert fight_date is not None
    assert input_parsing._compute_days_until_fight("2026-03-14", fight_date) == 1


def test_plan_input_uses_local_calendar_day_for_date_only_rollover(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: datetime(2026, 3, 13, 19, 30))

    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Full name", "value": "West Coast Athlete"},
                {"label": "When is your next fight?", "value": "2026-03-14"},
            ]
        )
    )

    assert parsed.days_until_fight == 1
    assert parsed.weeks_out == 1


def test_compute_days_until_fight_keeps_utc_reference_for_timestamped_values(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 13, 23, 30))
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: datetime(2026, 3, 13, 10, 0))

    fight_date = input_parsing.parse_fight_date("2026-03-15T00:00:00Z")

    assert fight_date is not None
    assert input_parsing._compute_days_until_fight("2026-03-15T00:00:00Z", fight_date) == 1