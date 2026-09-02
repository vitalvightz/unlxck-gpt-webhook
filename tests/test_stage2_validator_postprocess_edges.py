from fightcamp.stage2_validator_postprocess import postprocess_stage2_validator_report


def _brief(role_key: str, *, phase: str = "TAPER", category: str = "strength") -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 3,
                    "phase": phase,
                    "session_roles": [
                        {"role_key": role_key, "category": category},
                    ],
                }
            ]
        }
    }


def test_secondary_strength_touch_does_not_keep_primary_strength_requirement():
    warning = {
        "code": "missing_required_element",
        "phase": "TAPER",
        "requirement": "primary_strength",
    }
    report = postprocess_stage2_validator_report(
        planning_brief=_brief("strength_touch_day"),
        final_plan_text="TAPER — Week 3 (D-7 to D-0)\nD-5 (Monday): Neural speed touch.",
        validator_report={"warnings": [warning], "missing_required_elements": [warning]},
    )
    assert report["warnings"] == []
    assert report["missing_required_elements"] == []


def test_real_primary_strength_role_keeps_primary_strength_requirement_warning():
    warning = {
        "code": "missing_required_element",
        "phase": "GPP",
        "requirement": "primary_strength",
    }
    report = postprocess_stage2_validator_report(
        planning_brief=_brief("primary_strength_day", phase="GPP"),
        final_plan_text="GPP — Week 3 (D-23 to D-16)\nD-16 (Thursday): Aerobic support.",
        validator_report={"warnings": [warning]},
    )
    assert report["warnings"] == [warning]


def test_non_phase_section_closes_active_week_count_context():
    text = """TAPER — Week 3 (D-7 to D-0)
D-2 (Thursday): Fight-week freshness.
- Mobility/reset circuit.

Nutrition
D-1 (Friday): Carb timing note.
- This is not a training session.
"""
    warning = {
        "code": "weekly_session_overage",
        "phase": "TAPER",
        "week_index": 3,
        "expected_session_count": 1,
        "actual_session_count": 2,
    }
    report = postprocess_stage2_validator_report(
        planning_brief=_brief("fight_week_freshness_day", category="recovery"),
        final_plan_text=text,
        validator_report={"warnings": [warning]},
    )
    assert report["warnings"] == []


def test_stale_overage_becomes_incomplete_when_rendered_week_is_under_count():
    text = """SPP — Week 2 (D-15 to D-8)
D-12 (Monday): Neural speed touch.
- Speed Box Squat: 2 x 3.
"""
    warning = {
        "code": "weekly_session_overage",
        "phase": "SPP",
        "week_index": 2,
        "expected_session_count": 2,
        "actual_session_count": 3,
    }
    report = postprocess_stage2_validator_report(
        planning_brief={
            "weekly_role_map": {
                "weeks": [
                    {
                        "week_index": 2,
                        "phase": "SPP",
                        "session_roles": [
                            {"role_key": "strength_touch_day", "category": "strength"},
                            {"role_key": "technical_touch_day", "category": "technical"},
                        ],
                    }
                ]
            }
        },
        final_plan_text=text,
        validator_report={"warnings": [warning]},
    )
    assert len(report["warnings"]) == 1
    finding = report["warnings"][0]
    assert finding["code"] == "late_camp_session_incomplete"
    assert finding["actual_session_count"] == 1
    assert finding["expected_session_count"] == 2
