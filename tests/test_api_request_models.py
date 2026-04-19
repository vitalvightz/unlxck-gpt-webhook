from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from api.models import NutritionSharedCampContext, PlanRequest
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context
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
        support_work_days=[],
        key_goals=[],
        weak_areas=[],
    ).to_payload()

    fields = {field["label"]: field["value"] for field in payload["data"]["fields"]}

    assert fields["Equipment Access"] == []
    assert fields["Training Availability"] == []
    assert fields["Hard Sparring Days"] == []
    assert fields["Support Work Days"] == []
    assert fields["What are your key performance goals?"] == []
    assert fields["Where do you feel weakest right now?"] == []


def test_plan_request_rejects_more_than_four_hard_sparring_days():
    with pytest.raises(ValidationError, match="hard sparring days cap is 4"):
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
            },
            fight_date="2026-04-18",
            hard_sparring_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        )


def test_plan_request_rejects_hard_sparring_day_outside_training_availability():
    with pytest.raises(ValidationError, match="hard_sparring_days must be included in training_availability"):
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
            },
            fight_date="2026-04-18",
            training_availability=["Monday", "Wednesday"],
            hard_sparring_days=["Tuesday"],
        )


def test_plan_request_rejects_support_work_day_outside_training_availability():
    with pytest.raises(ValidationError, match="support_work_days must be included in training_availability"):
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
            },
            fight_date="2026-04-18",
            training_availability=["Monday", "Wednesday"],
            support_work_days=["Friday"],
        )


def test_plan_request_rejects_overlap_between_hard_sparring_and_support_work_days():
    with pytest.raises(ValidationError, match="hard_sparring_days and support_work_days must not overlap"):
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
            },
            fight_date="2026-04-18",
            training_availability=["Tuesday", "Thursday"],
            hard_sparring_days=["Tuesday"],
            support_work_days=["Tuesday"],
        )


def test_plan_request_migrates_legacy_technical_skill_days_to_support_work_days():
    request = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
        },
        fight_date="2026-04-18",
        training_availability=["Tuesday", "Friday"],
        technical_skill_days=["Tuesday", "Friday"],
    )

    assert request.support_work_days == ["Tuesday", "Friday"]


def test_plan_request_payload_round_trip_normalizes_real_app_goal_and_weakness_labels():
    request = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": ["Counter Striker"],
        },
        fight_date="2026-08-30",
        training_availability=["Monday", "Tuesday", "Thursday", "Saturday"],
        hard_sparring_days=["Tuesday", "Saturday"],
        support_work_days=["Monday"],
        key_goals=["Power & Explosiveness", "Speed / Reaction"],
        weak_areas=["Coordination / Proprioception"],
    )

    parsed = PlanInput.from_payload(request.to_payload())
    context = build_runtime_context(
        plan_input=parsed,
        random_seed=1,
        logger=logging.getLogger(__name__),
    )

    assert context.training_context.key_goals == ["explosive", "reactive"]
    assert context.training_context.weaknesses == ["coordination"]


def test_nutrition_shared_context_migrates_legacy_technical_skill_days_to_support_work_days():
    shared = NutritionSharedCampContext.model_validate(
        {
            "training_availability": ["Tuesday", "Friday"],
            "technical_skill_days": ["Tuesday", "Friday"],
        }
    )

    assert shared.support_work_days == ["Tuesday", "Friday"]


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


def test_plan_request_payload_round_trip_into_plan_input():
    request = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": ["pressure_fighter"],
        },
        fight_date="2026-08-30",
        training_availability=["Monday", "Tuesday", "Thursday", "Saturday"],
        hard_sparring_days=["Tuesday", "Saturday"],
        support_work_days=["Monday"],
        equipment_access=["barbell", "heavy_bag"],
        key_goals=["power", "conditioning"],
        weak_areas=["gas_tank", "defense"],
        guided_injury={
            "area": "left rib",
            "severity": "high",
            "trend": "worsening",
            "avoid": "contact and hard sparring",
            "notes": "pain breathing deeply after body shot",
        },
    )

    parsed = PlanInput.from_payload(request.to_payload())

    assert parsed.next_fight_date == "2026-08-30"
    assert parsed.training_days == ["Monday", "Tuesday", "Thursday", "Saturday"]
    assert parsed.hard_sparring_days == ["Tuesday", "Saturday"]
    assert parsed.support_work_days == ["Monday"]
    assert parsed.equipment_access == "barbell, heavy_bag"
    assert parsed.key_goals == "power, conditioning"
    assert parsed.weak_areas == "gas_tank, defense"
    assert parsed.guided_injury is not None
    assert parsed.guided_injury.area == "left rib"


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
