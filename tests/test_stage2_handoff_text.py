from fightcamp.stage2_payload import build_stage2_handoff_text


def test_build_stage2_handoff_text_uses_finalizer_packet_as_single_structured_context():
    planning_brief = {
        "athlete_snapshot": {"sport": "boxing", "status": "amateur"},
        "restrictions": [{"restriction": "heavy_overhead_pressing"}],
        "candidate_pools": {"SPP": {"strength_slots": [{"role": "primary_strength"}]}},
        "omission_ledger": {"SPP": {"removed": ["push press"]}},
        "decision_rules": {
            "selection_rules": ["Prefer strong compliant same-role options first."],
            "render_guards": {
                "has_active_injury": False,
                "suppress_rehab_headings": True,
                "suppress_phase_toolbox_sections": False,
                "render_mode": "camp_plan",
            },
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "role_key": "primary_strength_day",
                            "category": "strength",
                            "scheduled_day_hint": "tuesday",
                        }
                    ],
                }
            ]
        },
    }

    handoff = build_stage2_handoff_text(
        stage2_payload={
            "athlete_model": {"sport": "boxing"},
            "restrictions": [{"restriction": "heavy_overhead_pressing"}],
            "phase_briefs": {"SPP": {"objective": "fight-specific power"}},
            "candidate_pools": {"SPP": {"strength_slots": [{"role": "primary_strength"}]}},
            "omission_ledger": {"SPP": {"removed": ["push press"]}},
            "rewrite_guidance": {
                "selection_rules": ["Prefer strong compliant same-role options first."],
                "render_guards": {
                    "has_active_injury": False,
                    "suppress_rehab_headings": True,
                    "suppress_phase_toolbox_sections": False,
                    "render_mode": "camp_plan",
                },
            },
        },
        plan_text="Week 1\n- Landmine Press - 4x5",
        coach_notes="Keep this coach-facing note short.",
        planning_brief=planning_brief,
    )

    packet_block = handoff.split("FINALIZER PACKET\n", 1)[1].split("\n\n---\n\n", 1)[0]
    packet_body = packet_block.removeprefix("```json\n").removesuffix("\n```")

    athlete_profile_block = handoff.split("ATHLETE PROFILE\n", 1)[1].split("\n\n---\n\n", 1)[0]
    athlete_profile_body = athlete_profile_block.removeprefix("```json\n").removesuffix("\n```")

    assert "FINALIZER PACKET" in handoff
    assert "ATHLETE PROFILE" in handoff
    assert "UNLXCK FINAL RENDER CONTRACT" in handoff
    assert "D-5 (Tuesday) — Fight-speed primer" in handoff
    assert "GPP — Week 1 (D-X to D-X) — Objective" in handoff
    assert "SPP — Week 2 (D-X to D-X) — Objective" in handoff
    assert "TAPER — Week 3 (D-X to D-X) — Objective" in handoff
    assert "Return only the athlete-facing final plan." in handoff
    assert '"packet_type":"stage2_finalizer_packet"' in handoff
    assert '"render_mode":"camp_plan"' in handoff
    assert '"restrictions":[{"restriction":"heavy_overhead_pressing"}]' in handoff

    assert "COACH NOTES\nKeep this coach-facing note short." in handoff
    assert "STAGE 1 DRAFT PLAN\nWeek 1\n- Landmine Press - 4x5" in handoff

    assert packet_block.startswith("```json\n")
    assert packet_block.endswith("\n```")
    assert packet_body.startswith('{"packet_type":"stage2_finalizer_packet"')

    assert athlete_profile_block.startswith("```json\n")
    assert athlete_profile_block.endswith("\n```")
    assert athlete_profile_body == '{"sport":"boxing","status":"amateur"}'

    # Compact JSON formatting only.
    assert '\n  "' not in packet_body

    # Old bloated handoff must be gone.
    assert "PLANNING BRIEF" not in handoff
    assert '"candidate_pools"' not in handoff
    assert "RESTRICTIONS\n[" not in handoff
    assert "PHASE BRIEFS" not in handoff
    assert "CANDIDATE POOLS\n{" not in handoff
    assert "OMISSION LEDGER\n{" not in handoff
    assert "REWRITE GUIDANCE" not in handoff


def test_build_stage2_handoff_text_late_fight_excludes_candidate_pools_and_phase_briefs():
    handoff = build_stage2_handoff_text(
        stage2_payload={
            "payload_mode": "bridge_compression_payload",
            "athlete_model": {
                "sport": "boxing",
                "days_until_fight": 17,
                "fight_date": "2026-05-13",
                "has_active_injury": False,
            },
            "candidate_pools": {
                "SPP": {"toolbox": ["Should not be exposed"]},
                "GPP": {"toolbox": ["Should not be exposed"]},
                "TAPER": {"toolbox": ["Should not be exposed"]},
            },
            "phase_briefs": {
                "SPP": {"objective": "Should not be exposed in late-fight handoff"}
            },
            "rewrite_guidance": {
                "render_guards": {
                    "has_active_injury": False,
                    "suppress_rehab_headings": True,
                    "suppress_phase_toolbox_sections": True,
                    "render_mode": "late_fight_countdown_only",
                }
            },
        },
        plan_text="D-0\n- Fight day protocol",
        planning_brief={
            "athlete_snapshot": {
                "sport": "boxing",
                "days_until_fight": 17,
                "fight_date": "2026-05-13",
                "has_active_injury": False,
            },
            "decision_rules": {
                "render_guards": {
                    "has_active_injury": False,
                    "suppress_rehab_headings": True,
                    "suppress_phase_toolbox_sections": True,
                    "render_mode": "late_fight_countdown_only",
                }
            },
            "weekly_role_map": {
                "weeks": [
                    {
                        "week_index": 1,
                        "phase": "TAPER",
                        "session_roles": [
                            {
                                "role_key": "fight_day_protocol",
                                "scheduled_day_hint": "wednesday",
                                "display_text": "Fight day protocol — follow coach warm-up and fight protocol; no additional app S&C.",
                            }
                        ],
                    }
                ]
            },
        },
    )

    assert "FINALIZER PACKET" in handoff
    assert '"render_mode":"late_fight_countdown_only"' in handoff
    assert '"packet_type":"stage2_finalizer_packet"' in handoff

    # The finalizer must not see internal menus.
    assert '"candidate_pools"' not in handoff
    assert '"phase_briefs"' not in handoff
    assert "Should not be exposed" not in handoff
    assert "SPP toolbox" in handoff  # allowed only as forbidden-output label
    assert "key drills to keep in your toolbox" in handoff  # allowed only as forbidden-output label

    # No old full planning brief section.
    assert "PLANNING BRIEF" not in handoff


def test_stage2_handoff_gives_finalizer_exercise_selection_authority():
    handoff = build_stage2_handoff_text(
        stage2_payload={"athlete_model": {"sport": "boxing"}},
        plan_text="# Stage 1 Draft\n- Strength",
        planning_brief={"athlete_snapshot": {"sport": "boxing"}},
    )

    assert "Stage 1 selected exercises and draft text — candidate material only" in handoff
    assert "Treat Stage 1 selected exercises as candidates, not truth" in handoff
    assert "make the final exercise and prescription choices yourself" in handoff
    assert "Never let Stage 1 draft wording decide final exercise rendering" in handoff
    assert "Every app-owned session must include exact drill/exercise" in handoff
    assert "sets/reps/duration, rest, intensity or RPE, purpose, why today" in handoff
    assert "session_count_summary.reduced_from_planned" in handoff
    assert "Lead notes come first" in handoff
    assert "Taper means reduce volume, not remove sharpness" in handoff
    assert "Use selected_plan inside FINALIZER PACKET as the session source of truth" not in handoff


def test_build_stage2_handoff_text_carries_surgical_voice_rules():
    handoff = build_stage2_handoff_text(
        stage2_payload={},
        plan_text="Week 1\n- Landmine Press - 4x5",
        planning_brief={"athlete_snapshot": {"sport": "boxing"}},
    )

    assert "decisive" in handoff.lower() or "gym-realistic" in handoff.lower(), (
        "Handoff should convey a decisive, gym-realistic coach voice"
    )
    assert "make the call" in handoff or "corrective" in handoff.lower(), (
        "Handoff should instruct making a clear call on corrections"
    )
    assert "practical options" in handoff or "two options" in handoff.lower(), (
        "Handoff should limit optionality for the model"
    )
    assert "focus on" in handoff or "ensure" in handoff or "motivation" in handoff.lower(), (
        "Handoff should contain anti-filler coaching voice directives"
    )
    assert "fatigue" in handoff.lower() and "optionality" in handoff.lower(), (
        "Handoff should address fatigue → reduce optionality"
    )
    assert "injury" in handoff.lower() and ("constraints" in handoff.lower() or "stop rules" in handoff.lower()), (
        "Handoff should address injury → lead with constraints"
    )

def test_build_stage2_handoff_text_preserves_countdown_calendar_fields_in_weekly_role_map():
    handoff = build_stage2_handoff_text(
        stage2_payload={"athlete_model": {"sport": "boxing"}},
        plan_text="Week 1",
        planning_brief={
            "athlete_snapshot": {"sport": "boxing"},
            "weekly_role_map": {
                "weeks": [
                    {
                        "week_index": 1,
                        "phase": "SPP",
                        "projected_days_until_fight_start": 36,
                        "projected_days_until_fight_end": 30,
                        "countdown_range": [36, 30],
                        "calendar_days": [{"weekday": "Tue", "d_day": 36}],
                        "declared_training_days": ["Tue"],
                        "declared_hard_sparring_days": ["Wed"],
                        "declared_support_work_days": ["Thu"],
                        "effective_hard_sparring_days": ["Wed"],
                        "final_week_sparring_cap": {"active": False},
                        "coach_note_flags": ["keep_easy"],
                        "intentional_compression": {"active": False},
                        "intentionally_unused_days": ["Sun"],
                        "session_roles": [],
                    }
                ]
            },
        },
    )

    assert '"countdown_range":[36,30]' in handoff
    assert '"calendar_days":[{"weekday":"Tue","d_day":36}]' in handoff
    assert '"projected_days_until_fight_start":36' in handoff


def test_build_stage2_handoff_text_includes_priority_focus_guidance_without_raw_reason_codes():
    handoff = build_stage2_handoff_text(
        stage2_payload={"athlete_model": {"sport": "boxing"}},
        plan_text="Week 1",
        planning_brief={
            "athlete_snapshot": {"sport": "boxing"},
            "priority_focus": {
                "primary_goal": "power",
                "primary_weak_area": "power",
                "secondary_goals": ["conditioning"],
                "secondary_weak_areas": ["gas_tank"],
                "goal_weakness_collisions": ["power"],
                "collision_detail": "Power drops when tired",
                "collision_details": [
                    {"tag": "power", "label": "Power", "detail": "Power drops when tired"},
                    {"tag": "conditioning", "label": "Conditioning", "detail": "Late-round fatigue"},
                ],
                "derived_clarification_tags": ["explosive", "rate_of_force"],
            },
        },
    )

    # The priority-hierarchy doctrine is carried by the finalizer packet's
    # hard_rules (canonical, always sent) rather than a duplicate prose section.
    lowered = handoff.lower()
    assert "preserve the priority hierarchy from priority_focus" in lowered
    assert "primary goal and primary weak area shape emphasis" in lowered
    assert "preserve each clarification" in lowered
    assert "derived_clarification_tags" in handoff
    # The collision detail value still reaches the model via the priority_focus
    # data block, and multi-entry collision_details are preserved there.
    assert "Power drops when tired" in handoff
    assert '"collision_detail":"Power drops when tired"' in handoff
    # Raw internal reason-code labels must never surface in the handoff.
    assert "priority_primary_goal_match" not in handoff
    assert "priority_collision_goal_weakness" not in handoff
    assert "priority_clarification_tag_match" not in handoff


def test_build_stage2_handoff_text_keeps_structured_collision_details_in_packet():
    handoff = build_stage2_handoff_text(
        stage2_payload={"athlete_model": {"sport": "boxing"}},
        plan_text="Week 1",
        planning_brief={
            "athlete_snapshot": {"sport": "boxing"},
            "priority_focus": {
                "primary_goal": "power",
                "primary_weak_area": "power",
                "goal_weakness_collisions": ["power", "conditioning"],
                "collision_detail": "Power drops when tired",
                "collision_details": [
                    {"tag": "power", "label": "Power", "detail": "Power drops when tired"},
                    {"tag": "conditioning", "label": "Conditioning", "detail": "Late-round fatigue"},
                ],
                "derived_clarification_tags": ["explosive", "rate_of_force"],
            },
        },
    )

    assert '"collision_details":[{"tag":"power","label":"Power","detail":"Power drops when tired"},{"tag":"conditioning","label":"Conditioning","detail":"Late-round fatigue"}]' in handoff
    assert '"derived_clarification_tags":["explosive","rate_of_force"]' in handoff
