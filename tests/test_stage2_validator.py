from fightcamp.stage2_validator import validate_stage2_output



def _planning_brief_fixture() -> dict:
    return {
        "athlete_model": {"sport": "boxing", "equipment": ["landmine", "bike", "bands"]},
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
                        "session_index": 1,
                        "selected": {"name": "Landmine Press", "anchor_capable": True, "support_only": False},
                        "alternates": [{"name": "Half-Kneeling Cable Press", "anchor_capable": True, "support_only": False}],
                    }
                ],
                "conditioning_slots": [],
                "rehab_slots": [],
            },
            "SPP": {
                "strength_slots": [
                    {
                        "role": "push",
                        "session_index": 1,
                        "selected": {"name": "Landmine Press", "anchor_capable": True, "support_only": False},
                        "alternates": [{"name": "Half-Kneeling Cable Press", "anchor_capable": True, "support_only": False}],
                    },
                    {
                        "role": "core",
                        "session_index": 1,
                        "selected": {"name": "Dead Bug", "anchor_capable": False, "support_only": True},
                        "alternates": [{"name": "Pallof Press", "anchor_capable": False, "support_only": True}],
                    }
                ],
                "conditioning_slots": [
                    {
                        "role": "alactic",
                        "session_index": 1,
                        "selected": {
                            "name": "Air Bike Sprint",
                            "required_equipment": ["bike"],
                            "session_index": 1,
                        },
                        "alternates": [{"name": "Short Sprint"}],
                    },
                    {
                        "role": "glycolytic",
                        "session_index": 2,
                        "selected": {
                            "name": "Hard Shuttle",
                            "required_equipment": [],
                            "session_index": 2,
                        },
                        "alternates": [
                            {
                                "name": "Bag Sprint Round",
                                "required_equipment": ["heavy_bag"],
                                "session_index": 2,
                                "availability_contingency_reason": "only if heavy bag is the only available glycolytic tool",
                            }
                        ],
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


def _late_fight_planning_brief(days_out: str = "D-5") -> dict:
    payload_mode = "pre_fight_day_payload"
    session_cap = 1
    max_active_roles = 1
    forbidden_blocks = ["glycolytic", "hinge_transfer", "jumps", "contrast_work", "fight_pace_conditioning"]

    if days_out == "D-7":
        payload_mode = "late_fight_week_payload"
        session_cap = 3
        max_active_roles = 3
        forbidden_blocks = ["standalone_glycolytic", "multiple_hard_sparring_exposures"]
    elif days_out in {"D-6", "D-5"}:
        payload_mode = "late_fight_transition_payload"
        session_cap = 2
        max_active_roles = 2
        forbidden_blocks = ["hard_sparring", "standalone_glycolytic", "primary_strength_anchor"]
    elif days_out in {"D-4", "D-3", "D-2"}:
        payload_mode = "late_fight_session_payload"
        session_cap = 2 if days_out in {"D-4", "D-3"} else 1
        max_active_roles = session_cap
        forbidden_blocks = (
            ["hard_sparring", "standalone_glycolytic", "primary_strength_anchor"]
            if days_out in {"D-4", "D-3"}
            else ["conditioning", "hard_sparring", "primary_strength_anchor"]
        )
    elif days_out == "D-0":
        payload_mode = "fight_day_protocol_payload"
        forbidden_blocks = ["strength", "conditioning", "layered_rehab_stack"]

    return {
        "athlete_model": {"sport": "boxing", "days_until_fight": int(days_out.split("-")[-1])},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "late_fight_plan_spec": {
            "payload_mode": payload_mode,
            "days_out_bucket": days_out,
            "session_cap": session_cap,
            "max_active_roles": max_active_roles,
            "max_meaningful_stress_exposures": 1,
            "max_blocks_per_session": 4,
            "forbidden_blocks": forbidden_blocks,
        },
    }


def _late_fight_brief_with_allowed(days_out: str, allowed: list[str]) -> dict:
    brief = _late_fight_planning_brief(days_out)
    brief["late_fight_plan_spec"]["allowed_exercises_by_day"] = {days_out: allowed}
    return brief


def _boxing_crowded_week_planning_brief() -> dict:
    return {
        "athlete_model": {"sport": "boxing", "equipment": ["landmine", "bike", "bands"]},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "intentional_compression": {
                        "active": True,
                        "policy": "boxing_crowded_week",
                        "risk_signals": ["high_spar_load", "meaningful_weight_cut"],
                        "max_non_spar_roles": 2,
                        "max_support_roles": 1,
                        "standalone_glycolytic_allowed": False,
                    },
                    "session_roles": [
                        {
                            "role_key": "hard_sparring_day",
                            "category": "sparring",
                            "scheduled_day_hint": "Tuesday",
                            "governance": {"main_job": "hard_sparring"},
                        },
                        {
                            "role_key": "hard_sparring_day",
                            "category": "sparring",
                            "scheduled_day_hint": "Thursday",
                            "governance": {"main_job": "hard_sparring"},
                        },
                        {
                            "role_key": "neural_plus_strength_day",
                            "category": "strength",
                            "scheduled_day_hint": "Saturday",
                            "governance": {
                                "main_job": "anchor",
                                "support_cap": "light_only",
                                "forbidden_secondary_stressors": [
                                    "standalone_glycolytic",
                                    "hinge_transfer",
                                    "contrast_work",
                                    "jumps",
                                    "sharpness_touch",
                                    "hard_sparring",
                                ],
                            },
                        },
                        {
                            "role_key": "recovery_reset_day",
                            "category": "recovery",
                            "scheduled_day_hint": "Sunday",
                            "governance": {
                                "main_job": "support_recovery",
                                "support_cap": "light_only",
                                "forbidden_secondary_stressors": [
                                    "primary_strength_anchor",
                                    "standalone_glycolytic",
                                    "hinge_transfer",
                                    "contrast_work",
                                    "jumps",
                                    "sharpness_touch",
                                    "hard_sparring",
                                ],
                            },
                        },
                    ],
                }
            ]
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


def test_validate_stage2_output_does_not_count_post_phase_sections_for_last_phase():
    planning_brief = {
        "restrictions": [],
        "phase_strategy": {
            "TAPER": {
                "must_keep": ["rehab"],
            }
        },
        "candidate_pools": {
            "TAPER": {
                "strength_slots": [],
                "conditioning_slots": [],
                "rehab_slots": [
                    {
                        "role": "rehab_shoulder_strain",
                        "selected": {"name": "Band External Rotation"},
                        "alternates": [],
                    }
                ],
            }
        },
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 1: TAPER
        - Shadowboxing - 3 rounds
        ## Coach Notes
        - Band External Rotation worked well earlier in camp.
        """,
    )

    missing_requirements = {(item["phase"], item["requirement"]) for item in report["missing_required_elements"]}
    assert ("TAPER", "rehab") in missing_requirements


def test_validate_stage2_output_blocks_late_fight_overbuild_in_transition_window():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-5"),
        final_plan_text="""
        Monday - Hard Sparring
        - Hard sparring - 6 rounds
        Tuesday - Conditioning
        - Hard Shuttle - 6x20s / 60s
        Wednesday - Strength
        - Primary Strength - Trap Bar Deadlift 4x3
        """,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_active_role_overage" in warning_codes
    assert "late_fight_meaningful_stress_overage" in warning_codes
    assert "late_fight_hard_sparring_overage" in warning_codes
    assert "late_fight_forbidden_content" in warning_codes


def test_validate_stage2_output_blocks_d1_forbidden_blocks_and_block_overage():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        Friday - Primer
        - Neural Primer - 2x2 med-ball scoop toss
        - Jump Series - 3x3
        - Hinge Transfer - Trap Bar Pull 3x2
        - Contrast Pair - 2 rounds
        - Fight Pace Conditioning - 3 rounds
        """,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_block_overage" in warning_codes
    assert "late_fight_forbidden_content" in warning_codes


def test_validate_stage2_output_accepts_new_d3_sharpness_and_freshness_titles():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-3"),
        final_plan_text="""
        Monday - Sharpness Session
        - Power Touch - 3 x 2 med-ball scoop toss
        Tuesday - Freshness Session
        - Mobility / reset - 12 min
        - Breathing reset - 5 min
        """,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_active_role_overage" not in warning_codes
    assert "late_fight_meaningful_stress_overage" not in warning_codes
    assert "late_fight_forbidden_content" not in warning_codes


def test_late_fight_window_rules_block_d10_sprint_start():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-10"),
        final_plan_text="""
        ## D-10
        Monday - Sharpness Session
        - Band-Resisted Sprint Start - 4 x 6 sec
        - Mobility reset - 10 min
        """,
    )
    blocked = [w for w in report["warnings"] if w["code"] == "late_fight_window_forbidden_exercise"]
    assert blocked
    assert blocked[0]["days_out_bucket"] == "D-10"
    assert blocked[0]["window"] == "d13_to_d8"
    assert "Band-Resisted Sprint Start" in blocked[0]["line"]


def test_late_fight_window_rules_block_d3_med_ball_volume():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-3"),
        final_plan_text="""
        ## D-3
        Wednesday - Freshness Session
        - Medicine Ball Power Circuit - 4 x 3
        - Breathing reset - 5 min
        """,
    )
    blocked = [w for w in report["warnings"] if w["code"] == "late_fight_window_forbidden_exercise"]
    assert blocked
    assert blocked[0]["days_out_bucket"] == "D-3"
    assert blocked[0]["window"] == "d4_to_d2"
    assert "Medicine Ball Power Circuit" in blocked[0]["line"]


def test_late_fight_window_rules_accept_new_taper_mirror_drill_cue():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-3"),
        final_plan_text="""
        ## D-3
        Wednesday - Freshness Session
        - Mirror drill - 4 x 20 sec
        - Breathing reset - 5 min
        """,
    )
    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_window_preferred_missing" not in warning_codes
    assert "late_fight_window_forbidden_exercise" not in warning_codes


def test_late_fight_window_rules_block_d7_jump_reset():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-7"),
        final_plan_text="""
        ## D-7
        Tuesday - Sharpness
        - Band-Assisted Jump Reset - 3 x 2
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" and w["days_out_bucket"] == "D-7" for w in report["warnings"])


def test_late_fight_window_rules_block_d5_sprint_and_jump():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-5"),
        final_plan_text="""
        ## D-5
        Thursday - Primer
        - Band-Resisted Sprint Start - 4 x 6 sec
        - Band-Assisted Jump Reset - 3 x 3
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" and w["days_out_bucket"] == "D-5" for w in report["warnings"])


def test_late_fight_window_rules_block_d1_med_ball_barbell_trap_sprint_jump():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        ## D-1
        Friday - Primer
        - Medicine Ball Power Circuit - 2 x 2
        - Barbell push press - 2 x 2
        - Trap-bar pull - 2 x 2
        - Band-Resisted Sprint Start - 2 x 6 sec
        - Band-Assisted Jump Reset - 2 x 3
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" and w["days_out_bucket"] == "D-1" for w in report["warnings"])


def test_late_fight_window_rules_do_not_flag_instructional_negation_lines():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-3"),
        final_plan_text="""
        ## D-3
        Coach notes
        - No sprint starts this week.
        - Avoid jumps today.
        - Do not use med-ball in taper.
        - No heavy bag contact.
        - Avoid eccentric loading.
        - Trap bar is blocked after D-7.
        - Mirror drill - 3 x 20 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_window_forbidden_exercise" not in warning_codes


def test_late_fight_window_rules_do_not_count_negated_preferred_cues_as_present():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-3"),
        final_plan_text="""
        ## D-3
        Coach notes
        - Avoid Mobility Reset Flow today.
        - Do not use Technical Shadowboxing Tempo.
        - No Breathing Reset block.
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_window_preferred_missing" in warning_codes


def test_late_fight_window_rules_do_not_block_d13_trap_bar_deadlift_touch():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-13"),
        final_plan_text="""
        ## D-13
        - Trap Bar Deadlift - 2 x 2 (easy touch)
        - Band jab-cross - 4 x 6 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_window_forbidden_exercise" not in warning_codes


def test_late_fight_window_rules_block_d1_staggered_stance_med_ball_punch_throw():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        ## D-1
        - Staggered-Stance Medicine-Ball Punch Throw - 2 x 2
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" for w in report["warnings"])


def test_late_fight_window_rules_block_d1_light_heavy_bag_technical_tempo():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        ## D-1
        - Light Heavy-Bag Technical Tempo - 2 rounds
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" for w in report["warnings"])


def test_late_fight_window_rules_block_d1_scapular_pull_up_hold():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        ## D-1
        - Scapular Pull-Up Hold - 2 x 20 sec
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" for w in report["warnings"])


def test_late_fight_window_rules_block_d1_trap_bar_deadlift():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        ## D-1
        - Trap Bar Deadlift - 2 x 2
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" for w in report["warnings"])


def test_late_fight_window_rules_block_d1_hang_power_clean():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        ## D-1
        - Hang Power Clean - 2 x 2
        """,
    )
    assert any(w["code"] == "late_fight_window_forbidden_exercise" for w in report["warnings"])


def test_late_fight_window_rules_clean_d13_d6_d3_d1_sections_pass():
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-3"),
        final_plan_text="""
        ## D-13
        - Band-Resisted Jab-Cross Primer - 4 x 6 sec
        - Mobility Reset Flow - 10 min
        ## D-6
        - Explosive boxing burst intervals - 4 x 6 sec
        - Reactive shuffle repeats - 3 x 20 sec
        ## D-3
        - Mirror drill - 4 x 20 sec
        - Breathing reset - 5 min
        ## D-1
        - Band-Resisted Jab-Cross Primer - 2 x 6 sec
        - Mobility Reset Flow - 8 min
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_window_forbidden_exercise" not in warning_codes
    assert "late_fight_window_preferred_missing" not in warning_codes

def test_validate_stage2_output_accepts_same_level_subsections_inside_phase():
    base = _planning_brief_fixture()
    planning_brief = {
        "restrictions": [],
        "phase_strategy": {
            "SPP": {
                "must_keep": ["rehab", "alactic", "glycolytic"],
            }
        },
        "candidate_pools": {
            "SPP": base["candidate_pools"]["SPP"],
        },
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ## Strength & Power
        - Landmine Press - 4x5
        ## Conditioning
        - Air Bike Sprint - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        ## Rehab
        - Band External Rotation - 2x15
        """,
    )

    assert report["is_valid"] is True
    assert report["missing_required_elements"] == []


def test_validate_stage2_output_warns_for_weak_anchor_session_only_when_anchor_exists():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Dead Bug - 2x8
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weak_anchor_session" in warning_codes
    assert "support_takeover_before_anchor" in warning_codes


def test_validate_stage2_output_does_not_warn_for_force_isometric_anchor_when_justified():
    planning_brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {"GPP": {"must_keep": ["primary_strength"]}},
        "candidate_pools": {
            "GPP": {
                "strength_slots": [
                    {
                        "role": "hinge",
                        "session_index": 1,
                        "selected": {"name": "Deadlift Isometric", "anchor_capable": True, "support_only": False},
                        "alternates": [],
                    }
                ],
                "conditioning_slots": [],
                "rehab_slots": [],
            }
        },
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        GPP
        - Deadlift Isometric - 4 x 10 sec
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weak_anchor_session" not in warning_codes
    assert "support_takeover_before_anchor" not in warning_codes


def test_validate_stage2_output_warns_for_structural_conditionals():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Bike sprint or bag sprint depending on access
        - Trap Bar Death March - 5 x 30s
        - Band External Rotation - 2x15
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "conditional_conditioning_choice" in warning_codes


def test_validate_stage2_output_warns_for_low_trust_filler_and_motivation_cliches():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Stay consistent this week.
        - You've got this.
        - Trap Bar Deadlift - 4x5
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "generic_filler_phrase" in warning_codes
    assert "generic_motivation_cliche" in warning_codes


def test_validate_stage2_output_warns_for_generic_instruction_openers_with_rewrite_hint():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Focus on recovery today.
        - Ensure you keep the pace under control.
        - Trap Bar Deadlift - 4x5
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    opener_warnings = [warning for warning in report["warnings"] if warning["code"] == "generic_instruction_opener"]
    assert opener_warnings
    assert all("rewrite_hint" in warning for warning in opener_warnings)


def test_validate_stage2_output_warns_for_hedged_adjustment_without_decision():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Consider reducing intensity and prioritizing recovery.
        - Trap Bar Deadlift - 4x5
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    hedged_warnings = [warning for warning in report["warnings"] if warning["code"] == "hedged_adjustment_without_decision"]
    assert hedged_warnings
    assert hedged_warnings[0]["blocking"] is True


def test_validate_stage2_output_warns_for_empty_safety_language():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Consult a clinician before training.
        - Trap Bar Deadlift - 4x5
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    safety_warnings = [warning for warning in report["warnings"] if warning["code"] == "empty_safety_language"]
    assert safety_warnings
    assert safety_warnings[0].get("blocking") is False


def test_validate_stage2_output_blocks_empty_safety_language_in_high_risk_context():
    planning_brief = _planning_brief_fixture()
    planning_brief["athlete_model"]["fatigue"] = "high"
    planning_brief["athlete_model"]["readiness_flags"] = ["high_fatigue", "fight_week"]
    planning_brief["athlete_model"]["injuries"] = ["right shoulder pain"]

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        SPP
        - Listen to your body with upper-body loading.
        - Trap Bar Deadlift - 4x5
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    safety_warnings = [warning for warning in report["warnings"] if warning["code"] == "empty_safety_language"]
    assert safety_warnings
    assert safety_warnings[0]["blocking"] is True
    assert "high_fatigue" in safety_warnings[0]["risk_context"]


def test_validate_stage2_output_warns_when_session_presents_more_than_two_options():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Fight-Pace Conditioning
        - Option A: Air Bike Sprint - 6 x 6 sec
        - Option B: Short Sprint - 6 x 6 sec
        - Option C: Bag Sprint Round - 6 x 10 sec
        """,
    )

    overload_warnings = [warning for warning in report["warnings"] if warning["code"] == "option_overload"]
    assert overload_warnings
    assert overload_warnings[0].get("blocking") is False


def test_validate_stage2_output_blocks_option_overload_in_adjustment_context():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ## PHASE 2: SPP
        Strength
        - Option A: Reduce volume to 4 rounds.
        - Option B: Drop intensity and keep the same rounds.
        - Option C: Skip the hard finish and move to easy bike work.
        """,
    )

    overload_warnings = [warning for warning in report["warnings"] if warning["code"] == "option_overload"]
    assert overload_warnings
    assert overload_warnings[0]["blocking"] is True


def test_validate_stage2_output_does_not_false_positive_clear_coach_language():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - We are dropping volume today because fatigue is high and extra work buys soreness, not progress.
        - If pain is worse tomorrow morning, stop upper-body loading and reassess.
        - Trap Bar Deadlift - 4x5
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "generic_filler_phrase" not in warning_codes
    assert "generic_instruction_opener" not in warning_codes
    assert "generic_motivation_cliche" not in warning_codes
    assert "hedged_adjustment_without_decision" not in warning_codes
    assert "empty_safety_language" not in warning_codes


def test_validate_stage2_output_warns_for_boxing_sport_language_leaks():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Double-leg sprint entry - 6 x 6 sec
        - Hard Shuttle - 6x20s / 60s
        - Band External Rotation - 2x15
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "sport_language_leak" in warning_codes


def test_validate_stage2_output_warns_for_template_like_render_and_extra_fallbacks():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Fight-pace conditioning
        - Primary: Air Bike Sprint - 6 x 6 sec
        - Fallback: Short Sprint - 6 x 6 sec
        - Fallback: Bag Sprint Round - 6 x 10 sec
        - System: Glycolytic
        - Weekly Progression: Add 1 round
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "too_many_fallbacks" in warning_codes
    assert "template_like_session_render" in warning_codes


def test_validate_stage2_output_warns_for_taper_option_overload():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ## PHASE 3: TAPER
        ### Alactic sharpness
        - Primary: Air Bike Sprint - 4 x 6 sec
        - Fallback: Short Sprint - 4 x 6 sec
        - Bike sprint or bag sprint depending on access
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "taper_option_overload" in warning_codes


def test_validate_stage2_output_warns_for_equipment_incongruent_selection():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Strength
        - Landmine Press - 4x5
        ### Fight-Pace Conditioning
        - Bag Sprint Round - 6 x 15 sec
        ### Rehab
        - Band External Rotation - 2x15
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "equipment_incongruent_selection" in warning_codes


def test_validate_stage2_output_warns_for_unresolved_access_fallback_when_choice_is_already_resolved():
    report = validate_stage2_output(
        planning_brief=_planning_brief_fixture(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Fight-Pace Conditioning
        - Primary: Air Bike Sprint - 6 x 6 sec
        - Fallback: Short Sprint - 6 x 6 sec
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "unresolved_access_fallback" in warning_codes


def test_validate_stage2_output_allows_fallback_when_explicit_contingency_exists():
    planning_brief = _planning_brief_fixture()
    planning_brief["candidate_pools"]["SPP"]["conditioning_slots"][0]["alternates"] = [
        {
            "name": "Short Sprint",
            "required_equipment": [],
            "availability_contingency_reason": "use if bike access is unavailable that day",
            "session_index": 1,
        }
    ]

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ### Fight-Pace Conditioning
        - Primary: Air Bike Sprint - 6 x 6 sec
        - Fallback: Short Sprint - 6 x 6 sec
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "unresolved_access_fallback" not in warning_codes


def test_validate_stage2_output_warns_for_missing_late_week_structure_and_broken_boxer_rhythm():
    planning_brief = _planning_brief_fixture()
    planning_brief["phase_strategy"] = {
        "GPP": {"must_keep": ["primary_strength"]},
        "SPP": {"must_keep": ["rehab", "alactic", "glycolytic"]},
        "TAPER": {"must_keep": ["alactic"]},
    }
    planning_brief["weekly_role_map"] = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                    {"role_key": "recovery_reset_day", "category": "recovery"},
                    {"role_key": "neural_plus_strength_day", "category": "strength"},
                    {"role_key": "fight_pace_repeatability_day", "category": "conditioning"},
                ],
            },
            {
                "week_index": 2,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                    {"role_key": "recovery_reset_day", "category": "recovery"},
                    {"role_key": "neural_plus_strength_day", "category": "strength"},
                    {"role_key": "fight_pace_repeatability_day", "category": "conditioning"},
                ],
            },
            {
                "week_index": 3,
                "phase": "TAPER",
                "session_roles": [
                    {"role_key": "alactic_sharpness_day", "category": "conditioning"},
                    {"role_key": "fight_week_freshness_day", "category": "recovery"},
                ],
            },
        ]
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Strength
        - Landmine Press - 4x5
        #### Fight-pace conditioning
        - Hard Shuttle - 6x20s / 60s
        #### Recovery
        - Walk + mobility
        #### Strength
        - Landmine Press - 4x5
        #### Fight-pace conditioning
        - Air Bike Sprint - 6 x 6 sec

        ### Week 2
        #### Strength
        - Landmine Press - 4x5
        #### Recovery
        - Walk + mobility
        #### Fight-pace conditioning
        - Hard Shuttle - 6x20s / 60s
        #### Strength
        - Landmine Press - 4x5

        ## PHASE 3: TAPER
        ### Week 3
        #### Alactic sharpness
        - Air Bike Sprint - 4 x 6 sec
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weekly_rhythm_broken" in warning_codes
    assert "late_camp_session_incomplete" in warning_codes


def test_validate_stage2_output_warns_when_week_exceeds_requested_session_count():
    planning_brief = _planning_brief_fixture()
    planning_brief["weekly_role_map"] = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                    {"role_key": "recovery_reset_day", "category": "recovery"},
                    {"role_key": "neural_plus_strength_day", "category": "strength"},
                    {"role_key": "fight_pace_repeatability_day", "category": "conditioning"},
                ],
            },
            {
                "week_index": 2,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                    {"role_key": "recovery_reset_day", "category": "recovery"},
                    {"role_key": "neural_plus_strength_day", "category": "strength"},
                    {"role_key": "fight_pace_repeatability_day", "category": "conditioning"},
                ],
            },
        ]
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Monday - Strength
        - Landmine Press - 4x5
        #### Tuesday - Aerobic support
        - Easy Bike - 25 min
        #### Wednesday - Recovery
        - Walk + mobility
        #### Thursday - Strength
        - Trap Bar Deadlift - 4x3
        #### Friday - Fight-pace conditioning
        - Hard Shuttle - 6x20s / 60s
        #### Saturday - Recovery
        - Walk + mobility

        ### Week 2
        #### Monday - Strength
        - Landmine Press - 4x5
        #### Tuesday - Aerobic support
        - Easy Bike - 25 min
        #### Wednesday - Recovery
        - Walk + mobility
        #### Thursday - Strength
        - Trap Bar Deadlift - 4x3
        #### Friday - Fight-pace conditioning
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weekly_session_overage" in warning_codes


def test_validate_stage2_output_does_not_false_positive_session_overage_from_prose_lines():
    planning_brief = _planning_brief_fixture()
    planning_brief["weekly_role_map"] = {
        "weeks": [
            {
                "week_index": 4,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                ],
            },
            {
                "week_index": 5,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                ],
            },
        ]
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 4
        Session focus: keep intensity moderate this week.
        Day 4 note: athlete reported some fatigue, adjust load downward.
        #### Monday - Strength
        - Landmine Press - 4x5
        #### Tuesday - Aerobic support
        - Easy Bike - 25 min

        ### Week 5
        #### Monday - Strength
        - Landmine Press - 4x5
        #### Tuesday - Aerobic support
        - Easy Bike - 25 min
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weekly_session_overage" not in warning_codes


def test_validate_stage2_output_counts_explicit_numbered_session_headings():
    planning_brief = _planning_brief_fixture()
    planning_brief["weekly_role_map"] = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                ],
            },
            {
                "week_index": 2,
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "strength_touch_day", "category": "strength"},
                    {"role_key": "aerobic_support_day", "category": "conditioning"},
                ],
            },
        ]
    }

    report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Session 1 - Strength
        - Landmine Press - 4x5
        #### Day 2: Aerobic support
        - Easy Bike - 25 min
        #### Day 3: extra bonus session
        - Additional work

        ### Week 2
        #### Session 1 - Strength
        - Landmine Press - 4x5
        #### Day 2: Aerobic support
        - Easy Bike - 25 min
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weekly_session_overage" in warning_codes


def test_validate_stage2_output_warns_when_crowded_week_exceeds_non_spar_budget():
    report = validate_stage2_output(
        planning_brief=_boxing_crowded_week_planning_brief(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Tuesday - Hard Sparring
        - Hard Sparring - 6 x 3 min
        #### Thursday - Hard Sparring
        - Hard Sparring - 5 x 3 min
        #### Saturday - Strength
        - Landmine Press - 4x5
        #### Sunday - Recovery
        - Walk + mobility
        #### Monday - Extra Conditioning
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "crowded_week_non_spar_overage" in warning_codes


def test_validate_stage2_output_warns_for_anchor_day_identity_overload():
    report = validate_stage2_output(
        planning_brief=_boxing_crowded_week_planning_brief(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Tuesday - Hard Sparring
        - Hard Sparring - 6 x 3 min
        #### Thursday - Hard Sparring
        - Hard Sparring - 5 x 3 min
        #### Saturday - Strength
        - Landmine Press - 4x5
        - Hard Shuttle - 6x20s / 60s
        #### Sunday - Recovery
        - Walk + mobility
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "anchor_day_identity_overload" in warning_codes


def test_validate_stage2_output_matches_anchor_warning_by_scheduled_day_when_reordered():
    report = validate_stage2_output(
        planning_brief=_boxing_crowded_week_planning_brief(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Tuesday - Hard Sparring
        - Hard Sparring - 6 x 3 min
        #### Thursday - Hard Sparring
        - Hard Sparring - 5 x 3 min
        #### Sunday - Recovery
        - Walk + mobility
        #### Saturday - Strength
        - Landmine Press - 4x5
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "anchor_day_identity_overload" in warning_codes


def test_validate_stage2_output_warns_for_support_day_stress_leak():
    report = validate_stage2_output(
        planning_brief=_boxing_crowded_week_planning_brief(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Tuesday - Hard Sparring
        - Hard Sparring - 6 x 3 min
        #### Thursday - Hard Sparring
        - Hard Sparring - 5 x 3 min
        #### Saturday - Strength
        - Landmine Press - 4x5
        #### Sunday - Recovery
        - Trap Bar Deadlift - 4x3
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "support_recovery_day_stress_leak" in warning_codes


def test_validate_stage2_output_matches_support_warning_by_scheduled_day_when_reordered():
    report = validate_stage2_output(
        planning_brief=_boxing_crowded_week_planning_brief(),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Tuesday - Hard Sparring
        - Hard Sparring - 6 x 3 min
        #### Thursday - Hard Sparring
        - Hard Sparring - 5 x 3 min
        #### Sunday - Recovery
        - Trap Bar Deadlift - 4x3
        #### Saturday - Strength
        - Landmine Press - 4x5
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "support_recovery_day_stress_leak" in warning_codes


def _weight_cut_planning_brief(high_pressure: bool = True) -> dict:
    readiness_flags = ["active_weight_cut"]
    if high_pressure:
        readiness_flags.extend(["aggressive_weight_cut", "moderate_fatigue"])
    return {
        "athlete_model": {
            "sport": "boxing",
            "equipment": ["bike", "bodyweight"],
            "weight_cut_risk": True,
            "weight_cut_pct": 8.6,
            "fatigue": "moderate" if high_pressure else "low",
            "days_until_fight": 21 if high_pressure else 42,
            "readiness_flags": readiness_flags,
        },
        "phase_strategy": {},
        "candidate_pools": {},
    }


def test_validate_stage2_output_weight_cut_profile_only_does_not_count_as_acknowledgement():
    report = validate_stage2_output(
        planning_brief=_weight_cut_planning_brief(high_pressure=True),
        final_plan_text="""
        ## Athlete Profile
        - Weight: 72kg
        - Target Weight: 66kg
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "missing_weight_cut_acknowledgement" in warning_codes
    assert "high_pressure_weight_cut_underaddressed" not in warning_codes


def test_validate_stage2_output_accepts_summary_and_support_weight_cut_notes():
    report = validate_stage2_output(
        planning_brief=_weight_cut_planning_brief(high_pressure=True),
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 5
        #### Strength
        - Active weight-cut stress is part of this week, so keep the main work sharp and avoid extra soreness.
        - Trap Bar Deadlift - 4x3

        ## Nutrition
        - Active Weight-Cut Note:
        - Prioritize carbs, fluids, and sodium around key sessions to preserve strength expression and conditioning tolerance.
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "missing_weight_cut_acknowledgement" not in warning_codes
    assert "high_pressure_weight_cut_underaddressed" not in warning_codes


def test_validate_stage2_output_flags_weight_cut_state_contradiction():
    report = validate_stage2_output(
        planning_brief=_weight_cut_planning_brief(high_pressure=False),
        final_plan_text="""
        ## PHASE 1: GPP
        ### Week 1
        - Weight cut: none active — recovery tolerance is standard.
        - Keep the work crisp.
        """,
    )

    warning_codes = [warning["code"] for warning in report["warnings"]]
    assert "weight_cut_state_contradiction" in warning_codes


# ---------------------------------------------------------------------------
# Late-fight dosage ceiling tests
# ---------------------------------------------------------------------------

def test_late_fight_alactic_dose_overage_flagged_on_d5():
    """D-5 plan with 8 alactic bursts (> 6 cap) must emit alactic_dose_overage."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-5"),
        final_plan_text="""
        Thursday - Sharpness Session
        - Air Bike Sprint - 8 bursts x 8 sec @ RPE 8–9, rest 90 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_alactic_dose_overage" in warning_codes


def test_late_fight_alactic_dose_within_d5_ceiling_passes():
    """D-5 plan with 6 alactic bursts (at ceiling) must NOT emit alactic_dose_overage."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-5"),
        final_plan_text="""
        Thursday - Sharpness Session
        - Air Bike Sprint - 6 bursts x 8 sec @ RPE 8–9, rest 90 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_alactic_dose_overage" not in warning_codes


def test_late_fight_technical_round_overage_flagged_on_d5():
    """D-5 plan with 6 technical rounds (> 4 cap) must emit technical_round_overage."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-5"),
        final_plan_text="""
        Thursday - Technical Touch
        - Shadowboxing - 6 rounds @ RPE 6
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_technical_round_overage" in warning_codes


def test_late_fight_technical_round_within_d5_ceiling_passes():
    """D-5 plan with 4 technical rounds (at ceiling) must NOT emit technical_round_overage."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-5"),
        final_plan_text="""
        Thursday - Technical Touch
        - Shadowboxing - 4 rounds @ RPE 6
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_technical_round_overage" not in warning_codes


def test_late_fight_alactic_overage_flagged_on_d1():
    """D-1 plan with 5 alactic bursts (> 3 cap) must emit alactic_dose_overage."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        Friday - Neural Primer
        - Short Sprint - 5 bursts x 6 sec @ RPE 7–8, rest 120 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_alactic_dose_overage" in warning_codes


def test_late_fight_d1_conditioning_round_structure_forbidden():
    """D-1 plan with a conditioning-style round structure must emit the forbidden code."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        Friday - Neural Primer
        - Shadowboxing - 3 rounds of 2 min @ RPE 6
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_conditioning_round_structure_forbidden" in warning_codes


def test_late_fight_d1_simple_bursts_no_round_structure_flag():
    """D-1 with plain burst lines (no round structure) must NOT trigger the forbidden code."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-1"),
        final_plan_text="""
        Friday - Neural Primer
        - Short Sprint - 2 bursts x 6 sec @ RPE 7, rest 120 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_conditioning_round_structure_forbidden" not in warning_codes


def test_late_fight_countdown_validator_blocks_known_d6_and_d1_leaks():
    brief = _late_fight_planning_brief("D-6")
    brief["late_fight_plan_spec"].update(
        {
            "payload_mode": "pre_fight_compressed_payload",
            "days_out_bucket": "D-13",
            "max_active_roles": 8,
        }
    )

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-13 — Strength touch
        - Staggered-Stance Medicine-Ball Punch Throw
        - Band-Resisted Jab-Cross Primer

        D-6 — Alactic sharpness
        - Band-Assisted Jump Reset
        - Fallback: Band-Resisted Sprint Start

        D-1 — Neural primer
        - Band-Resisted Jab-Cross Primer
        - Staggered-Stance Medicine-Ball Punch Throw
        """,
    )

    blocked = [
        warning
        for warning in report["warnings"]
        if warning["code"] == "late_fight_countdown_blocked_drill"
    ]
    assert {warning["days_out_bucket"] for warning in blocked} == {"D-6", "D-1"}
    assert any(warning["blocked_drill"] == "Band-Assisted Jump Reset" for warning in blocked)
    assert any(warning["blocked_drill"] == "Band-Resisted Sprint Start" for warning in blocked)
    assert any(
        warning["blocked_drill"] == "Staggered-Stance Medicine-Ball Punch Throw"
        for warning in blocked
    )


def test_late_fight_countdown_clean_sample_has_no_d6_or_d1_blocked_drills():
    brief = _late_fight_planning_brief("D-6")
    brief["late_fight_plan_spec"].update(
        {
            "payload_mode": "pre_fight_compressed_payload",
            "days_out_bucket": "D-13",
            "max_active_roles": 8,
        }
    )

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-13 — Strength touch
        - Staggered-Stance Medicine-Ball Punch Throw — 3 x 3
        - Band-Resisted Jab-Cross Primer — 2 x 3
        - Breathing + shoulder mobility

        D-6 — Alactic sharpness
        - Explosive Boxing Burst Intervals — 3 x 6 sec
        - Reactive Shuffle Repeats — 3 x 6 sec
        - Breathing + shoulder mobility

        D-1 — Neural primer
        - Band Face Pull — 1 x 10
        - Breathing reset
        """,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_countdown_blocked_drill" not in warning_codes


def test_late_fight_countdown_blocks_non_rehab_band_work_on_d7_and_d1():
    brief = _late_fight_planning_brief("D-7")
    brief["late_fight_plan_spec"].update({"payload_mode": "late_fight_countdown_only"})
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-7 — Sharpness
        - Band-Resisted Split Jump
        - Band-Resisted Jab-Cross

        D-1 — Neural primer
        - Band-Resisted Jab-Cross
        """,
    )
    blocked = [w for w in report["warnings"] if w["code"] == "late_fight_countdown_blocked_drill"]
    assert any(w["days_out_bucket"] == "D-7" and w["blocked_drill"] == "non_rehab_band_work" for w in blocked)
    assert any(w["days_out_bucket"] == "D-1" and w["blocked_drill"] == "non_rehab_band_work" for w in blocked)


def test_late_fight_flags_d7_fight_day_mislabel():
    brief = _late_fight_planning_brief("D-7")
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-7 (Wednesday — Fight day)
        - Fight day protocol — follow coach warm-up and fight protocol.
        """,
    )
    blocking_codes = {warning["code"] for warning in report["warnings"] if warning.get("blocking")}
    assert "late_fight_countdown_fight_day_mislabel" in blocking_codes


def test_late_fight_allowlist_blocks_d13_band_resisted_sprint_starts():
    brief = _late_fight_brief_with_allowed(
        "D-13",
        ["Staggered-Stance Medicine-Ball Punch Throw", "Reactive Shuffle Repeats", "Breathing Reset"],
    )
    brief["late_fight_plan_spec"].update({"payload_mode": "pre_fight_compressed_payload"})

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-13 - Sharpness
        - Band-Resisted Sprint Starts (ATP-PCr) - 3 x 5 m
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_late_fight_countdown_blocks_d13_spp_only_resisted_acceleration_phrase():
    brief = _late_fight_brief_with_allowed("D-13", ["Reactive Shuffle Repeats", "Breathing Reset"])
    brief["late_fight_plan_spec"].update({"payload_mode": "pre_fight_compressed_payload"})

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-13 - Sharpness
        - Resisted Acceleration Sprint Start - 3 x 5 m
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_countdown_blocked_drill" in blocking_codes
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_late_fight_allowlist_blocks_d7_band_resisted_split_jump():
    brief = _late_fight_brief_with_allowed("D-7", ["Reactive Shuffle Repeats", "Breathing Reset"])

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-7 - Sharpness
        - Band-Resisted Split Jump - 2 x 3
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_late_fight_allowlist_blocks_d7_band_resisted_jab_cross_with_unicode_hyphen():
    brief = _late_fight_brief_with_allowed("D-7", ["Reactive Shuffle Repeats", "Breathing Reset"])

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-7 - Sharpness
        - Band‑Resisted Jab‑Cross Primer - 3 x 3
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes
    assert "late_fight_countdown_blocked_drill" in blocking_codes


def test_late_fight_allowlist_blocks_d1_band_resisted_jab_cross():
    brief = _late_fight_brief_with_allowed("D-1", ["Band Face Pull", "Technical Shadowboxing Tempo", "Breathing Reset"])

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-1 - Neural primer
        - Band-Resisted Jab-Cross - 2 x 3
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes
    assert "late_fight_countdown_blocked_drill" in blocking_codes


def test_late_fight_d1_rehab_band_work_passes_with_rehab_context():
    brief = _late_fight_brief_with_allowed("D-1", ["Technical Shadowboxing Tempo", "Breathing Reset"])

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-1 - Reset
        - Band Face Pull rehab - 1 x 10
        - Band External Rotation mobility - 1 x 8
        - band pull-aparts prehab reset - 1 x 10
        - Breathing reset - 3 min
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" not in blocking_codes
    assert "late_fight_countdown_blocked_drill" not in blocking_codes


def test_late_fight_d7_neural_power_stacking_triggers_retry_warning():
    brief = _late_fight_brief_with_allowed(
        "D-7",
        ["Speed Box Squat", "Reactive Shuffle Repeats", "Technical Shadowboxing Tempo"],
    )

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-7 - Sharpness
        - Speed Box Squat - 2 x 2
        - Reactive Shuffle Repeats - 3 x 6 sec
        - Technical Shadowboxing Tempo - 2 rounds
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_neural_power_stacking" in blocking_codes


def test_late_fight_allowlist_blocks_unknown_exercise_name():
    brief = _late_fight_brief_with_allowed("D-5", ["Reactive Shuffle Repeats", "Breathing Reset"])

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        Friday - Sharpness
        - Mystery Power Drill - 2 x 3
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_valid_late_fight_allowlisted_sample_passes():
    brief = _late_fight_brief_with_allowed(
        "D-5",
        ["Reactive Shuffle Repeats", "Technical Shadowboxing Tempo", "Breathing Reset"],
    )

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        Friday - Sharpness
        - Reactive Shuffle Repeats - 3 x 6 sec
        - Technical Shadowboxing Tempo - 2 rounds
        - Breathing reset - 3 min
        """,
    )

    blocking_codes = {w["code"] for w in report["warnings"] if w.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" not in blocking_codes
    assert not report["errors"]


def test_late_fight_countdown_blocks_resistance_and_mini_band_variants():
    brief = _late_fight_planning_brief("D-7")
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-7 — Sharpness
        - Resistance-band jab-cross release
        - Mini-band split jump
        """,
    )
    blocked = [w for w in report["warnings"] if w["code"] == "late_fight_countdown_blocked_drill"]
    assert any(w["blocked_drill"] == "non_rehab_band_work" for w in blocked)


def test_late_fight_countdown_blocks_single_day_non_rehab_band_work():
    brief = _late_fight_planning_brief("D-5")
    brief["late_fight_plan_spec"].update({"payload_mode": "late_fight_session_payload"})

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        Friday - Sharpness
        - Band-Resisted Jab-Cross - 3 x 6 sec
        """,
    )

    blocked = [w for w in report["warnings"] if w["code"] == "late_fight_countdown_blocked_drill"]
    assert any(
        w["days_out_bucket"] == "D-5" and w["blocked_drill"] == "non_rehab_band_work"
        for w in blocked
    )


def test_late_fight_countdown_band_lockout_uses_phrase_boundaries():
    brief = _late_fight_planning_brief("D-5")
    brief["late_fight_plan_spec"].update({"payload_mode": "late_fight_session_payload"})

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        Friday - Technical
        - Abandoned tempo cue review - 2 rounds
        """,
    )

    blocked = [w for w in report["warnings"] if w["code"] == "late_fight_countdown_blocked_drill"]
    assert not any(w["blocked_drill"] == "non_rehab_band_work" for w in blocked)


def test_late_fight_alactic_overage_d4():
    """D-4 plan with 7 alactic bursts (> 5 cap) must emit alactic_dose_overage."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-4"),
        final_plan_text="""
        Monday - Sharpness
        - Alactic Sprint - 7 bursts x 8 sec @ RPE 8, rest 90 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_alactic_dose_overage" in warning_codes


def test_late_fight_dosage_ceiling_not_applied_outside_countdown():
    """Plans with days_out_bucket D-7 (> 5) should not trigger dosage ceiling checks."""
    report = validate_stage2_output(
        planning_brief=_late_fight_planning_brief("D-7"),
        final_plan_text="""
        Monday - Sharpness Session
        - Air Bike Sprint - 8 bursts x 8 sec @ RPE 8–9, rest 90 sec
        """,
    )
    warning_codes = {w["code"] for w in report["warnings"]}
    assert "late_fight_alactic_dose_overage" not in warning_codes


def test_calendar_spine_thursday_fight_rejects_saturday_pretend_prefight():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "calendar_days": [
                        {"weekday": "thursday", "d_day": 0, "is_fight_day": True, "is_after_fight_day": False},
                        {"weekday": "saturday", "d_day": -2, "is_fight_day": False, "is_after_fight_day": True},
                    ],
                    "session_roles": [{"role_key": "fight_day_protocol", "scheduled_day_hint": "thursday"}],
                }
            ]
        },
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        ## Week 1
        Thursday - D-0
        - Fight-day protocol only.
        Saturday - D-2
        - Coach-led boxing session
        """,
    )
    codes = {w["code"] for w in report["warnings"]}
    assert "calendar_spine_post_fight_training_rendered" in codes


def test_calendar_spine_friday_fight_weekend_not_prefight():
    from fightcamp.fight_date_utils import build_calendar_days

    days = build_calendar_days(fight_weekday="friday", projected_days_until_fight_end=0, span_days=3)
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {"weeks": [{"week_index": 1, "phase": "TAPER", "calendar_days": days, "session_roles": []}]},
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        ## Week 1
        Saturday - D-1
        - Technical touch
        """,
    )
    assert any(w["code"] == "calendar_spine_unmapped_weekday_rendered" for w in report["warnings"])


def test_calendar_spine_accepts_abbreviated_rendered_weekday():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "GPP",
                    "calendar_days": [
                        {
                            "weekday": "monday",
                            "d_day": 7,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        }
                    ],
                    "session_roles": [
                        {
                            "role_key": "primary_strength",
                            "scheduled_day_hint": "mon",
                        }
                    ],
                }
            ]
        },
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        ## Week 1
        Mon (D-7) — Strength
        - Strength: Trap-bar deadlift — 3 x 3.
        """,
    )
    assert not any(
        warning["code"] in {
            "calendar_spine_unmapped_weekday_rendered",
            "calendar_spine_session_role_not_authorized",
        }
        for warning in report["warnings"]
    )


def test_calendar_spine_no_duplicate_weekday_math_uses_calendar_days_directly():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "calendar_days": [{"weekday": "wednesday", "d_day": 3, "is_fight_day": False, "is_after_fight_day": False}],
                    "session_roles": [{"role_key": "technical_touch_day", "scheduled_day_hint": "wednesday"}],
                }
            ]
        },
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="## Week 2\nWednesday - D-3\n- Technical touch",
    )
    assert not any(w["code"] == "calendar_spine_d_day_mismatch" for w in report["warnings"])


def test_calendar_spine_fight_day_protocol_text_rule():
    from fightcamp.fight_day_override import FIGHT_DAY_PROTOCOL_TEXT

    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "calendar_days": [{"weekday": "friday", "d_day": 0, "is_fight_day": True, "is_after_fight_day": False}],
                    "session_roles": [],
                }
            ]
        },
    }
    bad = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="## Week 1\nFriday - D-0\n- Coach-led boxing session",
    )
    assert any(w["code"] == "calendar_spine_fight_day_protocol_violation" for w in bad["warnings"])
    good = validate_stage2_output(
        planning_brief=brief,
        final_plan_text=f"## Week 1\nFriday - D-0\n- {FIGHT_DAY_PROTOCOL_TEXT}",
    )
    assert not any(w["code"] == "calendar_spine_fight_day_protocol_violation" for w in good["warnings"])
    
    
def test_calendar_spine_rejects_calendar_day_without_session_role():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "calendar_days": [
                        {
                            "weekday": "monday",
                            "d_day": 7,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        },
                        {
                            "weekday": "wednesday",
                            "d_day": 5,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        },
                    ],
                    "session_roles": [
                        {
                            "role_key": "technical_touch_day",
                            "scheduled_day_hint": "wednesday",
                        }
                    ],
                }
            ]
        },
    }

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        ## Week 1
        Monday - D-7
        - Strength: Trap-bar deadlift — 3 x 3.

        Wednesday - D-5
        - Technical touch
        """,
    )

    assert any(
        warning["code"] == "calendar_spine_session_role_not_authorized"
        for warning in report["warnings"]
    )


def test_calendar_spine_allows_unassigned_off_recovery_only_day():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "calendar_days": [
                        {
                            "weekday": "monday",
                            "d_day": 7,
                            "is_fight_day": False,
                            "is_after_fight_day": False,
                        },
                    ],
                    "session_roles": [],
                }
            ]
        },
    }

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        ## Week 1
        Monday - D-7
        - Off / recovery only day. No app S&C.
        """,
    )

    assert not any(
        warning["code"] == "calendar_spine_session_role_not_authorized"
        for warning in report["warnings"]
    )

def test_internal_render_contract_allows_coach_facing_anchor_phrase():
    report = validate_stage2_output(
        planning_brief={"athlete_model": {"sport": "boxing"}, "restrictions": [], "phase_strategy": {}, "candidate_pools": {}},
        final_plan_text="Monday - Strength\n- Keep this as your highest-neural anchor with clean reps.",
    )
    assert not any(w["code"] == "internal_render_contract_leak" for w in report["warnings"])


def test_internal_render_contract_blocks_scaffold_anchor_label():
    report = validate_stage2_output(
        planning_brief={"athlete_model": {"sport": "boxing"}, "restrictions": [], "phase_strategy": {}, "candidate_pools": {}},
        final_plan_text="Monday - Strength\n- 1) Anchor — Trap-bar deadlift 3 x 3",
    )
    assert any(w["code"] == "internal_render_contract_leak" for w in report["warnings"])


def test_calendar_spine_allows_one_line_d0_fight_day_protocol_header():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {"weeks": [{"week_index": 1, "phase": "TAPER", "calendar_days": [{"weekday": "sunday", "d_day": 0, "is_fight_day": True, "is_after_fight_day": False}], "session_roles": []}]},
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="## Week 1\nD-0 (Sunday) — Fight day protocol — follow coach warm-up and fight protocol; no additional app S&C.",
    )
    assert not any(w["code"] == "calendar_spine_fight_day_protocol_violation" for w in report["warnings"])


def test_calendar_spine_d0_still_rejects_extra_work():
    brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {"weeks": [{"week_index": 1, "phase": "TAPER", "calendar_days": [{"weekday": "sunday", "d_day": 0, "is_fight_day": True, "is_after_fight_day": False}], "session_roles": []}]},
    }
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="## Week 1\nSunday - D-0 — Fight day protocol\n- Fight day protocol — follow coach warm-up and fight protocol; no additional app S&C.\n- Add mobility and accessory rounds.",
    )
    assert any(w["code"] == "calendar_spine_fight_day_protocol_violation" for w in report["warnings"])
