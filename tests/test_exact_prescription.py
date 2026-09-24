import pytest

from fightcamp.exact_prescription import (
    ambiguous_working_dose,
    label_strength_sets_reps,
    missing_working_units,
    resolve_working_prescription,
)
from fightcamp.prescription_resolver import resolve_strength_slot_prescription
from fightcamp.stage2_validator import validate_stage2_output


def test_bank_ranges_resolve_to_one_working_dose():
    source = "2–5 sets x 4–6 reps @ 70–80% 1RM, RPE 6–7; work 20–40 sec; rest 60–90 sec"
    assert resolve_working_prescription(source) == (
        "2 sets x 4 reps @ 70% 1RM, RPE 6; work 20 sec; rest 90 sec"
    )
    assert resolve_working_prescription("2–3 rounds x 30–45 sec; rest 45–75 sec") == (
        "2 rounds x 30 sec; rest 75 sec"
    )
    assert resolve_working_prescription("Rehab hold 20–30 sec; rest 30–60 sec") == (
        "Rehab hold 20 sec; rest 60 sec"
    )
    assert resolve_working_prescription("RIR 1–3") == "RIR 3"
    assert resolve_working_prescription("sets: 2–5; reps: 4–6; rest: 60–90 sec") == (
        "sets: 2; reps: 4; rest: 90 sec"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2 x 20 m @ RPE 7", "2 x 20 m @ RPE 7"),
        ("3 x 30s hold", "3 x 30s hold"),
        ("3–5x3–5 @ 85–90% 1RM", "3 sets x 3 reps @ 85% 1RM"),
        ("3x8-12 @ 60-75% 1RM", "3 sets x 8 reps @ 60% 1RM"),
        ("2–3x6–10 @ RPE 6–7", "2 sets x 6 reps @ RPE 6"),
    ],
)
def test_strength_shorthand_resolves_without_changing_distance_or_time_units(source, expected):
    exact = label_strength_sets_reps(resolve_working_prescription(source))
    assert exact == expected
    resolved = resolve_strength_slot_prescription(
        role={}, slot={"selected": {"prescription": source}}, athlete_state={}
    )
    assert resolved["effective_prescription"] == expected


def test_ambiguous_and_missing_units_are_detected():
    assert ambiguous_working_dose("2–5 sets of rows")
    assert ambiguous_working_dose("sets: 2–5")
    assert ambiguous_working_dose("8x8x30")
    assert missing_working_units("3 sets x 8 reps; rest 60")
    assert missing_working_units("3 sets x 8 reps; load 80")
    assert not ambiguous_working_dose("3 sets x 8 reps; rest 60 sec; RPE 7")
    assert not missing_working_units("3 sets x 8 reps; rest 60 sec")


def test_stage2_blocks_ranged_or_unlabelled_exercise_lines_but_not_safety_guidance():
    base = "D-20 (Monday) — Strength\n- Trap Bar Deadlift — {dose}\n"
    for dose in ("8x8x30", "2–5 sets x 8 reps", "3 sets x 8 reps; rest 60"):
        report = validate_stage2_output(planning_brief={}, final_plan_text=base.format(dose=dose))
        assert any(item["code"] == "ambiguous_exercise_prescription" for item in report["errors"]), dose

    good = base.format(dose="3 sets x 8 reps @ RPE 7; rest 90 sec")
    good += "Easier: reduce to 2–3 sets if pain rises.\n"
    good += "- Reduce to 2–3 sets if symptoms worsen.\n"
    report = validate_stage2_output(planning_brief={}, final_plan_text=good)
    assert not any(item["code"] == "ambiguous_exercise_prescription" for item in report["errors"])

    open_report = validate_stage2_output(
        planning_brief={},
        final_plan_text="## Monday — Strength\n- Trap Bar Deadlift: 2–5 sets x 6 reps\n",
    )
    assert any(item["code"] == "ambiguous_exercise_prescription" for item in open_report["errors"])
