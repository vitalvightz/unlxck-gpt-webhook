import re
from datetime import datetime
import logging

import pytest

from fightcamp import input_parsing
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context


def _payload(fields: list[dict]) -> dict:
    return {"data": {"fields": fields}}


def test_invalid_training_frequency_raises_value_error():
    data = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Weekly Training Frequency", "value": "abc"},
            {"label": "Training Availability", "value": "Mon, Wed"},
        ]
    )
    with pytest.raises(ValueError, match="invalid Weekly Training Frequency"):
        PlanInput.from_payload(data)


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


def test_same_day_fight_date_remains_fight_week_active(monkeypatch):
    today = "2026-03-14"
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))
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


def test_guided_injury_payload_treats_area_as_source_of_truth():
    payload = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Fighting Style (Technical)", "value": "Boxing"},
            {"label": "Any injuries or areas you need to work around?", "value": "hip flexor (moderate, improving). Avoid: deep hip flexion. Notes: pain when driving knee up past pelvis"},
        ]
    )
    payload["guided_injury"] = {
        "area": "hip flexor",
        "severity": "moderate",
        "trend": "improving",
        "avoid": "deep hip flexion",
        "notes": "pain when driving knee up past pelvis",
    }

    parsed = PlanInput.from_payload(payload)

    assert parsed.guided_injury is not None
    assert len(parsed.parsed_injuries) == 1
    assert parsed.parsed_injuries[0]["canonical_location"] == "hip"
    assert parsed.parsed_injuries[0]["display_location"] == "hip flexor"
    assert parsed.parsed_injuries[0]["severity"] == "moderate"
    assert len(parsed.restrictions) == 1
    assert parsed.restrictions[0]["region"] == "hip"


def test_guided_injury_runtime_context_does_not_leak_note_body_parts():
    payload = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Fighting Style (Technical)", "value": "Boxing"},
            {"label": "Any injuries or areas you need to work around?", "value": "hip flexor (moderate, improving). Avoid: deep hip flexion. Notes: pain when driving knee up past pelvis"},
        ]
    )
    payload["guided_injury"] = {
        "area": "hip flexor",
        "severity": "moderate",
        "trend": "improving",
        "avoid": "deep hip flexion",
        "notes": "pain when driving knee up past pelvis",
    }

    parsed = PlanInput.from_payload(payload)
    context = build_runtime_context(
        plan_input=parsed,
        random_seed=None,
        logger=logging.getLogger(__name__),
    )

    assert context.injuries_only_text == "hip flexor"
    assert context.training_context.injuries == ["hip flexor"]
    assert all("knee" not in injury for injury in context.training_context.injuries)


@pytest.mark.parametrize(
    ("guided_severity", "expected_severity"),
    [("low", "mild"), ("high", "severe")],
)
def test_guided_injury_payload_converts_frontend_to_backend_severity_vocab(guided_severity, expected_severity):
    payload = _payload(
        [
            {"label": "Full name", "value": "Test Athlete"},
            {"label": "Fighting Style (Technical)", "value": "Boxing"},
            {"label": "Any injuries or areas you need to work around?", "value": "hip flexor"},
        ]
    )
    payload["guided_injury"] = {
        "area": "hip flexor",
        "severity": guided_severity,
    }

    parsed = PlanInput.from_payload(payload)

    assert parsed.parsed_injuries[0]["severity"] == expected_severity


def test_missing_frequency_is_intentionally_inferred_and_marked_system_inferred():
    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Training Availability", "value": "Mon, Thu, Sat"},
            ]
        )
    )
    assert parsed.training_frequency == 3
    assert parsed.parsing_metadata["training_frequency"]["source"] == "system_inferred"


def test_user_supplied_frequency_is_marked_user_supplied():
    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Weekly Training Frequency", "value": "4"},
                {"label": "Training Availability", "value": "Mon, Thu, Sat"},
            ]
        )
    )
    assert parsed.training_frequency == 4
    assert parsed.parsing_metadata["training_frequency"]["source"] == "user_supplied"


def test_malformed_fight_date_raises_value_error():
    with pytest.raises(ValueError, match="invalid fight date format"):
        PlanInput.from_payload(
            _payload([{"label": "When is your next fight?", "value": "03-14-2026"}])
        )


def test_date_only_fight_date_with_missing_timezone_uses_platform_default_timezone(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))

    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Full name", "value": "West Coast Athlete"},
                {"label": "When is your next fight?", "value": "2026-03-14"},
            ]
        )
    )

    assert parsed.days_until_fight == 0
    assert parsed.weeks_out == 1
    assert parsed.parsing_metadata["athlete_timezone"]["source"] == "defaulted_missing"


def test_plan_input_uses_athlete_timezone_for_date_only_rollover(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))

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
    assert parsed.parsing_metadata["athlete_timezone"]["source"] == "user_supplied"


def test_invalid_athlete_timezone_falls_back_to_platform_default(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 0, 30))

    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "Full name", "value": "Fallback Athlete"},
                {"label": "When is your next fight?", "value": "2026-03-14"},
                {"label": "Timezone", "value": "Mars/Olympus"},
            ]
        )
    )

    assert parsed.athlete_timezone == "UTC"
    assert parsed.days_until_fight == 0
    assert parsed.weeks_out == 1
    assert parsed.parsing_metadata["athlete_timezone"]["source"] == "defaulted_missing"


def test_timestamped_and_date_only_countdown_use_consistent_date_model(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 13, 12, 0))

    date_only = PlanInput.from_payload(
        _payload(
            [
                {"label": "When is your next fight?", "value": "2026-03-15"},
                {"label": "Athlete Time Zone", "value": "UTC"},
            ]
        )
    )
    timestamped = PlanInput.from_payload(
        _payload(
            [
                {"label": "When is your next fight?", "value": "2026-03-15T00:00:00Z"},
                {"label": "Athlete Time Zone", "value": "UTC"},
            ]
        )
    )

    assert date_only.days_until_fight == 2
    assert timestamped.days_until_fight == 2


def test_countdown_depends_only_on_utc_now(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 13, 23, 30))

    parsed = PlanInput.from_payload(
        _payload([{"label": "When is your next fight?", "value": "2026-03-14"}])
    )

    assert parsed.days_until_fight == 1


def test_countdown_stable_across_timezone_edge_cases(monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 3, 14, 7, 30))

    parsed = PlanInput.from_payload(
        _payload(
            [
                {"label": "When is your next fight?", "value": "2026-03-14"},
                {"label": "Athlete Time Zone", "value": "UTC-08:00"},
            ]
        )
    )

    assert parsed.days_until_fight == 1
