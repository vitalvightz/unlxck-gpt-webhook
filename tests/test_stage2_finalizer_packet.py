from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet


def test_finalizer_packet_passes_open_plan_spec_and_render_mode():
    stage2_payload = {
        "payload_mode": "open_ongoing_payload",
        "render_mode": "open_ongoing_system",
        "athlete_model": {"days_until_fight": None, "fight_date": None, "next_fight_date": None},
        "open_plan_spec": {"plan_type": "open_ongoing_system", "structure": ["Immediate Coach Summary"]},
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    assert packet["render_mode"] == "open_ongoing_system"
    assert packet["selected_plan"]["open_plan_spec"]["plan_type"] == "open_ongoing_system"


def test_open_ongoing_finalizer_packet_does_not_include_phase_briefs():
    stage2_payload = {
        "payload_mode": "open_ongoing_payload",
        "render_mode": "open_ongoing_system",
        "athlete_model": {"days_until_fight": None, "fight_date": None, "next_fight_date": None},
        "open_plan_spec": {"plan_type": "open_ongoing_system", "structure": ["Immediate Coach Summary"]},
        "phase_briefs": {"GPP": {}, "SPP": {}, "TAPER": {}},
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload)
    assert packet["render_mode"] == "open_ongoing_system"
    assert "phase_briefs" not in packet


def test_finalizer_packet_omits_redundant_calendar_authority_and_days_out_payload():
    # calendar_authority duplicated weekly_role_map.calendar_days (the named
    # authority) and days_out_payload was an ~85% subset of late_fight_plan_spec;
    # neither is referenced by any render instruction, so both are dropped to trim
    # prompt bytes. weekly_role_map.calendar_days and late_fight_plan_spec remain.
    stage2_payload = {
        "athlete_model": {"days_until_fight": 10},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "session_roles": [
                        {"session_index": 1, "role_key": "primary_strength_day", "scheduled_day_hint": "Monday"}
                    ],
                    "calendar_days": [{"weekday": "Monday", "countdown_label": "D-10"}],
                }
            ]
        },
        "late_fight_plan_spec": {"payload_mode": "pre_fight_compressed_payload", "countdown_mode_sequence": []},
        "days_out_payload": {"payload_mode": "pre_fight_compressed_payload"},
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    selected_plan = packet["selected_plan"]

    assert "calendar_authority" not in selected_plan
    assert "days_out_payload" not in selected_plan
    # Canonical sources the instructions actually name are still present.
    assert selected_plan["weekly_role_map"]["weeks"][0]["calendar_days"] == [
        {"weekday": "Monday", "countdown_label": "D-10"}
    ]
    assert selected_plan["late_fight_plan_spec"]["payload_mode"] == "pre_fight_compressed_payload"


def test_finalizer_packet_compact_role_omits_internal_selection_rationale():
    # selection_rule / placement_rule / day_assignment_reason are internal Stage 1
    # selection notes no render instruction references; they are stripped from the
    # LLM-facing role while the authoritative day/role signals are preserved.
    stage2_payload = {
        "athlete_model": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "session_index": 1,
                            "role_key": "primary_strength_day",
                            "category": "strength",
                            "scheduled_day_hint": "Wednesday",
                            "selection_rule": "Use the highest-priority compliant strength slot first.",
                            "placement_rule": "Place after the weekly recovery day.",
                            "day_assignment_reason": "Neural work belongs mid-week.",
                        }
                    ],
                }
            ]
        },
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]

    assert "selection_rule" not in role
    assert "placement_rule" not in role
    assert "day_assignment_reason" not in role
    # Authoritative placement/identity signals survive.
    assert role["role_key"] == "primary_strength_day"
    assert role["scheduled_day_hint"] == "Wednesday"
    assert role["category"] == "strength"


def test_finalizer_packet_strips_internal_late_fight_scaffolding():
    # visible_session_sequence duplicates the top-level session_sequence, and
    # allocator / role_budget / permission_policy are Stage 1 allocation internals
    # no instruction references. They are dropped from the LLM-facing spec, but the
    # referenced cap (max_active_roles) and countdown_mode_sequence are preserved,
    # and the source spec is not mutated.
    source_spec = {
        "payload_mode": "pre_fight_compressed_payload",
        "max_active_roles": 3,
        "countdown_mode_sequence": [{"stage_key": "d13_to_d8"}],
        "visible_session_sequence": [{"role_key": "x"}],
        "allocator": {"internal": True},
        "role_budget": {"selected_active_roles": 2},
        "permission_policy": {"allow": []},
    }
    stage2_payload = {"athlete_model": {}, "late_fight_plan_spec": source_spec}
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    spec = packet["selected_plan"]["late_fight_plan_spec"]

    for internal_key in ("visible_session_sequence", "allocator", "role_budget", "permission_policy"):
        assert internal_key not in spec
    assert spec["max_active_roles"] == 3
    assert spec["countdown_mode_sequence"] == [{"stage_key": "d13_to_d8"}]
    # Source object is untouched (non-mutating compaction).
    assert "allocator" in source_spec and "visible_session_sequence" in source_spec


def test_finalizer_packet_preserves_injury_context_fields_in_athlete_model():
    stage2_payload = {
        "athlete_model": {
            "has_active_injury": True,
            "injuries_raw_text": "shoulder pain after grappling",
            "parsed_injuries": [
                {
                    "injury_type": "pain",
                    "injury_type_source": "parser",
                    "guided_source_injury_subtypes": ["pain", "instability", "tightness"],
                }
            ],
            "guided_injury": {"area": "left shoulder", "injury_type": "pain"},
            "injury_restrictions": [{"restriction": "avoid overhead work", "region": "shoulder"}],
        }
    }

    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    athlete_model = packet["athlete_model"]

    assert athlete_model["has_active_injury"] is True
    assert athlete_model["injuries_raw_text"] == "shoulder pain after grappling"
    assert athlete_model["parsed_injuries"][0]["injury_type"] == "pain"
    assert athlete_model["parsed_injuries"][0]["guided_source_injury_subtypes"] == ["pain", "instability", "tightness"]
    assert athlete_model["guided_injury"] == {"area": "left shoulder", "injury_type": "pain"}
    assert athlete_model["injury_restrictions"] == [{"restriction": "avoid overhead work", "region": "shoulder"}]


def test_finalizer_packet_hard_rules_include_subtype_context_guardrail():
    packet = build_stage2_finalizer_packet(stage2_payload={"athlete_model": {}}, planning_brief={})
    assert any(
        "Use parsed_injuries and guided_source_injury_subtypes as injury context only." in rule
        for rule in packet["hard_rules"]
    )


def test_finalizer_packet_prefers_late_fight_visible_session_sequence():
    stage2_payload = {
        "athlete_model": {},
        "late_fight_session_sequence": [{"role_key": "alactic_sharpness_day", "scheduled_day_hint": "tuesday"}],
        "late_fight_plan_spec": {
            "visible_session_sequence": [
                {"role_key": "hard_sparring_day", "scheduled_day_hint": "monday"},
                {"role_key": "neural_primer_day", "scheduled_day_hint": "tuesday"},
            ],
            "session_sequence": [{"role_key": "fight_week_freshness_day", "scheduled_day_hint": "wednesday"}],
        },
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    assert [entry["role_key"] for entry in packet["selected_plan"]["session_sequence"]] == [
        "hard_sparring_day",
        "neural_primer_day",
    ]


def test_finalizer_packet_preserves_week_hard_sparring_plan_truth():
    stage2_payload = {
        "athlete_model": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "declared_hard_sparring_days": ["Monday", "Wednesday"],
                    "hard_sparring_plan": [
                        {
                            "day": "Monday",
                            "status": "hard_as_planned",
                            "effective_load": "hard",
                            "hard_day_class": "primary_hard",
                            "reason_codes": [],
                            "reason": "",
                        },
                        {
                            "day": "Wednesday",
                            "status": "deload_suggested",
                            "effective_load": "reduced",
                            "hard_day_class": "managed_hard",
                            "reason_codes": ["fight_week_taper", "final_week_sparring_cap"],
                            "reason": "Final taper week cap.",
                            "coach_note": "Keep the rounds controlled.",
                        },
                    ],
                    "effective_hard_sparring_days": ["Monday"],
                    "final_week_sparring_cap": {
                        "active": True,
                        "capped_declared_hard_sparring_days": ["Wednesday"],
                    },
                }
            ]
        },
    }

    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    week = packet["selected_plan"]["weekly_role_map"]["weeks"][0]

    assert week["hard_sparring_plan"] == stage2_payload["weekly_role_map"]["weeks"][0]["hard_sparring_plan"]
    assert week["effective_hard_sparring_days"] == ["Monday"]
    assert week["final_week_sparring_cap"]["active"] is True


def test_finalizer_packet_preserves_hard_sparring_role_dose_fields():
    stage2_payload = {
        "athlete_model": {},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "session_index": 1,
                            "category": "sparring",
                            "role_key": "hard_sparring_day",
                            "scheduled_day_hint": "Wednesday",
                            "hard_sparring_status": "deload_suggested",
                            "hard_sparring_class": "managed_hard",
                            "hard_sparring_reason_codes": ["high_fatigue"],
                            "hard_sparring_reason": "high_fatigue",
                            "coach_note_flags": ["deload hard sparring"],
                            "coach_note": "Keep the rounds controlled.",
                            "locked_day": "Wednesday",
                        }
                    ],
                    "suppressed_roles": [
                        {
                            "category": "sparring",
                            "role_key": "hard_sparring_day",
                            "scheduled_day_hint": "Friday",
                            "replacement_role_key": "no_hard_sparring_day",
                            "downgraded_from_role_key": "hard_sparring_day",
                            "hard_sparring_status": "convert_to_technical_suggested",
                            "hard_sparring_reason_codes": ["d17_hard_sparring_ban"],
                            "hard_sparring_reason": "D-17 ban.",
                            "locked_day": "Friday",
                        }
                    ],
                }
            ]
        },
    }

    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    week = packet["selected_plan"]["weekly_role_map"]["weeks"][0]
    role = week["session_roles"][0]
    suppressed = week["suppressed_roles"][0]

    assert role["hard_sparring_status"] == "deload_suggested"
    assert role["hard_sparring_class"] == "managed_hard"
    assert role["hard_sparring_reason_codes"] == ["high_fatigue"]
    assert role["hard_sparring_reason"] == "high_fatigue"
    assert role["coach_note_flags"] == ["deload hard sparring"]
    assert role["locked_day"] == "Wednesday"
    assert suppressed["replacement_role_key"] == "no_hard_sparring_day"
    assert suppressed["downgraded_from_role_key"] == "hard_sparring_day"
    assert suppressed["hard_sparring_status"] == "convert_to_technical_suggested"
    assert suppressed["hard_sparring_reason_codes"] == ["d17_hard_sparring_ban"]


def test_finalizer_packet_explains_reduced_count_for_bad_boxing_profile():
    stage2_payload = {
        "athlete_model": {
            "sport": "boxing",
            "status": "amateur",
            "training_frequency": 4,
            "training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
            "hard_sparring_days": ["Tuesday", "Saturday"],
            "technical_skill_days": ["Monday"],
            "fatigue": "moderate",
            "weight_cut_risk": True,
            "weight_cut_pct": 3.4,
            "readiness_flags": ["moderate_fatigue", "active_weight_cut", "injury_management"],
            "has_active_injury": True,
            "injuries_raw_text": "mild left shoulder irritation",
            "parsed_injuries": [{"area": "left shoulder", "injury_type": "irritation"}],
            "key_goals": ["power", "conditioning"],
            "weaknesses": ["gas_tank"],
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 3,
                    "phase": "TAPER",
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "declared_hard_sparring_days": ["Tuesday", "Saturday"],
                    "session_roles": [
                        {
                            "session_index": 1,
                            "category": "strength",
                            "role_key": "neural_primer_day",
                            "scheduled_day_hint": "Monday",
                        },
                        {
                            "session_index": 2,
                            "category": "sparring",
                            "role_key": "hard_sparring_day",
                            "scheduled_day_hint": "Tuesday",
                            "coach_owned": True,
                        },
                    ],
                    "suppressed_roles": [
                        {
                            "category": "conditioning",
                            "role_key": "light_fight_pace_touch_day",
                            "compression_reason_codes": ["active_weight_cut", "injury_management"],
                        },
                        {
                            "category": "sparring",
                            "role_key": "hard_sparring_day",
                            "scheduled_day_hint": "Saturday",
                            "hard_sparring_reason_codes": ["d17_hard_sparring_ban"],
                        },
                    ],
                    "hard_sparring_plan": [
                        {"day": "Tuesday", "status": "hard_as_planned", "reason_codes": []},
                        {
                            "day": "Saturday",
                            "status": "suppressed",
                            "reason_codes": ["d17_hard_sparring_ban"],
                        },
                    ],
                    "intentional_compression": {
                        "active": True,
                        "reason_codes": ["active_weight_cut", "injury_management"],
                        "summary": "Compression protects freshness around the cut and shoulder irritation.",
                    },
                }
            ]
        },
    }

    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    summary = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_count_summary"]

    assert summary["planned_weekly_count"] == 4
    assert summary["rendered_total_count"] == 2
    assert summary["rendered_app_owned_count"] == 1
    assert summary["coach_owned_count"] == 1
    assert summary["reduced_from_planned"] is True
    joined_reasons = " ".join(summary["reduction_reasons"]).lower()
    assert "taper" in joined_reasons
    assert "target-weight" in joined_reasons
    assert "d-17" in joined_reasons
    assert "injury" in joined_reasons
    assert "hard sparring / contact" in joined_reasons
    assert "intentional compression" in joined_reasons
