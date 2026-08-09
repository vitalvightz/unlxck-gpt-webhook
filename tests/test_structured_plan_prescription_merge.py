"""Focused tests for deterministic general prescription authority."""

from copy import deepcopy

from api.structured_plan_prescription_merge import merge_authoritative_prescription
from api.structured_plan_truth import extract_structured_plan_truth


def _plan(*, session: str = "Strength", day: str = "D-10", duplicate: bool = False):
    block = {
        "display_name": "Trap-bar deadlift",
        "sets": 4,
        "reps": 8,
        "rest": {"value": 60, "unit": "seconds"},
        "load": {"method": "percentage", "value": 70, "unit": "percent", "ref": "1RM"},
        "effort": {"method": "RPE", "value": 8},
        "purpose": "AI wording",
        "progression_rule": "AI progression",
        "regression_options": ["AI easier"],
        "category": "main lift",
        "energy_system": "alactic",
    }
    blocks = [block, deepcopy(block)] if duplicate else [block]
    return {
        "weeks": [
            {
                "days": [
                    {
                        "countdown_label": day,
                        "sessions": [{"title": session, "blocks": blocks}],
                    }
                ]
            }
        ]
    }


def _merge(source: str, **plan_args):
    return merge_authoritative_prescription(
        _plan(**plan_args), extract_structured_plan_truth(source)
    )


def test_scalar_prescription_and_labelled_truth_are_restored_without_losing_metadata():
    result = _merge(
        "D-10 - Strength\n"
        "- Trap-bar deadlift - 3 sets x 6 reps; Rest 90 sec; 85% 1RM; RPE 6.\n"
        "  Purpose: Preserve hip extension power.\n"
        "  Progress: Add one rep next week.\n"
        "  Easier: Use a kettlebell.\n"
        "  Stop: Stop if back pain starts.\n"
    )
    block = result.plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["sets"] == 3
    assert block["reps"] == 6
    assert block["rest"] == {"value": 90, "unit": "seconds"}
    assert block["load"]["value"] == 85
    assert block["effort"]["value"] == 6
    assert block["purpose"] == "Preserve hip extension power."
    assert block["regression_options"] == ["Use a kettlebell."]
    assert (
        block["progression_rule"]
        == "Progress: Add one rep next week.\nStop: Stop if back pain starts."
    )
    assert block["category"] == "main lift"
    assert block["energy_system"] == "alactic"


def test_ranges_are_preserved_only_where_schema_supports_them():
    result = _merge(
        "D-10 - Strength\n"
        "- Trap-bar deadlift - 2-3 sets x 8-10 reps; Rest 90-120 sec; 2-4 kg; RPE 6-7.\n"
    )
    block = result.plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["sets"] == 4
    assert block["reps"] == "8-10"
    assert block["rest"] == {"value": 60, "unit": "seconds"}
    assert block["load"]["value"] == 70
    assert block["effort"]["value"] == "6-7"
    assert {
        (issue.reason, issue.fields, issue.expected) for issue in result.unresolved
    } == {
        ("UNREPRESENTABLE_RANGE", ("sets",), "2-3"),
        ("UNREPRESENTABLE_RANGE", ("rest",), "90-120 sec"),
        ("UNREPRESENTABLE_RANGE", ("load",), "2-4 kg"),
    }


def test_wrong_structure_is_not_repaired_and_ambiguous_block_is_not_patched():
    wrong_day = _merge(
        "D-10 - Strength\n- Trap-bar deadlift - 3 sets x 6 reps\n", day="D-8"
    )
    wrong_session = _merge(
        "D-10 - Strength\n- Trap-bar deadlift - 3 sets x 6 reps\n", session="Recovery"
    )
    ambiguous = _merge(
        "D-10 - Strength\n- Trap-bar deadlift - 3 sets x 6 reps\n", duplicate=True
    )
    assert wrong_day.plan == _plan(day="D-8")
    assert wrong_session.plan == _plan(session="Recovery")
    assert ambiguous.plan == _plan(duplicate=True)
    assert wrong_day.unresolved[0].reason == "wrong_day"
    assert wrong_session.unresolved[0].reason == "wrong_session"
    assert ambiguous.unresolved[0].reason == "block_not_uniquely_resolved"


def test_merge_is_idempotent():
    truth = extract_structured_plan_truth(
        "D-10 - Strength\n- Trap-bar deadlift - 3 sets x 6 reps; RPE 6\n"
    )
    once = merge_authoritative_prescription(_plan(), truth).plan
    twice = merge_authoritative_prescription(once, truth).plan
    assert twice == once


def test_locked_truth_is_left_to_locked_merge():
    truth = extract_structured_plan_truth(
        "D-10 - Strength\n- Trap-bar deadlift - 3 sets x 6 reps\n",
        {
            "roles": [
                {
                    "countdown_label": "D-10",
                    "governance": {
                        "selected_drill_locked": True,
                        "selected_drill_name": "Trap-bar deadlift",
                    },
                }
            ]
        },
    )
    result = merge_authoritative_prescription(_plan(), truth)
    assert result.plan == _plan()
    assert not result.applied
