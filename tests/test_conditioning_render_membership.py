from fightcamp.stage2_pipeline import build_stage2_retry
from fightcamp.stage2_repair import (
    conditioning_render_repair_integrity_findings,
    reconcile_selected_conditioning_assignments,
)
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


def test_reconcile_restores_all_three_d16_assignments_with_authorised_doses():
    assignments = [
        {"name": "Plyo Step-Up Intervals", "effective_prescription": "2 x 30 sec work; 90 sec rest; RPE 8"},
        {"name": "Kettlebell Swing Intervals", "effective_prescription": "3 x 20 sec work; 100 sec rest; RPE 7"},
        {"name": "Assault Bike Repeat", "effective_prescription": "4 x 15 sec work; 75 sec rest; RPE 8"},
    ]
    brief = _brief(assignments=assignments)
    original = "D-16 (Thursday) — Conditioning\n- Plyo Step-Up Intervals: 2 x 30 sec work; 90 sec rest; RPE 8\n"
    report = validate_stage2_output(planning_brief=brief, final_plan_text=original)

    repaired = reconcile_selected_conditioning_assignments(
        planning_brief=brief,
        failed_plan_text=original,
        validator_report=report,
    )

    assert [item["exercise"] for item in repaired["applied"]] == [
        "Kettlebell Swing Intervals",
        "Assault Bike Repeat",
    ]
    for assignment in assignments:
        assert repaired["text"].count(assignment["name"]) == 1
        assert assignment["effective_prescription"] in repaired["text"]
    revalidated = validate_stage2_output(planning_brief=brief, final_plan_text=repaired["text"])
    assert not any(item["code"] == "missing_selected_conditioning_assignment" for item in revalidated["errors"])


def test_reconcile_restores_second_aerobic_assignment_on_d15():
    brief = _brief(assignments=[
        {"name": "Zone 2 Run", "effective_prescription": "20 min at RPE 4"},
        {"name": "Easy Bike", "effective_prescription": "15 min at RPE 3"},
    ])
    role = brief["weekly_role_map"]["weeks"][0]["session_roles"][0]
    role["scheduled_countdown_label"] = "D-15"
    brief["weekly_role_map"]["weeks"][0]["calendar_days"][0]["d_day"] = 15
    original = "D-15 (Thursday) — Aerobic conditioning\n- Zone 2 Run: 20 min at RPE 4\n"
    report = validate_stage2_output(planning_brief=brief, final_plan_text=original)

    repaired = reconcile_selected_conditioning_assignments(
        planning_brief=brief, failed_plan_text=original, validator_report=report
    )

    assert "- Easy Bike: 15 min at RPE 3" in repaired["text"]
    assert "D-16" not in repaired["text"]


def test_missing_conditioning_and_goal_failure_builds_render_retry_and_keeps_planner_flag():
    brief = _brief(assignments=[
        {"name": "Zone 2 Run", "effective_prescription": "20 min at RPE 4"},
        {"name": "Easy Bike", "effective_prescription": "15 min at RPE 3"},
    ])
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n",
    )
    report["errors"].append({"code": "goal_preservation_failed", "goal": "conditioning"})

    retry = build_stage2_retry(
        stage1_result={"planning_brief": brief},
        final_plan_text="D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n",
        validator_report=report,
    )

    assert retry["needs_retry"] is True
    assert retry["repair_prompt"]
    assert retry["requires_planner_regeneration"] is True


def test_goal_failure_without_render_omission_does_not_request_render_retry():
    brief = _brief(assignments=[
        {"name": "Zone 2 Run", "effective_prescription": "20 min at RPE 4"},
    ])
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n",
    )
    report["errors"].append({"code": "goal_preservation_failed", "goal": "conditioning"})

    retry = build_stage2_retry(
        stage1_result={"planning_brief": brief},
        final_plan_text="D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n",
        validator_report=report,
    )

    assert retry["needs_retry"] is False
    assert retry["repair_prompt"] is None
    assert retry["requires_planner_regeneration"] is True


def test_reconcile_leaves_restricted_selected_assignment_out_without_substitution():
    brief = _brief(assignments=[
        {"name": "Zone 2 Run", "effective_prescription": "20 min at RPE 4"},
        {"name": "Kettlebell Swing Intervals", "effective_prescription": "3 x 20 sec work; 100 sec rest"},
    ])
    brief["restrictions"] = [{"restriction": "kettlebell_swing", "blocked_patterns": ["kettlebell swing"]}]
    original = "D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n"
    report = validate_stage2_output(planning_brief=brief, final_plan_text=original)

    repaired = reconcile_selected_conditioning_assignments(
        planning_brief=brief, failed_plan_text=original, validator_report=report
    )

    assert repaired["text"] == original
    assert repaired["applied"] == []
    assert repaired["unresolved"][0]["reason"] == "selected_assignment_restricted"
    assert "substitut" not in repaired["text"].lower()


def test_reconcile_refuses_ambiguous_rendered_day_and_clean_plan_is_unchanged():
    brief = _brief(assignments=[
        {"name": "Zone 2 Run", "effective_prescription": "20 min at RPE 4"},
        {"name": "Easy Bike", "effective_prescription": "15 min at RPE 3"},
    ])
    ambiguous = (
        "D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n"
        "D-16 (Thursday) — Conditioning notes\n- Keep the pace smooth\n"
    )
    report = validate_stage2_output(planning_brief=brief, final_plan_text=ambiguous)
    refused = reconcile_selected_conditioning_assignments(
        planning_brief=brief, failed_plan_text=ambiguous, validator_report=report
    )
    assert refused["text"] == ambiguous
    assert refused["applied"] == []
    assert refused["unresolved"][0]["reason"] == "ambiguous_or_missing_authoritative_day"

    clean = "D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n- Easy Bike: 15 min at RPE 3\n"
    clean_report = validate_stage2_output(planning_brief=brief, final_plan_text=clean)
    untouched = reconcile_selected_conditioning_assignments(
        planning_brief=brief, failed_plan_text=clean, validator_report=clean_report
    )
    assert untouched == {"text": clean, "applied": [], "unresolved": []}


def test_increased_conditioning_dose_is_detected_and_restored_to_effective_source():
    brief = _brief(assignments=[
        {"name": "Assault Bike Repeat", "effective_prescription": "4 x 15 sec work; 75 sec rest; RPE 8"},
    ])
    increased = (
        "D-16 (Thursday) — Conditioning\n"
        "- Assault Bike Repeat: 8 x 30 sec work; 30 sec rest; RPE 10\n"
    )
    report = validate_stage2_output(planning_brief=brief, final_plan_text=increased)
    mismatches = [
        item
        for item in report["errors"]
        if item["code"] == "selected_conditioning_effective_prescription_mismatch"
    ]
    assert len(mismatches) == 1

    repaired = reconcile_selected_conditioning_assignments(
        planning_brief=brief, failed_plan_text=increased, validator_report=report
    )

    assert repaired["text"].count("Assault Bike Repeat") == 1
    assert "8 x 30 sec" not in repaired["text"]
    assert "4 x 15 sec work; 75 sec rest; RPE 8" in repaired["text"]
    revalidated = validate_stage2_output(planning_brief=brief, final_plan_text=repaired["text"])
    assert not any(
        item["code"] == "selected_conditioning_effective_prescription_mismatch"
        for item in revalidated["errors"]
    )


def test_repair_integrity_rejects_unselected_duplicate_and_extra_session():
    brief = _brief(assignments=[
        {"name": "Zone 2 Run", "effective_prescription": "20 min at RPE 4"},
        {"name": "Easy Bike", "effective_prescription": "15 min at RPE 3"},
    ])
    before = "D-16 (Thursday) — Conditioning\n- Zone 2 Run: 20 min at RPE 4\n"
    after = (
        "D-16 (Thursday) — Conditioning\n"
        "- Zone 2 Run: 20 min at RPE 4\n"
        "- Easy Bike: 15 min at RPE 3\n"
        "- Easy Bike: 15 min at RPE 3\n"
        "- Unselected Sprint: 6 x 20 sec\n"
        "D-14 (Saturday) — Extra conditioning\n"
        "- Unselected Sprint: 6 x 20 sec\n"
    )

    findings = conditioning_render_repair_integrity_findings(
        planning_brief=brief, before_text=before, after_text=after
    )
    codes = {item["code"] for item in findings}

    assert "conditioning_render_repair_calendar_changed" in codes
    assert "unselected_conditioning_assignment_introduced" in codes
    assert "duplicate_selected_conditioning_assignment" in codes


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
