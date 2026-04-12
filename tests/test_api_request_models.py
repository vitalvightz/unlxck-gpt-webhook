from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.models import PlanRequest
from support import _build_request


def test_plan_request_to_payload_uses_existing_parser_labels():
    payload = _build_request().to_payload()
    labels = {field["label"] for field in payload["data"]["fields"]}

    assert "Full name" in labels
    assert "When is your next fight?" in labels
    assert "Training Availability" in labels
    assert "Athlete Time Zone" in labels
    assert "Sessions per Week" in labels


def test_plan_request_to_payload_keeps_list_backed_fields_as_lists_when_empty():
    payload = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": [],
        },
        fight_date="2026-04-18",
        equipment_access=[],
        training_availability=[],
        hard_sparring_days=[],
        technical_skill_days=[],
        key_goals=[],
        weak_areas=[],
    ).to_payload()

    fields = {field["label"]: field["value"] for field in payload["data"]["fields"]}

    assert fields["Equipment Access"] == []
    assert fields["Training Availability"] == []
    assert fields["Hard Sparring Days"] == []
    assert fields["Technical Skill Days"] == []
    assert fields["What are your key performance goals?"] == []
    assert fields["Where do you feel weakest right now?"] == []


def test_plan_request_to_payload_includes_guided_injury_when_present():
    payload = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
        },
        fight_date="2026-04-18",
        injuries="hip flexor (moderate, improving). Avoid: deep hip flexion.",
        guided_injury={
            "area": "hip flexor",
            "severity": "moderate",
            "trend": "improving",
            "avoid": "deep hip flexion",
            "notes": "pain when driving knee up past pelvis",
        },
    ).to_payload()

    assert payload["guided_injury"]["area"] == "hip flexor"
    assert payload["guided_injury"]["avoid"] == "deep hip flexion"


def test_plan_request_to_payload_includes_guided_injuries_and_mirrors_first_card():
    payload = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
        },
        fight_date="2026-04-18",
        injuries="hip flexor (moderate, improving). Avoid: deep hip flexion. Right heel. Notes: roadwork flare-up.",
        guided_injuries=[
            {
                "area": "hip flexor",
                "severity": "moderate",
                "trend": "improving",
                "avoid": "deep hip flexion",
            },
            {
                "area": "right heel",
                "notes": "roadwork flare-up",
            },
        ],
    ).to_payload()

    assert payload["guided_injury"]["area"] == "hip flexor"
    assert payload["guided_injuries"][0]["area"] == "hip flexor"
    assert payload["guided_injuries"][1]["area"] == "right heel"


@pytest.mark.parametrize(
    ("guided_severity", "expected_severity"),
    [("low", "low"), ("mild", "low"), ("moderate", "moderate"), ("severe", "high"), ("high", "high")],
)
def test_plan_request_guided_injury_severity_accepts_and_normalizes_aliases(guided_severity, expected_severity):
    payload = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
        },
        fight_date="2026-04-18",
        guided_injury={
            "area": "hip flexor",
            "severity": guided_severity,
        },
    ).to_payload()

    assert payload["guided_injury"]["severity"] == expected_severity


def test_plan_request_guided_injury_severity_rejects_unknown_values():
    with pytest.raises(ValidationError, match="guided injury severity must be one of low, moderate, or high"):
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
            },
            fight_date="2026-04-18",
            guided_injury={
                "area": "hip flexor",
                "severity": "critical",
            },
        )


def test_plan_request_coerces_fractional_height_values_for_saved_retries():
    req = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "height_cm": 182.8,
        },
        fight_date="2026-04-18",
    )
    req_from_string = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "height_cm": "182.2",
        },
        fight_date="2026-04-18",
    )

    assert req.athlete.height_cm == 183
    assert req_from_string.athlete.height_cm == 182


def test_plan_request_rejects_non_numeric_height_string():
    with pytest.raises(ValidationError, match="height_cm"):
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
                "height_cm": "six feet",
            },
            fight_date="2026-04-18",
        )


def test_record_format_validation_rejects_invalid_values():
    try:
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
                "record": "five and one",
            },
            fight_date="2026-04-18",
        )
    except Exception as exc:
        assert "x-x or x-x-x" in str(exc)
    else:
        raise AssertionError("invalid record format should be rejected")


def test_record_format_validation_accepts_valid_formats():
    for record in ("5-1", "12-2-1", "0-0", "10-0-3"):
        req = PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
                "record": record,
            },
            fight_date="2026-04-18",
        )
        assert req.athlete.record == record


def test_record_format_validation_accepts_empty_record():
    req = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "record": "",
        },
        fight_date="2026-04-18",
    )
    assert req.athlete.record == ""


def test_record_format_validation_rejects_partial_format():
    for bad in ("5-", "-1", "5", "5-1-2-3"):
        try:
            PlanRequest(
                athlete={
                    "full_name": "Ari Mensah",
                    "technical_style": ["boxing"],
                    "record": bad,
                },
                fight_date="2026-04-18",
            )
        except Exception as exc:
            assert "x-x or x-x-x" in str(exc)
        else:
            raise AssertionError(f"record '{bad}' should be rejected")
