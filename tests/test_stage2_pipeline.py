from fightcamp.stage2_pipeline import (
    apply_structural_integrity_hold,
    build_stage2_package,
    build_stage2_retry,
    repair_stage2_structural_text,
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


def _structural_brief_fixture() -> dict:
    return {
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
                        {"weekday": "Mon", "d_day": 28},
                        {"weekday": "Tue", "d_day": 27},
                    ],
                    "session_roles": [
                        {
                            "role_key": "strength_day",
                            "category": "strength",
                            "athlete_facing_label": "Strength build",
                            "scheduled_day_hint": "Mon",
                            "scheduled_countdown_label": "D-28",
                            "display_text": "- Landmine Press - 4x5",
                        },
                        {
                            "role_key": "hard_sparring_day",
                            "category": "sparring",
                            "athlete_facing_label": "Hard sparring",
                            "scheduled_day_hint": "Tue",
                            "scheduled_countdown_label": "D-27",
                            "coach_owned": True,
                        },
                    ],
                },
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "calendar_days": [
                        {"weekday": "Mon", "d_day": 21},
                        {"weekday": "Tue", "d_day": 20},
                    ],
                    "session_roles": [
                        {
                            "role_key": "conditioning_day",
                            "category": "conditioning",
                            "athlete_facing_label": "Alactic conditioning",
                            "scheduled_day_hint": "Mon",
                            "scheduled_countdown_label": "D-21",
                            "selected_exercise_assignments": [
                                {
                                    "name": "Air Bike Sprint",
                                    "effective_prescription": {"display": "6 x 6 sec / 90 sec easy"},
                                }
                            ],
                        }
                    ],
                },
            ]
        },
    }


_RENDERED_WEEK_ONE = (
    "## PHASE 1: GPP\n"
    "### Week 1\n"
    "#### Mon (D-28) — Strength build\n"
    "- Landmine Press - 4x5\n"
)


def test_repair_restores_missing_day_into_canonical_week_in_place():
    brief = _structural_brief_fixture()
    report = {
        "blocking_warnings": [
            {"code": "missing_week_session_role", "phase": "SPP", "week_index": 2, "role_key": "conditioning_day"},
        ],
        "review_flags": [],
        "errors": [],
    }

    # Week 1 renders fully; week 2 renders its header but dropped its one session.
    final_plan_text = _RENDERED_WEEK_ONE + "\n## PHASE 2: SPP\n### Week 2\n"

    repaired = repair_stage2_structural_text(
        planning_brief=brief,
        final_plan_text=final_plan_text,
        validator_report=report,
    )

    # The dropped day is restored from its authoritative effective prescription,
    # inside the existing week 2 section (no appended second schedule).
    assert "### Mon (D-21) — Alactic conditioning" in repaired["text"]
    assert "- Air Bike Sprint — 6 x 6 sec / 90 sec easy" in repaired["text"]
    assert "# Stage 1 Structural Repair" not in repaired["text"]
    assert repaired["text"].count("Week 2") == 1
    # The restored day lands in week 2's section, before EOF (no new week header).
    assert repaired["text"].index("Alactic conditioning") > repaired["text"].index("### Week 2")
    assert [entry["role_key"] for entry in repaired["applied"]] == ["conditioning_day"]
    assert repaired["unresolved"] == []


def test_repair_holds_wholly_missing_week_instead_of_appending():
    brief = _structural_brief_fixture()
    report = {
        "blocking_warnings": [
            {"code": "phase_section_missing", "phase": "GPP"},
            {"code": "missing_week_session_role", "phase": "SPP", "week_index": 2, "role_key": "conditioning_day"},
        ],
        "review_flags": [],
        "errors": [],
    }

    # Week 1 is not rendered at all; it cannot be restored in place.
    repaired = repair_stage2_structural_text(
        planning_brief=brief,
        final_plan_text="## PHASE 2: SPP\n### Week 2\n",
        validator_report=report,
    )

    # No second schedule is appended for the missing week.
    assert "GPP" not in repaired["text"]
    assert "Week 1" not in repaired["text"]
    assert "# Stage 1 Structural Repair" not in repaired["text"]
    # The missing mandatory week-1 strength day is reported as unresolved so the
    # caller holds; the coach-owned sparring day is neither restored nor unresolved.
    unresolved_keys = {entry["role_key"] for entry in repaired["unresolved"]}
    assert "strength_day" in unresolved_keys
    assert "hard_sparring_day" not in unresolved_keys
    # A rendered week's own dropped session is still restored in place.
    assert "Air Bike Sprint" in repaired["text"]


def test_repair_uses_changed_effective_prescription_not_stale_content():
    # A role that survived Stage 1 but had its dose legitimately changed carries
    # the changed dose in its effective prescription. The repair must restore the
    # effective (changed) content, never a stale/preferred value.
    brief = _structural_brief_fixture()
    conditioning = brief["weekly_role_map"]["weeks"][1]["session_roles"][0]
    conditioning["preferred_exercise_names"] = ["Air Bike Sprint MAX (stale)"]
    conditioning["selected_exercise_assignments"] = [
        {
            "name": "Air Bike Sprint",
            "effective_prescription": {"display": "3 x 6 sec / 3 min easy (reduced)"},
        }
    ]
    report = {
        "blocking_warnings": [
            {"code": "missing_week_session_role", "phase": "SPP", "week_index": 2, "role_key": "conditioning_day"},
        ],
        "review_flags": [],
        "errors": [],
    }

    repaired = repair_stage2_structural_text(
        planning_brief=brief,
        final_plan_text=_RENDERED_WEEK_ONE + "\n## PHASE 2: SPP\n### Week 2\n",
        validator_report=report,
    )

    assert "3 x 6 sec / 3 min easy (reduced)" in repaired["text"]
    assert "stale" not in repaired["text"]


def test_repair_holds_role_without_authoritative_content():
    # A mandatory app-work role that only carries preferred exercise names (no
    # display_text, no priced effective prescription) is NOT synthesised: it is
    # left unresolved so the plan holds.
    brief = _structural_brief_fixture()
    brief["weekly_role_map"]["weeks"][1]["session_roles"][0] = {
        "role_key": "conditioning_day",
        "category": "conditioning",
        "athlete_facing_label": "Alactic conditioning",
        "scheduled_day_hint": "Mon",
        "scheduled_countdown_label": "D-21",
        "preferred_exercise_names": ["Air Bike Sprint"],
    }
    report = {
        "blocking_warnings": [
            {"code": "missing_week_session_role", "phase": "SPP", "week_index": 2, "role_key": "conditioning_day"},
        ],
        "review_flags": [],
        "errors": [],
    }

    repaired = repair_stage2_structural_text(
        planning_brief=brief,
        final_plan_text=_RENDERED_WEEK_ONE + "\n## PHASE 2: SPP\n### Week 2\n",
        validator_report=report,
    )

    assert "Air Bike Sprint" not in repaired["text"]
    assert repaired["applied"] == []
    unresolved_keys = {entry["role_key"] for entry in repaired["unresolved"]}
    assert "conditioning_day" in unresolved_keys


def test_repair_requires_exact_day_identity_not_repeated_marker():
    # The missing role's marker appears on a DIFFERENT day. Loose matching would
    # treat the role as surviving; exact role/day identity must still detect it
    # missing and restore it into its own canonical day.
    brief = _structural_brief_fixture()
    report = {
        "blocking_warnings": [
            {"code": "missing_week_session_role", "phase": "SPP", "week_index": 2, "role_key": "conditioning_day"},
        ],
        "review_flags": [],
        "errors": [],
    }
    # Week 2 renders a Tuesday day that name-drops "Alactic conditioning", but the
    # role's own Monday (D-21) slot is absent.
    final_plan_text = (
        _RENDERED_WEEK_ONE
        + "\n## PHASE 2: SPP\n### Week 2\n"
        + "#### Tue (D-20) — Note about Alactic conditioning\n"
        + "- Easy Bike - 20 min\n"
    )

    repaired = repair_stage2_structural_text(
        planning_brief=brief,
        final_plan_text=final_plan_text,
        validator_report=report,
    )

    assert "### Mon (D-21) — Alactic conditioning" in repaired["text"]
    assert "- Air Bike Sprint — 6 x 6 sec / 90 sec easy" in repaired["text"]
    assert [entry["role_key"] for entry in repaired["applied"]] == ["conditioning_day"]
    assert repaired["unresolved"] == []


def test_structural_integrity_hold_blocks_unresolved_missing_role_flags():
    report = {
        "release_decision": "publish_with_flags",
        "is_athlete_releasable": True,
        "is_publishable": True,
        "errors": [],
        "blocking_warnings": [],
        "review_flags": [
            {"code": "missing_week_session_role", "phase": "SPP", "week_index": 4, "role_key": "recovery_day"}
        ],
    }

    held = apply_structural_integrity_hold(report)

    assert held["release_decision"] == "hold"
    assert held["is_athlete_releasable"] is False
    assert held["is_publishable"] is False
    assert held["errors"][-1]["code"] == "structural_integrity_failure"


def test_repair_never_restores_suppressed_or_coach_owned_content():
    brief = _structural_brief_fixture()
    # A role dropped for safety lives in suppressed_roles, never in session_roles.
    brief["weekly_role_map"]["weeks"][0]["suppressed_roles"] = [
        {"role_key": "max_effort_strength", "reason": "injury_restriction"}
    ]
    report = {
        "blocking_warnings": [
            {"code": "phase_section_missing", "phase": "GPP"},
            {"code": "missing_week_session_role", "phase": "GPP", "week_index": 1, "role_key": "hard_sparring_day"},
        ],
        "review_flags": [],
        "errors": [],
    }

    # Week 1 renders its strength day but the coach-owned hard-sparring day is
    # absent; week 2 renders only its header.
    repaired = repair_stage2_structural_text(
        planning_brief=brief,
        final_plan_text=_RENDERED_WEEK_ONE + "\n## PHASE 2: SPP\n### Week 2\n",
        validator_report=report,
    )

    # Suppressed roles are never resurrected.
    assert "max_effort_strength" not in repaired["text"]
    # Coach-owned sparring is never synthesised from a category and is not one of
    # the repair's unresolved diagnostics (the validator still owns its loss).
    assert "declared hard-sparring/contact session" not in repaired["text"]
    assert "Hard sparring" not in repaired["text"]
    assert all(
        entry["role_key"] != "hard_sparring_day" for entry in repaired["unresolved"]
    )
    assert all(
        entry["role_key"] != "hard_sparring_day" for entry in repaired["applied"]
    )


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
        - Band-Resisted Sprint Start - 3 x 5 m
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
