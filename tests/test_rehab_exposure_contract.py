from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.contracts.rehab_exposure import ExposureDose, RehabExposureEvent


def _event(**overrides):
    injury_id = overrides.pop("injury_id", uuid4())
    episode_id = overrides.pop("injury_episode_id", uuid4())
    payload = {
        "exposure_id": uuid4(),
        "injury_id": injury_id,
        "injury_episode_id": episode_id,
        "drill_id": "single_leg_calf_raise",
        "body_region": "ankle",
        "side": "left",
        "demand": {
            "target_regions": ["ankle"],
            "target_tissues": None,
            "load": "moderate",
            "impact": "none",
            "velocity": "low",
            "contraction_type": ["concentric", "eccentric"],
            "sport_specificity": "general_rehab",
        },
        "prescribed_dose": {"sets": 3, "reps": 10},
        "dose_completed": {"sets": 3, "reps": 8, "external_load_kg": 10},
        "response": {},
        "occurred_at": datetime.now(UTC),
        "provenance": {"source": "athlete_logged_rehab", "recorded_at": datetime.now(UTC)},
    }
    payload.update(overrides)
    return payload


def test_exposure_requires_injury_and_episode_identity():
    for field in ("injury_id", "injury_episode_id"):
        payload = _event()
        del payload[field]
        with pytest.raises(ValidationError):
            RehabExposureEvent.model_validate(payload)


def test_region_and_laterality_are_preserved_and_attributed_together():
    event = RehabExposureEvent.model_validate(_event())
    injury = {"id": event.injury_id, "episode_id": event.injury_episode_id, "body_region": "ankle", "side": "left"}
    assert event.side == "left"
    assert event.is_attributable_to(injury)
    assert not event.is_attributable_to({**injury, "body_region": "shoulder"})
    assert not event.is_attributable_to({**injury, "side": "right"})
    assert not event.is_attributable_to({**injury, "id": uuid4()})
    assert not event.is_attributable_to({**injury, "episode_id": uuid4()})


def test_bilateral_is_explicit_and_unknown_side_is_not_attributable():
    bilateral = RehabExposureEvent.model_validate(_event(side="bilateral"))
    injury = {"id": bilateral.injury_id, "episode_id": bilateral.injury_episode_id, "body_region": "ankle", "side": "left"}
    assert bilateral.is_attributable_to(injury)
    unknown = RehabExposureEvent.model_validate(_event(side="unknown"))
    injury = {"id": unknown.injury_id, "episode_id": unknown.injury_episode_id, "body_region": "ankle", "side": "left"}
    assert not unknown.is_attributable_to(injury)


def test_missing_response_remains_unknown_and_not_sure_is_not_zero():
    event = RehabExposureEvent.model_validate(_event())
    assert event.response.pain_during is None
    assert event.response.next_day_response == "not_yet_known"
    unsure = RehabExposureEvent.model_validate(_event(response={"pain_during": "not_sure"}))
    assert unsure.response.pain_during == "not_sure"
    assert unsure.response.pain_during != 0


def test_symptom_stop_and_completed_dose_are_observations_not_prescription():
    event = RehabExposureEvent.model_validate(
        _event(response={"stopped_due_to_symptoms": True}, dose_completed={"sets": 1, "stopped_early": True})
    )
    assert event.response.stopped_due_to_symptoms is True
    assert event.dose_completed.sets == 1
    assert event.prescribed_dose.sets == 3


@pytest.mark.parametrize("pain", [-1, 11])
def test_malformed_pain_fails(pain):
    with pytest.raises(ValidationError):
        RehabExposureEvent.model_validate(_event(response={"pain_during": pain}))


@pytest.mark.parametrize("dose", [{}, {"reps": -1}, {"completed_fraction": 1.1}])
def test_malformed_completed_dose_fails(dose):
    with pytest.raises(ValidationError):
        RehabExposureEvent.model_validate(_event(dose_completed=dose))


def test_unquantified_performed_state_is_an_honest_observation():
    dose = ExposureDose(completion_state="performed_amount_unknown")
    assert dose.completed_fraction is None
    assert dose.sets is None


@pytest.mark.parametrize(
    "dose",
    [
        {"completion_state": "performed_amount_unknown", "reps": 10},
        {"completion_state": "partial_amount_unknown", "completed_fraction": 0.5},
        {"completion_state": "quantified"},
    ],
)
def test_completion_state_cannot_contradict_the_observed_amount(dose):
    with pytest.raises(ValidationError):
        ExposureDose.model_validate(dose)


def test_invalid_or_mismatched_demand_region_fails():
    for regions in (["invented_region"], ["shoulder"]):
        payload = _event()
        payload["demand"]["target_regions"] = regions
        with pytest.raises(ValidationError):
            RehabExposureEvent.model_validate(payload)


def test_contract_has_no_generic_session_or_progression_evidence_fields():
    fields = RehabExposureEvent.model_fields
    assert not {"camp_phase", "session_completed", "session_rpe", "pain_after", "updated_at", "tolerated"} & set(fields)


def test_unknown_contract_fields_cannot_bypass_validation():
    payload = _event()
    payload["response"]["tolerated"] = True
    with pytest.raises(ValidationError):
        RehabExposureEvent.model_validate(payload)
