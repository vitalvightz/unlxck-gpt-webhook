from fightcamp.stage2_payload import (
    build_planning_brief,
    build_stage2_payload,
)
from fightcamp.training_context import TrainingContext


def _build_brief(athlete_model: dict, *, restrictions: list[dict] | None = None, phase: str = "SPP") -> dict:
    phase_briefs = {
        phase: {
            "objective": "increase fight-specific repeatability and power transfer",
            "emphasize": ["sport speed", "fight-pace transfer"],
            "deprioritize": ["non-specific volume"],
            "risk_flags": ["manage accumulated fatigue"],
            "selection_guardrails": {
                "must_keep_if_present": ["alactic", "rehab"],
                "conditioning_drop_order_if_thin": ["glycolytic"],
            },
        }
    }
    candidate_pools = {
        phase: {
            "strength_slots": [{"role": "primary_strength"}],
            "conditioning_slots": [{"role": "alactic"}, {"role": "glycolytic"}],
            "rehab_slots": [],
        }
    }
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=restrictions or [],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )



def _build_taper_payload_and_brief() -> tuple[dict, dict]:
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=5,
        days_available=5,
        training_days=["Mon", "Tue", "Wed", "Fri", "Sat"],
        injuries=["shoulder strain"],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=["boxing"],
        equipment=["air_bike", "bodyweight"],
        weight_cut_risk=True,
        weight_cut_pct=5.5,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["conditioning", "power"],
        training_preference="balanced",
        mental_block=[],
        age=27,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 0, "SPP": 0, "TAPER": 2, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=10,
    )

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="5-1",
        rounds_format="3x3",
        camp_len=6,
        short_notice=True,
        restrictions=[],
        phase_weeks={"GPP": 0, "SPP": 0, "TAPER": 2, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={
            "GPP": None,
            "SPP": None,
            "TAPER": {
                "exercises": [
                    {"name": "Trap Bar Jump", "movement": "hinge", "tags": ["explosive"], "method": "3x3"},
                    {"name": "Dead Bug", "movement": "core", "tags": ["core"], "method": "2x8"},
                ],
                "why_log": [
                    {"name": "Trap Bar Jump", "explanation": "balanced selection", "reasons": {}},
                    {"name": "Dead Bug", "explanation": "balanced selection", "reasons": {}},
                ],
                "candidate_reservoir": {"hinge": [], "core": []},
            },
        },
        conditioning_blocks={
            "TAPER": {
                "grouped_drills": {
                    "alactic": [
                        {"name": "Short Sprint", "tags": ["alactic"], "timing": "6 sec", "rest": "90 sec", "load": "fast"}
                    ],
                    "glycolytic": [
                        {"name": "Hard Shuttle", "tags": ["glycolytic"], "timing": "20 sec", "rest": "60 sec", "load": "hard"}
                    ],
                },
                "why_log": [
                    {"name": "Short Sprint", "system": "alactic", "explanation": "balanced selection", "reasons": {}},
                    {"name": "Hard Shuttle", "system": "glycolytic", "explanation": "balanced selection", "reasons": {}},
                ],
                "missing_systems": [],
                "candidate_reservoir": {"alactic": [], "glycolytic": []},
            }
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": "- Shoulder (Strain):\n  - Band External Rotation - 2x15"},
    )
    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )
    return payload, brief



def test_build_planning_brief_exposes_limiter_led_weekly_stress_map():
    brief = _build_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 6,
            "days_until_fight": 24,
            "short_notice": False,
            "fatigue": "moderate",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["skill_refinement"],
            "weaknesses": ["coordination_proprioception"],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["moderate_fatigue"],
        }
    )

    assert brief["limiter_profile"]["key"] == "coordination"
    assert brief["sport_load_profile"]["key"] == "boxing"
    assert [entry["driver"] for entry in brief["decision_hierarchy"][:4]] == [
        "phase_survival_rules",
        "safety_and_readiness",
        "sport_load_collision_rules",
        "main_limiter",
    ]
    assert (
        brief["limiter_profile"]["organising_principle"]
        == "timing, rhythm, body control, and transfer under fatigue"
    )

    spp_stress = brief["weekly_stress_map"]["SPP"]
    assert spp_stress["organising_limiter"] == "coordination"
    assert spp_stress["conditioning_sequence"] == ["alactic", "aerobic", "glycolytic"]
    assert "limiter quality" in spp_stress["protect_first"]
    assert "hard sparring" in spp_stress["sparring_collision_rule"]
    assert "pad or bag rounds" in spp_stress["replace_missing_live_load"]



def test_phase_survival_rules_keep_taper_slot_priorities_above_sport_load_pressure():
    payload, brief = _build_taper_payload_and_brief()

    taper_slots = payload["candidate_pools"]["TAPER"]["conditioning_slots"]

    assert brief["decision_hierarchy"][0]["driver"] == "phase_survival_rules"
    assert brief["sport_load_profile"]["key"] == "boxing"
    assert taper_slots[0]["role"] == "alactic"
    assert taper_slots[0]["priority"] == "critical"
    assert taper_slots[1]["role"] == "glycolytic"
    assert taper_slots[1]["priority"] == "low"



def test_safety_and_readiness_override_limiter_ambition_in_stress_map():
    brief = _build_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 9,
            "short_notice": True,
            "fatigue": "high",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power"],
            "weaknesses": ["coordination_proprioception"],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": True,
            "weight_cut_pct": 5.0,
            "readiness_flags": ["high_fatigue", "fight_week", "active_weight_cut"],
        },
        phase="TAPER",
    )

    limiter_profile = brief["limiter_profile"]
    taper_stress = brief["weekly_stress_map"]["TAPER"]

    assert limiter_profile["key"] == "coordination"
    assert limiter_profile["protect_first"] == "timing quality, rhythm, and body control before extra fatigue work"
    assert taper_stress["protect_first"].startswith("Because fatigue is high")
    assert "Because this is short notice" in taper_stress["cut_first_when_collisions_rise"]



def test_sport_load_collision_rules_beat_goal_push_when_collisions_rise():
    brief = _build_brief(
        {
            "sport": "mma",
            "status": "amateur",
            "rounds_format": "3x5",
            "camp_length_weeks": 8,
            "days_until_fight": 42,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["wrestling"],
            "tactical_styles": ["pressure"],
            "key_goals": ["conditioning", "power"],
            "weaknesses": ["conditioning"],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        }
    )

    push_rules = brief["global_priorities"]["push"]
    spp_stress = brief["weekly_stress_map"]["SPP"]

    assert any("Prioritize conditioning slots" in rule for rule in push_rules)
    assert any("Preserve explosive and alactic work" in rule for rule in push_rules)
    assert brief["sport_load_profile"]["key"] == "wrestling"
    assert brief["decision_hierarchy"][2]["driver"] == "sport_load_collision_rules"
    assert "When sport load spikes, cut optional strength accessories and non-essential conditioning density first." in spp_stress["cut_first_when_collisions_rise"]
    assert "short positional goes or takedown chains before extra lifting" in spp_stress["replace_missing_live_load"]



def test_build_planning_brief_uses_tissue_state_for_stiffness_or_injury_driven_cases():
    brief = _build_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 8,
            "days_until_fight": 40,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "conservative",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["durability"],
            "weaknesses": ["stiffness"],
            "equipment": ["bands", "dumbbell"],
            "injuries": ["shoulder strain"],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["injury_management"],
        },
        restrictions=[{"restriction": "heavy_overhead_pressing"}],
    )

    brief_profile = brief["limiter_profile"]
    spp_stress = brief["weekly_stress_map"]["SPP"]

    assert brief_profile["key"] == "tissue_state"
    assert brief["sport_load_profile"]["key"] == "boxing"
    assert "conservative loading" in brief_profile["organising_principle"]
    assert "ballistic work" in brief_profile["cut_first"]
    assert spp_stress["conditioning_sequence"] == ["aerobic", "alactic", "glycolytic"]
    assert "recovery plus rehab only" in spp_stress["sport_load_interaction"]



def test_build_planning_brief_uses_boxing_quality_profile_when_boxing_is_the_limiter():
    brief = _build_brief(
        {
            "sport": "boxing",
            "status": "pro",
            "rounds_format": "10x3",
            "camp_length_weeks": 8,
            "days_until_fight": 35,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["out_boxer"],
            "key_goals": ["skill_refinement", "striking"],
            "weaknesses": ["boxing"],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        }
    )

    brief_profile = brief["limiter_profile"]
    spp_stress = brief["weekly_stress_map"]["SPP"]

    assert brief_profile["key"] == "boxing_quality_under_load"
    assert brief["sport_load_profile"]["key"] == "boxing"
    assert "S&C staying secondary to sport output" in brief_profile["organising_principle"]
    assert "boxing quality and sparring freshness" in brief_profile["protect_first"]
    assert "Hard sparring owns the main combat stress slot" in spp_stress["sparring_collision_rule"]



def test_build_planning_brief_uses_sharpness_profile_for_short_notice_fatigue_cases():
    brief = _build_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 10,
            "short_notice": True,
            "fatigue": "high",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": [],
            "weaknesses": [],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["high_fatigue", "fight_week"],
        },
        phase="TAPER",
    )

    brief_profile = brief["limiter_profile"]
    taper_stress = brief["weekly_stress_map"]["TAPER"]

    assert brief_profile["key"] == "sharpness_under_fatigue"
    assert brief["sport_load_profile"]["key"] == "boxing"
    assert "quality preservation" in brief_profile["organising_principle"]
    assert "Because fatigue is high" in taper_stress["protect_first"]
    assert "Because this is short notice" in taper_stress["cut_first_when_collisions_rise"]



def test_build_planning_brief_uses_muay_thai_sport_load_profile():
    brief = _build_brief(
        {
            "sport": "muay_thai",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 6,
            "days_until_fight": 28,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "technical",
            "technical_styles": ["muay thai"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning"],
            "weaknesses": [],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        }
    )

    sport_load = brief["sport_load_profile"]
    spp_stress = brief["weekly_stress_map"]["SPP"]

    assert sport_load["key"] == "kickboxing_muay_thai"
    assert "clinch volume" in sport_load["highest_collision_load"]
    assert any("clinch" in rule.lower() for rule in sport_load["collision_rules"])
    assert "pad or clinch rounds" in spp_stress["replace_missing_live_load"]



def test_build_planning_brief_uses_wrestling_sport_load_profile_from_style_identity():
    brief = _build_brief(
        {
            "sport": "mma",
            "status": "amateur",
            "rounds_format": "3x5",
            "camp_length_weeks": 8,
            "days_until_fight": 42,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["wrestling"],
            "tactical_styles": ["pressure"],
            "key_goals": ["power"],
            "weaknesses": [],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        }
    )

    sport_load = brief["sport_load_profile"]
    spp_stress = brief["weekly_stress_map"]["SPP"]

    assert sport_load["key"] == "wrestling"
    assert "live goes" in sport_load["highest_collision_load"]
    assert any("live goes" in rule.lower() for rule in sport_load["collision_rules"])
    assert "takedown chains" in spp_stress["replace_missing_live_load"]



def test_build_planning_brief_falls_back_to_general_fight_readiness():
    brief = _build_brief(
        {
            "sport": "mma",
            "status": "amateur",
            "rounds_format": "3x5",
            "camp_length_weeks": 8,
            "days_until_fight": 56,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["mma"],
            "tactical_styles": ["generalist"],
            "key_goals": [],
            "weaknesses": [],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        },
        phase="GPP",
    )

    brief_profile = brief["limiter_profile"]
    sport_load = brief["sport_load_profile"]
    gpp_stress = brief["weekly_stress_map"]["GPP"]

    assert brief_profile["key"] == "general_fight_readiness"
    assert sport_load["key"] == "mma"
    assert brief["decision_hierarchy"][0]["driver"] == "phase_survival_rules"
    assert brief["decision_hierarchy"][2]["driver"] == "sport_load_collision_rules"
    assert "balanced development" in brief_profile["organising_principle"]
    assert gpp_stress["conditioning_sequence"] == ["aerobic", "glycolytic", "alactic"]
    assert "phase-critical work before accessories" in gpp_stress["protect_first"]
    assert "live wrestling or wall-work rounds" in gpp_stress["highest_collision_sport_load"]


def _build_progression_brief(athlete_model: dict, phase_briefs: dict[str, dict]) -> dict:
    candidate_pools = {
        phase: {
            "strength_slots": [{"role": "primary_strength"}],
            "conditioning_slots": [{"role": "aerobic"}, {"role": "glycolytic"}, {"role": "alactic"}],
            "rehab_slots": [],
        }
        for phase in phase_briefs
    }
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )



def test_build_planning_brief_adds_adaptive_week_by_week_progression():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 5,
            "days_until_fight": 33,
            "short_notice": False,
            "fatigue": "moderate",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning", "power"],
            "weaknesses": ["conditioning"],
            "equipment": ["air_bike"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["moderate_fatigue"],
        },
        {
            "GPP": {
                "objective": "build aerobic base and general force capacity",
                "emphasize": ["aerobic repeatability", "general force"],
                "deprioritize": ["fight-week intensity"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["aerobic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["alactic", "glycolytic"],
                },
                "weeks": 2,
                "days": 13,
            },
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["glycolytic", "alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 2,
                "days": 15,
            },
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 2},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 5,
            },
        },
    )

    progression = brief["week_by_week_progression"]
    weeks = progression["weeks"]

    assert progression["model"] == "adaptive_phase_overlay.v1"
    assert progression["active_week_count"] == 5
    assert [week["phase"] for week in weeks] == ["GPP", "GPP", "SPP", "SPP", "TAPER"]
    assert [week["stage_key"] for week in weeks] == [
        "foundation_restore",
        "build_repeatability",
        "specific_density_build",
        "peak_specificity",
        "fight_week_survival_rhythm",
    ]
    assert sum(week["span_days"] for week in weeks) == 33



def test_build_planning_brief_compresses_progression_for_short_notice_camp():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 10,
            "short_notice": True,
            "fatigue": "high",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power"],
            "weaknesses": ["coordination_proprioception"],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": True,
            "weight_cut_pct": 5.0,
            "readiness_flags": ["high_fatigue", "fight_week", "short_notice", "active_weight_cut"],
        },
        {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["sport speed", "fight-pace transfer"],
                "deprioritize": ["non-specific volume"],
                "risk_flags": ["manage accumulated fatigue", "manage cut stress"],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 0},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic"],
                },
                "weeks": 0,
                "days": 6,
            },
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue", "manage cut stress"],
                "session_counts": {"strength": 0, "conditioning": 1, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 0,
                "days": 4,
            },
        },
    )

    progression = brief["week_by_week_progression"]
    weeks = progression["weeks"]

    assert progression["active_week_count"] == 2
    assert [week["phase"] for week in weeks] == ["SPP", "TAPER"]
    assert weeks[0]["stage_key"] == "specific_density_to_peak"
    assert weeks[1]["stage_key"] == "fight_week_survival_rhythm"
    assert weeks[0]["phase_week_total"] == 1
    assert weeks[1]["phase_week_total"] == 1
    assert sum(week["span_days"] for week in weeks) == 10
    assert weeks[1]["protect_first"].startswith("Because fatigue is high")



def test_week_by_week_progression_inherits_phase_guardrails_and_stress_rules():
    brief = _build_progression_brief(
        {
            "sport": "mma",
            "status": "amateur",
            "rounds_format": "3x5",
            "camp_length_weeks": 3,
            "days_until_fight": 18,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["wrestling"],
            "tactical_styles": ["pressure"],
            "key_goals": ["conditioning"],
            "weaknesses": ["conditioning"],
            "equipment": ["bodyweight"],
            "injuries": ["shoulder strain"],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["injury_management"],
        },
        {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": ["respect injury guardrails"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["rehab", "glycolytic", "alactic"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 1,
                "days": 6,
            },
        },
    )

    week = brief["week_by_week_progression"]["weeks"][0]
    stress = brief["weekly_stress_map"]["SPP"]

    assert week["must_keep"] == ["rehab", "glycolytic", "alactic"]
    assert week["drop_order_if_thin"] == ["aerobic"]
    assert week["conditioning_sequence"] == stress["conditioning_sequence"]
    assert week["cut_first_when_collisions_rise"] == stress["cut_first_when_collisions_rise"]
    assert week["highest_collision_sport_load"] == stress["highest_collision_sport_load"]


def test_build_planning_brief_adds_weekly_role_map_from_progression():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 5,
            "days_until_fight": 33,
            "short_notice": False,
            "fatigue": "moderate",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning", "power"],
            "weaknesses": ["conditioning"],
            "equipment": ["air_bike"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["moderate_fatigue"],
        },
        {
            "GPP": {
                "objective": "build aerobic base and general force capacity",
                "emphasize": ["aerobic repeatability", "general force"],
                "deprioritize": ["fight-week intensity"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["aerobic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["alactic", "glycolytic"],
                },
                "weeks": 2,
                "days": 13,
            },
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["glycolytic", "alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 2,
                "days": 15,
            },
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 2},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 5,
            },
        },
    )

    role_map = brief["weekly_role_map"]
    first_week_roles = role_map["weeks"][0]["session_roles"]

    assert role_map["model"] == "session_role_overlay.v1"
    assert len(role_map["weeks"]) == 5
    assert len(first_week_roles) == 5
    assert [role["role_key"] for role in first_week_roles] == [
        "primary_strength_day",
        "secondary_strength_day",
        "aerobic_base_day",
        "controlled_repeatability_day",
        "recovery_reset_day",
    ]



def test_weekly_role_map_compresses_to_sharpness_and_freshness_for_short_notice():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 10,
            "short_notice": True,
            "fatigue": "high",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power"],
            "weaknesses": ["coordination_proprioception"],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": True,
            "weight_cut_pct": 5.0,
            "readiness_flags": ["high_fatigue", "fight_week", "short_notice", "active_weight_cut"],
        },
        {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["sport speed", "fight-pace transfer"],
                "deprioritize": ["non-specific volume"],
                "risk_flags": ["manage accumulated fatigue", "manage cut stress"],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 0},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic"],
                },
                "weeks": 0,
                "days": 6,
            },
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue", "manage cut stress"],
                "session_counts": {"strength": 0, "conditioning": 1, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 0,
                "days": 4,
            },
        },
    )

    taper_roles = brief["weekly_role_map"]["weeks"][1]["session_roles"]

    assert [role["role_key"] for role in taper_roles] == [
        "alactic_sharpness_day",
        "fight_week_freshness_day",
    ]
    assert taper_roles[0]["anchor"] == "highest_neural_day"
    assert taper_roles[1]["anchor"] == "lowest_load_day"



def test_weekly_role_map_inherits_existing_stress_anchors():
    brief = _build_progression_brief(
        {
            "sport": "mma",
            "status": "amateur",
            "rounds_format": "3x5",
            "camp_length_weeks": 3,
            "days_until_fight": 18,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["wrestling"],
            "tactical_styles": ["pressure"],
            "key_goals": ["conditioning"],
            "weaknesses": ["conditioning"],
            "equipment": ["bodyweight"],
            "injuries": ["shoulder strain"],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["injury_management"],
        },
        {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": ["respect injury guardrails"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["rehab", "glycolytic", "alactic"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 1,
                "days": 6,
            },
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]
    stress = brief["weekly_stress_map"]["SPP"]
    fight_pace_role = next(role for role in week["session_roles"] if role["role_key"] == "fight_pace_repeatability_day")
    recovery_role = next(role for role in week["session_roles"] if role["category"] == "recovery")

    assert fight_pace_role["anchor"] == "highest_glycolytic_day"
    assert fight_pace_role["placement_rule"] == stress["highest_glycolytic_day"]
    assert recovery_role["anchor"] == "lowest_load_day"
    assert recovery_role["placement_rule"] == stress["lowest_load_day"]


def test_weekly_role_map_marks_roles_as_execution_layer_only():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 3,
            "days_until_fight": 19,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning"],
            "weaknesses": ["conditioning"],
            "equipment": ["air_bike"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        },
        {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": [],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["glycolytic", "alactic"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 1,
                "days": 6,
            },
        },
    )

    role = brief["weekly_role_map"]["weeks"][0]["session_roles"][0]

    assert role["governance"]["authority"] == "execution_layer_only"
    assert role["governance"]["execution_only"] is True
    assert role["governance"]["governed_by"] == [entry["driver"] for entry in brief["decision_hierarchy"]]
    assert role["governance"]["cannot_override"][:3] == [
        "phase_survival_rules",
        "safety_and_readiness",
        "sport_load_collision_rules",
    ]



def test_weekly_role_map_suppresses_optional_taper_glycolytic_roles():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 9,
            "short_notice": True,
            "fatigue": "moderate",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning"],
            "weaknesses": [],
            "equipment": ["air_bike"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["fight_week"],
        },
        {
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 1, "conditioning": 3, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 5,
            },
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]
    role_keys = [role["role_key"] for role in week["session_roles"]]
    suppressed = next(item for item in week["suppressed_roles"] if item["role_key"] == "light_fight_pace_touch_day")

    assert "light_fight_pace_touch_day" not in role_keys
    assert suppressed["preferred_system"] == "glycolytic"
    assert suppressed["governance"]["authority"] == "execution_layer_only"
    assert "sport-load rules keep glycolytic density optional" in suppressed["reasons"][0]



def test_weekly_role_map_suppresses_sharpness_roles_when_tissue_protection_wins():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 11,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "conservative",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["durability"],
            "weaknesses": ["stiffness"],
            "equipment": ["bands"],
            "injuries": ["shoulder strain"],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["injury_management"],
        },
        {
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["freshness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["respect injury guardrails"],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["rehab"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 5,
            },
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]
    role_keys = [role["role_key"] for role in week["session_roles"]]
    suppressed_keys = [item["role_key"] for item in week["suppressed_roles"]]

    assert "neural_primer_day" not in role_keys
    assert "alactic_sharpness_day" not in role_keys
    assert "neural_primer_day" in suppressed_keys
    assert "alactic_sharpness_day" in suppressed_keys



def test_weekly_role_map_does_not_create_strength_roles_when_strength_count_is_zero():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 8,
            "short_notice": True,
            "fatigue": "moderate",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power"],
            "weaknesses": [],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["fight_week"],
        },
        {
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 0, "conditioning": 1, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 4,
            },
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]

    assert all(role["category"] != "strength" for role in week["session_roles"])
    assert all(item["category"] != "strength" for item in week["suppressed_roles"])
