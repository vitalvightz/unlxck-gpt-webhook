import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from fightcamp import input_parsing, main as main_module, plan_pipeline

FIXED_NOW = datetime(2026, 3, 13, 12, 0)
SNAPSHOT_DIR = Path(__file__).resolve().parent / "golden_snapshots"


def _payload(*, seed: int, fields: list[dict]) -> dict:
    return {
        "random_seed": seed,
        "data": {
            "fields": fields,
        },
    }


GOLDEN_CASES = {
    "boxing_amateur_foundation": _payload(
        seed=11,
        fields=[
            {"label": "Full name", "value": "Maya Carter"},
            {"label": "Age", "value": "24"},
            {"label": "Weight (kg)", "value": "62"},
            {"label": "Target Weight (kg)", "value": "60"},
            {"label": "Height (cm)", "value": "168"},
            {"label": "Fighting Style (Technical)", "value": ["boxing"]},
            {"label": "Fighting Style (Tactical)", "value": ["counter striker"]},
            {"label": "Stance", "value": "Orthodox"},
            {"label": "Professional Status", "value": "amateur"},
            {"label": "Current Record", "value": "6-1"},
            {"label": "When is your next fight?", "value": "2026-04-24"},
            {"label": "Rounds x Minutes", "value": "3x3"},
            {"label": "Weekly Training Frequency", "value": "4"},
            {"label": "Fatigue Level", "value": "Low"},
            {"label": "Equipment Access", "value": "Dumbbells, Bands, Medicine Ball"},
            {"label": "Training Availability", "value": "Monday, Tuesday, Thursday, Saturday"},
            {"label": "Any injuries or areas you need to work around?", "value": ""},
            {"label": "What are your key performance goals?", "value": "skill refinement, power"},
            {"label": "Where do you feel weakest right now?", "value": "pull, gas tank"},
            {"label": "Do you prefer certain training styles?", "value": "technical"},
            {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": "I rush exchanges late in rounds"},
            {"label": "Are there any parts of your previous plan you hated or loved?", "value": "Prefers concise sessions"},
        ],
    ),
    "mma_short_notice_shoulder_management": _payload(
        seed=17,
        fields=[
            {"label": "Full name", "value": "Isaac Moreno"},
            {"label": "Age", "value": "29"},
            {"label": "Weight (kg)", "value": "79"},
            {"label": "Target Weight (kg)", "value": "74"},
            {"label": "Height (cm)", "value": "180"},
            {"label": "Fighting Style (Technical)", "value": ["mma"]},
            {"label": "Fighting Style (Tactical)", "value": ["pressure fighter"]},
            {"label": "Stance", "value": "Switch"},
            {"label": "Professional Status", "value": "professional"},
            {"label": "Current Record", "value": "14-4"},
            {"label": "When is your next fight?", "value": "2026-03-23"},
            {"label": "Rounds x Minutes", "value": "3x5"},
            {"label": "Weekly Training Frequency", "value": "5"},
            {"label": "Fatigue Level", "value": "High"},
            {"label": "Equipment Access", "value": "Barbell, Dumbbells, Air Bike, Bands, Heavy Bag"},
            {"label": "Training Availability", "value": "Monday, Tuesday, Wednesday, Friday, Saturday"},
            {"label": "Any injuries or areas you need to work around?", "value": "mild right shoulder impingement and avoid heavy overhead pressing"},
            {"label": "What are your key performance goals?", "value": "conditioning, power"},
            {"label": "Where do you feel weakest right now?", "value": "pull, aerobic base"},
            {"label": "Do you prefer certain training styles?", "value": "aggressive"},
            {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": "I worry about my gas tank in hard grappling rounds"},
            {"label": "Are there any parts of your previous plan you hated or loved?", "value": "Needs a hard cap on soreness"},
        ],
    ),
    "muay_thai_injury_management": _payload(
        seed=23,
        fields=[
            {"label": "Full name", "value": "Lena Phan"},
            {"label": "Age", "value": "27"},
            {"label": "Weight (kg)", "value": "58"},
            {"label": "Target Weight (kg)", "value": "56"},
            {"label": "Height (cm)", "value": "165"},
            {"label": "Fighting Style (Technical)", "value": ["muay thai"]},
            {"label": "Fighting Style (Tactical)", "value": ["clinch fighter"]},
            {"label": "Stance", "value": "Orthodox"},
            {"label": "Professional Status", "value": "amateur"},
            {"label": "Current Record", "value": "9-2"},
            {"label": "When is your next fight?", "value": "2026-05-08"},
            {"label": "Rounds x Minutes", "value": "5x2"},
            {"label": "Weekly Training Frequency", "value": "4"},
            {"label": "Fatigue Level", "value": "Moderate"},
            {"label": "Equipment Access", "value": "Dumbbells, Bands, Thai Pads, Heavy Bag, Medicine Ball"},
            {"label": "Training Availability", "value": "Monday, Wednesday, Friday, Sunday"},
            {"label": "Any injuries or areas you need to work around?", "value": "left hamstring tightness"},
            {"label": "What are your key performance goals?", "value": "conditioning, skill refinement"},
            {"label": "Where do you feel weakest right now?", "value": "aerobic base, footwork"},
            {"label": "Do you prefer certain training styles?", "value": "balanced"},
            {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": "My confidence dips after getting hit clean"},
            {"label": "Are there any parts of your previous plan you hated or loved?", "value": "Avoid too much impact running"},
        ],
    ),
}


def _normalize_snapshot(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines) + "\n"


def _snapshot_text(result: dict) -> str:
    planning_brief = result["planning_brief"]
    brief_summary = {
        "main_limiter": planning_brief["main_limiter"],
        "fight_demands": planning_brief["fight_demands"],
        "phase_strategy": planning_brief["phase_strategy"],
    }
    sections = [
        "# Plan Text",
        result["plan_text"].strip(),
        "",
        "# Coach Notes",
        result["coach_notes"].strip(),
        "",
        "# Planning Brief Summary",
        json.dumps(brief_summary, indent=2, sort_keys=True),
    ]
    return _normalize_snapshot("\n".join(sections))


@pytest.mark.parametrize("case_name", sorted(GOLDEN_CASES))
def test_golden_end_to_end_plan_snapshots(case_name: str, monkeypatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)
    monkeypatch.setattr(plan_pipeline, "html_to_pdf", lambda html, output_path: None)

    result = asyncio.run(main_module.generate_plan(GOLDEN_CASES[case_name]))
    assert result["stage2_payload"] is not None
    assert result["planning_brief"] is not None

    actual = _snapshot_text(result)
    snapshot_path = SNAPSHOT_DIR / f"{case_name}.md"

    if os.getenv("REGENERATE_GOLDENS") == "1":
        snapshot_path.write_text(actual, encoding="utf-8")

    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected