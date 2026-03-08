from fightcamp.stage2_repair import build_stage2_repair_prompt


def _planning_brief_fixture() -> dict:
    return {
        "schema_version": "planning_brief.v1",
        "global_priorities": {
            "preserve": ["Keep rehab continuity."],
            "push": ["Preserve alactic sharpness."],
            "avoid": ["Avoid violating restrictions."],
        },
        "phase_strategy": {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "must_keep": ["rehab", "alactic", "glycolytic"],
            }
        },
        "candidate_pools": {
            "SPP": {
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
        "restrictions": [
            {
                "restriction": "heavy_overhead_pressing",
                "strength": "avoid",
                "blocked_patterns": ["push press", "overhead press"],
                "mechanical_equivalents": ["thruster", "jerk"],
            }
        ],
    }



def test_build_stage2_repair_prompt_includes_revision_inputs():
    validator_report = {
        "is_valid": False,
        "errors": [
            {
                "code": "restriction_violation",
                "message": "Restriction heavy_overhead_pressing matched line: Push Press - 4x3",
                "restriction": "heavy_overhead_pressing",
                "line": "Push Press - 4x3",
            }
        ],
        "warnings": [],
        "missing_required_elements": [],
        "restricted_hits": [
            {
                "restriction": "heavy_overhead_pressing",
                "line": "Push Press - 4x3",
            }
        ],
    }
    prompt = build_stage2_repair_prompt(
        planning_brief=_planning_brief_fixture(),
        failed_plan_text="SPP\n- Push Press - 4x3",
        validator_report=validator_report,
    )

    assert "You are revising a Stage 2 final plan after validation." in prompt
    assert "REVISION PRIORITIES" in prompt
    assert "VALIDATOR REPORT" in prompt
    assert "PLANNING BRIEF" in prompt
    assert "PREVIOUS FINAL PLAN" in prompt
    assert "Push Press - 4x3" in prompt



def test_build_stage2_repair_prompt_surfaces_missing_required_elements():
    validator_report = {
        "is_valid": True,
        "errors": [],
        "warnings": [
            {
                "code": "missing_required_element",
                "phase": "SPP",
                "requirement": "alactic",
                "candidate_names": ["Air Bike Sprint", "Short Sprint"],
            }
        ],
        "missing_required_elements": [
            {
                "phase": "SPP",
                "requirement": "alactic",
                "candidate_names": ["Air Bike Sprint", "Short Sprint"],
            }
        ],
        "restricted_hits": [],
    }
    prompt = build_stage2_repair_prompt(
        planning_brief=_planning_brief_fixture(),
        failed_plan_text="SPP\n- Hard Shuttle - 6x20s / 60s",
        validator_report=validator_report,
    )

    assert "restore_phase_critical_element" in prompt
    assert "Air Bike Sprint" in prompt
    assert "Short Sprint" in prompt
    assert "alactic" in prompt



def test_build_stage2_repair_prompt_requests_athlete_facing_output_only():
    validator_report = {
        "is_valid": False,
        "errors": [],
        "warnings": [],
        "missing_required_elements": [],
        "restricted_hits": [],
    }
    prompt = build_stage2_repair_prompt(
        planning_brief=_planning_brief_fixture(),
        failed_plan_text="SPP\n- Landmine Press - 4x5",
        validator_report=validator_report,
    )

    assert "Return only the revised athlete-facing final plan." in prompt
    assert "Do not mention the validator" in prompt