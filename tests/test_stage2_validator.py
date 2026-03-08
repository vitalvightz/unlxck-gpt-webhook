from fightcamp.stage2_validator import validate_stage2_output



def _planning_brief_fixture() -> dict:
    return {
        "restrictions": [
            {
                "restriction": "heavy_overhead_pressing",
                "strength": "avoid",
                "region": "shoulder",
                "source_phrase": "avoid heavy overhead pressing",
                "blocked_patterns": ["push press", "overhead press"],
                "mechanical_equivalents": ["thruster", "jerk"],
            }
        ],
        "phase_strategy": {
            "GPP": {
                "must_keep": ["primary_strength"],
            },
            "SPP": {
                "must_keep": ["rehab", "alactic", "glycolytic"],
            },
        },
        "candidate_pools": {
            "GPP": {
                "strength_slots": [
                    {
                        "role": "push",
                        "selected": {"name": "Landmine Press"},
                        "alternates": [{"name": "Half-Kneeling Cable Press"}],
                    }
                ],
                "conditioning_slots": [],
                "rehab_slots": [],
            },
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
            },
        },
    }



def test_validate_stage2_output_flags_restriction_violations():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Push Press - 4x3
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    assert report["is_valid"] is False
    assert report["restricted_hits"]
    assert report["restricted_hits"][0]["restriction"] == "heavy_overhead_pressing"
    assert any(error["code"] == "restriction_violation" for error in report["errors"])



def test_validate_stage2_output_ignores_restriction_warning_lines():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Avoid heavy overhead pressing this week.
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    assert report["restricted_hits"] == []
    assert report["errors"] == []



def test_validate_stage2_output_warns_when_phase_critical_elements_go_missing():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        GPP
        ### Strength & Power
        - Goblet Squat - 4x5
        SPP
        - Landmine Press - 4x5
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    assert report["is_valid"] is True
    missing_requirements = {(item["phase"], item["requirement"]) for item in report["missing_required_elements"]}
    assert ("SPP", "rehab") in missing_requirements
    assert ("SPP", "alactic") in missing_requirements
    assert ("GPP", "primary_strength") not in missing_requirements
    assert any(warning["code"] == "missing_required_element" for warning in report["warnings"])



def test_validate_stage2_output_is_phase_aware_for_missing_elements():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        GPP
        - Air Bike Sprint - 6 x 6 sec
        SPP
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    missing_requirements = {(item["phase"], item["requirement"]) for item in report["missing_required_elements"]}
    assert ("SPP", "alactic") in missing_requirements



def test_validate_stage2_output_does_not_count_negated_structure_as_present():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        GPP
        ### Strength & Power
        - Goblet Squat - 4x5
        SPP
        - No rehab needed this week.
        - Do not add alactic work.
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    missing_requirements = {(item["phase"], item["requirement"]) for item in report["missing_required_elements"]}
    assert ("SPP", "rehab") in missing_requirements
    assert ("SPP", "alactic") in missing_requirements



def test_validate_stage2_output_warns_when_multiphase_sections_are_missing():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ### Strength & Power
        - Goblet Squat - 4x5
        ### Glycolytic
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    phase_warnings = {(warning["code"], warning["phase"]) for warning in report["warnings"]}
    assert ("phase_section_missing", "GPP") in phase_warnings
    assert ("phase_section_missing", "SPP") in phase_warnings



def test_validate_stage2_output_passes_clean_plan_with_structural_strength_section():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        GPP
        ### Strength & Power
        - Goblet Squat - 4x5
        SPP
        ### Alactic
        - Sprint Variation - 6 x 6 sec
        ### Glycolytic
        - Hard Shuttle - 6x20s / 60s
        ### Rehab
        - Band External Rotation - 2x15
        """,
    )

    assert report["is_valid"] is True
    assert report["restricted_hits"] == []
    assert report["missing_required_elements"] == []
