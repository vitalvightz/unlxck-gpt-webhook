from fightcamp.stage2_pipeline import build_stage2_retry
from fightcamp.stage2_validator import validate_stage2_output


def _brief(*, assignments):
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": [{"weekday": "thursday", "d_day": 16}],
                    "session_roles": [
                        {
                            "category": "conditioning",
                            "role_key": "fight_pace_repeatability_day",
                            "scheduled_day_hint": "thursday",
                            "scheduled_countdown_label": "D-16",
                            "selected_exercise_assignments": assignments,
                        }
                    ],
                }
            ]
        }
    }


def test_missing_selected_conditioning_assignment_blocks_and_requests_retry():
    brief = _brief(assignments=[
        {"name": "Plyo Step-Up Intervals", "effective_prescription": "2 x 30 sec work; 90 sec rest; RPE 8"},
        {"name": "Kettlebell Swing Intervals", "effective_prescription": "2 x 30 sec work; 90 sec rest; RPE 8"},
    ])
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-16 (Thursday) — Conditioning\n- Plyo Step-Up Intervals: 2 x 30 sec work; 90 sec rest; RPE 8\n",
    )

    missing = [item for item in report["errors"] if item["code"] == "missing_selected_conditioning_assignment"]
    assert [item["exercise"] for item in missing] == ["Kettlebell Swing Intervals"]

    retry = build_stage2_retry(
        stage1_result={"planning_brief": brief},
        final_plan_text="D-16 (Thursday) — Conditioning\n- Plyo Step-Up Intervals: 2 x 30 sec work; 90 sec rest; RPE 8\n",
        validator_report=report,
    )
    assert retry["needs_retry"] is True


def test_all_selected_conditioning_assignments_render_cleanly():
    brief = _brief(assignments=[
        {"name": "Plyo Step-Up Intervals", "effective_prescription": "2 x 30 sec work; 90 sec rest; RPE 8"},
        {"name": "Kettlebell Swing Intervals", "effective_prescription": "2 x 30 sec work; 90 sec rest; RPE 8"},
    ])
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text=(
            "D-16 (Thursday) — Conditioning\n"
            "- Plyo Step-Up Intervals: 2 x 30 sec work; 90 sec rest; RPE 8\n"
            "- Kettlebell Swing Intervals: 2 x 30 sec work; 90 sec rest; RPE 8\n"
        ),
    )

    assert not any(item["code"] == "missing_selected_conditioning_assignment" for item in report["errors"])


def test_easier_line_is_not_treated_as_an_unselected_exercise():
    brief = {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "category": "strength",
                            "role_key": "strength_touch_day",
                            "effective_strength_envelope": {
                                "scheduled_d_day": 16,
                                "complete_exercise_allow_list": True,
                                "allowed_exercise_names": ["Back Squat"],
                            },
                        }
                    ],
                }
            ]
        }
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text=(
            "D-16 (Thursday) — Strength\n"
            "- Back Squat: 2 x 3 @ RPE 6\n"
            "- Easier: reduce to 1 x 3 @ RPE 5 if bar speed drops.\n"
            "- Stop: stop if pain rises.\n"
        ),
    )

    assert not any(item["code"] == "late_camp_effective_prescription_exceeded" for item in report["errors"])
