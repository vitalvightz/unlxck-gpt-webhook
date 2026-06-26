from fightcamp.fight_day_override import FIGHT_DAY_PROTOCOL_TEXT
from fightcamp.stage2_pipeline import (
    build_stage2_package,
    build_stage2_retry,
    canonicalize_terminal_d0_protocol,
    review_stage2_output,
)


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


def _late_fight_planning_brief(days_out_bucket: str = "D-0") -> dict:
    return {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "late_fight_plan_spec": {
            "days_out_bucket": days_out_bucket,
            "payload_mode": "late_fight_countdown_only",
        },
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


def test_review_stage2_output_returns_pass_for_non_safety_structure_gaps():
    review = review_stage2_output(
        planning_brief=_stage1_result_fixture()["planning_brief"],
        final_plan_text="""
        SPP
        - Landmine Press - 4x5
        - Hard Shuttle - 6x20s / 60s
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False


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


def test_review_stage2_output_keeps_hedged_adjustment_non_blocking():
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

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False


def test_review_stage2_output_keeps_empty_safety_language_non_blocking():
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

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False


def test_review_stage2_output_treats_countdown_banded_lockout_as_non_blocking():
    planning_brief = _stage1_result_fixture()["planning_brief"]
    planning_brief["late_fight_plan_spec"] = {
        "days_out_bucket": "D-7",
        "payload_mode": "late_fight_countdown_only",
    }
    review = review_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        D-7 — Sharpness
        - Resistance-band jab-cross release
        - Band External Rotation mobility
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False


def test_review_stage2_output_treats_late_fight_unapproved_exercise_as_non_blocking():
    planning_brief = _stage1_result_fixture()["planning_brief"]
    planning_brief["late_fight_plan_spec"] = {
        "days_out_bucket": "D-13",
        "payload_mode": "pre_fight_compressed_payload",
        "allowed_exercises_by_day": {"D-13": ["Reactive Shuffle Repeats", "Breathing Reset"]},
    }
    review = review_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        D-13 - Sharpness
        - Band-Resisted Sprint Starts (ATP-PCr) - 3 x 5 m
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False


def test_canonicalize_terminal_d0_protocol_removes_final_coach_notes_after_d0():
    normalized = canonicalize_terminal_d0_protocol(
        "Lead notes\n"
        "- Keep the final week calm.\n"
        "\n"
        "D-1 (Saturday) - Freshness\n"
        "- Mobility reset.\n"
        "\n"
        "D-0 (Sunday) - Fight day protocol\n"
        "Fight day protocol - follow coach warm-up and fight protocol; no additional app S&C.\n"
        "\n"
        "Final coach notes\n"
        "- Stay relaxed."
    )

    assert normalized == (
        "Lead notes\n"
        "- Keep the final week calm.\n"
        "\n"
        "D-1 (Saturday) - Freshness\n"
        "- Mobility reset.\n"
        "\n"
        "D-0 (Sunday) \u2014 Fight day protocol\n"
        f"{FIGHT_DAY_PROTOCOL_TEXT}"
    )
    assert "Final coach notes" not in normalized
    assert normalized.endswith(FIGHT_DAY_PROTOCOL_TEXT)


def test_canonicalize_terminal_d0_protocol_rewrites_body_to_fight_day_text():
    normalized = canonicalize_terminal_d0_protocol(
        "D-0 (Friday) - Fight day protocol\n"
        "Follow coach warm-up and fight protocol; no additional app S&C."
    )

    assert normalized == (
        "D-0 (Friday) \u2014 Fight day protocol\n"
        f"{FIGHT_DAY_PROTOCOL_TEXT}"
    )


def test_review_stage2_output_accepts_normalized_terminal_d0_protocol():
    normalized = canonicalize_terminal_d0_protocol(
        """
        D-0 (Sunday) - Fight day protocol
        Follow coach warm-up and fight protocol; no additional app S&C.

        Coach note (one line)
        Stay loose.
        """
    )
    review = review_stage2_output(
        planning_brief=_late_fight_planning_brief("D-0"),
        final_plan_text=normalized,
    )

    blocking_codes = {
        warning["code"]
        for warning in review["validator_report"]["warnings"]
        if warning.get("blocking")
    }
    assert "late_fight_d0_protocol_expanded" not in blocking_codes


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
    assert "explicit converted low-load support role" in retry["repair_prompt"]


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


def test_build_stage2_retry_skips_prompt_when_only_card_rescuable_blocking_warning_exists():
    retry = build_stage2_retry(
        stage1_result=_stage1_result_fixture(),
        final_plan_text="SPP\n- Landmine Press - 4x5",
        validator_report={
            "errors": [],
            "warnings": [
                {
                    "code": "generic_filler_phrase",
                    "message": "Low-trust filler.",
                    "severity": "blocker",
                }
            ],
        },
    )

    assert retry["status"] == "PASS"
    assert retry["needs_retry"] is False
    assert retry["repair_prompt"] is None


def test_build_stage2_retry_prompt_includes_publish_blocking_warnings_for_hard_blocker():
    retry = build_stage2_retry(
        stage1_result=_stage1_result_fixture(),
        final_plan_text="SPP\n- Push Press - 4x3",
        validator_report={
            "errors": [{"code": "restriction_violation", "line": "Push Press"}],
            "warnings": [
                {
                    "code": "generic_filler_phrase",
                    "message": "Low-trust filler.",
                    "severity": "warning",
                }
            ],
            "blocking_warnings": [
                {
                    "code": "missing_required_element",
                    "message": "Missing phase-critical element.",
                    "severity": "blocker",
                }
            ],
            "review_flags": [
                {
                    "code": "sport_language_leak",
                    "message": "Cross-sport wording leaked in.",
                }
            ],
            "restricted_hits": [{"restriction": "heavy_overhead_pressing", "line": "Push Press"}],
        },
    )

    assert retry["status"] == "FAIL"
    assert retry["needs_retry"] is True
    assert retry["repair_prompt"] is not None
    assert "restriction_violation" in retry["repair_prompt"]
    assert "generic_filler_phrase" not in retry["repair_prompt"]
    assert "missing_required_element" in retry["repair_prompt"]
    assert "sport_language_leak" not in retry["repair_prompt"]


def test_build_stage2_retry_prompts_for_publish_blocking_review_flag():
    retry = build_stage2_retry(
        stage1_result=_stage1_result_fixture(),
        final_plan_text="SPP\n- Landmine Press - 4x5",
        validator_report={
            "errors": [],
            "warnings": [
                {
                    "code": "missing_required_element",
                    "message": "Missing phase-critical element.",
                    "phase": "SPP",
                    "requirement": "alactic",
                    "candidate_names": ["Air Bike Sprint"],
                }
            ],
            "review_flags": [
                {
                    "code": "missing_required_element",
                    "phase": "SPP",
                    "requirement": "alactic",
                    "candidate_names": ["Air Bike Sprint"],
                }
            ],
            "missing_required_elements": [
                {
                    "phase": "SPP",
                    "requirement": "alactic",
                    "candidate_names": ["Air Bike Sprint"],
                }
            ],
        },
    )

    assert retry["status"] == "WARN"
    assert retry["needs_retry"] is True
    assert retry["repair_prompt"] is not None
    assert "restore_phase_critical_element" in retry["repair_prompt"]
    assert "Air Bike Sprint" in retry["repair_prompt"]


def test_review_stage2_output_keeps_weekly_session_overage_as_review_flag():
    planning_brief = {
        "athlete_model": {"sport": "boxing"},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "session_roles": [
                        {"role_key": "strength_touch_day", "category": "strength"},
                        {"role_key": "conditioning_day", "category": "conditioning"},
                    ],
                },
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "session_roles": [
                        {"role_key": "strength_touch_day", "category": "strength"},
                        {"role_key": "conditioning_day", "category": "conditioning"},
                    ],
                },
            ]
        },
    }

    review = review_stage2_output(
        planning_brief=planning_brief,
        final_plan_text="""
        ## PHASE 2: SPP
        ### Week 1
        #### Monday - Strength
        - Landmine Press - 4x5
        #### Tuesday - Conditioning
        - Easy Bike - 25 min
        #### Wednesday - Extra work
        - Walk + mobility

        ### Week 2
        #### Monday - Strength
        - Landmine Press - 4x5
        #### Tuesday - Conditioning
        - Easy Bike - 25 min
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False
    assert review["validator_report"]["blocking_warnings"] == []
    review_flag_codes = [warning["code"] for warning in review["validator_report"]["review_flags"]]
    assert "weekly_session_overage" in review_flag_codes
