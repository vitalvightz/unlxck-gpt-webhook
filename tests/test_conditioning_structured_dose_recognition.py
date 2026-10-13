"""The structured conditioning dose must survive into the composed assignment.

Live payloads showed `alactic_speed_day` roles carrying legitimate speed work -
Backstep Counter Reset 8 x 5 sec / 60 sec - whose persisted
`selected_exercise_assignments` had only `effective_rounds`,
`base_prescription` and `effective_prescription`. The candidate pool those were
resolved from is compacted in persistence, so by the time goal-preservation
recomputed evidence there was no numeric dose anywhere and `speed_quality`
never fired: a real Speed exposure read as missing.

The fix carries the canonical numeric fields from `_conditioning_effective_dose`
into the assignment, and lets the evidence layer fall back to them. Recognition
must never depend on parsing the rendered prescription text back out.
"""

from __future__ import annotations

import pytest

from fightcamp.goal_preservation import _member_slot, _other_stimuli
from fightcamp.session_composition import _conditioning_effective_dose


# ---------------------------------------------------------------------------
# The dose authority itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,work_sec,rounds",
    [("Backstep Counter Reset", 5, 8), ("Escape-Recatch Burst", 6, 8)],
)
def test_the_canonical_dose_exposes_numeric_fields(name, work_sec, rounds):
    option = {
        "name": name,
        "selection_metadata": {
            "work_sec": work_sec,
            "rest_sec": 60,
            "rounds": rounds,
            "system": "ATP-PCr",
        },
    }
    dose = _conditioning_effective_dose(option)
    assert dose["work_sec"] == work_sec
    assert dose["rest_sec"] == 60
    assert dose["rounds"] == rounds


# ---------------------------------------------------------------------------
# Repro B: the compacted-pool shape that lost Speed
# ---------------------------------------------------------------------------


def _assignment(*, structured: bool):
    """The persisted shape. `structured` mirrors before/after the fix."""
    assignment = {
        "slot_id": "spp-alactic-1",
        "name": "Backstep Counter Reset",
        "base_prescription": "8 x 5 sec / 60 sec rest",
        "effective_prescription": "8 x 5 sec / 60 sec rest",
        "effective_rounds": 8,
    }
    if structured:
        assignment.update({"work_sec": 5.0, "rest_sec": 60.0, "rounds": 8.0})
    return assignment


def _role(*, structured: bool):
    return {
        "category": "conditioning",
        "role_key": "alactic_speed_day",
        "preferred_system": "alactic",
        "scheduled_day_hint": "Monday",
        "selected_exercise_assignments": [_assignment(structured=structured)],
    }


def _compacted_pool():
    """Persistence compacts the pool: identity survives, numeric dose does not."""
    return {
        "conditioning_slots": [
            {
                "slot_id": "spp-alactic-1",
                "session_index": 1,
                "selected": {
                    "name": "Backstep Counter Reset",
                    "prescription": "8 x 5 sec / 60 sec rest",
                    "system": "ATP-PCr",
                    "selection_metadata": {},
                },
            }
        ]
    }


def test_without_the_structured_dose_speed_work_is_invisible():
    """The regression this fix closes."""
    stimuli = _other_stimuli(_role(structured=False), {"SPP": _compacted_pool()}, "SPP", {})
    assert stimuli == []


def test_the_propagated_dose_restores_speed_recognition():
    stimuli = _other_stimuli(_role(structured=True), {"SPP": _compacted_pool()}, "SPP", {})
    assert len(stimuli) == 1
    assert "speed_quality" in stimuli[0]["intents"]


def test_recognition_does_not_parse_the_prescription_text():
    """Strip the readable text entirely: recognition must still hold."""
    role = _role(structured=True)
    for key in ("base_prescription", "effective_prescription"):
        role["selected_exercise_assignments"][0].pop(key)
    pool = _compacted_pool()
    pool["conditioning_slots"][0]["selected"].pop("prescription")
    stimuli = _other_stimuli(role, {"SPP": pool}, "SPP", {})
    assert "speed_quality" in stimuli[0]["intents"]


def test_pool_metadata_still_wins_when_present():
    """The fallback is a fallback: a live pool keeps its own authority."""
    role = _role(structured=False)
    pool = _compacted_pool()
    pool["conditioning_slots"][0]["selected"]["selection_metadata"] = {
        "work_sec": 5,
        "rest_sec": 60,
        "rounds": 8,
    }
    assert "speed_quality" in _other_stimuli(role, {"SPP": pool}, "SPP", {})[0]["intents"]


# ---------------------------------------------------------------------------
# The member lookup: exact final identity, never a compatible candidate
# ---------------------------------------------------------------------------


def test_member_is_matched_by_slot_id_and_name():
    member = _role(structured=True)["selected_exercise_assignments"][0]
    slot = _member_slot(member, {"SPP": _compacted_pool()}, "SPP", "conditioning_slots")
    assert slot["selected"]["name"] == "Backstep Counter Reset"


def test_a_same_named_candidate_in_another_slot_is_not_the_member():
    """A name alone once let a pool candidate borrow a member's dose."""
    member = _role(structured=True)["selected_exercise_assignments"][0]
    pool = {"conditioning_slots": [{"slot_id": "other-id", "selected": {"name": "Backstep Counter Reset"}}]}
    assert _member_slot(member, {"SPP": pool}, "SPP", "conditioning_slots") is None


def test_an_unassigned_candidate_never_becomes_evidence():
    """Swimming on the day is not the bike drill left in the pool."""
    role = {
        "category": "conditioning", "role_key": "aerobic_base_day", "preferred_system": "aerobic",
        "scheduled_day_hint": "Monday",
        "selected_exercise_assignments": [{"slot_id": "swim", "name": "Swimming (Freestyle Laps)",
                                           "slot_group": "conditioning_slots", "source_phase": "GPP"}],
    }
    pool = {"conditioning_slots": [
        {"slot_id": "bike", "role": "aerobic",
         "selected": {"name": "Easy Assault Bike", "system": "aerobic", "selection_metadata": {"total_minutes": 30}}},
        {"slot_id": "swim", "role": "aerobic",
         "selected": {"name": "Swimming (Freestyle Laps)", "system": "aerobic", "selection_metadata": {"total_minutes": 25}}},
    ]}
    names = [s["name"] for s in _other_stimuli(role, {"GPP": pool}, "GPP", {})]
    assert names == ["Swimming (Freestyle Laps)"]
