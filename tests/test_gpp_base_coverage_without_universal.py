"""GPP base-category coverage survives Universal GPP Strength retirement.

The retired Universal GPP Strength bank existed to backfill GPP base
categories after selection. These tests prove the point of the retirement:
with the main `exercise_bank.json` as the only strength source, the selector's
own `_promote_base_categories` path still fills every required GPP base role
that the athlete's equipment can support.

Equipment-safety guard: a category is only asserted present when at least one
GPP-eligible main-bank exercise can actually provide it for that equipment
profile. Where the equipment genuinely cannot support a role, the selector is
allowed to leave it unfilled.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp import strength
from fightcamp.strength_session_quality import (
    classify_strength_item,
    missing_base_categories,
)
from fightcamp.training_context import normalize_equipment_list

ROOT = Path(__file__).resolve().parents[1]

# Representative equipment profiles from bodyweight-only up to a fully stocked
# commercial gym. bodyweight is implicitly available everywhere a fighter can
# train, so richer profiles include it.
EQUIPMENT_PROFILES = {
    "bodyweight_only": ["bodyweight"],
    "dumbbells": ["dumbbells", "bodyweight"],
    "commercial_gym": [
        "barbell",
        "dumbbells",
        "rack",
        "bench",
        "cable_machine",
        "kettlebell",
        "medicine_ball",
        "bodyweight",
    ],
    "barbell_rack": ["barbell", "rack", "bench", "bodyweight"],
}

BASE_CATEGORIES = ["lower_body_loaded", "upper_body_push_pull", "unilateral"]


def _exercise_bank() -> list[dict]:
    return json.loads((ROOT / "data" / "exercise_bank.json").read_text(encoding="utf-8"))


def _equipment_eligible(bank: list[dict], equipment: list[str], phase: str = "GPP") -> list[dict]:
    access = set(normalize_equipment_list(equipment))
    eligible = []
    for exercise in bank:
        if phase not in exercise.get("phases", []):
            continue
        needed = set(normalize_equipment_list(exercise.get("equipment", [])))
        if needed.issubset(access):
            eligible.append(exercise)
    return eligible


def _providable_categories(exercises: list[dict]) -> set[str]:
    present: set[str] = set()
    for exercise in exercises:
        present.update(classify_strength_item(exercise)["base_categories"])
    return present


def _generate_gpp(equipment: list[str], *, explosive_priority: bool = False) -> list[dict]:
    key_goals = ["explosive power"] if explosive_priority else []
    weaknesses = ["explosive power"] if explosive_priority else []
    block = strength.generate_strength_block(
        flags={
            "phase": "GPP",
            "fatigue": "low",
            "fight_format": "mma",
            "sport": "mma",
            "key_goals": key_goals,
            "training_days": ["Mon", "Wed", "Fri"],
            "training_frequency": 3,
            "days_available": 3,
            "days_until_fight": 60,
            "equipment": equipment,
            "injuries": [],
            "prev_exercises": [],
            "recent_exercises": [],
            "restrictions": [],
            "ignore_restrictions": False,
            "random_seed": 11,
        },
        weaknesses=weaknesses,
        mindset_cue=None,
    )
    return block["exercises"]


@pytest.mark.parametrize("profile_name", sorted(EQUIPMENT_PROFILES))
def test_gpp_fills_equipment_supported_base_categories_without_universal(profile_name):
    equipment = EQUIPMENT_PROFILES[profile_name]
    bank = _exercise_bank()
    providable = _providable_categories(_equipment_eligible(bank, equipment))

    exercises = _generate_gpp(equipment)
    assert exercises, f"{profile_name}: GPP generation must yield strength exercises"

    present = _providable_categories(exercises)
    for category in BASE_CATEGORIES:
        if category not in providable:
            # Equipment genuinely cannot support this role — the selector is
            # allowed to leave it unfilled. (In practice the main bank covers
            # all three even for bodyweight, but this keeps the test honest.)
            continue
        assert category in present, (
            f"{profile_name}: base category {category!r} is providable from the main "
            f"bank for this equipment but was not filled after Universal retirement"
        )


def test_gpp_fills_lower_body_explosive_anchor_when_prioritized_without_universal():
    # The explosive-anchor base category is only *required* when the athlete
    # carries an explicit lower-body explosive/power priority.
    equipment = EQUIPMENT_PROFILES["commercial_gym"]
    bank = _exercise_bank()
    providable = _providable_categories(_equipment_eligible(bank, equipment))
    assert "lower_body_explosive_anchor" in providable, (
        "precondition: commercial gym must be able to provide an explosive anchor"
    )

    exercises = _generate_gpp(equipment, explosive_priority=True)
    missing = missing_base_categories(exercises, require_lower_body_explosive_anchor=True)
    assert "lower_body_explosive_anchor" not in missing, (
        "explosive-anchor role must still be filled from the main bank under an "
        "explicit lower-body explosive priority"
    )
