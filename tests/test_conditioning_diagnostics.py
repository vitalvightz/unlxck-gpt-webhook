import asyncio
import json
from pathlib import Path

from fightcamp.conditioning import render_conditioning_block
from fightcamp.main import generate_plan
from fightcamp.stage2_payload import build_stage2_payload
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

    handoff_text = result.get("stage2_handoff_text", "")
    assert "You are Stage 2 (finalizer)." in handoff_text
    assert "ATHLETE PROFILE" in handoff_text
    assert "STAGE 1 DRAFT PLAN" in handoff_text

    active_phases = set(payload["phase_briefs"].keys())
    assert active_phases
    assert active_phases.issubset(set(payload["candidate_pools"].keys()))



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