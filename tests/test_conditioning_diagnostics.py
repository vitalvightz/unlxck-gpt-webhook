import asyncio
import json
from pathlib import Path

from fightcamp.conditioning import render_conditioning_block
from fightcamp.main import generate_plan
from fightcamp.stage2_payload import build_planning_brief, build_stage2_payload
from fightcamp.training_context import TrainingContext


def test_plan_missing_system_messaging():
    data_path = Path(__file__).resolve().parents[1] / "test_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    result = asyncio.run(generate_plan(data))
    plan_text = result["plan_text"]
    forbidden_phrases = [
        "No AEROBIC drills available",
        "No GLYCOLYTIC drills available",
        "No ATP",
        "No drills available",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in plan_text


def test_missing_system_block_formatting():
    output = render_conditioning_block(
        {},
        phase="GPP",
        phase_color="#000",
        missing_systems=["aerobic"],
        diagnostic_context={"time_to_fight_days": 10, "fatigue_level": "low", "injuries": []},
    )
    assert "AEROBIC (Status: Not prescribed)" in output
    assert "Reason:" in output
    assert "Coach option:" in output


def test_generate_plan_returns_stage2_payload():
    data_path = Path(__file__).resolve().parents[1] / "test_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    result = asyncio.run(generate_plan(data))

    payload = result.get("stage2_payload")
    assert payload is not None
    assert payload["schema_version"] == "stage2_payload.v1"
    assert "athlete_model" in payload
    assert "restrictions" in payload
    assert "phase_briefs" in payload
    assert "candidate_pools" in payload

    planning_brief = result.get("planning_brief")
    assert planning_brief is not None
    assert planning_brief["schema_version"] == "planning_brief.v1"
    assert "archetype_summary" in planning_brief
    assert "main_limiter" in planning_brief
    assert "global_priorities" in planning_brief
    assert "phase_strategy" in planning_brief
    assert "week_by_week_progression" in planning_brief
    assert planning_brief["week_by_week_progression"]["weeks"]

    handoff_text = result.get("stage2_handoff_text", "")
    assert "You are Stage 2 (planner/finalizer)." in handoff_text
    assert "PLANNING BRIEF" in handoff_text
    assert "SOURCE OF TRUTH" in handoff_text
    assert "ATHLETE PROFILE" in handoff_text
    assert "STAGE 1 DRAFT PLAN" in handoff_text

    active_phases = set(payload["phase_briefs"].keys())
    assert active_phases
    assert active_phases.issubset(set(payload["candidate_pools"].keys()))
    assert active_phases.issubset(set(planning_brief["phase_strategy"].keys()))



def test_stage2_payload_uses_slot_alternates_and_rehab_drills():
    training_context = TrainingContext(
        fatigue="low",
        training_frequency=4,
        days_available=4,
        training_days=["Mon", "Tue", "Thu", "Sat"],
        injuries=["shoulder strain"],
        style_technical=["boxing"],
        style_tactical=["counter_striker"],
        weaknesses=["pull"],
        equipment=["dumbbell", "bands"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["conditioning"],
        training_preference="balanced",
        mental_block=[],
        age=25,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 4, "SPP": 0, "TAPER": 0, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=35,
    )

    selected_strength = {
        "name": "Rear Foot Elevated Split Squat",
        "movement": "lunge",
        "tags": ["unilateral", "quad_dominant"],
        "method": "3x6 each side",
    }
    selected_conditioning = {
        "name": "Tempo Run",
        "tags": ["aerobic", "low_impact"],
        "timing": "20 min",
        "rest": "",
        "load": "Zone 2",
    }

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=6,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 4, "SPP": 0, "TAPER": 0, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={
            "GPP": {
                "exercises": [selected_strength],
                "why_log": [{"name": selected_strength["name"], "explanation": "1 weakness tag", "reasons": {}}],
                "candidate_reservoir": {
                    "lunge": [
                        {"exercise": selected_strength, "explanation": "1 weakness tag"},
                        {
                            "exercise": {
                                "name": "Step-Up",
                                "movement": "lunge",
                                "tags": ["unilateral", "knee_drive"],
                                "method": "3x8 each side",
                            },
                            "explanation": "balanced selection",
                        },
                        {
                            "exercise": {
                                "name": "Split Squat Iso Hold",
                                "movement": "lunge",
                                "tags": ["unilateral", "isometric"],
                                "method": "3x20s each side",
                            },
                            "explanation": "1 phase tag",
                        },
                    ]
                },
            },
            "SPP": None,
            "TAPER": None,
        },
        conditioning_blocks={
            "GPP": {
                "grouped_drills": {"aerobic": [selected_conditioning]},
                "why_log": [{"name": selected_conditioning["name"], "system": "aerobic", "explanation": "1 goal match", "reasons": {}}],
                "missing_systems": [],
                "candidate_reservoir": {
                    "aerobic": [
                        {"drill": selected_conditioning, "explanation": "1 goal match"},
                        {
                            "drill": {
                                "name": "Air Bike Flush",
                                "tags": ["aerobic", "low_impact"],
                                "timing": "15 min",
                                "rest": "",
                                "load": "easy",
                            },
                            "explanation": "balanced selection",
                        },
                    ]
                },
            }
        },
        rehab_blocks={
            "GPP": "- Shoulder (Strain):\n  - Band External Rotation - 2x15\n  - Scap Push-Up - 2x10",
            "SPP": "",
            "TAPER": "",
        },
    )

    gpp_pool = payload["candidate_pools"]["GPP"]
    strength_slot = gpp_pool["strength_slots"][0]
    conditioning_slot = gpp_pool["conditioning_slots"][0]
    rehab_slots = gpp_pool["rehab_slots"]

    assert strength_slot["alternates"]
    assert strength_slot["alternates"][0]["name"] == "Step-Up"
    assert conditioning_slot["alternates"]
    assert conditioning_slot["alternates"][0]["name"] == "Air Bike Flush"
    assert [slot["selected"]["name"] for slot in rehab_slots] == [
        "Band External Rotation",
        "Scap Push-Up",
    ]

def test_stage2_payload_exposes_mechanical_restriction_hints():
    training_context = TrainingContext(
        fatigue="low",
        training_frequency=4,
        days_available=4,
        training_days=["Mon", "Tue", "Thu", "Sat"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=[],
        equipment=["barbell", "track"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["power"],
        training_preference="balanced",
        mental_block=[],
        age=25,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 4, "SPP": 0, "TAPER": 0, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=35,
    )

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=6,
        short_notice=False,
        restrictions=[
            {
                "restriction": "heavy_overhead_pressing",
                "region": "shoulder",
                "strength": "avoid",
                "original_phrase": "avoid heavy overhead pressing",
            },
            {
                "restriction": "max_velocity",
                "region": None,
                "strength": "limit",
                "original_phrase": "limit max velocity sprinting",
            },
        ],
        phase_weeks={"GPP": 4, "SPP": 0, "TAPER": 0, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={
            "GPP": {
                "exercises": [
                    {
                        "name": "Push Press",
                        "movement": "push",
                        "tags": ["overhead", "press_heavy", "dynamic_overhead"],
                        "method": "4x3",
                    }
                ],
                "why_log": [{"name": "Push Press", "explanation": "balanced selection", "reasons": {}}],
                "candidate_reservoir": {"push": []},
            },
            "SPP": None,
            "TAPER": None,
        },
        conditioning_blocks={
            "GPP": {
                "grouped_drills": {
                    "alactic": [
                        {
                            "name": "Flying Sprint",
                            "tags": ["speed", "max_velocity", "mech_max_velocity"],
                            "timing": "6 sec",
                            "rest": "90 sec",
                            "load": "all-out",
                        }
                    ]
                },
                "why_log": [{"name": "Flying Sprint", "system": "alactic", "explanation": "balanced selection", "reasons": {}}],
                "missing_systems": [],
                "candidate_reservoir": {"alactic": []},
            }
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )

    strength_selected = payload["candidate_pools"]["GPP"]["strength_slots"][0]["selected"]
    conditioning_selected = payload["candidate_pools"]["GPP"]["conditioning_slots"][0]["selected"]
    restrictions = {entry["restriction"]: entry for entry in payload["restrictions"]}

    assert "heavy_overhead_pressing" in strength_selected["mechanical_risk_tags"]
    assert "max_velocity" in conditioning_selected["mechanical_risk_tags"]
    assert "high_impact_lower" in conditioning_selected["mechanical_risk_tags"]
    assert "push press" in restrictions["heavy_overhead_pressing"]["blocked_patterns"]
    assert "flying sprint" in restrictions["max_velocity"]["mechanical_equivalents"]

def test_stage2_payload_phase_guardrails_prioritize_survival_structure():
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=5,
        days_available=5,
        training_days=["Mon", "Tue", "Wed", "Fri", "Sat"],
        injuries=["shoulder strain"],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=[],
        equipment=["air_bike", "bodyweight"],
        weight_cut_risk=True,
        weight_cut_pct=5.5,
        fight_format="boxing",
        status="amateur",
        training_split={},
        key_goals=["conditioning"],
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
        short_notice=False,
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
                    "alactic": [{"name": "Short Sprint", "tags": ["alactic"], "timing": "6 sec", "rest": "90 sec", "load": "fast"}],
                    "glycolytic": [{"name": "Hard Shuttle", "tags": ["glycolytic"], "timing": "20 sec", "rest": "60 sec", "load": "hard"}],
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

    taper_brief = payload["phase_briefs"]["TAPER"]
    taper_guardrails = taper_brief["selection_guardrails"]
    taper_pool = payload["candidate_pools"]["TAPER"]

    assert taper_guardrails["conditioning_minimums"]["alactic"] == 1
    assert taper_guardrails["must_keep_rehab_if_present"] is True
    assert taper_guardrails["conditioning_drop_order_if_thin"][0] == "glycolytic"
    assert taper_pool["conditioning_slots"][0]["priority"] == "critical"
    assert taper_pool["conditioning_slots"][1]["priority"] == "low"
    assert taper_pool["rehab_slots"][0]["priority"] == "critical"

def test_build_planning_brief_elevates_stage2_payload_into_coaching_brief():
    athlete_model = {
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
    restrictions = [{"restriction": "heavy_overhead_pressing", "blocked_patterns": ["push press"]}]
    rewrite_guidance = {"selection_rules": ["Prefer selected items first."]}
    omission_ledger = {"SPP": {"conditioning": [{"reason": "missing_system", "details": "aerobic"}]}}

    brief = build_planning_brief(
        athlete_model=athlete_model,
        restrictions=restrictions,
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger=omission_ledger,
        rewrite_guidance=rewrite_guidance,
    )

    assert brief["schema_version"] == "planning_brief.v1"
    assert brief["archetype_summary"]["readiness_state"] == "managed"
    assert brief["main_limiter"] == "Primary limiter is pull."
    assert brief["main_risks"]
    assert brief["global_priorities"]["preserve"]
    assert brief["phase_strategy"]["SPP"]["must_keep"] == ["rehab", "glycolytic", "alactic"]
    assert brief["phase_strategy"]["SPP"]["slot_counts"]["conditioning"] == 2
    assert brief["week_by_week_progression"]["weeks"][0]["phase"] == "SPP"
    assert brief["week_by_week_progression"]["weeks"][0]["stage_key"] == "specific_density_to_peak"
