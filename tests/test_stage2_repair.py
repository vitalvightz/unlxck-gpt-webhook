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
    assert "make one clear coaching call" in prompt
    assert "Replace generic motivation, scripted empathy, and empty safety language" in prompt
    assert "Do not open corrective lines with generic openers such as 'focus on', 'ensure', 'make sure', or 'it's important to'" in prompt
    assert "immutable hard_sparring_day slots" in prompt
    assert "If fatigue is high or fight-week pressure is active, reduce optionality" in prompt
    assert "If injury management is active, lead with constraints, substitutions, or stop rules" in prompt


def test_build_stage2_repair_prompt_surfaces_internal_scaffolding_cleanup():
    validator_report = {
        "is_valid": False,
        "errors": [
            {
                "code": "internal_section_leak",
                "section": "Selection Rationale",
                "line": "Selection Rationale",
            },
            {
                "code": "html_markup_present",
                "line": "Hard Shuttle<br>6x20s / 60s",
            },
        ],
        "warnings": [],
        "missing_required_elements": [],
        "restricted_hits": [],
    }
    prompt = build_stage2_repair_prompt(
        planning_brief=_planning_brief_fixture(),
        failed_plan_text="## Selection Rationale\n- Keep Hard Shuttle<br>6x20s / 60s",
        validator_report=validator_report,
    )

    assert "remove_internal_scaffolding" in prompt
    assert "remove_formatting_artifact" in prompt
    assert "Remove raw HTML" in prompt


def test_build_stage2_repair_prompt_surfaces_quality_repairs():
    validator_report = {
        "is_valid": True,
        "errors": [],
        "warnings": [
            {
                "code": "weak_anchor_session",
                "phase": "SPP",
                "session_index": 1,
                "anchor_candidates": ["Landmine Press"],
            },
            {
                "code": "conditional_conditioning_choice",
                "line": "Bike sprint or bag sprint depending on access",
            },
            {
                "code": "template_like_session_render",
                "phase": "SPP",
                "session_index": 1,
            },
            {
                "code": "too_many_fallbacks",
                "phase": "SPP",
                "session_index": 1,
            },
            {
                "code": "taper_option_overload",
                "phase": "TAPER",
                "session_index": 1,
            },
            {
                "code": "equipment_incongruent_selection",
                "phase": "SPP",
                "line": "Bag Sprint Round - 6 x 15 sec",
                "required_equipment": ["heavy_bag"],
            },
            {
                "code": "unresolved_access_fallback",
                "phase": "SPP",
                "session_index": 1,
                "line": "Fallback: Short Sprint - 6 x 6 sec",
            },
            {
                "code": "missing_week_session_role",
                "phase": "SPP",
                "week_index": 5,
                "expected_roles": ["hard_sparring_day", "recovery_reset_day", "neural_plus_strength_day"],
                "expected_role_days": [
                    {"role_key": "hard_sparring_day", "scheduled_day_hint": "Tuesday"},
                    {"role_key": "recovery_reset_day", "scheduled_day_hint": "Wednesday"},
                ],
            },
            {
                "code": "late_camp_session_incomplete",
                "phase": "TAPER",
                "week_index": 6,
                "expected_roles": ["alactic_sharpness_day", "fight_week_freshness_day"],
                "expected_role_days": [
                    {"role_key": "fight_week_freshness_day", "scheduled_day_hint": "Friday"},
                ],
            },
            {
                "code": "weekly_session_overage",
                "phase": "SPP",
                "week_index": 5,
                "expected_session_count": 5,
                "actual_session_count": 6,
            },
            {
                "code": "weekly_rhythm_broken",
                "phase": "SPP",
                "week_index": 5,
            },
            {
                "code": "missing_weight_cut_acknowledgement",
            },
            {
                "code": "high_pressure_weight_cut_underaddressed",
                "summary_lines": [],
                "support_lines": [],
            },
            {
                "code": "option_overload",
                "phase": "SPP",
                "session_index": 1,
                "risk_context": ["high_fatigue"],
            },
        ],
        "missing_required_elements": [],
        "restricted_hits": [],
    }
    prompt = build_stage2_repair_prompt(
        planning_brief=_planning_brief_fixture(),
        failed_plan_text="SPP\n- Dead Bug - 2x8\n- Bike sprint or bag sprint depending on access",
        validator_report=validator_report,
    )

    assert "quality_repairs" in prompt
    assert "restore_anchor_session_quality" in prompt
    assert "resolve_conditioning_to_primary_plus_fallback" in prompt
    assert "rewrite_session_as_final_prescription" in prompt
    assert "collapse_extra_fallbacks_to_final_choice" in prompt
    assert "simplify_taper_session" in prompt
    assert "replace_with_equipment_valid_same_role_option" in prompt
    assert "remove_unneeded_fallback_branch_or_make_contingency_explicit" in prompt
    assert "collapse_options_to_safe_equivalent_choices_or_one_final_call" in prompt
    assert '"scheduled_day_hint": "Tuesday"' in prompt


def test_build_stage2_repair_prompt_surfaces_style_repairs():
    validator_report = {
        "is_valid": True,
        "errors": [],
        "warnings": [
            {
                "code": "generic_motivation_cliche",
                "line": "You've got this.",
            },
            {
                "code": "generic_instruction_opener",
                "line": "Focus on recovery today.",
            },
            {
                "code": "hedged_adjustment_without_decision",
                "line": "Consider reducing intensity and prioritizing recovery.",
            },
            {
                "code": "empty_safety_language",
                "line": "If you have pain, consult a clinician.",
            },
        ],
        "missing_required_elements": [],
        "restricted_hits": [],
    }
    prompt = build_stage2_repair_prompt(
        planning_brief=_planning_brief_fixture(),
        failed_plan_text="SPP\n- You've got this.",
        validator_report=validator_report,
    )

    assert "replace_low_trust_filler_with_concrete_coaching" in prompt
    assert "rewrite_adjustment_as_clear_call_with_short_why" in prompt
    assert "replace_empty_safety_line_with_operational_guardrails" in prompt
