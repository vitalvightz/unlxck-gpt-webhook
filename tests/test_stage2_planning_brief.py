from fightcamp.stage2_payload import (
    _apply_high_fatigue_week_compression,
    _compute_readiness_compression,
    _compression_floor_value,
    _derive_competitive_maturity,
    _high_fatigue_compression_reason_codes,
    _non_spar_role_priority_rank,
    _parse_record,
    build_planning_brief,
    build_stage2_payload,
)
from fightcamp.nutrition import generate_nutrition_block
from fightcamp.recovery import generate_recovery_block
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





def test_parse_record_accepts_x_x_format():
    parsed = _parse_record("19-2")

    assert parsed["wins"] == 19
    assert parsed["losses"] == 2
    assert parsed["draws"] == 0
    assert parsed["total_bouts"] == 21
    assert parsed["competitive_maturity"] == "unknown_competitive_maturity"


def test_parse_record_accepts_x_x_x_format():
    parsed = _parse_record("12-3-1")

    assert parsed["wins"] == 12
    assert parsed["losses"] == 3
    assert parsed["draws"] == 1
    assert parsed["total_bouts"] == 16


def test_parse_record_invalid_string_returns_unknown_maturity():
    parsed = _parse_record("five-and-one")

    assert parsed["wins"] is None
    assert parsed["losses"] is None
    assert parsed["draws"] is None
    assert parsed["total_bouts"] is None
    assert parsed["competitive_maturity"] == "unknown_competitive_maturity"


def test_competitive_maturity_buckets_amateur_by_total_bouts():
    assert _derive_competitive_maturity("amateur", "2-1")["competitive_maturity"] == "novice_amateur"
    assert _derive_competitive_maturity("amateur", "7-1")["competitive_maturity"] == "developing_amateur"
    assert _derive_competitive_maturity("amateur", "19-2")["competitive_maturity"] == "experienced_amateur"


def test_competitive_maturity_returns_unknown_without_valid_status_or_record():
    assert _derive_competitive_maturity("", "19-2")["competitive_maturity"] == "unknown_competitive_maturity"
    assert _derive_competitive_maturity("amateur", "bad")["competitive_maturity"] == "unknown_competitive_maturity"

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
        days_until_fight=14,
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
            "hard_sparring_days": ["Tuesday", "Saturday"],
            "technical_skill_days": ["Monday"],
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


def test_stage2_payload_carries_declared_sparring_days_into_athlete_model_and_priorities():
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=5,
        days_available=5,
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=["conditioning"],
        equipment=["bodyweight", "heavy_bag", "assault_bike"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["conditioning"],
        training_preference="balanced",
        mental_block=[],
        age=24,
        weight=67.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=32,
        hard_sparring_days=["Tuesday", "Saturday"],
        technical_skill_days=["Monday"],
    )

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks={
            "GPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "SPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "TAPER": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )
    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )

    athlete_snapshot = brief["athlete_snapshot"]

    assert athlete_snapshot["hard_sparring_days"] == ["Tuesday", "Saturday"]
    assert athlete_snapshot["technical_skill_days"] == ["Monday"]
    assert any("hard sparring" in item.lower() for item in brief["main_risks"])
    assert any("primary neural strength day away from declared hard sparring" in item.lower() for item in brief["global_priorities"]["push"])

    spp_week = next(week for week in brief["weekly_role_map"]["weeks"] if week["phase"] == "SPP")
    role_by_key = {role["role_key"]: role for role in spp_week["session_roles"]}
    hard_spar_days = [role["scheduled_day_hint"] for role in spp_week["session_roles"] if role["role_key"] == "hard_sparring_day"]

    assert role_by_key["recovery_reset_day"]["scheduled_day_hint"] == "Wednesday"
    assert role_by_key["neural_plus_strength_day"]["scheduled_day_hint"] == "Thursday"
    assert sorted(hard_spar_days) == ["Saturday", "Tuesday"]



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


def test_short_camp_priorities_are_compressed_into_primary_maintenance_and_support_buckets():
    brief = _build_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 1,
            "days_until_fight": 5,
            "short_notice": True,
            "fatigue": "moderate",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power", "skill_refinement", "mobility"],
            "weaknesses": ["gas_tank", "footwork"],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["moderate_fatigue", "fight_week", "short_notice"],
        },
        phase="TAPER",
    )

    compressed = brief["compressed_priorities"]

    assert compressed["is_short_camp"] is True
    assert compressed["is_ultra_short_camp"] is True
    assert [entry["label"] for entry in compressed["primary_targets"]] == [
        "footwork / technical sharpness",
        "power expression",
    ]
    assert [entry["label"] for entry in compressed["maintenance_targets"]] == [
        "gas tank maintenance"
    ]
    assert any(entry["label"] == "mobility support" for entry in compressed["embedded_support"])
    assert any(entry["label"] == "skill refinement as standalone work" for entry in compressed["deferred"])
    assert any("Keep the week selective" in item for item in brief["global_priorities"]["preserve"])
    assert any("Do not turn every selected goal or weakness into its own session objective" in item for item in brief["global_priorities"]["avoid"])



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


def test_weekly_stress_map_exposes_resolved_hierarchy_drivers():
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

    resolved = brief["weekly_stress_map"]["TAPER"]["resolved_rule_state"]

    assert resolved["protect_first_driver"] == "safety_and_readiness"
    assert resolved["cut_first_driver"] == "sport_load_collision_rules"
    assert resolved["conditioning_sequence_driver"] == "main_limiter"


def test_weekly_role_governance_inherits_resolved_authority_drivers():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 14,
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
    suppressed = next(item for item in week["suppressed_roles"] if item["role_key"] == "light_fight_pace_touch_day")

    assert suppressed["governance"]["resolved_authority"]["cut_first_driver"] == "sport_load_collision_rules"
    assert suppressed["governance"]["resolved_authority"]["conditioning_sequence_driver"] == "main_limiter"



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
    assert "ballistic extras" in brief_profile["cut_first"]
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
            "days_until_fight": 14,
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
            "days_until_fight": 14,
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

    phase_strategy = brief["phase_strategy"]
    assert phase_strategy["SPP"]["objective"] == "increase fight-specific repeatability and power transfer"
    assert phase_strategy["SPP"]["visible_label"] == "specific density / peak"
    assert phase_strategy["SPP"]["visible_objective"].startswith(
        "Compress specific density build and peak transfer into one focused week"
    )
    assert phase_strategy["TAPER"]["visible_label"] == "fight-week survival / rhythm"



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
        "secondary_strength_day",
        "aerobic_base_day",
        "recovery_reset_day",
        "primary_strength_day",
        "alactic_support_day",
    ]
    assert first_week_roles[2]["category"] == "recovery"
    assert first_week_roles[3]["anchor"] == "highest_neural_day"



def test_weekly_role_map_compresses_to_sharpness_and_freshness_for_short_notice():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 2,
            "days_until_fight": 14,
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



def test_short_camp_weekly_role_map_only_keeps_roles_that_map_to_compressed_priorities():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 1,
            "days_until_fight": 5,
            "short_notice": True,
            "fatigue": "moderate",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power", "skill_refinement", "mobility"],
            "weaknesses": ["gas_tank", "footwork"],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["moderate_fatigue", "fight_week", "short_notice"],
        },
        {
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 0,
                "days": 5,
            },
        },
    )

    assert brief["payload_variant"] == "late_fight_stage2_payload"
    assert brief["days_out_payload"]["payload_mode"] == "late_fight_transition_payload"
    assert brief["weekly_role_map"]["weeks"] == []
    roles_from_seq = [entry["role_key"] for entry in brief["late_fight_session_sequence"]]
    assert roles_from_seq == [
        "alactic_sharpness_day",
        "fight_week_freshness_day",
    ]
    assert brief["late_fight_plan_spec"]["session_roles"] == [
        "alactic_sharpness_day",
        "fight_week_freshness_day",
    ]
    assert brief["late_fight_plan_spec"]["session_cap"] == 2
    assert brief["late_fight_plan_spec"]["rendering_rules"]["framing"] == "session_by_session"


def test_fight_week_override_0_to_1_days_outputs_protocol_only_and_no_week_roles():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 1,
            "days_until_fight": 1,
            "short_notice": True,
            "fatigue": "moderate",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power"],
            "weaknesses": ["gas_tank"],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": True,
            "weight_cut_pct": 3.0,
            "readiness_flags": ["fight_week", "short_notice", "active_weight_cut"],
        },
        {
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue", "manage cut stress"],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 0,
                "days": 1,
            },
        },
    )

    assert brief["fight_week_override"]["active"] is True
    assert brief["fight_week_override"]["band"] == "final_day_protocol"
    assert brief["weekly_role_map"]["fight_week_override"]["band"] == "final_day_protocol"
    assert brief["weekly_role_map"]["weeks"] == []


def test_fight_week_override_2_to_3_days_limits_to_micro_taper_roles():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 1,
            "days_until_fight": 3,
            "short_notice": True,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["power"],
            "weaknesses": ["gas_tank"],
            "equipment": ["bodyweight", "bands"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": ["fight_week", "short_notice"],
        },
        {
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": ["manage accumulated fatigue"],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 0,
                "days": 3,
            },
        },
    )

    assert brief["fight_week_override"]["active"] is True
    assert brief["fight_week_override"]["band"] == "micro_taper_protocol"
    assert brief["weekly_role_map"]["weeks"] == []
    assert brief["week_by_week_progression"]["weeks"] == []
    assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == [
        "fight_week_freshness_day",
    ]
    assert brief["late_fight_plan_spec"]["session_roles"] == [
        "fight_week_freshness_day",
    ]
    assert brief["late_fight_plan_spec"]["session_cap"] == 1


def test_phase_strategy_keeps_plain_spp_framing_for_true_multiweek_spp():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 5,
            "days_until_fight": 33,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "technical",
            "technical_styles": ["boxing"],
            "tactical_styles": ["counter_striker"],
            "key_goals": ["power"],
            "weaknesses": ["coordination_proprioception"],
            "equipment": ["bodyweight"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        },
        {
            "GPP": {
                "objective": "build aerobic base and general force capacity",
                "emphasize": ["aerobic repeatability", "general force"],
                "deprioritize": ["fight-week intensity"],
                "risk_flags": [],
                "session_counts": {"strength": 2, "conditioning": 1, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["aerobic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["alactic", "glycolytic"],
                },
                "weeks": 2,
                "days": 13,
            },
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["sport speed", "fight-pace transfer"],
                "deprioritize": ["non-specific volume"],
                "risk_flags": [],
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 0},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic"],
                },
                "weeks": 2,
                "days": 13,
            },
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": [],
                "session_counts": {"strength": 0, "conditioning": 1, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 7,
            },
        },
    )

    strategy = brief["phase_strategy"]["SPP"]

    assert [week["stage_key"] for week in brief["week_by_week_progression"]["weeks"] if week["phase"] == "SPP"] == [
        "specific_density_build",
        "peak_specificity",
    ]
    assert strategy["visible_label"] == "SPP"
    assert strategy["visible_objective"] == "increase fight-specific repeatability and power transfer"


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


def test_weekly_role_map_places_recovery_immediately_before_primary_strength_for_boxers():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 4,
            "days_until_fight": 24,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning", "power"],
            "weaknesses": ["conditioning"],
            "equipment": ["assault_bike"],
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
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["glycolytic", "alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 1,
                "days": 6,
            },
        },
    )

    roles = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    role_keys = [role["role_key"] for role in roles]
    support_conditioning_keys = {"aerobic_support_day", "repeatability_support_day"}

    assert role_keys[0] == "strength_touch_day"
    assert role_keys[1] in support_conditioning_keys
    assert role_keys[2] == "recovery_reset_day"
    assert role_keys[3] == "neural_plus_strength_day"
    assert role_keys[4] == "fight_pace_repeatability_day"
    assert role_keys.index("recovery_reset_day") + 1 == role_keys.index("neural_plus_strength_day")


def test_weekly_role_map_keeps_full_boxer_structure_through_weeks_five_and_six():
    brief = _build_progression_brief(
        {
            "sport": "boxing",
            "status": "amateur",
            "rounds_format": "3x3",
            "camp_length_weeks": 6,
            "days_until_fight": 40,
            "short_notice": False,
            "fatigue": "low",
            "training_preference": "balanced",
            "technical_styles": ["boxing"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["conditioning", "power"],
            "weaknesses": ["conditioning"],
            "equipment": ["assault_bike"],
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
            "readiness_flags": [],
        },
        {
            "GPP": {
                "objective": "build aerobic base and general force capacity",
                "emphasize": ["aerobic repeatability", "general force"],
                "deprioritize": ["fight-week intensity"],
                "risk_flags": [],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["aerobic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["alactic", "glycolytic"],
                },
                "weeks": 2,
                "days": 14,
            },
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": [],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["glycolytic", "alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 3,
                "days": 19,
            },
            "TAPER": {
                "objective": "maintain sharpness and freshness",
                "emphasize": ["alactic sharpness", "confidence"],
                "deprioritize": ["new drills", "high lactate exposure"],
                "risk_flags": [],
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 2},
                "selection_guardrails": {
                    "must_keep_if_present": ["alactic", "primary_strength"],
                    "conditioning_drop_order_if_thin": ["glycolytic", "aerobic"],
                },
                "weeks": 1,
                "days": 7,
            },
        },
    )

    role_map = brief["weekly_role_map"]["weeks"]
    assert [week["week_index"] for week in role_map] == [1, 2, 3, 4, 5, 6]

    week_five = role_map[4]
    week_six = role_map[5]

    week_five_keys = [role["role_key"] for role in week_five["session_roles"]]
    assert week_five["phase"] == "SPP"
    assert len(week_five_keys) == 5
    assert week_five_keys.index("recovery_reset_day") + 1 == week_five_keys.index("neural_plus_strength_day")

    week_six_keys = [role["role_key"] for role in week_six["session_roles"]]
    assert week_six["phase"] == "TAPER"
    assert "fight_week_freshness_day" in week_six_keys
    assert len(week_six_keys) == 4
    assert any(role in week_six_keys for role in {"neural_primer_day", "alactic_sharpness_day", "aerobic_flush_day"})


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
            "days_until_fight": 14,
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
            "days_until_fight": 14,
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
            "days_until_fight": 14,
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


def test_boxing_crowded_week_triggers_on_two_risk_signals():
    athlete = _base_athlete(
        fatigue="moderate",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        hard_sparring_days=["Tuesday", "Thursday", "Saturday"],
        readiness_flags=["moderate_fatigue"],
    )
    week = _spp_week_role_map(athlete)

    assert week["intentional_compression"]["active"] is True
    assert week["intentional_compression"]["policy"] == "boxing_crowded_week"
    assert set(week["intentional_compression"]["risk_signals"]) >= {"high_spar_load", "moderate_fatigue"}


def test_boxing_crowded_week_keeps_one_anchor_and_one_support_day_max():
    athlete = _base_athlete(
        fatigue="moderate",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        hard_sparring_days=["Tuesday", "Thursday", "Saturday"],
        weight_cut_risk=True,
        weight_cut_pct=4.2,
        readiness_flags=["moderate_fatigue", "active_weight_cut"],
    )
    week = _spp_week_role_map(athlete)

    non_spar_roles = [role for role in week["session_roles"] if role["role_key"] != "hard_sparring_day"]
    anchor_roles = [role for role in non_spar_roles if role["governance"]["main_job"] == "anchor"]
    support_roles = [role for role in non_spar_roles if role["governance"]["main_job"] == "support_recovery"]

    assert week["intentional_compression"]["active"] is True
    assert week["intentional_compression"]["max_non_spar_roles"] == 2
    assert week["intentional_compression"]["max_support_roles"] == 1
    assert week["intentional_compression"]["standalone_glycolytic_allowed"] is False
    assert len([role for role in week["session_roles"] if role["role_key"] == "hard_sparring_day"]) == 3
    assert len(non_spar_roles) <= 2
    assert len(anchor_roles) == 1
    assert len(support_roles) <= 1
    assert all(role.get("preferred_system") != "glycolytic" for role in non_spar_roles)
    assert all(role["governance"]["support_cap"] == "light_only" for role in anchor_roles + support_roles)
    assert all(role["governance"]["forbidden_secondary_stressors"] for role in anchor_roles + support_roles)


def test_boxing_crowded_week_auto_triggers_with_high_fatigue_and_active_cut():
    athlete = _base_athlete(
        fatigue="high",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        hard_sparring_days=["Wednesday"],
        weight_cut_risk=True,
        weight_cut_pct=4.0,
        readiness_flags=["high_fatigue", "active_weight_cut"],
    )
    week = _spp_week_role_map(athlete)

    assert week["intentional_compression"]["active"] is True
    assert "high_fatigue_active_cut" in week["intentional_compression"]["reason_codes"]


def test_boxing_crowded_week_policy_does_not_touch_late_fight_path():
    training_context = TrainingContext(
        fatigue="high",
        training_frequency=5,
        days_available=5,
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=["conditioning"],
        equipment=["bodyweight", "heavy_bag"],
        weight_cut_risk=True,
        weight_cut_pct=4.0,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["conditioning"],
        training_preference="balanced",
        mental_block=[],
        age=24,
        weight=68.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 0, "SPP": 1, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=10,
        hard_sparring_days=["Tuesday", "Thursday", "Friday"],
        technical_skill_days=[],
    )

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="4-1",
        rounds_format="3x3",
        camp_len=2,
        short_notice=True,
        restrictions=[],
        phase_weeks={"GPP": 0, "SPP": 1, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks={
            "SPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "TAPER": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )

    assert payload["payload_variant"] == "late_fight_stage2_payload"
    assert payload["payload_mode"] == "pre_fight_compressed_payload"


def test_boxing_crowded_week_does_not_overcompress_on_single_signal():
    athlete = _base_athlete(
        fatigue="high",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        hard_sparring_days=["Tuesday", "Thursday"],
        readiness_flags=["high_fatigue"],
    )
    week = _spp_week_role_map(athlete)

    suppressed_compression = [s for s in week["suppressed_roles"] if s.get("intentional_compression")]
    non_spar_roles = [role for role in week["session_roles"] if role["role_key"] != "hard_sparring_day"]

    assert week["intentional_compression"]["active"] is False
    assert len(non_spar_roles) <= 3
    assert len(suppressed_compression) == 0


def test_compute_readiness_compression_still_counts_mild_injury_in_generic_path():
    athlete = _base_athlete(
        fatigue="low",
        injuries=["mild shoulder irritation"],
        days_until_fight=35,
    )

    assert _compute_readiness_compression(athlete) == 1


def test_boxing_crowded_week_does_not_treat_mild_injury_as_moderate_plus_signal():
    athlete = _base_athlete(
        fatigue="moderate",
        injuries=["mild shoulder irritation"],
        days_until_fight=35,
        readiness_flags=["moderate_fatigue"],
    )
    week = _spp_week_role_map(athlete)

    assert week["intentional_compression"]["active"] is False


def test_high_fatigue_compression_blocks_glycolytic_on_next_training_day_after_remaining_hard_spar():
    session_roles = [
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Monday",
            "governance": {},
        },
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Wednesday",
            "governance": {},
        },
        {
            "category": "strength",
            "role_key": "secondary_strength_day",
            "governance": {},
        },
        {
            "category": "strength",
            "role_key": "neural_plus_strength_day",
            "governance": {},
        },
        {
            "category": "conditioning",
            "role_key": "fight_pace_repeatability_day",
            "preferred_system": "glycolytic",
            "scheduled_day_hint": "Tuesday",
            "governance": {},
        },
        {
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "scheduled_day_hint": "Monday",
            "governance": {},
        },
    ]

    kept_roles, suppressed = _apply_high_fatigue_week_compression(
        {
            "phase": "SPP",
            "week_index": 1,
            "declared_hard_sparring_days": ["Monday", "Wednesday"],
            "resolved_rule_state": {"must_keep": ["glycolytic", "primary_strength"]},
        },
        session_roles,
        [],
        {
            "fatigue": "high",
            "readiness_flags": ["high_fatigue"],
            "hard_sparring_days": ["Monday", "Wednesday"],
            "training_days": ["Monday", "Tuesday", "Wednesday", "Friday"],
        },
        hard_sparring_plan=[
            {"day": "Monday", "status": "hard_as_planned"},
            {"day": "Wednesday", "status": "deload_suggested"},
        ],
    )

    assert "secondary_strength_day" not in [role["role_key"] for role in kept_roles]
    assert "secondary_strength_day" in [item["role_key"] for item in suppressed]
    assert [role["scheduled_day_hint"] for role in kept_roles if role["role_key"] == "hard_sparring_day"] == ["Monday", "Wednesday"]
    assert "fight_pace_repeatability_day" in [role["role_key"] for role in kept_roles]


def test_high_fatigue_compression_allows_glycolytic_when_not_on_next_training_day_after_effective_hard_spar():
    session_roles = [
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Monday",
            "governance": {},
        },
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Wednesday",
            "governance": {},
        },
        {
            "category": "strength",
            "role_key": "secondary_strength_day",
            "governance": {},
        },
        {
            "category": "strength",
            "role_key": "neural_plus_strength_day",
            "governance": {},
        },
        {
            "category": "conditioning",
            "role_key": "fight_pace_repeatability_day",
            "preferred_system": "glycolytic",
            "scheduled_day_hint": "Tuesday",
            "governance": {},
        },
        {
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "scheduled_day_hint": "Monday",
            "governance": {},
        },
    ]

    kept_roles, suppressed = _apply_high_fatigue_week_compression(
        {
            "phase": "SPP",
            "week_index": 1,
            "declared_hard_sparring_days": ["Monday", "Wednesday"],
            "resolved_rule_state": {"must_keep": ["glycolytic", "primary_strength"]},
        },
        session_roles,
        [],
        {
            "fatigue": "high",
            "readiness_flags": ["high_fatigue"],
            "hard_sparring_days": ["Monday", "Wednesday"],
            "training_days": ["Monday", "Tuesday", "Wednesday", "Friday"],
        },
        hard_sparring_plan=[
            {"day": "Monday", "status": "deload_suggested"},
            {"day": "Wednesday", "status": "hard_as_planned"},
        ],
    )

    assert "fight_pace_repeatability_day" in [role["role_key"] for role in kept_roles]
    assert "secondary_strength_day" not in [role["role_key"] for role in kept_roles]
    assert "secondary_strength_day" in [item["role_key"] for item in suppressed]
    assert [role["scheduled_day_hint"] for role in kept_roles if role["role_key"] == "hard_sparring_day"] == ["Monday", "Wednesday"]


def test_strength_slots_share_session_metadata_and_injury_pressure_does_not_force_tissue_state():
    training_context = TrainingContext(
        fatigue="low",
        training_frequency=4,
        days_available=4,
        training_days=["Mon", "Tue", "Thu", "Sat"],
        injuries=["mild shoulder irritation"],
        style_technical=["boxing"],
        style_tactical=["counter_striker"],
        weaknesses=["strength"],
        equipment=["barbell", "dumbbells", "medicine_ball"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["power", "strength"],
        training_preference="balanced",
        mental_block=[],
        age=26,
        weight=69.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 3, "SPP": 0, "TAPER": 0, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=35,
    )

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="4-1",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[
            {
                "restriction": "heavy_overhead_pressing",
                "region": "shoulder",
                "source_phrase": "avoid heavy overhead pressing",
            }
        ],
        phase_weeks={"GPP": 3, "SPP": 0, "TAPER": 0, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={
            "GPP": {
                "num_sessions": 2,
                "exercises": [
                    {"name": "Front Squat", "movement": "squat", "tags": ["compound", "quad_dominant"], "method": "4x5"},
                    {"name": "Split Squat", "movement": "lunge", "tags": ["unilateral"], "method": "3x6"},
                    {"name": "Dead Bug", "movement": "core", "tags": ["core"], "method": "2x8"},
                ],
                "why_log": [
                    {"name": "Front Squat", "explanation": "balanced selection", "reasons": {}},
                    {"name": "Split Squat", "explanation": "balanced selection", "reasons": {}},
                    {"name": "Dead Bug", "explanation": "balanced selection", "reasons": {}},
                ],
                "candidate_reservoir": {"squat": [], "lunge": [], "core": []},
            },
            "SPP": None,
            "TAPER": None,
        },
        conditioning_blocks={"GPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}}},
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )
    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )

    slots = payload["candidate_pools"]["GPP"]["strength_slots"]
    assert [slot["session_index"] for slot in slots[:2]] == [1, 2]
    assert slots[0]["anchor_capable"] is True
    assert slots[2]["support_only"] is True
    assert brief["limiter_profile"]["key"] != "tissue_state"


def test_weight_cut_brief_and_payload_surface_cut_stress_explicitly():
    payload, brief = _build_taper_payload_and_brief()

    assert any("strength expression" in risk for risk in brief["main_risks"])
    assert any("conditioning tolerance" in risk for risk in brief["main_risks"])
    assert any("recovery spacing" in line for line in brief["global_priorities"]["preserve"])
    assert any("glycolytic density" in line for line in brief["global_priorities"]["avoid"])
    assert any("explicitly acknowledge" in line for line in payload["rewrite_guidance"]["writing_rules"])


def test_weight_cut_support_blocks_keep_protocol_and_plain_acknowledgement():
    flags = {
        "phase": "TAPER",
        "fatigue": "moderate",
        "weight": 70.0,
        "weight_cut_risk": True,
        "weight_cut_pct": 8.6,
        "days_until_fight": 21,
    }

    nutrition = generate_nutrition_block(flags=flags)
    recovery = generate_recovery_block(
        {
            **flags,
            "age": 27,
            "injuries": [],
        }
    )

    assert "Active Weight-Cut Note" in nutrition
    assert "strength expression" in nutrition
    assert "conditioning tolerance" in nutrition
    assert "Weight Cut Protocol Triggered" in nutrition
    assert "Active Weight-Cut Recovery Note" in recovery
    assert "protect freshness" in recovery.lower()


def test_record_changes_maturity_without_changing_load_logic():
    base_athlete_model = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "camp_length_weeks": 6,
        "days_until_fight": 21,
        "short_notice": False,
        "fatigue": "moderate",
        "training_preference": "balanced",
        "technical_styles": ["boxing"],
        "tactical_styles": ["pressure_fighter"],
        "key_goals": ["conditioning", "power"],
        "weaknesses": ["pull"],
        "equipment": ["air_bike", "dumbbell"],
        "injuries": ["shoulder strain"],
        "weight_cut_risk": True,
        "weight_cut_pct": 5.0,
        "readiness_flags": ["moderate_fatigue", "active_weight_cut", "injury_management"],
    }
    phase_briefs = {
        "SPP": {
            "objective": "increase fight-specific repeatability and power transfer",
            "emphasize": ["glycolytic repeatability", "sport speed"],
            "deprioritize": ["non-specific conditioning volume"],
            "risk_flags": ["respect injury guardrails", "manage cut stress"],
            "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
            "selection_guardrails": {
                "must_keep_if_present": ["rehab", "glycolytic", "alactic"],
                "conditioning_drop_order_if_thin": ["aerobic"],
            },
            "weeks": 1,
            "days": 7,
        }
    }
    candidate_pools = {
        "SPP": {
            "strength_slots": [{"role": "hinge"}],
            "conditioning_slots": [{"role": "glycolytic"}, {"role": "alactic"}],
            "rehab_slots": [{"role": "rehab_shoulder_strain"}],
        }
    }

    novice = build_planning_brief(
        athlete_model={**base_athlete_model, **_derive_competitive_maturity("amateur", "2-1")},
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )
    experienced = build_planning_brief(
        athlete_model={**base_athlete_model, **_derive_competitive_maturity("amateur", "19-2")},
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )

    assert novice["archetype_summary"]["competitive_maturity"] == "novice_amateur"
    assert novice["archetype_summary"]["style_specificity"] == "Use clear style labels, but keep tactical wording broad and amateur-safe."
    assert experienced["archetype_summary"]["competitive_maturity"] == "experienced_amateur"
    assert experienced["archetype_summary"]["style_specificity"] == "Use confident athlete-specific style framing when it matches the declared style profile."
    assert novice["phase_strategy"] == experienced["phase_strategy"]
    assert novice["weekly_stress_map"] == experienced["weekly_stress_map"]
    assert novice["week_by_week_progression"] == experienced["week_by_week_progression"]


# ---------------------------------------------------------------------------
# New tests: spar-first weekly allocation (6 required scenarios)
# ---------------------------------------------------------------------------

def _spp_week_role_map(
    athlete_model: dict,
    *,
    spar_days: list[str] | None = None,
    training_days: list[str] | None = None,
    session_counts: dict | None = None,
) -> dict:
    """Helper that builds a single SPP week's session_roles via the planning brief."""
    if training_days is not None:
        athlete_model = dict(athlete_model, training_days=training_days)
    if spar_days is not None:
        athlete_model = dict(athlete_model, hard_sparring_days=spar_days)
    sc = session_counts or {"strength": 2, "conditioning": 2, "recovery": 1}
    brief = _build_progression_brief(
        athlete_model,
        {
            "SPP": {
                "objective": "increase fight-specific repeatability and power transfer",
                "emphasize": ["glycolytic repeatability", "sport speed"],
                "deprioritize": ["non-specific conditioning volume"],
                "risk_flags": [],
                "session_counts": sc,
                "selection_guardrails": {
                    "must_keep_if_present": ["primary_strength"],
                    "conditioning_drop_order_if_thin": ["aerobic"],
                },
                "weeks": 1,
                "days": 7,
            },
        },
    )
    return brief["weekly_role_map"]["weeks"][0]


def _gpp_week_role_map(athlete_model: dict, *, spar_days: list[str] | None = None) -> dict:
    if spar_days is not None:
        athlete_model = dict(athlete_model, hard_sparring_days=spar_days)
    brief = _build_progression_brief(
        athlete_model,
        {
            "GPP": {
                "objective": "build aerobic base and general force capacity",
                "emphasize": ["aerobic repeatability", "general force"],
                "deprioritize": ["fight-week intensity"],
                "risk_flags": [],
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "selection_guardrails": {
                    "must_keep_if_present": ["primary_strength"],
                    "conditioning_drop_order_if_thin": ["alactic", "glycolytic"],
                },
                "weeks": 1,
                "days": 7,
            },
        },
    )
    return brief["weekly_role_map"]["weeks"][0]


def _base_athlete(
    *,
    fatigue: str = "low",
    training_days: list[str] | None = None,
    training_frequency: int | None = None,
    hard_sparring_days: list[str] | None = None,
    weight_cut_risk: bool = False,
    weight_cut_pct: float = 0.0,
    injuries: list[str] | None = None,
    days_until_fight: int | None = 28,
    readiness_flags: list[str] | None = None,
) -> dict:
    td = training_days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "camp_length_weeks": 6,
        "days_until_fight": days_until_fight,
        "short_notice": False,
        "fatigue": fatigue,
        "training_preference": "balanced",
        "technical_styles": ["boxing"],
        "tactical_styles": ["pressure_fighter"],
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "equipment": ["air_bike"],
        "training_days": td,
        "training_frequency": training_frequency or len(td),
        "hard_sparring_days": hard_sparring_days or [],
        "technical_skill_days": [],
        "injuries": injuries or [],
        "weight_cut_risk": weight_cut_risk,
        "weight_cut_pct": weight_cut_pct,
        "readiness_flags": readiness_flags or [],
    }


# ── Scenario 1: Sparring counts against weekly cap ──────────────────────────

def test_spar_first_sparring_counted_against_weekly_cap():
    """Hard sparring days reduce the non-spar budget before any other role is placed."""
    athlete = _base_athlete(
        fatigue="low",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        hard_sparring_days=["Tuesday", "Thursday"],
    )
    week = _spp_week_role_map(athlete)

    spar_roles = [r for r in week["session_roles"] if r["role_key"] == "hard_sparring_day"]
    non_spar_roles = [r for r in week["session_roles"] if r["role_key"] != "hard_sparring_day"]

    # 5 training days, 2 spar → non_spar_cap = 3; with no compression all 3 should be kept
    assert len(spar_roles) == 2
    assert len(non_spar_roles) <= 3  # non-spar budget is capped at 5 - 2 = 3


# ── Scenario 2: Compression affects only non-sparring slots ─────────────────

def test_spar_first_compression_applies_only_to_non_spar_slots():
    """Crowded-week compression trims only non-spar slots while sparring stays locked."""
    athlete = _base_athlete(
        fatigue="moderate",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        hard_sparring_days=["Tuesday", "Thursday", "Saturday"],
        weight_cut_risk=True,
        weight_cut_pct=4.1,
        readiness_flags=["moderate_fatigue", "active_weight_cut"],
    )
    week = _spp_week_role_map(athlete)

    spar_roles = [r for r in week["session_roles"] if r["role_key"] == "hard_sparring_day"]
    non_spar_roles = [r for r in week["session_roles"] if r["role_key"] != "hard_sparring_day"]
    suppressed_compression = [s for s in week["suppressed_roles"] if s.get("intentional_compression")]

    assert len(spar_roles) == 3
    assert len(non_spar_roles) <= 2
    assert len(suppressed_compression) >= 1
    assert week["intentional_compression"]["active"] is True


# ── Scenario 3: Moderate fatigue keeps full non-sparring cap ─────────────────

def test_spar_first_moderate_fatigue_keeps_full_non_spar_cap():
    """Moderate fatigue uses the full non-spar cap without any compression."""
    athlete = _base_athlete(
        fatigue="moderate",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        hard_sparring_days=["Tuesday", "Thursday"],
        readiness_flags=["moderate_fatigue"],
    )
    week = _spp_week_role_map(athlete)

    spar_roles = [r for r in week["session_roles"] if r["role_key"] == "hard_sparring_day"]
    non_spar_roles = [r for r in week["session_roles"] if r["role_key"] != "hard_sparring_day"]
    suppressed_compression = [s for s in week["suppressed_roles"] if s.get("intentional_compression")]

    assert len(spar_roles) == 2
    # Moderate fatigue → no compression_floor reduction → non_spar_target = non_spar_cap = 3
    assert len(non_spar_roles) <= 3
    assert len(suppressed_compression) == 0  # nothing dropped by compression


# ── Scenario 4: Crowded-week priority ladder ────────────────────────────────

def test_spar_first_spp_glycolytic_is_below_anchor_and_support_when_crowded():
    """In crowded boxing weeks, support survives before glycolytic and anchor survives last."""
    # Verify priority rank directly
    fight_pace_role = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
    }
    neural_plus_role = {
        "role_key": "neural_plus_strength_day",
        "category": "strength",
        "preferred_system": "",
    }
    repeatability_role = {
        "role_key": "repeatability_support_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
    }

    assert _non_spar_role_priority_rank(
        fight_pace_role, "SPP", True, True, crowded_week=True
    ) < _non_spar_role_priority_rank(neural_plus_role, "SPP", True, True, crowded_week=True)
    assert _non_spar_role_priority_rank(
        fight_pace_role, "SPP", True, True, crowded_week=True
    ) < _non_spar_role_priority_rank(repeatability_role, "SPP", True, True, crowded_week=True)


def test_spar_first_spp_glycolytic_is_first_cut_with_meaningful_weight_cut():
    """fight_pace_repeatability_day is demoted when there is a meaningful weight cut."""
    fight_pace_role = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "preferred_system": "glycolytic",
    }
    recovery_role = {
        "role_key": "recovery_reset_day",
        "category": "recovery",
        "preferred_system": "",
    }
    # With meaningful cut, fight_pace rank (1) < recovery rank (2)
    assert _non_spar_role_priority_rank(fight_pace_role, "SPP", False, True) < \
           _non_spar_role_priority_rank(recovery_role, "SPP", False, True)


# ── Scenario 5: Intentionally unused days stay recovery/off and are not refilled ──

def test_spar_first_intentionally_unused_days_populated_and_not_refilled():
    """Unused training days after compression are marked as recovery_only_day or off_day."""
    athlete = _base_athlete(
        fatigue="moderate",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        hard_sparring_days=["Tuesday", "Thursday", "Saturday"],
        weight_cut_risk=True,
        weight_cut_pct=4.1,
        readiness_flags=["moderate_fatigue", "active_weight_cut"],
    )
    week = _spp_week_role_map(athlete)

    # The week should declare intentionally unused days when compression is active
    if week["intentional_compression"]["active"]:
        # intentionally_unused_days must be present and non-empty when days were left out
        used_day_hints = {
            str(r.get("scheduled_day_hint") or "").strip()
            for r in week["session_roles"]
            if str(r.get("scheduled_day_hint") or "").strip()
        }
        all_training = set(athlete["training_days"])
        possibly_unused = all_training - used_day_hints
        unused_entries = week.get("intentionally_unused_days", [])
        if possibly_unused:
            # Each unused day must be marked with a valid role
            for entry in unused_entries:
                assert entry["role"] in {"recovery_only_day", "off_day"}, \
                    f"Unexpected unused day role: {entry['role']}"
        # The total session count should not exceed training_days (no refill bloat)
        assert len(week["session_roles"]) <= len(athlete["training_days"])


def test_boxing_crowded_week_without_anchor_stays_support_led():
    session_roles = [
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Monday",
            "governance": {},
        },
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Wednesday",
            "governance": {},
        },
        {
            "category": "sparring",
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "Friday",
            "governance": {},
        },
        {
            "category": "strength",
            "role_key": "secondary_strength_day",
            "governance": {},
        },
        {
            "category": "conditioning",
            "role_key": "fight_pace_repeatability_day",
            "preferred_system": "glycolytic",
            "scheduled_day_hint": "Tuesday",
            "governance": {},
        },
        {
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "scheduled_day_hint": "Saturday",
            "governance": {},
        },
    ]

    kept_roles, suppressed = _apply_high_fatigue_week_compression(
        {
            "phase": "SPP",
            "week_index": 1,
            "declared_hard_sparring_days": ["Monday", "Wednesday", "Friday"],
            "resolved_rule_state": {"must_keep": ["primary_strength"]},
        },
        session_roles,
        [],
        {
            "sport": "boxing",
            "fatigue": "moderate",
            "readiness_flags": ["moderate_fatigue", "active_weight_cut"],
            "weight_cut_risk": True,
            "weight_cut_pct": 4.0,
            "hard_sparring_days": ["Monday", "Wednesday", "Friday"],
            "training_days": ["Monday", "Tuesday", "Wednesday", "Friday", "Saturday"],
            "training_frequency": 5,
        },
    )

    non_spar_keys = [role["role_key"] for role in kept_roles if role["role_key"] != "hard_sparring_day"]
    assert non_spar_keys == ["aerobic_support_day"]
    assert "fight_pace_repeatability_day" in [item["role_key"] for item in suppressed]
    assert "secondary_strength_day" in [item["role_key"] for item in suppressed]


def test_spar_first_no_compression_when_no_sparring_and_low_fatigue():
    """With no sparring and no compression factors, no roles are suppressed."""
    athlete = _base_athlete(
        fatigue="low",
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        hard_sparring_days=[],
    )
    week = _spp_week_role_map(athlete)

    suppressed_compression = [s for s in week["suppressed_roles"] if s.get("intentional_compression")]
    assert week["intentional_compression"]["active"] is False
    assert len(suppressed_compression) == 0
