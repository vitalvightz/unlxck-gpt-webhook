from fightcamp.stage2_pipeline import build_stage2_package, build_stage2_retry, review_stage2_output



def _stage1_result_fixture() -> dict:
    planning_brief = {
        "schema_version": "planning_brief.v1",
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