import asyncio
import json
from pathlib import Path

from fightcamp.conditioning import _glycolytic_fallback, format_drill_block, render_conditioning_block
from fightcamp.diagnostics import _late_fight_lever, _short_notice_lever, format_missing_system_block
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


def test_plan_text_has_no_mojibake_or_duplicate_time_short_prefix():
    data_path = Path(__file__).resolve().parents[1] / "test_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    result = asyncio.run(generate_plan(data))
    plan_text = result["plan_text"]

    assert "â€“" not in plan_text
    assert "**If Time Short:** If time short:" not in plan_text


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


def test_render_conditioning_block_uses_plain_markdown_and_targeted_name_cleanup():
    output = render_conditioning_block(
        {
            "glycolytic": [
                {
                    "name": "Trap Bar Death March",
                    "equipment": ["trap_bar"],
                    "timing": "30s work / 30s rest x 5",
                    "rest": "30s",
                    "load": "heavy",
                    "purpose": "Build fight-specific carrying power.",
                    "red_flags": "None",
                },
                {
                    "name": "Thai Clinch EMOM",
                    "equipment": ["medicine_ball"],
                    "timing": "8 x 20s",
                    "rest": "40s",
                    "load": "fast",
                    "purpose": "Boxing hand-fight density.",
                    "red_flags": "None",
                    "availability_contingency_reason": "only if medicine ball access replaces the trap bar session",
                },
            ]
        },
        phase="SPP",
        phase_color="#000",
        sport="boxing",
    )

    assert "<br>" not in output
    assert "Trap Bar Carry Intervals" in output
    assert "Thai Clinch EMOM" not in output
    assert "Hand-Fight Intervals" in output
    assert "**Fallback:" in output
    assert "Drill:" not in output
    assert "Conditioning Block" not in output


def test_format_drill_block_uses_plain_markdown_without_html_markup():
    output = format_drill_block(
        {
            "name": "Trap Bar Carry Intervals",
            "load": "heavy",
            "rest": "30s",
            "timing": "30s work / 30s rest x 5",
            "purpose": "Build repeatability.",
            "red_flags": "None",
            "equipment_note": "swap to sled if trap bar unavailable",
        }
    )

    assert output.startswith("- **Trap Bar Carry Intervals**")
    assert "<br>" not in output
    assert "Drill:" not in output


def test_render_conditioning_block_limits_fallbacks_per_session_and_simplifies_taper():
    output = render_conditioning_block(
        {
            "glycolytic": [
                {
                    "name": "Trap Bar Death March",
                    "timing": "30s work / 30s rest x 5",
                    "rest": "30s",
                    "load": "heavy",
                    "purpose": "Build repeatability.",
                    "red_flags": "None",
                },
                {
                    "name": "Barbell Smash & Dash",
                    "timing": "4 rounds",
                    "rest": "75s",
                    "load": "hard",
                    "purpose": "Fallback option.",
                    "red_flags": "None",
                },
            ],
            "alactic": [
                {
                    "name": "Ankle Snap Bounce",
                    "timing": "4 x 10s",
                    "rest": "30s",
                    "load": "fast",
                    "purpose": "Sharpness.",
                    "red_flags": "None",
                },
                {
                    "name": "Thai Clinch EMOM",
                    "timing": "6 x 15s",
                    "rest": "45s",
                    "load": "fast",
                    "purpose": "Extra fallback that should not render in taper.",
                    "red_flags": "None",
                },
            ],
        },
        phase="TAPER",
        phase_color="#000",
        sport="boxing",
    )

    assert output.count("**Fallback:") == 0
    assert "Conditioning Block" not in output
    assert "**System:" not in output
    assert "Ankling" in output
    assert "Thai Clinch EMOM" not in output


def test_render_conditioning_block_allows_only_one_fallback_across_multi_system_session():
    output = render_conditioning_block(
        {
            "glycolytic": [
                {
                    "name": "Trap Bar Death March",
                    "timing": "30s work / 30s rest x 5",
                    "rest": "30s",
                    "load": "heavy",
                    "purpose": "Primary glycolytic choice.",
                    "red_flags": "None",
                },
                {
                    "name": "Barbell Smash & Dash",
                    "timing": "4 rounds",
                    "rest": "75s",
                    "load": "hard",
                    "purpose": "Fallback glycolytic choice.",
                    "red_flags": "None",
                    "availability_contingency_reason": "use only if trap bar access is unavailable that day",
                },
            ],
            "alactic": [
                {
                    "name": "Ankle Snap Bounce",
                    "timing": "4 x 10s",
                    "rest": "30s",
                    "load": "fast",
                    "purpose": "Primary alactic choice.",
                    "red_flags": "None",
                },
                {
                    "name": "Thai Clinch EMOM",
                    "timing": "6 x 15s",
                    "rest": "45s",
                    "load": "fast",
                    "purpose": "This second fallback should stay hidden.",
                    "red_flags": "None",
                },
            ],
        },
        phase="SPP",
        phase_color="#000",
        sport="boxing",
        num_sessions=1,
    )

    assert output.count("**Fallback:") == 1


def test_render_conditioning_block_omits_fallback_when_equipment_already_resolves_choice():
    output = render_conditioning_block(
        {
            "glycolytic": [
                {
                    "name": "Trap Bar Death March",
                    "equipment": ["trap_bar"],
                    "timing": "30s work / 30s rest x 5",
                    "rest": "30s",
                    "load": "heavy",
                    "purpose": "Primary glycolytic choice.",
                    "red_flags": "None",
                },
                {
                    "name": "Barbell Smash & Dash",
                    "equipment": ["barbell"],
                    "timing": "4 rounds",
                    "rest": "75s",
                    "load": "hard",
                    "purpose": "Second drill should not auto-render as fallback.",
                    "red_flags": "None",
                },
            ],
        },
        phase="SPP",
        phase_color="#000",
        sport="boxing",
        num_sessions=1,
    )

    assert "**Fallback:" not in output
    assert "Barbell Clean Sprint Intervals" not in output


def test_conditioning_helper_fallbacks_are_equipment_valid():
    fallback = _glycolytic_fallback("boxing")

    assert fallback["required_equipment"] == []
    assert fallback["equipment"] == []
    assert fallback["generic_fallback"] is True


def test_generate_plan_returns_controlled_error_for_invalid_payload():
    result = asyncio.run(generate_plan({"data": {}}))

    assert result["status"] == "invalid_input"
    assert result["ok"] is False
    assert result["error"] == "payload missing required data.fields list"
    assert result["missing_fields"] == []
    assert result["pdf_url"] is None
    assert result["why_log"] == {}
    assert result["plan_text"] == ""
    assert result["planning_brief"] is None
    assert result["stage2_payload"] is None


def test_generate_plan_returns_structured_code_for_invalid_training_frequency_format():
    result = asyncio.run(
        generate_plan(
            {
                "data": {
                    "fields": [
                        {"label": "Full name", "value": "Test Athlete"},
                        {"label": "Fighting Style (Technical)", "value": "boxing"},
                        {"label": "When is your next fight?", "value": "2026-04-26"},
                        {"label": "Athlete Time Zone", "value": "UTC"},
                        {"label": "Training Availability", "value": "Mon, Wed"},
                        {"label": "Weekly Training Frequency", "value": "abc"},
                    ]
                }
            }
        )
    )

    assert result["status"] == "invalid_input"
    assert result["missing_fields"] == ["invalid_training_frequency_format"]


def test_generate_plan_returns_structured_code_for_missing_timezone_strategy():
    result = asyncio.run(
        generate_plan(
            {
                "data": {
                    "fields": [
                        {"label": "Full name", "value": "Test Athlete"},
                        {"label": "Fighting Style (Technical)", "value": "boxing"},
                        {"label": "When is your next fight?", "value": "2026-04-26"},
                        {"label": "Training Availability", "value": "Mon, Wed"},
                        {"label": "Weekly Training Frequency", "value": "4"},
                    ]
                }
            }
        )
    )

    assert result["status"] == "invalid_input"
    assert result["missing_fields"] == ["missing_timezone_strategy"]


def test_generate_plan_rejects_missing_generation_requirements():
    result = asyncio.run(
        generate_plan(
            {
                "data": {
                    "fields": [
                        {"label": "Full name", "value": "Test Athlete"},
                    ]
                }
            }
        )
    )

    assert result["status"] == "invalid_input"
    assert result["ok"] is False
    assert set(result["missing_fields"]) == {
        "missing_fighting_style_technical",
        "missing_next_fight_date",
        "missing_training_availability",
        "invalid_training_frequency",
    }
    assert result["pdf_url"] is None
    assert result["why_log"] == {}
    assert result["stage2_payload"] is None
    assert result["planning_brief"] is None


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
    assert "weekly_role_map" in planning_brief
    assert planning_brief["weekly_role_map"]["weeks"]

    handoff_text = result.get("stage2_handoff_text", "")
    assert "You are Stage 2 (planner/finalizer)." in handoff_text
    assert "PLANNING BRIEF" in handoff_text
    assert "AUTHORITY ORDER" in handoff_text
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
    assert strength_slot["session_index"] == 1
    assert strength_slot["quality_class"] == "anchor_loaded"
    assert strength_slot["anchor_capable"] is True
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


def test_short_notice_false_for_past_date():
    data = {
        "data": {
            "fields": [
                {"label": "Full name", "value": "Past Date Athlete"},
                {"label": "Age", "value": "25"},
                {"label": "Weight (kg)", "value": "70"},
                {"label": "Target Weight (kg)", "value": "68"},
                {"label": "Height (cm)", "value": "175"},
                {"label": "Fighting Style (Technical)", "value": ["boxing"]},
                {"label": "Fighting Style (Tactical)", "value": ["pressure fighter"]},
                {"label": "Stance", "value": "Orthodox"},
                {"label": "Professional Status", "value": "Active"},
                {"label": "Current Record", "value": "5-2-0"},
                {"label": "When is your next fight?", "value": "2000-01-01"},
                {"label": "Rounds x Minutes", "value": "3x3"},
                {"label": "Weekly Training Frequency", "value": "3"},
                {"label": "Fatigue Level", "value": "Low"},
                {"label": "Equipment Access", "value": ["Dumbbells", "Bands"]},
                {"label": "Training Availability", "value": ["Monday", "Wednesday", "Friday"]},
                {"label": "Any injuries or areas you need to work around?", "value": ""},
                {"label": "What are your key performance goals?", "value": "conditioning"},
                {"label": "Where do you feel weakest right now?", "value": "pull"},
                {"label": "Do you prefer certain training styles?", "value": "hybrid"},
                {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": ""},
                {"label": "Notes (anything else we should know)", "value": "Past fight date test"},
            ]
        }
    }

    result = asyncio.run(generate_plan(data))

    assert result["planning_brief"]["fight_demands"]["days_until_fight"] is None
    assert result["planning_brief"]["fight_demands"]["short_notice"] is False
    assert result["stage2_payload"]["athlete_model"]["days_until_fight"] is None


# ---------------------------------------------------------------------------
# Patch D: countdown-aware diagnostics / fallback late-fight leak tests
# ---------------------------------------------------------------------------


def test_short_notice_lever_alactic_not_countdown_aware():
    """Baseline: _short_notice_lever still returns the generic large-burst text for non-late-fight use."""
    lever = _short_notice_lever("alactic")
    assert "6–8" in lever or "8–10s" in lever


def test_late_fight_lever_alactic_caps_by_day():
    """_late_fight_lever returns tighter burst prescriptions for each countdown day."""
    d5 = _late_fight_lever("alactic", 5)
    assert "6" in d5
    assert "6–8" not in d5  # generic oversized prescription must not appear

    d4 = _late_fight_lever("alactic", 4)
    assert "5" in d4
    assert "6–8 × 8–10s" not in d4

    d3 = _late_fight_lever("alactic", 3)
    assert "4" in d3

    d2 = _late_fight_lever("alactic", 2)
    assert "2–4" in d2

    d1 = _late_fight_lever("alactic", 1)
    assert "2–3" in d1
    assert "conditioning structure" not in d1.lower() or "no conditioning structure" in d1.lower()

    d0 = _late_fight_lever("alactic", 0)
    assert "fight day" in d0.lower() or "walk-through" in d0.lower()


def test_late_fight_lever_glycolytic_suppressed():
    """Glycolytic conditioning must be suppressed for all late-fight days."""
    for day in range(6):
        lever = _late_fight_lever("glycolytic", day)
        assert "4–6 × 2:00" not in lever, f"Generic glycolytic prescription leaked at D-{day}"
        assert "freshness" in lever.lower() or "omitted" in lever.lower()


def test_late_fight_lever_aerobic_caps_by_day():
    """Aerobic lever stays within freshness-preserving limits for each countdown day."""
    d5 = _late_fight_lever("aerobic", 5)
    assert "20–30 min" not in d5  # generic short-notice dose must not appear
    assert "15–20 min" in d5

    d4 = _late_fight_lever("aerobic", 4)
    d3 = _late_fight_lever("aerobic", 3)
    for lever in (d4, d3):
        assert "20–30 min" not in lever
        assert "10–15 min" in lever

    d1 = _late_fight_lever("aerobic", 1)
    assert "omitted" in d1.lower() or "activation" in d1.lower()

    d0 = _late_fight_lever("aerobic", 0)
    assert "no aerobic" in d0.lower() or "fight day" in d0.lower()


def test_format_missing_system_block_uses_late_fight_lever_for_days_le_5():
    """format_missing_system_block picks the countdown-aware lever for D-5 to D-0."""
    for day in range(6):
        output = format_missing_system_block(
            "alactic",
            phase="TAPER",
            sport="mma",
            context={"days_until_fight": day},
        )
        # Must not contain the old generic oversized burst prescription
        assert "6–8 × 8–10s full-rest bursts" not in output, (
            f"Generic oversized alactic prescription leaked at D-{day}"
        )
        assert "Coach option:" in output


def test_format_missing_system_block_generic_lever_outside_late_fight():
    """format_missing_system_block keeps generic short-notice text for D-6 to D-14."""
    for day in (6, 7, 10, 14):
        output = format_missing_system_block(
            "alactic",
            phase="TAPER",
            sport="mma",
            context={"days_until_fight": day},
        )
        # Generic text is still appropriate for non-late-fight short-notice windows
        assert "6–8 × 8–10s full-rest bursts" in output, (
            f"Expected generic short-notice alactic text at D-{day}, got: {output}"
        )


def test_render_conditioning_block_missing_alactic_late_fight_no_large_burst():
    """render_conditioning_block must not surface oversized burst cues when alactic is missing in late-fight."""
    output = render_conditioning_block(
        {},
        phase="TAPER",
        phase_color="#000",
        missing_systems=["alactic"],
        diagnostic_context={"days_until_fight": 3, "fatigue_level": "low", "injuries": []},
    )
    assert "6–8 × 8–10s full-rest bursts" not in output
    assert "ALACTIC" in output
    assert "Coach option:" in output
