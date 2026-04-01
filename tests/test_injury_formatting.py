import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_formatting import (
    format_injury_summary,
    parse_injury_entry,
    parse_injuries_and_restrictions,
)
from fightcamp.injury_synonyms import split_injury_text
from fightcamp.main import generate_plan
from fightcamp.rehab_protocols import format_injury_guardrails


def test_format_injury_summary_basics():
    assert (
        format_injury_summary(
            {
                "canonical_location": "ankle",
                "laterality": None,
                "injury_type": "stiffness",
                "severity": "low",
            }
        )
        == "Ankle — Stiffness (Severity: Low)"
    )
    assert (
        format_injury_summary(
            {
                "canonical_location": "hamstring",
                "laterality": "left",
                "injury_type": "strain",
                "severity": "moderate",
            }
        )
        == "Left Hamstring — Strain (Severity: Moderate)"
    )


def test_format_injury_summary_prefers_display_location():
    assert (
        format_injury_summary(
            {
                "canonical_location": "hip",
                "display_location": "hip flexor",
                "laterality": None,
                "injury_type": "unspecified",
                "severity": "moderate",
            }
        )
        == "Hip Flexor â€” Unspecified (Severity: Moderate)"
    )


def test_plan_output_has_no_region_wrappers():
    data_path = Path(__file__).resolve().parents[1] / "test_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data["random_seed"] = 7
    result = asyncio.run(generate_plan(data))
    plan_text = result.get("plan_text", "")

    forbidden_substrings = [
        "Lower leg/foot (",
        "Upper body (",
        "Hip/Glutes (",
        " (Ankle)",
    ]
    assert plan_text
    assert not any(token in plan_text for token in forbidden_substrings)
    assert not re.search(r"\(.*\)\s—", plan_text)


def test_injury_parsing_handles_multiple_locations_with_punctuation():
    sample = (
        "Right shin splints (mild) + left shoulder impingement (mild). "
        "Avoid high-volume impact running and heavy overhead pressing."
    )
    phrases = split_injury_text(sample)
    entries = [parse_injury_entry(phrase) for phrase in phrases]
    entries = [entry for entry in entries if entry]
    locations = {entry.get("canonical_location") for entry in entries}
    injury_types = {entry.get("injury_type") for entry in entries}
    assert "shin" in locations
    assert "shoulder" in locations
    assert "contusion" not in injury_types


def test_torn_hamstring_severity_is_severe():
    guardrails = format_injury_guardrails("GPP", "torn hamstring", [])
    assert "Severity: Severe" in guardrails


def test_mild_impingement_respects_phrase_severity():
    guardrails = format_injury_guardrails("GPP", "mild right shoulder impingement", [])
    assert "Right Shoulder — Impingement (Severity: Mild)" in guardrails


def test_guardrails_render_restrictions_without_injury_summary():
    injuries = "avoid deep knee flexion under load, heavy overhead pressing"
    _, restrictions = parse_injuries_and_restrictions(injuries)
    guardrails = format_injury_guardrails("GPP", injuries, restrictions)
    assert "**Restrictions (Stage-2 daily planner only)**" in guardrails
    assert "Injury Summary" not in guardrails
    assert "- avoid deep knee flexion under load" in guardrails
    assert "- heavy overhead pressing" in guardrails


def test_guardrails_preserve_guided_display_location_without_note_leak():
    guardrails = format_injury_guardrails(
        "SPP",
        "hip flexor (moderate, improving). Avoid: deep hip flexion. Notes: pain when driving knee up past pelvis",
        [
            {
                "restriction": "generic_constraint",
                "region": "hip",
                "strength": "avoid",
                "side": None,
                "original_phrase": "avoid deep hip flexion",
            }
        ],
        parsed_entries=[
            {
                "injury_type": "unspecified",
                "canonical_location": "hip",
                "display_location": "hip flexor",
                "laterality": None,
                "severity": "moderate",
                "original_phrase": "hip flexor",
            }
        ],
    )

    assert "Hip Flexor â€” Unspecified (Severity: Moderate)" in guardrails
    assert "Knee â€”" not in guardrails
    assert "Unspecified Location â€” Pain" not in guardrails
    assert "- avoid deep hip flexion" in guardrails
