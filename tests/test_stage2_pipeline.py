from fightcamp.stage2_pipeline import build_stage2_package, build_stage2_retry, review_stage2_output


def _stage1_result_fixture() -> dict:
    planning_brief = {
        "schema_version": "planning_brief.v1",
        "athlete_model": {"sport": "boxing"},
        "restrictions": [
            {
                "restriction": "heavy_overhead_pressing",
                "strength": "avoid",
                "blocked_patterns": ["push press", "overhead press"],
                "mechanical_equivalents": ["thruster", "jerk"],
            }
        ],
        "phase_strategy": {
            "SPP": {
                "must_keep": ["rehab", "alactic", "glycolytic"],
            }
        },
        "candidate_pools": {
            "SPP": {
                "strength_slots": [
                    {
                        "role": "push",
                        "selected": {"name": "Landmine Press"},
                        "alternates": [{"name": "Half-Kneeling Cable Press"}],
                    }
                ],
                "conditioning_slots": [
                    {
                        "role": "alactic",
                        "selected": {"name": "Air Bike Sprint"},
                        "alternates": [{"name": "Short Sprint"}],
                    },
                    {
                        "role": "glycolytic",
                        "selected": {"name": "Hard Shuttle"},
                        "alternates": [{"name": "Bag Sprint Round"}],
                    },
                ],
                "rehab_slots": [
                    {
                        "role": "rehab_shoulder_strain",
                        "selected": {"name": "Band External Rotation"},
                        "alternates": [{"name": "Scap Push-Up"}],
                    }
                ],
            }
        },
    }
    return {
        "planning_brief": planning_brief,
        "stage2_payload": {"schema_version": "stage2_payload.v1"},
        "stage2_handoff_text": "handoff text",
        "plan_text": "draft plan",
        "coach_notes": "notes",
    }


def test_build_stage2_package_returns_ready_bundle():
    package = build_stage2_package(stage1_result=_stage1_result_fixture())

    assert package["status"] == "READY"
    assert package["handoff_text"] == "handoff text"
    assert package["draft_plan_text"] == "draft plan"
    assert package["coach_notes"] == "notes"
    assert "1 phase(s)" in package["summary"]
    assert "4 candidate slot(s)" in package["summary"]


def test_review_stage2_output_returns_fail_for_restriction_violation():
    review = review_stage2_output(
        planning_brief=_stage1_result_fixture()["planning_brief"],
        final_plan_text="""
        SPP
        - Push Press - 4x3
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    assert review["status"] == "FAIL"
    assert review["needs_retry"] is True
    assert "needs revision" in review["summary"]
    assert any("Push Press" in line for line in review["summary_lines"])


def test_review_stage2_output_returns_warn_for_missing_phase_critical_elements():
    review = review_stage2_output(
        planning_brief=_stage1_result_fixture()["planning_brief"],
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    assert review["status"] == "WARN"
    assert review["needs_retry"] is True
    assert any("Restore rehab" in line for line in review["summary_lines"])
    assert any("Restore alactic" in line for line in review["summary_lines"])


def test_review_stage2_output_returns_pass_with_non_blocking_review_flags():
    review = review_stage2_output(
        planning_brief=_stage1_result_fixture()["planning_brief"],
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        - Double-leg sprint entry - 6 x 6 sec
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False
    assert review["validator_report"]["blocking_warnings"] == []
    review_flag_codes = [warning["code"] for warning in review["validator_report"]["review_flags"]]
    assert "sport_language_leak" in review_flag_codes


def test_review_stage2_output_promotes_hedged_adjustment_to_blocking_warning():
    review = review_stage2_output(
        planning_brief=_stage1_result_fixture()["planning_brief"],
        final_plan_text="""
        SPP
        - Consider reducing intensity and prioritizing recovery.
        - Landmine Press - 4x5
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    assert review["status"] == "WARN"
    assert review["needs_retry"] is True
    blocking_codes = [warning["code"] for warning in review["validator_report"]["blocking_warnings"]]
    assert "hedged_adjustment_without_decision" in blocking_codes


def test_review_stage2_output_promotes_empty_safety_in_high_risk_context():
    planning_brief = _stage1_result_fixture()["planning_brief"]
    planning_brief["athlete_model"]["fatigue"] = "high"
    planning_brief["athlete_model"]["readiness_flags"] = ["high_fatigue", "fight_week"]
    planning_brief["athlete_model"]["injuries"] = ["left hamstring strain"]

    review = review_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        SPP
        - Listen to your body with lower-body loading.
        - Landmine Press - 4x5
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    assert review["status"] == "WARN"
    assert review["needs_retry"] is True
    blocking_codes = [warning["code"] for warning in review["validator_report"]["blocking_warnings"]]
    assert "empty_safety_language" in blocking_codes


def test_build_stage2_retry_returns_repair_prompt_when_needed():
    retry = build_stage2_retry(
        stage1_result=_stage1_result_fixture(),
        final_plan_text="""
        SPP
        - Push Press - 4x3
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    assert retry["status"] == "FAIL"
    assert retry["needs_retry"] is True
    assert retry["repair_prompt"] is not None
    assert "REVISION PRIORITIES" in retry["repair_prompt"]
    assert "PLANNING BRIEF" in retry["repair_prompt"]


def test_build_stage2_retry_skips_prompt_when_plan_passes():
    retry = build_stage2_retry(
        stage1_result=_stage1_result_fixture(),
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    assert retry["status"] == "PASS"
    assert retry["needs_retry"] is False
    assert retry["repair_prompt"] is None


def test_build_stage2_retry_skips_prompt_when_only_review_flags_exist():
    retry = build_stage2_retry(
        stage1_result=_stage1_result_fixture(),
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        - Double-leg sprint entry - 6 x 6 sec
        """,
    )

    assert retry["status"] == "PASS"
    assert retry["needs_retry"] is False
    assert retry["repair_prompt"] is None


def test_build_stage2_retry_weekly_session_overage_uses_active_session_language():
    stage1_result = _stage1_result_fixture()
    retry = build_stage2_retry(
        stage1_result=stage1_result,
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
        validator_report={
            "is_valid": True,
            "errors": [],
            "warnings": [
                {
                    "code": "weekly_session_overage",
                    "phase": "SPP",
                    "week_index": 5,
                    "expected_session_count": 4,
                    "actual_session_count": 5,
                }
            ],
            "missing_required_elements": [],
            "restricted_hits": [],
        },
    )

    assert "planned active sessions for the week" in retry["repair_prompt"]
    assert "requested sessions per week" not in retry["repair_prompt"]
