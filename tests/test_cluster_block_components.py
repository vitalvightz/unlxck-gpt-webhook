"""Cluster (contrast-pair) blocks keep their structure through the card.

Doses are the exact planner prescriptions from an open plan whose strength day
rendered with no rounds, a pair dose only as a coaching-cue sentence, a hidden
85% 1RM load and a dropped qualitative rest.
"""
from __future__ import annotations

import pytest

from api.structured_plan_deterministic_fallback import _lift_dose_fields, _source_block
from api.structured_plan_faithfulness import project_source_adjustments
from api.structured_plan_models import SessionBlock, safe_parse_structured_plan
from tests.test_open_plan_programming_fidelity import _project, _reference_row

CONTRAST = ("3 rounds: heavy movement 2 reps @ 85% 1RM → explosive movement 2 reps "
            "at max intent; rest 4 min per round.")
CARRY = "3 holds x 10s @ 7/10 effort; full rest between holds."
PERCENT_85 = {"method": "percentage", "value": 85, "unit": "percent", "ref": "1RM", "display": "85% 1RM"}


def test_planner_contrast_dose_lifts_rounds_rest_and_one_row_per_movement():
    fields, _ = _lift_dose_fields(CONTRAST, "Back Squat → Box Jump")
    assert fields["rounds"] == 3
    assert fields["rest"] == {"value": 4, "unit": "minutes"}
    assert fields["components"] == [
        {"name": "Back Squat", "reps": 2, "load": PERCENT_85},
        {"name": "Box Jump", "reps": 2, "effort": {"method": "intent", "value": "max"}},
    ]
    assert "sets" not in fields and "reps" not in fields  # Never one flattened set x rep.


def test_plan_text_contrast_grammar_assigns_load_to_its_own_movement():
    fields, _ = _lift_dose_fields(
        "3 rounds; RDL 2 reps @ 85% 1RM, then Broad Jump 2 reps; rest 4 min between rounds.",
        "Heavy RDL → Broad Jump")
    assert fields["components"] == [
        {"name": "Heavy RDL", "reps": 2, "load": PERCENT_85},
        {"name": "Broad Jump", "reps": 2},
    ]


@pytest.mark.parametrize(("name", "dose"), [
    ("Back Squat", CONTRAST),  # Not a named pair: nothing to split.
    ("Back Squat → Box Jump", "3 rounds: heavy movement 2 reps then jumps; rest 4 min."),  # One rep count.
    ("Back Squat → Box Jump", "heavy movement 2 reps @ 85% 1RM → jump 2 reps."),  # No round count.
])
def test_ambiguous_pairs_lift_no_components(name, dose):
    fields, _ = _lift_dose_fields(dose, name)
    assert "components" not in fields


def test_out_of_ten_effort_and_full_rest_are_kept_without_inventing_a_number():
    fields, _ = _lift_dose_fields(CARRY, "Single-Leg Farmer Carry Hold")
    assert fields["sets"] == 3
    assert fields["duration"] == {"value": 10, "unit": "seconds"}
    assert fields["effort"] == {"method": "RPE", "value": 7, "scale": "1-10"}
    assert fields["rest_note"] == "Full rest between holds"
    assert "rest" not in fields
    # A numeric rest wins; the note is only for rest written as words.
    fields, _ = _lift_dose_fields("4x2 reps at max speed; full rest 120s.")
    assert fields["rest"] == {"value": 120, "unit": "seconds"} and "rest_note" not in fields


def test_lifted_load_carries_its_display_string():
    assert _lift_dose_fields("3x5 @ 80% 1RM")[0]["load"]["display"] == "80% 1RM"
    assert _lift_dose_fields("3x5 @ 100 kg")[0]["load"]["display"] == "100 kg"


def test_new_fields_are_omitted_when_absent_so_existing_cards_keep_their_shape():
    dumped = SessionBlock(block_type="strength", display_name="Back Squat").model_dump()
    assert "components" not in dumped and "rest_note" not in dumped
    pair = SessionBlock(block_type="strength", display_name="Back Squat → Box Jump",
                        **_lift_dose_fields(CONTRAST, "Back Squat → Box Jump")[0]).model_dump()
    assert [c["name"] for c in pair["components"]] == ["Back Squat", "Box Jump"]


def test_open_plan_card_carries_cluster_rows_and_drops_the_sentence_cue():
    row = _reference_row()
    for week in row["planning_brief"]["open_plan_spec"]["weekly_session_plan"]["weeks"]:
        strength = next(s for s in week["sessions"] if s["category"] == "strength")
        strength["exercises"][0] = {"name": "Heavy RDL → Broad Jump", "prescription": CONTRAST}
        strength["exercises"][-1] = {"name": "Single-Leg Farmer Carry Hold", "prescription": CARRY}
    effective, _ = _project(row)
    assert safe_parse_structured_plan(effective).ok
    blocks = [b for week in effective["weeks"] for day in week["days"] for s in day["sessions"]
              for b in s["blocks"]]
    pairs = [b for b in blocks if b["display_name"] == "Heavy RDL → Broad Jump"]
    carries = [b for b in blocks if b["display_name"] == "Single-Leg Farmer Carry Hold"]
    assert pairs and carries
    for block in pairs:
        assert block["rounds"] == 3
        assert [c["name"] for c in block["components"]] == ["Heavy RDL", "Broad Jump"]
        assert CONTRAST not in (block.get("coaching_cues") or [])
        assert CONTRAST.rstrip(".") not in str(block.get("execution_instructions") or "")
    for block in carries:
        assert block["rest_note"] == "Full rest between holds"
        assert block["effort"]["value"] == 7


def test_dated_card_gets_cluster_rows_projected_from_its_exact_source_line():
    name = "Heavy RDL → Broad Jump"
    source = "\n".join([
        "D-30 (Monday) — Strength",
        "Why: build heavy strength while keeping explosive power.",
        f"- {name}: 3 rounds; RDL 2 reps @ 85% 1RM, then Broad Jump 2 reps; rest 4 min between rounds.",
        "  Cue: hinge from hips, drive hips forward.",
    ])
    assert _source_block(source.splitlines(), name)["components"]
    plan = {"weeks": [{"days": [{"countdown_label": "D-30", "sessions": [{"title": "Strength", "blocks": [
        {"block_type": "strength", "display_name": name, "rest": {"value": 4, "unit": "minutes"}},
    ]}]}]}]}
    block = project_source_adjustments(plan, source)["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["rounds"] == 3
    assert [(c["name"], c["reps"]) for c in block["components"]] == [("Heavy RDL", 2), ("Broad Jump", 2)]
