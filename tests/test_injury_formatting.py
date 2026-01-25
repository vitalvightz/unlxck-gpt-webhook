import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_formatting import format_injury_summary, parse_injury_entry
from fightcamp.injury_synonyms import split_injury_text
from fightcamp.main import generate_plan


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


def test_plan_output_has_no_region_wrappers():
    data_path = Path(__file__).resolve().parents[1] / "test_data.json"
    data = json.loads(data_path.read_text())
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
