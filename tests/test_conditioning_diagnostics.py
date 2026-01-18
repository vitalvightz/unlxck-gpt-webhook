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
    assert "Stage-2 lever:" in output
