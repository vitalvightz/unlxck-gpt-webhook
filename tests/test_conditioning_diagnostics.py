import asyncio
import json
from pathlib import Path

from fightcamp.conditioning import render_conditioning_block
from fightcamp.main import generate_plan


def test_plan_missing_system_messaging():
    data_path = Path(__file__).resolve().parents[1] / "test_data.json"
    data = json.loads(data_path.read_text())
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
    data = json.loads(data_path.read_text())
    result = asyncio.run(generate_plan(data))

    payload = result.get("stage2_payload")
    assert payload is not None
    assert payload["schema_version"] == "stage2_payload.v1"
    assert "athlete_model" in payload
    assert "restrictions" in payload
    assert "phase_briefs" in payload
    assert "candidate_pools" in payload

    active_phases = set(payload["phase_briefs"].keys())
    assert active_phases
    assert active_phases.issubset(set(payload["candidate_pools"].keys()))
