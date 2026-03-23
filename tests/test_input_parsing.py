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


def test_rounds_format_common_variants_are_normalized_without_warning():
    data = _payload(
        [
            {"label": "Fighting Style (Technical)", "value": "Boxing"},
            {"label": "Rounds x Minutes", "value": "3 - 3"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.rounds_format == "3x3"
    assert parsed.rounds_format_raw == "3 - 3"
    assert parsed.rounds_format_warning == ""


def test_rounds_format_unusual_for_sport_gets_non_blocking_warning():
    data = _payload(
        [
            {"label": "Fighting Style (Technical)", "value": "Boxing"},
            {"label": "Rounds x Minutes", "value": "7-4"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.rounds_format == "7x4"
    assert parsed.rounds_format_warning
    assert "unusual for boxing" in parsed.rounds_format_warning.lower()


def test_rounds_format_unparseable_value_gets_non_blocking_warning():
    data = _payload(
        [
            {"label": "Fighting Style (Technical)", "value": "Boxing"},
            {"label": "Rounds x Minutes", "value": "banana"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.rounds_format == "banana"
    assert parsed.rounds_format_warning
    assert "could not confidently interpret" in parsed.rounds_format_warning.lower()


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


def test_equipment_multiselect_value_maps_from_option_ids():
    data = _payload(
        [
            {
                "label": "Equipment Access",
                "value": [2, 3],
                "options": [
                    {"id": "1", "text": "Barbell"},
                    {"id": "2", "text": "Bands"},
                    {"id": "3", "text": "Heavy Bag"},
                ],
            }
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.equipment_access == "Bands, Heavy Bag"


def test_sparring_day_fields_round_trip_from_payload():
    data = _payload(
        [
            {"label": "Training Availability", "value": "Monday, Tuesday, Thursday, Saturday"},
            {"label": "Hard Sparring Days", "value": "Tuesday, Saturday"},
            {"label": "Technical Skill Days", "value": "Monday"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.training_days == ["Monday", "Tuesday", "Thursday", "Saturday"]
    assert parsed.hard_sparring_days == ["Tuesday", "Saturday"]
    assert parsed.technical_skill_days == ["Monday"]


def test_contradictory_frequency_and_availability_stay_explicit_for_downstream_review():
    data = _payload(
        [
            {"label": "Weekly Training Frequency", "value": "6"},
            {"label": "Training Availability", "value": "Mon, Wed"},
            {"label": "When is your next fight?", "value": "2099-03-01"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.training_frequency == 6
    assert parsed.training_days == ["Mon", "Wed"]
    assert parsed.frequency_raw == "6"


def test_messy_injury_input_keeps_real_issue_and_discards_empty_markers():
    data = _payload(
        [
            {"label": "Any injuries or areas you need to work around?", "value": "none / right heel soreness + toe pain"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.injuries == "right heel soreness, toe pain"
    assert parsed.parsed_injuries


def test_guided_injury_summary_is_preserved_and_parsed():
    summary = (
        "Hip / groin - moderate, worsening, can train with modifications. "
        "Avoid: sprinting, deep hip flexion. "
        "Notes: pain spikes when driving knee up and after sparring."
    )
    data = _payload(
        [
            {"label": "Any injuries or areas you need to work around?", "value": summary},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.injuries == summary
    assert len(parsed.parsed_injuries) == 1
    assert parsed.parsed_injuries[0]["original_phrase"] == "Hip / groin"
    assert parsed.parsed_injuries[0]["severity"] == "moderate"
    assert len(parsed.restrictions) == 2
    assert any(restriction["restriction"] == "high_impact_lower" for restriction in parsed.restrictions)
    assert any(restriction.get("region") for restriction in parsed.restrictions)


def test_guided_injury_notes_only_still_create_restriction_signal():
    summary = (
        "Shoulder - severe, worsening, cannot do key movements properly. "
        "Notes: pain with any overhead motion and after sparring."
    )
    data = _payload(
        [
            {"label": "Any injuries or areas you need to work around?", "value": summary},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.injuries == summary
    assert len(parsed.parsed_injuries) == 1
    assert len(parsed.restrictions) == 1
    assert parsed.restrictions[0]["restriction"] == "generic_constraint"
    assert parsed.restrictions[0]["region"] == "shoulder"
    assert parsed.restrictions[0]["strength"] == "avoid"


def test_incomplete_input_can_still_be_salvaged_when_training_days_exist():
    data = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Training Availability", "value": "Monday, Thursday, Saturday"},
            {"label": "Any injuries or areas you need to work around?", "value": "n/a"},
        ]
    )

    parsed = PlanInput.from_payload(data)

    assert parsed.training_frequency == 3
    assert parsed.injuries == ""


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


def test_plan_input_uses_athlete_timezone_for_date_only_rollover(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: datetime(2026, 3, 14, 0, 30))

    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Full name", "value": "West Coast Athlete"},
                {"label": "When is your next fight?", "value": "2026-03-14"},
                {"label": "Athlete Time Zone", "value": "UTC-08:00"},
                {"label": "Athlete Locale", "value": "en-US"},
            ]
        )
    )

    assert parsed.athlete_timezone == "UTC-08:00"
    assert parsed.athlete_locale == "en-US"
    assert parsed.days_until_fight == 1
    assert parsed.weeks_out == 1


def test_invalid_athlete_timezone_falls_back_to_local_calendar(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: datetime(2026, 3, 13, 19, 30))

    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Full name", "value": "Fallback Athlete"},
                {"label": "When is your next fight?", "value": "2026-03-14"},
                {"label": "Timezone", "value": "Mars/Olympus"},
            ]
        )
    )

    assert parsed.athlete_timezone == "Mars/Olympus"
    assert parsed.days_until_fight == 1
    assert parsed.weeks_out == 1


def test_compute_days_until_fight_keeps_utc_reference_for_timestamped_values(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 13, 23, 30))
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: datetime(2026, 3, 13, 10, 0))

    fight_date = input_parsing.parse_fight_date("2026-03-15T00:00:00Z")

    assert fight_date is not None
    assert input_parsing._compute_days_until_fight("2026-03-15T00:00:00Z", fight_date) == 1
