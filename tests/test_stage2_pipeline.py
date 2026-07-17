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


def test_review_stage2_output_holds_admin_blocking_structure_gaps():
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
    blocking_codes = {warning["code"] for warning in review["validator_report"]["blocking_warnings"]}
    assert blocking_codes == {"missing_required_element"}


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
        Injury watch: left hamstring strain; keep lower-body loading within restrictions.

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


def _late_fight_review_brief(days_out: str = "D-3", allowed: list[str] | None = None) -> dict:
    return {
        "athlete_model": {"sport": "boxing", "days_until_fight": int(days_out.split("-")[-1])},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "late_fight_plan_spec": {
            "days_out_bucket": days_out,
            "payload_mode": "late_fight_session_payload",
            "allowed_exercises_by_day": {days_out: allowed or []},
            "countdown_exercise_rules": [
                {
                    "countdown_label": "D-1",
                    "blocked_drills": [
                        "Staggered-Stance Medicine-Ball Punch Throw",
                        "Band-Resisted Sprint Start",
                    ],
                }
            ],
        },
    }


def _blocking_codes(review: dict) -> set[str]:
    return {
        warning["code"]
        for warning in review["validator_report"].get("blocking_warnings", [])
    }


def _assert_non_publishable_retry(review: dict, code: str) -> None:
    assert review["status"] in {"WARN", "FAIL"}
    assert review["needs_retry"] is True
    assert review["validator_report"]["is_publishable"] is False
    assert code in _blocking_codes(review)


def _assert_soft_review_flag(review: dict, code: str) -> None:
    # Rendering an exercise outside a countdown day's curated allowlist is a
    # soft review flag, not a hard blocker: it is surfaced for review but does
    # not hold the plan or force a retry.
    assert code not in _blocking_codes(review)
    warning_codes = {
        warning["code"] for warning in review["validator_report"].get("warnings", [])
    }
    assert code in warning_codes
    assert review["validator_report"]["is_publishable"] is True
    assert review["needs_retry"] is False


def test_review_stage2_output_treats_countdown_banded_lockout_as_blocking():
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

    _assert_non_publishable_retry(review, "late_fight_countdown_blocked_drill")


def test_review_stage2_output_still_blocks_d13_band_resisted_drill_via_dedicated_check():
    # Downgrading late_fight_unapproved_exercise_rendered must not weaken the
    # dedicated safety checks: a banded late-fight drill is still hard-blocked
    # by late_fight_countdown_blocked_drill.
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

    blocking = _blocking_codes(review)
    assert "late_fight_unapproved_exercise_rendered" not in blocking
    assert "late_fight_countdown_blocked_drill" in blocking
    assert review["validator_report"]["is_publishable"] is False


def test_review_stage2_output_still_blocks_d3_sandbag_shouldering_via_forbidden_window():
    # Sandbag shouldering in the freshness window stays hard-blocked by
    # late_fight_window_forbidden_exercise even though the generic
    # unapproved-exercise catch-all is now a soft review flag.
    review = review_stage2_output(
        planning_brief=_late_fight_review_brief("D-3", ["Mobility Reset Flow", "Breathing Reset"]),
        final_plan_text="""
        D-3 (Wednesday) — Fight-week freshness
        - Sandbag Shouldering — 4 x 4-6 reps each side
        - Breathing Reset — 3 min
        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    blocking = _blocking_codes(review)
    assert "late_fight_unapproved_exercise_rendered" not in blocking
    assert "late_fight_window_forbidden_exercise" in blocking
    assert review["validator_report"]["is_publishable"] is False


def test_review_stage2_output_retries_when_d1_renders_med_ball_punch_throw():
    review = review_stage2_output(
        planning_brief=_late_fight_review_brief("D-1", ["Technical Shadowboxing Tempo", "Breathing Reset"]),
        final_plan_text="""
        D-1 (Friday) — Final neural primer
        - Staggered-Stance Medicine-Ball Punch Throw — 2 x 3-4 throws per side
        - Breathing Reset — 3 min
        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    _assert_non_publishable_retry(review, "late_fight_countdown_blocked_drill")
    assert "late_fight_window_forbidden_exercise" in _blocking_codes(review)


def test_review_stage2_output_flags_but_does_not_retry_on_d3_unallowed_exercise():
    review = review_stage2_output(
        planning_brief=_late_fight_review_brief("D-3", ["Mobility Reset Flow", "Breathing Reset"]),
        final_plan_text="""
        D-3 (Wednesday) — Fight-week freshness
        - Mystery Power Drill — 2 x 3
        - Breathing Reset — 3 min
        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    _assert_soft_review_flag(review, "late_fight_unapproved_exercise_rendered")


def test_review_stage2_output_retries_when_d1_renders_countdown_blocked_drill():
    review = review_stage2_output(
        planning_brief=_late_fight_review_brief("D-1", ["Technical Shadowboxing Tempo", "Breathing Reset"]),
        final_plan_text="""
        D-1 (Friday) — Final neural primer
        - Band-Resisted Sprint Start — 2 x 5 m
        - Breathing Reset — 3 min
        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    _assert_non_publishable_retry(review, "late_fight_countdown_blocked_drill")


def test_review_stage2_output_passes_valid_d3_allowed_exercise():
    review = review_stage2_output(
        planning_brief=_late_fight_review_brief("D-3", ["Mobility Reset Flow", "Breathing Reset"]),
        final_plan_text="""
        D-3 (Wednesday) — Fight-week freshness
        - Mobility Reset Flow — 6 min
        - Breathing Reset — 3 min
        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False
    assert review["validator_report"]["is_publishable"] is True


def test_review_stage2_output_passes_valid_d1_primer_reset():
    review = review_stage2_output(
        planning_brief=_late_fight_review_brief("D-1", ["Technical Shadowboxing Tempo", "Breathing Reset"]),
        final_plan_text="""
        D-1 (Friday) — Final neural primer
        - Technical Shadowboxing Tempo — 2 light rounds
        - Breathing Reset — 3 min
        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False
    assert review["validator_report"]["is_publishable"] is True


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


def test_review_stage2_output_holds_weekly_session_overage_for_admin_review():
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

    assert review["status"] == "WARN"
    assert review["needs_retry"] is True
    blocking_codes = [warning["code"] for warning in review["validator_report"]["blocking_warnings"]]
    assert "weekly_session_overage" in blocking_codes
    review_flag_codes = [warning["code"] for warning in review["validator_report"]["review_flags"]]
    assert "weekly_session_overage" in review_flag_codes
