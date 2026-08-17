from api.generation_health import (
    build_non_health_generation_payload,
    non_health_planner_payload,
)
from tests.support import _build_request


def test_non_health_planner_payload_omits_health_fields_instead_of_defaulting_them():
    request = _build_request(
        {
            "fatigue_level": "",
            "injuries": "",
            "guided_injury": None,
            "guided_injuries": None,
            "athlete": {"weight_kg": None, "target_weight_kg": None},
        }
    )

    planner_payload = non_health_planner_payload(request.to_payload())
    labels = {field["label"] for field in planner_payload["data"]["fields"]}

    assert "Fatigue Level" not in labels
    assert "Weight (kg)" not in labels
    assert "Target Weight (kg)" not in labels
    assert "Any injuries or areas you need to work around?" not in labels
    assert "guided_injury" not in planner_payload
    assert "guided_injuries" not in planner_payload


def test_non_health_generation_payload_does_not_copy_unrelated_stored_context():
    payload = _build_request(
        {
            "fatigue_level": "",
            "injuries": "",
            "guided_injury": None,
            "guided_injuries": None,
            "athlete": {"weight_kg": None, "target_weight_kg": None},
        }
    ).model_dump(mode="json")

    cleaned = build_non_health_generation_payload(payload)

    assert cleaned["_generation_health_mode"] == "withheld"
    assert "fatigue_level" not in cleaned
    assert "injuries" not in cleaned
    assert "weight_kg" not in cleaned["athlete"]
