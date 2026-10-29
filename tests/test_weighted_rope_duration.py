"""Regression for the weighted-vest rope row showing only its rest."""

import pytest

from api.structured_plan_deterministic_fallback import _lift_dose_fields, _session
from api.structured_plan_faithfulness import _source_day_section_lines


def test_live_weighted_rope_prescription_keeps_rounds_work_and_rest():
    text = """D-20 (Monday) — Strength
- Jump Rope (Weighted Vest) — 3 rounds of 60s work at a steady, repeatable rhythm; rest 60s.
How: Light rhythm with vest, steady timing and footwork.
Cue: Soft knees, quick feet.
Stop: Stop if breathing becomes very heavy.
"""
    role = {
        "role_key": "strength", "category": "strength", "scheduled_d_day": 20,
        "selected_exercise_assignments": [{
            "name": "Jump Rope (Weighted Vest)",
            "effective_prescription": "3 rounds x 60s; rest 60s.",
        }],
    }
    session = _session(role, 20, _source_day_section_lines(text)[20])
    (block,) = session["blocks"]
    assert block["rounds"] == 3
    assert block["work"] == {"value": 60, "unit": "seconds"}
    assert block["rest"] == {"value": 60, "unit": "seconds"}
    assert "reps" not in block
    assert "steady timing and footwork" in block["execution_instructions"]
    assert block["coaching_cues"] == ["Cue: Soft knees, quick feet."]
    assert block["stop_rules"] == ["Stop if breathing becomes very heavy."]


@pytest.mark.parametrize("dose, rounds, value, unit", [
    ("3 rounds of 60s work; rest 60s", 3, 60, "seconds"),
    ("4 rounds of 2 minutes work; rest 1 min", 4, 2, "minutes"),
    ("1 round of 30 seconds work; rest 90s", 1, 30, "seconds"),
    ("3 rounds x 60s; rest 60s", 3, 60, "seconds"),
])
def test_exact_timed_round_spellings(dose, rounds, value, unit):
    fields, _ = _lift_dose_fields(dose)
    assert fields["rounds"] == rounds
    assert fields["work"] == {"value": value, "unit": unit}


@pytest.mark.parametrize("dose", [
    "3 rounds of footwork; rest 60s",
    "3 rounds of 45-60s work; rest 60s",
    "3 rounds of 10 reps; rest 60s",
])
def test_no_work_duration_is_invented(dose):
    fields, _ = _lift_dose_fields(dose)
    assert "work" not in fields
    assert "duration" not in fields
    assert fields["rest"] == {"value": 60, "unit": "seconds"}
