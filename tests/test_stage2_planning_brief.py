from fightcamp.stage2_payload import build_planning_brief


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

