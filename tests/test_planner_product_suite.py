from __future__ import annotations

from fightcamp.stage2_payload import build_planning_brief


def _athlete_model(**overrides) -> dict:
    athlete = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "camp_length_weeks": 6,
        "days_until_fight": 28,
        "short_notice": False,
        "fatigue": "low",
        "training_preference": "balanced",
        "technical_styles": ["boxing"],
        "tactical_styles": ["pressure_fighter"],
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "equipment": ["bodyweight", "bands"],
        "injuries": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "readiness_flags": [],
    }
    athlete.update(overrides)
    return athlete


def _phase_brief(
    phase: str,
    *,
    strength: int,
    conditioning: int,
    recovery: int,
    must_keep: list[str],
    drop_order: list[str],
    weeks: int = 1,
    days: int = 7,
    objective: str | None = None,
    emphasize: list[str] | None = None,
    deprioritize: list[str] | None = None,
    risk_flags: list[str] | None = None,
) -> dict:
    defaults = {
        "GPP": {
            "objective": "build aerobic base and general force capacity",
            "emphasize": ["aerobic repeatability", "general force"],
            "deprioritize": ["fight-week intensity"],
        },
        "SPP": {
            "objective": "increase fight-specific repeatability and power transfer",
            "emphasize": ["sport speed", "fight-pace transfer"],
            "deprioritize": ["non-specific volume"],
        },
        "TAPER": {
            "objective": "maintain sharpness and freshness",
            "emphasize": ["alactic sharpness", "confidence"],
            "deprioritize": ["new drills", "high lactate exposure"],
        },
    }[phase]
    return {
        "objective": objective or defaults["objective"],
        "emphasize": emphasize or defaults["emphasize"],
        "deprioritize": deprioritize or defaults["deprioritize"],
        "risk_flags": risk_flags or [],
        "session_counts": {
            "strength": strength,
            "conditioning": conditioning,
            "recovery": recovery,
        },
        "selection_guardrails": {
            "must_keep_if_present": must_keep,
            "conditioning_drop_order_if_thin": drop_order,
        },
        "weeks": weeks,
        "days": days,
    }


def _candidate_pools(phases: list[str], *, include_rehab: bool = False) -> dict[str, dict]:
    rehab_slots = []
    if include_rehab:
        rehab_slots = [
            {
                "role": "rehab_wrist",
                "selected": {"name": "Band Wrist Extension"},
                "alternates": [{"name": "Pronated Isometric Hold"}],
            }
        ]
    return {
        phase: {
            "strength_slots": [
                {
                    "role": "primary_strength",
                    "selected": {"name": "Trap Bar Deadlift"},
                    "alternates": [{"name": "Goblet Squat"}],
                },
                {
                    "role": "secondary_strength",
                    "selected": {"name": "Rear-Foot Elevated Split Squat"},
                    "alternates": [{"name": "Step-Up"}],
                },
            ],
            "conditioning_slots": [
                {
                    "role": "aerobic",
                    "selected": {"name": "Tempo Run"},
                    "alternates": [{"name": "Air Bike Flush"}],
                },
                {
                    "role": "glycolytic",
                    "selected": {"name": "Hard Shuttle"},
                    "alternates": [{"name": "Bag Sprint Round"}],
                },
                {
                    "role": "alactic",
                    "selected": {"name": "Air Bike Sprint"},
                    "alternates": [{"name": "Short Sprint"}],
                },
            ],
            "rehab_slots": list(rehab_slots),
        }
        for phase in phases
    }


def _build_product_brief(
    *,
    athlete_overrides: dict | None = None,
    phase_briefs: dict[str, dict],
    include_rehab: bool = False,
    restrictions: list[dict] | None = None,
) -> dict:
    athlete_model = _athlete_model(**(athlete_overrides or {}))
    candidate_pools = _candidate_pools(list(phase_briefs.keys()), include_rehab=include_rehab)
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=restrictions or [],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )


def test_rule_contract_taper_does_not_keep_unnecessary_density():
    brief = _build_product_brief(
        athlete_overrides={
            "days_until_fight": 9,
            "short_notice": True,
            "readiness_flags": ["fight_week"],
        },
        phase_briefs={
            "TAPER": _phase_brief(
                "TAPER",
                strength=1,
                conditioning=3,
                recovery=1,
                must_keep=["alactic", "primary_strength"],
                drop_order=["glycolytic", "aerobic"],
                weeks=1,
                days=5,
            )
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]
    role_keys = [role["role_key"] for role in week["session_roles"]]

    assert "light_fight_pace_touch_day" not in role_keys
    assert any(item["role_key"] == "light_fight_pace_touch_day" for item in week["suppressed_roles"])


def test_rule_contract_zero_strength_means_zero_strength_roles():
    brief = _build_product_brief(
        athlete_overrides={
            "days_until_fight": 8,
            "short_notice": True,
            "readiness_flags": ["fight_week"],
        },
        phase_briefs={
            "TAPER": _phase_brief(
                "TAPER",
                strength=0,
                conditioning=1,
                recovery=1,
                must_keep=["alactic"],
                drop_order=["glycolytic", "aerobic"],
                weeks=1,
                days=4,
            )
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]

    assert all(role["category"] != "strength" for role in week["session_roles"])
    assert all(item["category"] != "strength" for item in week["suppressed_roles"])


def test_rule_contract_tissue_protection_suppresses_sharpness_roles():
    brief = _build_product_brief(
        athlete_overrides={
            "days_until_fight": 11,
            "training_preference": "conservative",
            "weaknesses": ["stiffness"],
            "injuries": ["shoulder strain"],
            "readiness_flags": ["injury_management"],
        },
        phase_briefs={
            "TAPER": _phase_brief(
                "TAPER",
                strength=1,
                conditioning=2,
                recovery=1,
                must_keep=["rehab"],
                drop_order=["glycolytic", "aerobic"],
                weeks=1,
                days=5,
                risk_flags=["respect injury guardrails"],
                emphasize=["freshness", "confidence"],
            )
        },
        include_rehab=True,
    )

    week = brief["weekly_role_map"]["weeks"][0]
    role_keys = [role["role_key"] for role in week["session_roles"]]

    assert "neural_primer_day" not in role_keys
    assert "alactic_sharpness_day" not in role_keys
    assert any(item["role_key"] == "neural_primer_day" for item in week["suppressed_roles"])
    assert any(item["role_key"] == "alactic_sharpness_day" for item in week["suppressed_roles"])


def test_scenario_fatigued_amateur_boxer_with_wrist_soreness():
    brief = _build_product_brief(
        athlete_overrides={
            "days_until_fight": 12,
            "fatigue": "high",
            "injuries": ["wrist soreness"],
            "readiness_flags": ["high_fatigue", "injury_management"],
        },
        phase_briefs={
            "SPP": _phase_brief(
                "SPP",
                strength=1,
                conditioning=2,
                recovery=1,
                must_keep=["rehab", "alactic"],
                drop_order=["glycolytic"],
                risk_flags=["manage accumulated fatigue", "respect injury guardrails"],
            )
        },
        include_rehab=True,
    )

    assert brief["sport_load_profile"]["key"] == "boxing"
    assert brief["limiter_profile"]["key"] == "tissue_state"
    assert brief["weekly_stress_map"]["SPP"]["resolved_rule_state"]["protect_first_driver"] == "safety_and_readiness"
    assert "rehab" in brief["phase_strategy"]["SPP"]["must_keep"]


def test_scenario_fresh_pro_kickboxer_without_injuries():
    brief = _build_product_brief(
        athlete_overrides={
            "sport": "muay_thai",
            "status": "pro",
            "rounds_format": "5x3",
            "camp_length_weeks": 8,
            "days_until_fight": 42,
            "training_preference": "technical",
            "technical_styles": ["muay thai"],
            "tactical_styles": ["pressure_fighter"],
            "key_goals": ["power"],
        },
        phase_briefs={
            "SPP": _phase_brief(
                "SPP",
                strength=2,
                conditioning=2,
                recovery=1,
                must_keep=["alactic", "glycolytic", "primary_strength"],
                drop_order=["aerobic"],
                weeks=2,
                days=14,
            )
        },
    )

    assert brief["sport_load_profile"]["key"] == "kickboxing_muay_thai"
    assert brief["limiter_profile"]["key"] == "general_fight_readiness"
    assert brief["weekly_stress_map"]["SPP"]["resolved_rule_state"]["tissue_protection_priority"] is False


def test_scenario_wrestler_with_knee_pain_and_low_aerobic_base():
    brief = _build_product_brief(
        athlete_overrides={
            "sport": "mma",
            "rounds_format": "3x5",
            "technical_styles": ["wrestling"],
            "tactical_styles": ["pressure"],
            "key_goals": ["conditioning"],
            "weaknesses": ["conditioning"],
            "injuries": ["knee pain"],
            "readiness_flags": ["injury_management"],
        },
        phase_briefs={
            "GPP": _phase_brief(
                "GPP",
                strength=2,
                conditioning=2,
                recovery=1,
                must_keep=["rehab", "aerobic", "primary_strength"],
                drop_order=["alactic", "glycolytic"],
                weeks=2,
                days=14,
                risk_flags=["respect injury guardrails"],
            )
        },
        include_rehab=True,
    )

    assert brief["sport_load_profile"]["key"] == "wrestling"
    assert brief["limiter_profile"]["key"] == "aerobic_repeatability"
    assert brief["weekly_stress_map"]["GPP"]["conditioning_sequence"][0] == "aerobic"
    assert "rehab" in brief["phase_strategy"]["GPP"]["must_keep"]


def test_scenario_coordination_limited_boxer_near_fight_week():
    brief = _build_product_brief(
        athlete_overrides={
            "days_until_fight": 8,
            "short_notice": True,
            "fatigue": "high",
            "weaknesses": ["coordination_proprioception"],
            "readiness_flags": ["high_fatigue", "fight_week"],
        },
        phase_briefs={
            "TAPER": _phase_brief(
                "TAPER",
                strength=1,
                conditioning=2,
                recovery=1,
                must_keep=["alactic", "primary_strength"],
                drop_order=["glycolytic", "aerobic"],
                weeks=1,
                days=4,
            )
        },
    )

    assert brief["limiter_profile"]["key"] == "coordination"
    assert brief["weekly_stress_map"]["TAPER"]["resolved_rule_state"]["protect_first_driver"] == "safety_and_readiness"
    assert brief["weekly_stress_map"]["TAPER"]["conditioning_sequence"][0] == "alactic"


def test_output_quality_weekly_role_map_does_not_create_session_bloat():
    brief = _build_product_brief(
        athlete_overrides={"fatigue": "moderate", "readiness_flags": ["moderate_fatigue"]},
        phase_briefs={
            "GPP": _phase_brief(
                "GPP",
                strength=2,
                conditioning=2,
                recovery=1,
                must_keep=["aerobic", "primary_strength"],
                drop_order=["alactic", "glycolytic"],
                weeks=2,
                days=13,
            ),
            "SPP": _phase_brief(
                "SPP",
                strength=2,
                conditioning=2,
                recovery=1,
                must_keep=["alactic", "glycolytic", "primary_strength"],
                drop_order=["aerobic"],
                weeks=2,
                days=15,
            ),
            "TAPER": _phase_brief(
                "TAPER",
                strength=1,
                conditioning=1,
                recovery=2,
                must_keep=["alactic", "primary_strength"],
                drop_order=["glycolytic", "aerobic"],
                weeks=1,
                days=5,
            ),
        },
    )

    progression_by_week = {
        week["week_index"]: week for week in brief["week_by_week_progression"]["weeks"]
    }
    for week in brief["weekly_role_map"]["weeks"]:
        declared_counts = progression_by_week[week["week_index"]]["session_counts"]
        assert len(week["session_roles"]) <= sum(declared_counts.values())
        assert sum(role["category"] == "strength" for role in week["session_roles"]) <= declared_counts["strength"]
        assert sum(role["category"] == "conditioning" for role in week["session_roles"]) <= declared_counts["conditioning"]
        assert sum(role["category"] == "recovery" for role in week["session_roles"]) <= declared_counts["recovery"]


def test_high_fatigue_week_compression_logs_explicit_suppression_reason():
    brief = _build_product_brief(
        athlete_overrides={
            "fatigue": "high",
            "training_frequency": 4,
            "training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
            "hard_sparring_days": ["Tuesday", "Saturday"],
            "readiness_flags": ["high_fatigue"],
        },
        phase_briefs={
            "SPP": _phase_brief(
                "SPP",
                strength=1,
                conditioning=2,
                recovery=1,
                must_keep=["glycolytic", "alactic", "primary_strength"],
                drop_order=["aerobic"],
            )
        },
    )

    week = brief["weekly_role_map"]["weeks"][0]

    # Spar-first allocation: 2 hard sparring days consume 2 of 4 weekly slots.
    # High-fatigue compression reduces non-spar target from 2 → 1.
    # Only neural_plus_strength_day (highest SPP priority) survives.
    non_spar_roles = [r for r in week["session_roles"] if r["role_key"] != "hard_sparring_day"]
    spar_roles = [r for r in week["session_roles"] if r["role_key"] == "hard_sparring_day"]
    assert len(spar_roles) == 2
    assert [r["role_key"] for r in non_spar_roles] == ["neural_plus_strength_day"]

    suppressed_keys = {item["role_key"] for item in week["suppressed_roles"]}
    assert "fight_pace_repeatability_day" in suppressed_keys
    assert "repeatability_support_day" in suppressed_keys
    assert "recovery_reset_day" in suppressed_keys

    # Compression metadata recorded on week entry
    compression = week.get("intentional_compression", {})
    assert compression.get("active") is True
    assert "high_fatigue" in compression.get("reason_codes", [])
    assert "two_hard_spar_days" in compression.get("reason_codes", [])


def test_output_quality_taper_keeps_taper_identity():
    brief = _build_product_brief(
        athlete_overrides={"days_until_fight": 7, "readiness_flags": ["fight_week"]},
        phase_briefs={
            "TAPER": _phase_brief(
                "TAPER",
                strength=1,
                conditioning=2,
                recovery=2,
                must_keep=["alactic", "primary_strength"],
                drop_order=["glycolytic", "aerobic"],
                weeks=1,
                days=5,
            )
        },
    )

    role_keys = [role["role_key"] for role in brief["weekly_role_map"]["weeks"][0]["session_roles"]]

    assert "fight_pace_repeatability_day" not in role_keys
    assert "controlled_repeatability_day" not in role_keys
    assert any(role_key in role_keys for role_key in ["alactic_sharpness_day", "fight_week_freshness_day", "neural_primer_day"])


def test_output_quality_injured_athlete_keeps_rehab_representation():
    brief = _build_product_brief(
        athlete_overrides={"injuries": ["wrist soreness"], "readiness_flags": ["injury_management"]},
        phase_briefs={
            "SPP": _phase_brief(
                "SPP",
                strength=1,
                conditioning=2,
                recovery=1,
                must_keep=["rehab", "alactic"],
                drop_order=["glycolytic"],
                weeks=1,
                days=6,
                risk_flags=["respect injury guardrails"],
            )
        },
        include_rehab=True,
    )

    week = brief["week_by_week_progression"]["weeks"][0]
    recovery_role = next(role for role in brief["weekly_role_map"]["weeks"][0]["session_roles"] if role["category"] == "recovery")

    assert brief["candidate_pools"]["SPP"]["rehab_slots"]
    assert "rehab" in brief["phase_strategy"]["SPP"]["must_keep"]
    assert "rehab" in week["must_keep"]
    assert recovery_role["preferred_pool"] == "rehab_slots_or_recovery_only"


def test_output_quality_objective_and_role_sequence_stay_aligned():
    brief = _build_product_brief(
        athlete_overrides={"weaknesses": ["conditioning"]},
        phase_briefs={
            "GPP": _phase_brief(
                "GPP",
                strength=2,
                conditioning=2,
                recovery=1,
                must_keep=["aerobic", "primary_strength"],
                drop_order=["alactic", "glycolytic"],
                weeks=1,
                days=7,
                objective="build aerobic base and general force capacity",
                emphasize=["aerobic repeatability", "general force"],
            )
        },
    )

    gpp_week = brief["weekly_role_map"]["weeks"][0]
    conditioning_roles = [role["role_key"] for role in gpp_week["session_roles"] if role["category"] == "conditioning"]

    assert brief["limiter_profile"]["key"] == "aerobic_repeatability"
    assert brief["weekly_stress_map"]["GPP"]["conditioning_sequence"][0] == "aerobic"
    assert conditioning_roles[0] == "aerobic_base_day"
