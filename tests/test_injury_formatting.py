import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_formatting import format_injury_summary
from fightcamp.main import generate_plan


def test_format_injury_summary_basics():
    assert (
        format_injury_summary(
            {
                "canonical_location": "ankle",
                "laterality": None,
                "injury_type": "stiffness",
                "severity": "mild",
            }
        )
        == "Ankle — Stiffness (Severity: Mild)"
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
