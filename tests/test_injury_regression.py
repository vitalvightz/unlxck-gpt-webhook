from __future__ import annotations

from fightcamp.conditioning import generate_conditioning_block
from fightcamp.injury_guard import injury_decision
from fightcamp.strength import generate_strength_block


def _base_flags(injuries: list[str]) -> dict:
    return {
        "phase": "GPP",
        "fatigue": "low",
        "injuries": injuries,
        "training_frequency": 3,
        "days_available": 3,
        "training_days": ["Mon", "Wed", "Fri"],
        "style_tactical": [],
        "style_technical": [],
        "key_goals": [],
        "weaknesses": [],
        "equipment": [],
        "fight_format": "mma",
    }


def _count_exclusions(items: list[dict], injuries: list[str]) -> int:
    return sum(
        1
        for item in items
        if injury_decision(item, injuries, "GPP", "low").action == "exclude"
    )


def test_injury_filters_return_selections_and_limit_exclusions():
    cases = {
        "no_injury": [],
        "shoulder": ["shoulder pain"],
        "knee": ["knee pain"],
        "back": ["lower back strain"],
        "ankle": ["ankle sprain"],
        "multi": ["shoulder pain", "knee pain", "lower back strain", "ankle sprain"],
    }
    exclusion_cap = 2

    for injuries in cases.values():
        flags = _base_flags(injuries)

        strength_block = generate_strength_block(flags=flags, weaknesses=[], mindset_cue=None)
        exercises = strength_block.get("exercises", [])
        assert exercises
        assert _count_exclusions(exercises, injuries) < exclusion_cap

        _, _, _, grouped_drills, _ = generate_conditioning_block(flags)
        selected_drills = [d for drills in grouped_drills.values() for d in drills]
        assert selected_drills
        assert _count_exclusions(selected_drills, injuries) < exclusion_cap
