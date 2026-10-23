"""Dose spellings from the affected open card, without athlete information."""
import pytest

from api.structured_plan_deterministic_fallback import _exact_working_dose, _lift_dose_fields


@pytest.mark.parametrize("prescription, expected", [
    ("1-2 controlled sets x 3-5 slow reps (each side if one-sided); stop before fatigue",
     {"sets": 1, "reps": 3}),
    ("2 x 180s work / 60s rest",
     {"rounds": 2, "work": {"value": 180, "unit": "seconds"}, "rest": {"value": 60, "unit": "seconds"}}),
    ("2 rounds x 180 sec work; rest 60 sec",
     {"rounds": 2, "work": {"value": 180, "unit": "seconds"}, "rest": {"value": 60, "unit": "seconds"}}),
    ("4x2 reps; RPE ~7", {"sets": 4, "reps": 2, "effort": {"method": "RPE", "value": 7, "scale": "1-10"}}),
    ("3x8 @ 65-75% 1RM; rest 90s",
     {"sets": 3, "reps": 8, "load": {"method": "percentage", "value": 65, "unit": "percent", "ref": "1RM", "display": "65% 1RM"},
      "rest": {"value": 90, "unit": "seconds"}}),
])
def test_open_card_lifts_working_dose_without_losing_quantities(prescription, expected):
    fields, _ = _lift_dose_fields(_exact_working_dose(prescription))
    assert fields == expected


def test_an_undosed_movement_does_not_get_an_invented_load():
    fields, _ = _lift_dose_fields("4x2 reps at max speed; full rest 120s.")
    assert "load" not in fields
    assert fields["rest"] == {"value": 120, "unit": "seconds"}
