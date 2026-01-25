import asyncio
import re

from fightcamp.main import (
    MUAY_THAI_REPLACEMENTS,
    MUAY_THAI_TERM_REPLACEMENTS,
    generate_plan,
)


def _build_payload(
    *,
    full_name="Stage One Tester",
    technical_styles=None,
    tactical_styles=None,
    injuries="",
    random_seed=42,
):
    technical_styles = technical_styles or ["Boxing"]
    tactical_styles = tactical_styles or ["Pressure Fighter"]
    fields = [
        {"label": "Full name", "value": full_name},
        {"label": "Age", "value": "28"},
        {"label": "Weight (kg)", "value": "70"},
        {"label": "Target Weight (kg)", "value": "68"},
        {"label": "Height (cm)", "value": "175"},
        {"label": "Fighting Style (Technical)", "value": technical_styles},
        {"label": "Fighting Style (Tactical)", "value": tactical_styles},
        {"label": "Stance", "value": "Orthodox"},
        {"label": "Professional Status", "value": "Amateur"},
        {"label": "Current Record", "value": "5-1-0"},
        {"label": "When is your next fight?", "value": "2030-01-01"},
        {"label": "Rounds x Minutes", "value": "3x3"},
        {"label": "Weekly Training Frequency", "value": "4"},
        {"label": "Fatigue Level", "value": "Low"},
        {"label": "Training Phase", "value": "Early-Camp"},
        {"label": "Equipment Access", "value": ["Dumbbells", "Bands"]},
        {
            "label": "Training Availability",
            "value": ["Monday", "Wednesday", "Friday", "Saturday"],
        },
        {
            "label": "Any injuries or areas you need to work around?",
            "value": injuries or "None",
        },
        {
            "label": "What are your key performance goals?",
            "value": ["Conditioning / Endurance", "Skill Refinement"],
        },
        {"label": "Where do you feel weakest right now?", "value": ["core stability"]},
        {"label": "Do you prefer certain training styles?", "value": "interval-based work"},
        {
            "label": "Do you struggle with any mental blockers or mindset challenges?",
            "value": "confidence under pressure",
        },
        {
            "label": "Are there any parts of your previous plan you hated or loved?",
            "value": "Loved pad rounds, hated long steady-state runs",
        },
    ]
    return {"data": {"fields": fields}, "random_seed": random_seed}


def _generate_plan_text(payload: dict) -> str:
    result = asyncio.run(generate_plan(payload))
    return result["plan_text"]


def _assert_no_merged_headings(text: str) -> None:
    labels = [
        "Mindset Focus",
        "Strength & Power",
        "Conditioning",
        "Injury Guardrails",
        "Nutrition",
        "Recovery",
        "Rehab Protocols",
        "Mindset Overview",
        "Coach Notes",
        "Selection Rationale",
    ]
    for label in labels:
        for other in labels:
            if label == other:
                continue
            assert f"{label}{other}" not in text


def test_stage1_guardrails_time_labels_and_headings():
    payload = _build_payload()
    plan_text = _generate_plan_text(payload)

    assert "**If Time Short:**" in plan_text
    assert "**If Time Short:** **If Time Short:**" not in plan_text
    assert not re.search(r"(?i)(?<!\*\*)if time short:", plan_text)
    assert not re.search(r"(?i)(?<!\*\*)if fatigue high:", plan_text)
    assert "No rehab drills available" not in plan_text
    assert "No drills available" not in plan_text
    _assert_no_merged_headings(plan_text)


def test_stage1_guardrails_no_wrong_sport_terms():
    payload = _build_payload(
        full_name="Muay Thai Tester",
        technical_styles=["Muay Thai"],
        tactical_styles=["Distance Striker"],
        injuries="left ankle sprain",
    )
    plan_text = _generate_plan_text(payload)

    for term in [*MUAY_THAI_REPLACEMENTS.keys(), *MUAY_THAI_TERM_REPLACEMENTS.keys()]:
        assert not re.search(re.escape(term), plan_text, re.IGNORECASE)
    _assert_no_merged_headings(plan_text)
